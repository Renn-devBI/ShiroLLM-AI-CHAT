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
from shiro.colab_watchdog import (
    _next_stepdown_ctx,
    run_shiro_supervisor,
    detect_cuda_tag,
    find_prebuilt_cuda_wheel_url,
    ensure_cuda_llama_cpp,
)


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

    def test_detect_cuda_tag_and_prebuilt_wheel_selection(self):
        """Deteksi versi CUDA & pencarian wheel Linux pra-kompilasi Python 3.12/3.13 bekerja akurat (API & offline fallback)."""
        fake_smi_128 = MagicMock(returncode=0, stdout="| NVIDIA-SMI 570.124  CUDA Version: 12.8 |", stderr="")
        with patch("shiro.colab_watchdog.subprocess.run", return_value=fake_smi_128):
            tags = detect_cuda_tag()
            self.assertEqual(tags[:3], ["cu128", "cu126", "cu124"])

        fake_smi_130 = MagicMock(returncode=0, stdout="| NVIDIA-SMI 580.65  CUDA Version: 13.0 |", stderr="")
        with patch("shiro.colab_watchdog.subprocess.run", return_value=fake_smi_130):
            tags_130 = detect_cuda_tag()
            self.assertEqual(tags_130[0], "cu130")
            self.assertIn("cu128", tags_130)

        api_payload = json.dumps([
            {
                "tag_name": "v0.4.8-cu128-linux-20261122",
                "assets": [
                    {
                        "name": "llama_cpp_python-0.4.8+cu128-cp313-cp313-linux_x86_64.whl",
                        "browser_download_url": "https://github.com/JamePeng/llama-cpp-python/releases/download/v0.4.8-cu128-linux-20261122/llama_cpp_python-0.4.8+cu128-cp313-cp313-linux_x86_64.whl",
                    },
                    {
                        "name": "llama_cpp_python-0.4.8+cu128-cp312-cp312-linux_x86_64.whl",
                        "browser_download_url": "https://github.com/JamePeng/llama-cpp-python/releases/download/v0.4.8-cu128-linux-20261122/llama_cpp_python-0.4.8+cu128-cp312-cp312-linux_x86_64.whl",
                    },
                ],
            }
        ]).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = api_payload
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_resp

        with patch("shiro.colab_watchdog.urllib.request.urlopen", return_value=mock_cm):
            urls = find_prebuilt_cuda_wheel_url(py_tag="cp313", preferred_cu_tags=["cu128", "cu124"])
            self.assertTrue(urls[0].endswith("llama_cpp_python-0.4.8+cu128-cp313-cp313-linux_x86_64.whl"))

        # Offline fallback jika API diblokir / rate-limit
        with patch("shiro.colab_watchdog.urllib.request.urlopen", side_effect=RuntimeError("rate limit")):
            offline_urls = find_prebuilt_cuda_wheel_url(py_tag="cp313", preferred_cu_tags=["cu128", "cu124"])
            self.assertTrue(len(offline_urls) >= 2)
            self.assertIn("cp313-cp313-linux_x86_64.whl", offline_urls[0])

    def test_ensure_cuda_llama_cpp_skips_when_already_active_and_repairs_when_cpu_only(self):
        """ensure_cuda_llama_cpp langsung True jika CUDA aktif, atau memasang wheel CUDA jika terdeteksi CPU-only."""
        with patch("shiro.colab_watchdog.detect_colab_gpu", return_value=(True, "NVIDIA A100-SXM4-80GB, 81920 MiB")), \
             patch("shiro.colab_watchdog.refresh_cuda_ldconfig", return_value=""), \
             patch("shiro.colab_watchdog.check_cuda_offload_subprocess", return_value=True), \
             patch("shiro.colab_watchdog.subprocess.run") as mock_pip:
            self.assertTrue(ensure_cuda_llama_cpp(force=False))
            mock_pip.assert_not_called()

        pip_calls = []
        def fake_pip_run(cmd, **kwargs):
            pip_calls.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("shiro.colab_watchdog.detect_colab_gpu", return_value=(True, "NVIDIA A100-SXM4-80GB, 81920 MiB")), \
             patch("shiro.colab_watchdog.refresh_cuda_ldconfig", return_value=""), \
             patch("shiro.colab_watchdog.check_cuda_offload_subprocess", side_effect=[False, True]), \
             patch("shiro.colab_watchdog.find_prebuilt_cuda_wheel_url", return_value=["https://example.com/cuda-cp313.whl"]), \
             patch("shiro.colab_watchdog.subprocess.run", side_effect=fake_pip_run):
            self.assertTrue(ensure_cuda_llama_cpp(force=False))
            self.assertEqual(len(pip_calls), 1)
            self.assertIn("pip", pip_calls[0])
            self.assertIn("https://example.com/cuda-cp313.whl", pip_calls[0])

    def test_detect_cuda_tag_ignores_cu13x_when_runtime_is_cuda12(self):
        """Jika nvidia-smi melaporkan driver 13.0 tetapi libcudart terpasang adalah 12.x, cu13x disaring keluar."""
        fake_smi_130 = MagicMock(returncode=0, stdout="| NVIDIA-SMI 580.65  CUDA Version: 13.0 |", stderr="")
        with patch("shiro.colab_watchdog.subprocess.run", return_value=fake_smi_130), \
             patch("shiro.colab_watchdog._detect_installed_cuda_runtime_major", return_value=12):
            tags = detect_cuda_tag()
            self.assertFalse(any(t.startswith("cu13") for t in tags))
            self.assertEqual(tags[:3], ["cu128", "cu126", "cu124"])

    def test_wait_for_server_ready_streams_log_progress(self):
        """wait_for_server_ready mencetak baris progres baru dari log_path dan mengembalikan True saat /api/health 200."""
        import io
        import tempfile
        from contextlib import redirect_stdout
        from shiro.colab_watchdog import wait_for_server_ready

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tf:
            tmp_log = tf.name
            tf.write("llama_model_loader: loaded meta data\n")
            tf.write("✓ Model loaded: ShiroHaru-Lyra-Agent\n")

        try:
            proc = MagicMock()
            proc.poll.return_value = None
            resp_ok = MagicMock(status=200)
            cm_ok = MagicMock()
            cm_ok.__enter__.return_value = resp_ok

            buf = io.StringIO()
            with patch("shiro.colab_watchdog.urllib.request.urlopen", return_value=cm_ok), \
                 redirect_stdout(buf):
                ok = wait_for_server_ready(proc, timeout_sec=10, port=7474, log_path=tmp_log)
            self.assertTrue(ok)
            out = buf.getvalue()
            self.assertIn("Model loaded: ShiroHaru-Lyra-Agent", out)
            self.assertNotIn("llama_model_loader", out)
        finally:
            try:
                os.remove(tmp_log)
            except OSError:
                pass

    def test_wheel_ordering_tries_distinct_cuda_tags_before_older_versions(self):
        """find_prebuilt_cuda_wheel_url mengurutkan 1 wheel terbaru per tag CUDA (cu130, cu128, cu124) sebelum versi lama (0.4.7+cu130)."""
        api_payload = json.dumps([
            {
                "tag_name": "v0.4.8-cu130-linux",
                "assets": [
                    {
                        "name": "llama_cpp_python-0.4.8+cu130-cp313-cp313-linux_x86_64.whl",
                        "browser_download_url": "https://example.com/llama_cpp_python-0.4.8+cu130-cp313-cp313-linux_x86_64.whl",
                    }
                ],
            },
            {
                "tag_name": "v0.4.7-cu130-linux",
                "assets": [
                    {
                        "name": "llama_cpp_python-0.4.7+cu130-cp313-cp313-linux_x86_64.whl",
                        "browser_download_url": "https://example.com/llama_cpp_python-0.4.7+cu130-cp313-cp313-linux_x86_64.whl",
                    }
                ],
            },
            {
                "tag_name": "v0.4.8-cu128-linux",
                "assets": [
                    {
                        "name": "llama_cpp_python-0.4.8+cu128-cp313-cp313-linux_x86_64.whl",
                        "browser_download_url": "https://example.com/llama_cpp_python-0.4.8+cu128-cp313-cp313-linux_x86_64.whl",
                    }
                ],
            },
        ]).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = api_payload
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_resp

        with patch("shiro.colab_watchdog.urllib.request.urlopen", return_value=mock_cm):
            urls = find_prebuilt_cuda_wheel_url(py_tag="cp313", preferred_cu_tags=["cu130", "cu128", "cu124"])

        self.assertIn("0.4.8+cu130", urls[0])
        self.assertIn("0.4.8+cu128", urls[1])
        self.assertIn("0.4.8+cu124", urls[2])
        self.assertIn("0.4.7+cu130", urls[3])

    def test_probe_cuda_offload_subprocess_loads_backends_and_reports_dlopen_error(self):
        """probe_cuda_offload_subprocess memuat ggml_backend_load_all_from_path di skrip probe dan menangkap SHIRO_CUDA_DLOPEN_ERR."""
        from shiro.colab_watchdog import probe_cuda_offload_subprocess

        seen_cmds = []

        def fake_sub_ok(cmd, **kwargs):
            seen_cmds.append(cmd)
            return MagicMock(returncode=0, stdout="SHIRO_GPU_OFFLOAD=True\n", stderr="")

        with patch("shiro.colab_watchdog.subprocess.run", side_effect=fake_sub_ok):
            ok, detail = probe_cuda_offload_subprocess()
        self.assertTrue(ok)
        self.assertIn("ggml_backend_load_all_from_path", seen_cmds[0][2])
        self.assertIn("llama_backend_init", seen_cmds[0][2])

        fake_fail = MagicMock(
            returncode=0,
            stdout="SHIRO_GPU_OFFLOAD=False\nSHIRO_CUDA_DLOPEN_ERR=libcudart.so.13: cannot open shared object file\n",
            stderr="",
        )
        with patch("shiro.colab_watchdog.subprocess.run", return_value=fake_fail):
            ok2, detail2 = probe_cuda_offload_subprocess()
        self.assertFalse(ok2)
        self.assertIn("libcudart.so.13", detail2)


if __name__ == "__main__":
    unittest.main()
