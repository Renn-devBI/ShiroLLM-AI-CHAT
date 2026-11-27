# -*- coding: utf-8 -*-
import os
import re
import unittest

import web
from shiro.server_state import state
from shiro.agent.tools import detect_agent_intent
from shiro.web.realtime_intel import classify_intent
from shiro.pipeline.inference import _is_heavy_agent_task


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestMultiSessionAndIntentFixes(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()
        self.mem = state.init_memory()
        with self.mem.lock:
            self._had_notif_key = "notifications_enabled" in self.mem.system_metadata
            self._orig_notif = self.mem.system_metadata.get("notifications_enabled", True)

    def tearDown(self):
        with self.mem.lock:
            if self._had_notif_key:
                self.mem.system_metadata["notifications_enabled"] = self._orig_notif
            else:
                self.mem.system_metadata.pop("notifications_enabled", None)
            self.mem.save_memory()

    def test_casual_and_identity_questions_never_trigger_agent_or_heavy_path(self):
        """Pertanyaan biasa / identitas / kapabilitas tidak memicu intent Search/Agent atau kotak Analyzing."""
        casual_prompts = [
            "siapa kamu",
            "siapa pencipta kamu",
            "shiro kamu sedang apa hari ini",
            "apa kabar sekarang",
            "apakah kamu bisa bikin website?",
            "kamu bisa baca video?",
            "who are you",
            "who created you",
            "what can you do",
            "halo shiro",
            "terima kasih shiro",
        ]
        for prompt in casual_prompts:
            intel = classify_intent(prompt)
            self.assertEqual(
                intel.kind, "none",
                f"classify_intent('{prompt}') seharusnya 'none', malah '{intel.kind}' ({intel.reasons})"
            )
            intent = detect_agent_intent(prompt)
            self.assertEqual(
                intent["intent"], "none",
                f"detect_agent_intent('{prompt}') seharusnya 'none', malah '{intent}'"
            )
            heavy = _is_heavy_agent_task(raw_user_typed=prompt, agent_intent=intent["intent"])
            self.assertFalse(
                heavy,
                f"_is_heavy_agent_task('{prompt}') seharusnya False agar tidak muncul Analyzing request"
            )

    def test_real_agent_search_code_archive_prompts_still_trigger(self):
        """Perintah nyata coding, pencarian web, dan kompresi arsip tetap aktif."""
        self.assertTrue(_is_heavy_agent_task("buatkan website login app.py dan index.html", agent_intent="none"))
        self.assertTrue(_is_heavy_agent_task("perbaiki bug di script.js", agent_intent="none"))

        arch = detect_agent_intent("jadikan zip semua file")
        self.assertEqual(arch["intent"], "archive")
        self.assertTrue(_is_heavy_agent_task("jadikan zip semua file", agent_intent=arch["intent"]))

        search = detect_agent_intent("carikan berita terbaru AI 2026")
        self.assertEqual(search["intent"], "search")
        self.assertTrue(_is_heavy_agent_task("carikan berita terbaru AI 2026", agent_intent=search["intent"]))

    def test_notifications_enabled_persistence_in_privacy_and_history(self):
        """Pengaturan notifications_enabled tersimpan di /api/settings/privacy & terbaca di /api/history."""
        r_off = self.client.post("/api/settings/privacy", json={"notifications_enabled": False})
        self.assertEqual(r_off.status_code, 200)
        d_off = r_off.get_json()
        self.assertTrue(d_off["success"])
        self.assertFalse(d_off["notifications_enabled"])

        r_get = self.client.get("/api/settings/privacy")
        self.assertEqual(r_get.status_code, 200)
        self.assertFalse(r_get.get_json()["notifications_enabled"])

        r_hist = self.client.get("/api/history")
        self.assertEqual(r_hist.status_code, 200)
        self.assertFalse(r_hist.get_json()["notifications_enabled"])

        r_on = self.client.post("/api/settings/privacy", json={"notifications_enabled": True})
        self.assertEqual(r_on.status_code, 200)
        self.assertTrue(r_on.get_json()["notifications_enabled"])

    def test_frontend_send_stop_thought_switching_and_notif_contracts(self):
        """Verifikasi statis JS & HTML untuk tombol send/stop, thought guard, switching sesi, dan toggle notifikasi."""
        script_path = os.path.join(ROOT_DIR, "static", "script.js")
        index_path = os.path.join(ROOT_DIR, "templates", "index.html")
        with open(script_path, "r", encoding="utf-8") as f:
            js = f.read()
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()

        # 1. Tombol send & stop dibungkus arrow function agar tidak melempar PointerEvent
        self.assertIn("sendBtn.addEventListener('click', () => sendMessage());", js)
        self.assertIn("stopBtn.addEventListener('click', () => stopGeneration());", js)
        self.assertIn("overridePayload instanceof Event", js)
        self.assertIn("typeof targetSessionId === 'string'", js)

        # 2. renderAgentThoughtHTML tidak merender kotak kosong saat tidak ada steps & thoughtText
        m_rth = re.search(r"function renderAgentThoughtHTML\(meta\)\s*\{([\s\S]*?)const isOpen", js)
        self.assertIsNotNone(m_rth)
        self.assertIn("if (!steps.length && !thoughtText) return '';", m_rth.group(1))
        self.assertNotIn("!steps.length && !thoughtText && !isRunning", m_rth.group(1))

        # 3. switchSession mengatur activeSessionId SEBELUM await fetch & tidak memanggil await loadSessions()
        m_sw = re.search(r"async function switchSession\(sessionId, force = false\)\s*\{([\s\S]*?)^\}", js, re.MULTILINE)
        self.assertIsNotNone(m_sw)
        sw_body = m_sw.group(1)
        pos_active = sw_body.find("activeSessionId = sessionId;")
        pos_fetch = sw_body.find("await fetch('/api/sessions/switch'")
        self.assertGreater(pos_active, -1)
        self.assertGreater(pos_fetch, pos_active)
        self.assertIn("applySessionsListUI(data.sessions", sw_body)
        self.assertNotIn("await loadSessions();", sw_body)

        # 4. Notifications toggle tersedia di UI dan dihormati di showSessionDoneNotification
        self.assertIn('id="notifications-enabled-toggle"', html)
        self.assertIn("if (!notificationsEnabled) return;", js)
        self.assertIn("toast-mute-btn", js)


if __name__ == "__main__":
    unittest.main()
