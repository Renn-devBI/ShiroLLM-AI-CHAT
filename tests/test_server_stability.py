# -*- coding: utf-8 -*-
"""
Tests for Server Stability, Thread-Safe LLM Serialization, SSE Prefill Heartbeats,
CPU/GPU Safeguards, Health Endpoint, and Colab Auto-Healing Watchdog.
"""

import os
import sys
import json
import time
import types
import threading
import unittest
from unittest.mock import patch, MagicMock
from flask import Flask

from shiro.server_state import state
from shiro.pipeline import inference as inf_mod
from shiro.routes.chat import chat_bp
from shiro.routes.admin import admin_bp
from shiro.models import (
    get_optimal_model_tokens,
    get_optimal_n_threads,
    build_qwen38_500k_llama_kwargs,
    instantiate_llama_model,
    QWEN38_27B_EXTENDED_CTX,
    QWEN38_27B_CPU_SAFE_CTX,
)
from shiro.colab_watchdog import _next_stepdown_ctx, run_shiro_supervisor


class TestServerStability(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(chat_bp)
        self.app.register_blueprint(admin_bp)
        self.client = self.app.test_client()
        self._orig_llm = state.llm
        self._orig_vis = state.vision_chat_handler

    def tearDown(self):
        state.llm = self._orig_llm
        state.vision_chat_handler = self._orig_vis
        # Pastikan lock tidak pernah tertinggal dalam kondisi terkunci
        self.assertFalse(state.is_llm_busy(), "state.llm_lock leaked after test!")

    def test_concurrent_llm_streams_are_strictly_serialized(self):
        """Dua request chat paralel TIDAK BOLEH masuk ke create_chat_completion bersamaan (mencegah GGML_ASSERT / SIGABRT)."""
        active_calls = 0
        max_concurrent = 0
        counter_lock = threading.Lock()
        overlap_detected = False

        class FakeSlowLLM:
            model_path = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"

            def n_ctx(self):
                return 32768

            def create_chat_completion(self, messages, stream=False, **kwargs):
                nonlocal active_calls, max_concurrent, overlap_detected
                with counter_lock:
                    active_calls += 1
                    if active_calls > max_concurrent:
                        max_concurrent = active_calls
                    if active_calls > 1:
                        overlap_detected = True

                def _gen():
                    nonlocal active_calls
                    try:
                        time.sleep(0.15)
                        yield {"choices": [{"delta": {"content": "Halo "}}]}
                        time.sleep(0.05)
                        yield {"choices": [{"delta": {"content": "Kakak!"}}]}
                    finally:
                        with counter_lock:
                            active_calls -= 1

                if stream:
                    return _gen()
                try:
                    time.sleep(0.1)
                    return {"choices": [{"message": {"content": "Halo Kakak!"}, "finish_reason": "stop"}]}
                finally:
                    with counter_lock:
                        active_calls -= 1

        state.llm = FakeSlowLLM()
        results = []
        errors = []

        def _worker(prompt):
            try:
                events = list(inf_mod.stream_shiro_reply(prompt))
                results.append(events)
            except Exception as exc:
                errors.append(exc)

        with patch.object(inf_mod, "SSE_HEARTBEAT_INTERVAL", 0.05):
            t1 = threading.Thread(target=_worker, args=("pesan pertama",))
            t2 = threading.Thread(target=_worker, args=("pesan kedua",))
            t1.start()
            time.sleep(0.03)  # Pastikan t1 masuk dulu
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertFalse(overlap_detected, "Concurrent llama.cpp invocation detected!")
        self.assertEqual(max_concurrent, 1)
        # Request kedua harus menerima status menunggu giliran saat request pertama masih berjalan
        all_statuses = [
            ev.get("status", "")
            for ev_list in results
            for ev in ev_list
            if ev.get("type") == "status"
        ]
        self.assertTrue(
            any("menyelesaikan proses sebelumnya" in s for s in all_statuses),
            f"Expected queue wait status message, got: {all_statuses}",
        )

    def test_sse_emits_heartbeat_pings_during_slow_prefill(self):
        """Selama prompt evaluation (prefill) lambat sebelum token pertama keluar, ping SSE wajib dikirim berkala."""
        class SlowPrefillLLM:
            model_path = "model/Qwen3-4B-Q4_K_M.gguf"

            def n_ctx(self):
                return 8192

            def create_chat_completion(self, messages, stream=False, **kwargs):
                # Simulasikan prefill lambat sebelum yield token pertama
                time.sleep(0.22)

                def _gen():
                    yield {"choices": [{"delta": {"content": "Selesai prefill!"}}]}

                return _gen()

        state.llm = SlowPrefillLLM()
        with patch.object(inf_mod, "SSE_HEARTBEAT_INTERVAL", 0.05):
            events = list(inf_mod.stream_shiro_reply("Halo Shiro"))

        ping_count = sum(1 for e in events if e.get("type") == "ping")
        done_events = [e for e in events if e.get("type") == "done"]
        self.assertGreaterEqual(ping_count, 3, f"Expected multiple prefill pings, got {ping_count}")
        self.assertEqual(len(done_events), 1)
        self.assertIn("Selesai prefill!", done_events[0].get("reply", ""))

    def test_client_disconnect_releases_llm_lock_cleanly(self):
        """Saat klien memutus koneksi (GeneratorExit / Stop), worker berhenti dan state.llm_lock dilepas tanpa leak."""
        class LongStreamLLM:
            model_path = "model/Qwen3-4B-Q4_K_M.gguf"

            def n_ctx(self):
                return 8192

            def create_chat_completion(self, messages, stream=False, **kwargs):
                def _gen():
                    for i in range(100):
                        time.sleep(0.02)
                        yield {"choices": [{"delta": {"content": f"tok{i} "}}]}

                return _gen()

        state.llm = LongStreamLLM()
        with patch.object(inf_mod, "SSE_HEARTBEAT_INTERVAL", 0.05):
            gen = inf_mod.stream_shiro_reply("buatkan cerita panjang")
            # Ambil beberapa event lalu tutup paksa (simulasi client abort)
            for _ in range(4):
                next(gen)
            gen.close()

        # Tunggu sebentar agar worker thread menyelesaikan cleanup & melepas lock
        deadline = time.time() + 2.0
        while state.is_llm_busy() and time.time() < deadline:
            time.sleep(0.02)
        self.assertFalse(state.is_llm_busy(), "state.llm_lock was not released after GeneratorExit!")

    def test_qwen38_cpu_mode_uses_safe_context_and_no_cpu_flash_attn(self):
        """Di mode CPU tanpa GPU, Qwen3.8-27B diamankan ke 32K tanpa flash_attn CPU agar ggml-cpu tidak crash."""
        captured = []

        def fake_llama(**kwargs):
            captured.append(kwargs)
            m = MagicMock()
            m.n_ctx = lambda: kwargs["n_ctx"]
            return m

        fake_mod = types.ModuleType("llama_cpp")
        fake_mod.Llama = fake_llama
        fake_mod.LLAMA_ROPE_SCALING_TYPE_YARN = 2
        fake_mod.GGML_TYPE_Q8_0 = 8
        fake_mod.GGML_TYPE_Q4_0 = 2

        with patch.dict(sys.modules, {"llama_cpp": fake_mod}), \
             patch.dict(os.environ, {}, clear=False), \
             patch("shiro.models.init_vision_handler", return_value=None), \
             patch("shiro.models.find_active_lora_path", return_value=None), \
             patch("shiro.models.get_gpu_layers", return_value=0):
            os.environ.pop("SHIRO_QWEN38_27B_CONTEXT_SIZE", None)
            n_ctx, _ = get_optimal_model_tokens("model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf")
            self.assertEqual(n_ctx, QWEN38_27B_CPU_SAFE_CTX)

            instantiate_llama_model("model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf")
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0]["n_ctx"], QWEN38_27B_CPU_SAFE_CTX)
            self.assertNotIn("flash_attn", captured[0])
            self.assertNotIn("type_k", captured[0])
            self.assertGreaterEqual(captured[0]["n_threads"], 4)

    def test_qwen38_gpu_mode_preserves_500k_context(self):
        """Di mode GPU aktif, Qwen3.8-27B-Uncensored tetap memakai Extended Context 500K via YaRN."""
        with patch("shiro.models.get_gpu_layers", return_value=-1):
            os.environ.pop("SHIRO_QWEN38_27B_CONTEXT_SIZE", None)
            n_ctx, max_out = get_optimal_model_tokens("model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf")
            self.assertEqual(n_ctx, QWEN38_27B_EXTENDED_CTX)
            self.assertEqual(max_out, 16384)

    def test_optimal_n_threads(self):
        self.assertGreaterEqual(get_optimal_n_threads(0), 4)
        self.assertGreaterEqual(get_optimal_n_threads(-1), 4)

    def test_health_endpoint(self):
        """Endpoint /api/health harus merespons 200 dengan status model & busy flag."""
        dummy = MagicMock()
        dummy.model_path = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"
        dummy.n_ctx = lambda: 500000
        state.llm = dummy

        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["model_loaded"])
        self.assertFalse(data["busy"])
        self.assertEqual(data["active_context_window"], 500000)

    def test_watchdog_context_stepdown_and_auto_restart(self):
        """Watchdog Colab harus otomatis restart server saat crash dan menurunkan context saat SIGABRT/OOM berulang."""
        self.assertEqual(_next_stepdown_ctx(None), 262144)
        self.assertEqual(_next_stepdown_ctx(262144), 131072)
        self.assertEqual(_next_stepdown_ctx(131072), 65536)
        self.assertEqual(_next_stepdown_ctx(65536), 32768)
        self.assertEqual(_next_stepdown_ctx(32768), 32768)

        # Simulasi server crash 1x (SIGABRT -6), lalu watchdog restart dan user tekan KeyboardInterrupt
        crashed_proc = MagicMock()
        crashed_proc.poll.return_value = -6
        crashed_proc.returncode = -6

        restarted_proc = MagicMock()
        restarted_proc.poll.side_effect = [None, KeyboardInterrupt(), None]

        with patch("shiro.colab_watchdog.spawn_web_server", return_value=restarted_proc) as mock_spawn, \
             patch("shiro.colab_watchdog.wait_for_server_ready", return_value=True), \
             patch("shiro.colab_watchdog.backup_memory_to_drive", return_value=True), \
             patch("shiro.colab_watchdog.time.sleep", return_value=None):
            run_shiro_supervisor(
                server_proc=crashed_proc,
                log_path="shiro_server.log",
                public_url="https://example.trycloudflare.com",
                tunnel_proc=None,
                tunnel_mode="cloudflare",
                poll_interval=0.01,
            )
            self.assertEqual(mock_spawn.call_count, 1)

    def test_colab_notebook_valid_json_and_python_syntax(self):
        """Pastikan Shiro_LLMA_Colab.ipynb adalah JSON valid dan seluruh cell Python valid."""
        nb_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Shiro_LLMA_Colab.ipynb")
        with open(nb_path, "r", encoding="utf-8") as f:
            nb = json.load(f)
        self.assertIn("cells", nb)
        found_watchdog_ref = 0
        for cell in nb["cells"]:
            if cell.get("cell_type") == "code":
                src = "".join(cell.get("source", []))
                if "run_shiro_supervisor" in src:
                    found_watchdog_ref += 1
                # Validasi sintaks Python (abaikan magic/shell lines IPython seperti %cd atau !pip dengan tetap menjaga indentasi)
                clean_lines = [
                    (line[:len(line) - len(line.lstrip())] + "pass")
                    if line.lstrip().startswith(("!", "%")) else line
                    for line in src.splitlines()
                ]
                compile("\n".join(clean_lines), "<colab_cell>", "exec")
        self.assertGreaterEqual(found_watchdog_ref, 3, "Semua 3 cell server Colab harus memakai run_shiro_supervisor!")


if __name__ == "__main__":
    unittest.main()
