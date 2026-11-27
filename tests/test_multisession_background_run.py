# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import web
from shiro.server_state import state
from shiro.models import get_saved_lyra_tier, save_lyra_tier


class TestMultiSessionBackgroundRun(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()
        self.mem = state.init_memory()
        self._orig_llm = state.llm
        self._orig_vh = state.vision_chat_handler
        self._orig_lyra_tier = get_saved_lyra_tier()
        self._orig_sessions = {k: dict(v) for k, v in (getattr(self.mem, "sessions_store", {}) or {}).items()}
        self._orig_active = getattr(self.mem, "active_session_id", "default")
        self._orig_hist = list(self.mem.short_term_history)

    def tearDown(self):
        state.llm = self._orig_llm
        state.vision_chat_handler = self._orig_vh
        save_lyra_tier(self._orig_lyra_tier)
        with self.mem.lock:
            self.mem.sessions_store = self._orig_sessions
            self.mem.active_session_id = self._orig_active
            self.mem.short_term_history = self._orig_hist
            self.mem.save_memory()
        with state._running_sessions_lock:
            state._running_sessions.clear()

    def test_memory_add_message_scoped_to_background_session(self):
        """Menyimpan pesan ke session_id A saat sesi aktif B tidak merusak short_term_history sesi B."""
        sid_a = self.mem.create_new_session(title="Sesi Alpha")
        sid_b = self.mem.create_new_session(title="Sesi Beta")
        self.assertEqual(self.mem.active_session_id, sid_b)

        self.mem.add_message("user", "pesan khusus beta", session_id=sid_b)
        self.mem.add_message("user", "pesan khusus alpha latar belakang", session_id=sid_a)

        hist_a = self.mem.get_session_history(sid_a)
        hist_b = self.mem.get_session_history(sid_b)
        self.assertEqual([m["content"] for m in hist_a], ["pesan khusus alpha latar belakang"])
        self.assertEqual([m["content"] for m in hist_b], ["pesan khusus beta"])
        self.assertEqual(self.mem.active_session_id, sid_b)

    def test_chat_endpoint_pins_execution_to_origin_session_id(self):
        """POST /api/chat dengan session_id A saat active_session_id == B membalas memakai konteks A dan menulis ke A."""
        sid_a = self.mem.create_new_session(title="Sesi Proyek A")
        self.mem.add_message("user", "Rahasia Proyek A adalah ORION-99", session_id=sid_a)

        sid_b = self.mem.create_new_session(title="Sesi Proyek B")
        self.mem.add_message("user", "Ini obrolan B yang terpisah", session_id=sid_b)
        self.assertEqual(self.mem.active_session_id, sid_b)

        captured_prompts = []

        class ScopedSessionLLM:
            model_path = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"
            _shiro_fast_chatml = True

            def n_ctx(self):
                return 500000

            def create_completion(self, prompt, stream=False, **kwargs):
                captured_prompts.append(prompt)
                if stream:
                    def _gen():
                        yield {"choices": [{"text": "Jawaban latar belakang untuk Sesi A selesai."}]}
                    return _gen()
                return {
                    "choices": [{"text": "Jawaban sinkron untuk Sesi A.", "finish_reason": "stop"}],
                    "usage": {},
                }

        state.llm = ScopedSessionLLM()
        with patch("shiro.models.get_gpu_layers", return_value=-1):
            # Non-streaming pinned to sid_a while active is sid_b
            resp_sync = self.client.post("/api/chat", json={
                "message": "lanjutkan analisa A",
                "session_id": sid_a,
                "stream": False,
                "lyra_tier": "low",
            })
            self.assertEqual(resp_sync.status_code, 200)
            sync_data = resp_sync.get_json()
            self.assertEqual(sync_data["session_id"], sid_a)
            self.assertEqual(sync_data["session_title"], "Sesi Proyek A")
            self.assertIn("ORION-99", captured_prompts[0])
            self.assertNotIn("Ini obrolan B yang terpisah", captured_prompts[0])

            # Streaming SSE pinned to sid_a while active is sid_b
            resp_sse = self.client.post("/api/chat", json={
                "message": "streaming latar belakang A",
                "session_id": sid_a,
                "stream": True,
                "lyra_tier": "low",
            })
            self.assertEqual(resp_sse.status_code, 200)
            sse_body = resp_sse.get_data(as_text=True)
            self.assertIn(f'"session_id": "{sid_a}"', sse_body)
            self.assertIn('"session_title": "Sesi Proyek A"', sse_body)
            self.assertIn("Jawaban latar belakang untuk Sesi A selesai.", sse_body)

        # Pastikan active session B tetap aktif dan tidak tercampur pesan A
        self.assertEqual(self.mem.active_session_id, sid_b)
        hist_b = [m["content"] for m in self.mem.get_session_history(sid_b)]
        self.assertEqual(hist_b, ["Ini obrolan B yang terpisah"])

        hist_a = [m["content"] for m in self.mem.get_session_history(sid_a)]
        self.assertIn("Jawaban sinkron untuk Sesi A.", hist_a)
        self.assertIn("Jawaban latar belakang untuk Sesi A selesai.", hist_a)
        self.assertEqual(state.get_running_session_ids(), [])

    def test_sessions_api_exposes_running_state(self):
        """GET /api/sessions menandai is_running untuk sesi yang sedang aktif di server."""
        sid_run = self.mem.create_new_session(title="Sesi Latar")
        sid_idle = self.mem.create_new_session(title="Sesi Idle")

        state.mark_session_running(sid_run)
        try:
            resp = self.client.get("/api/sessions")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertIn(sid_run, data["running_sessions"])
            self.assertNotIn(sid_idle, data["running_sessions"])
            by_id = {s["id"]: s for s in data["sessions"]}
            self.assertTrue(by_id[sid_run]["is_running"])
            self.assertFalse(by_id[sid_idle]["is_running"])
        finally:
            state.mark_session_done(sid_run)

        resp2 = self.client.get("/api/sessions")
        self.assertEqual(resp2.get_json()["running_sessions"], [])

    def test_ui_multisession_nonblocking_and_bottom_right_closable_toast(self):
        """Frontend tidak mengunci switchSession saat running, menampilkan indikator sidebar, dan notifikasi pojok kanan bawah bisa ditutup."""
        root = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(root, "static", "script.js"), "r", encoding="utf-8") as f:
            js = f.read()
        with open(os.path.join(root, "static", "style.css"), "r", encoding="utf-8") as f:
            css = f.read()

        # switchSession, createNewSession, deleteSessionById tidak boleh diblokir isGenerating
        self.assertNotIn("let isGenerating =", js)
        self.assertIn("const sessionRuns = new Map();", js)
        self.assertIn("function showSessionDoneNotification", js)
        self.assertIn("toast-close-btn", js)
        self.assertIn("session-running-badge", js)
        self.assertIn("session_id: targetSessionId", js)
        self.assertIn("function stopGeneration", js)

        # Toast berada di pojok kanan bawah
        self.assertIn("right: 20px;", css)
        self.assertIn("bottom: 20px;", css)
        self.assertIn(".session-running-badge", css)
        self.assertIn(".toast-close-btn", css)


if __name__ == "__main__":
    unittest.main()
