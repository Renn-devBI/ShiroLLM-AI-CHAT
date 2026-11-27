# -*- coding: utf-8 -*-
import os
import sys
import zipfile
import shutil
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import web  # noqa: E402
from shiro.server_state import state
from shiro.agent import packager as pk
from shiro.agent.tools import detect_agent_intent
from shiro.pipeline.inference import stream_shiro_reply


class TestAgentBehaviorAndQueue(unittest.TestCase):
    def setUp(self):
        self.prev_llm = state.llm
        self.prev_vis = state.vision_chat_handler
        self.mem = state.init_memory()
        self.prev_history = list(self.mem.short_term_history)
        self.created_bundles = []

    def tearDown(self):
        state.llm = self.prev_llm
        state.vision_chat_handler = self.prev_vis
        with self.mem.lock:
            self.mem.short_term_history = list(self.prev_history)
        for b in self.created_bundles:
            shutil.rmtree(b, ignore_errors=True)

    def test_multiturn_zip_collects_app_py_and_latest_index_html_only_post_llm(self):
        """
        Jika app.py dibuat di giliran 1 dan index.html diedit di giliran 2,
        permintaan 'jadikan zip app.py nya dan index.html nya' harus menggabungkan app.py + index.html terbaru,
        dan artefak zip HANYA muncul setelah AI selesai berpikir/merespons.
        """
        with self.mem.lock:
            self.mem.short_term_history = [
                {"role": "user", "content": "buatkan web flask login"},
                {
                    "role": "assistant",
                    "content": (
                        "### File: `app.py`\n```python\nfrom flask import Flask\napp = Flask(__name__)\n```\n"
                        "### File: `index.html`\n```html\n<h1>Versi Lama</h1>\n```\n"
                    ),
                },
                {"role": "user", "content": "perbagus tampilan index.html nya"},
                {
                    "role": "assistant",
                    "content": (
                        "Ini pembaruan tampilannya:\n"
                        "### File: `index.html`\n```html\n<h1>Versi Modern Baru</h1>\n```\n"
                    ),
                },
            ]

        class NaturalAgentZipLLM:
            model_path = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"
            _shiro_fast_chatml = True

            def n_ctx(self):
                return 500000

            def create_completion(self, prompt, stream=False, **kwargs):
                self.captured_prompt = prompt
                def _gen():
                    yield {"choices": [{"text": "<think>1. Checking workspace files: app.py and updated index.html are present across turns.</think>\n"}]}
                    yield {"choices": [{"text": "Siap Kakak! Arsip berisi `app.py` (backend Flask) dan `index.html` versi terbaru sudah dikemas."}]}
                return _gen()

        fake_llm = NaturalAgentZipLLM()
        state.llm = fake_llm
        with patch("shiro.models.get_gpu_layers", return_value=-1):
            events = list(stream_shiro_reply("jadikan zip app.py nya dan index.html nya", lyra_tier="high"))

        # Pastikan prompt memberi inventaris workspace netral (bukan kalimat template 'SUDAH BERHASIL DIBUAT')
        self.assertIn("INVENTARIS BERKAS WORKSPACE", fake_llm.captured_prompt)
        self.assertNotIn("SUDAH BERHASIL DIBUAT", fake_llm.captured_prompt)

        ev_types = [e.get("type") for e in events]
        self.assertIn("thought_done", ev_types)
        self.assertIn("artifacts", ev_types)
        self.assertGreater(ev_types.index("artifacts"), ev_types.index("thought_done"))
        self.assertGreater(ev_types.index("artifacts"), max(i for i, t in enumerate(ev_types) if t == "token"))

        done = [e for e in events if e.get("type") == "done"][-1]
        arch = done["artifacts"][0]
        self.created_bundles.append(os.path.join(pk.GENERATED_ARTIFACTS_DIR, arch["id"]))
        self.assertEqual(sorted(arch["files_included"]), ["app.py", "index.html"])

        zip_disk = os.path.join(pk.GENERATED_ARTIFACTS_DIR, arch["id"], arch["filename"])
        with zipfile.ZipFile(zip_disk, "r") as zf:
            self.assertIn("Flask(__name__)", zf.read("app.py").decode("utf-8"))
            html_content = zf.read("index.html").decode("utf-8")
            self.assertIn("Versi Modern Baru", html_content)
            self.assertNotIn("Versi Lama", html_content)

    def test_autonomous_react_browser_search_and_sources_images(self):
        """Model yang memanggil [[AGENT_TOOL:web_search|query=...]] mengeksekusi tool browser, menyembunyikan tag mentah, dan menyertakan sumber + gambar."""
        with self.mem.lock:
            self.mem.short_term_history = []

        class ReactSearchLLM:
            model_path = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"
            _shiro_fast_chatml = True

            def __init__(self):
                self.calls = 0

            def n_ctx(self):
                return 500000

            def create_completion(self, prompt, stream=False, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    def _gen1():
                        yield {"choices": [{"text": "<think>Need to search browser for official specs and images.</think>\n"}]}
                        yield {"choices": [{"text": "[[AGENT_TOOL:web_search|query=RTX 5090 specs]]"}]}
                    return _gen1()
                else:
                    self.second_prompt = prompt
                    def _gen2():
                        yield {"choices": [{"text": "Berdasarkan sumber [NVIDIA Official](https://example.com/rtx5090), berikut ringkasan RTX 5090!\n\n![RTX 5090](https://example.com/rtx5090.jpg)"}]}
                    return _gen2()

        mock_search_out = {
            "success": True,
            "summary": "1. [NVIDIA Official](https://example.com/rtx5090)\nRTX 5090 specs",
            "results": [
                {"title": "NVIDIA Official", "url": "https://example.com/rtx5090", "snippet": "32GB GDDR7", "source": "Bing Search"}
            ],
            "images": [
                {"title": "RTX 5090", "url": "https://example.com/rtx5090.jpg", "source_url": "https://example.com/rtx5090", "source": "Bing Images"}
            ],
        }

        fake_llm = ReactSearchLLM()
        state.llm = fake_llm
        with patch("shiro.models.get_gpu_layers", return_value=-1), \
             patch("shiro.agent.tools.search_google_web", return_value=mock_search_out):
            events = list(stream_shiro_reply("jelaskan tentang rtx 5090", lyra_tier="high"))

        self.assertEqual(fake_llm.calls, 2)
        self.assertIn("https://example.com/rtx5090", fake_llm.second_prompt)

        streamed_text = "".join(e["token"] for e in events if e.get("type") == "token")
        self.assertNotIn("AGENT_TOOL", streamed_text)

        done = [e for e in events if e.get("type") == "done"][-1]
        self.assertNotIn("AGENT_TOOL", done["reply"])
        action = done.get("agent_action") or {}
        self.assertTrue(any(s.get("url") == "https://example.com/rtx5090" for s in (action.get("sources") or [])))
        self.assertTrue(any(im.get("url") == "https://example.com/rtx5090.jpg" for im in (action.get("web_images") or [])))

    def test_broad_info_and_image_search_intent_detection(self):
        """Permintaan informasi & gambar otomatis memicu search, sedangkan curhat/coding tidak."""
        r_img = detect_agent_intent("tolong carikan gambar kucing ragdoll lucu")
        self.assertEqual(r_img["intent"], "search")
        self.assertTrue(r_img["params"].get("wants_images"))

        r_spec = detect_agent_intent("info spesifikasi RTX 5090 dan harga terbaru")
        self.assertEqual(r_spec["intent"], "search")

        r_src = detect_agent_intent("carikan sumber dan link dokumentasi PyTorch resmi")
        self.assertEqual(r_src["intent"], "search")

        self.assertEqual(detect_agent_intent("aku lagi sedih dan capek banget")["intent"], "none")
        self.assertEqual(detect_agent_intent("buatkan website login modern tanpa emoji")["intent"], "none")

    def test_frontend_queue_spinner_and_live_upload_markup(self):
        """Pastikan index.html, style.css, dan script.js memiliki spinner presisi, panel antrean, dan tombol upload aktif saat generasi."""
        root = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(root, "templates", "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        with open(os.path.join(root, "static", "style.css"), "r", encoding="utf-8") as f:
            css = f.read()
        with open(os.path.join(root, "static", "script.js"), "r", encoding="utf-8") as f:
            js = f.read()

        self.assertIn('id="queued-messages-panel"', html)
        self.assertIn(".ag-spinner-ring", css)
        self.assertIn(".queued-messages-panel", css)
        self.assertNotIn(".input-section.is-generating .btn-media", css)
        self.assertIn("ag-spinner-ring", js)
        self.assertIn("enqueueCurrentComposer", js)
        self.assertIn("renderQueuedMessagesPanel", js)
        self.assertIn("renderWebSourcesHTML", js)


if __name__ == "__main__":
    unittest.main()
