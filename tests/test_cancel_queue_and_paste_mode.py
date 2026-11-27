# -*- coding: utf-8 -*-
import os
import re
import unittest


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCancelQueueAndPasteMode(unittest.TestCase):
    def test_cancel_clears_running_state_and_never_queues_next_message(self):
        """Setelah stopGeneration(), pesan berikutnya langsung dikirim dan tidak terjebak di antrean."""
        with open(os.path.join(ROOT_DIR, "static", "script.js"), "r", encoding="utf-8") as f:
            js = f.read()

        # 1. stopGeneration menandai recentlyAbortedSessions & langsung membersihkan serverRunningSessions + input lock
        m_stop = re.search(r"function stopGeneration\([^)]*\)\s*\{([\s\S]*?)^\}", js, re.MULTILINE)
        self.assertIsNotNone(m_stop)
        stop_body = m_stop.group(1)
        self.assertIn("recentlyAbortedSessions.set(sid, Date.now());", stop_body)
        self.assertIn("serverRunningSessions.delete(sid);", stop_body)
        self.assertIn("run.aborted = true;", stop_body)
        self.assertIn("run.isRunning = false;", stop_body)
        self.assertIn("setInputLock(false);", stop_body)

        # 2. sendMessage hanya mengantrekan jika isSessionActivelyRunningLocally(targetSessionId) bernilai true
        self.assertIn("if (!overridePayload && isSessionActivelyRunningLocally(targetSessionId))", js)
        self.assertIn("recentlyAbortedSessions.delete(targetSessionId);", js)

        # 3. applySessionsListUI menyaring sesi yang baru dihentikan agar tidak menyalakan spinner lagi
        self.assertIn("filter(id => !isSessionRecentlyAborted(id))", js)

    def test_pasted_long_text_has_click_preview_and_paste_as_text_option(self):
        """Teks panjang yang menjadi file lampiran bisa diklik dan memiliki tombol Paste untuk beralih ke mode teks langsung."""
        with open(os.path.join(ROOT_DIR, "static", "script.js"), "r", encoding="utf-8") as f:
            js = f.read()
        with open(os.path.join(ROOT_DIR, "static", "style.css"), "r", encoding="utf-8") as f:
            css = f.read()

        self.assertIn("is_pasted: true", js)
        self.assertIn("function convertAttachedDocToText(", js)
        self.assertIn("function toggleAttachedDocPreview(", js)
        self.assertIn("attach-doc-preview-panel", js)
        self.assertIn("attach-paste-as-text-btn", js)
        self.assertIn("paste_as_text_btn", js)
        self.assertIn(".attach-doc-preview-panel", css)
        self.assertIn(".attach-paste-as-text-btn", css)


if __name__ == "__main__":
    unittest.main()
