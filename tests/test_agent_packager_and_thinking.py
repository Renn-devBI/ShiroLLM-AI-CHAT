# -*- coding: utf-8 -*-
import os
import sys
import json
import gzip
import shutil
import zipfile
import tarfile
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import web
from shiro.server_state import state
from shiro.agent import packager as pk
from shiro.agent.tools import detect_agent_intent
from shiro.pipeline.inference import stream_shiro_reply


class TestAgentPackagerAndThinking(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()
        self.prev_llm = state.llm
        self.prev_vis = state.vision_chat_handler
        self.mem = state.init_memory()
        self.prev_history = list(self.mem.short_term_history)
        self.tmp_artifacts_dir = tempfile.mkdtemp(prefix="shiro_art_test_")

    def tearDown(self):
        state.llm = self.prev_llm
        state.vision_chat_handler = self.prev_vis
        with self.mem.lock:
            self.mem.short_term_history = list(self.prev_history)
        shutil.rmtree(self.tmp_artifacts_dir, ignore_errors=True)

    def test_detect_archive_intent_multi_format_and_info_guard(self):
        """detect_agent_intent mengenali kompresi zip/tar.gz/7z/tar/gz/rar dan mengabaikan pertanyaan teoritis."""
        r_zip = detect_agent_intent("jadikan zip semua shiro!!")
        self.assertEqual(r_zip["intent"], "archive")
        self.assertEqual(r_zip["params"]["format"], "zip")

        r_targz = detect_agent_intent("compress project files into my-web.tar.gz")
        self.assertEqual(r_targz["intent"], "archive")
        self.assertEqual(r_targz["params"]["format"], "tar.gz")
        self.assertEqual(r_targz["params"]["archive_name"], "my-web.tar.gz")

        r_7z = detect_agent_intent("kompres semua kode menjadi arsip .7z dong")
        self.assertEqual(r_7z["intent"], "archive")
        self.assertEqual(r_7z["params"]["format"], "7z")

        r_rar = detect_agent_intent("jadikan rar file ini")
        self.assertEqual(r_rar["intent"], "archive")
        self.assertEqual(r_rar["params"]["format"], "zip")
        self.assertIsNotNone(r_rar["params"].get("note"))

        # Pertanyaan definisi biasa tidak boleh dianggap perintah mengompres
        r_info = detect_agent_intent("apa itu zip dan bagaimana cara kerjanya?")
        self.assertNotEqual(r_info["intent"], "archive")

    def test_extract_exact_custom_filenames_including_login_app(self):
        """Ekstraksi kode wajib mempertahankan nama persis seperti login.app (tidak diubah ke main.py/txt)."""
        md = (
            "Berikut berkas aplikasi yang diminta:\n\n"
            "### File 1: `login.app`\n"
            "```python\n"
            "def login(user):\n    return bool(user)\n"
            "```\n\n"
            "```html:templates/dashboard.html\n"
            "<h1>Dashboard</h1>\n"
            "```\n\n"
            "```javascript\n"
            "// filename: assets/app.js\n"
            "console.log('ready');\n"
            "```\n"
        )
        files = pk.extract_named_files_from_markdown(md)
        names = [f["filename"] for f in files]
        basenames = [f["basename"] for f in files]
        self.assertEqual(names, ["login.app", "templates/dashboard.html", "assets/app.js"])
        self.assertEqual(basenames[0], "login.app")

    def test_create_real_extractable_archives_all_standard_formats(self):
        """create_archive_artifact membuat arsip nyata (.zip, .tar.gz, .tar.bz2, .tar.xz, .tar, .gz) yang valid dibuka."""
        sample_files = [
            {"filename": "login.app", "basename": "login.app", "content": "print('login.app ok')\n", "language": "python"},
            {"filename": "templates/index.html", "basename": "index.html", "content": "<h1>Pondok Kayu</h1>\n", "language": "html"},
        ]

        # 1. ZIP
        z_art = pk.create_archive_artifact(sample_files, fmt="zip", project_name="pondok-kayu", base_dir=self.tmp_artifacts_dir)
        self.assertEqual(z_art["filename"], "pondok-kayu.zip")
        z_path = os.path.join(self.tmp_artifacts_dir, z_art["id"], z_art["filename"])
        self.assertTrue(os.path.exists(z_path))
        with zipfile.ZipFile(z_path, "r") as zf:
            self.assertEqual(sorted(zf.namelist()), ["login.app", "templates/index.html"])
            self.assertIn("login.app ok", zf.read("login.app").decode("utf-8"))

        # 2. TAR.GZ / TAR.BZ2 / TAR.XZ / TAR
        for fmt_name, read_mode in [("tar.gz", "r:gz"), ("tar.bz2", "r:bz2"), ("tar.xz", "r:xz"), ("tar", "r:")]:
            t_art = pk.create_archive_artifact(sample_files, fmt=fmt_name, project_name="shiro-pkg", base_dir=self.tmp_artifacts_dir)
            self.assertTrue(t_art["filename"].endswith(f".{fmt_name}"))
            t_path = os.path.join(self.tmp_artifacts_dir, t_art["id"], t_art["filename"])
            with tarfile.open(t_path, read_mode) as tf:
                self.assertEqual(sorted(tf.getnames()), ["login.app", "templates/index.html"])

        # 3. Single file .gz
        g_art = pk.create_archive_artifact([sample_files[0]], fmt="gz", base_dir=self.tmp_artifacts_dir)
        self.assertEqual(g_art["filename"], "login.app.gz")
        g_path = os.path.join(self.tmp_artifacts_dir, g_art["id"], g_art["filename"])
        with gzip.open(g_path, "rb") as gf:
            self.assertIn("login.app ok", gf.read().decode("utf-8"))

    def test_artifact_download_endpoint_preserves_exact_filename_and_blocks_traversal(self):
        """GET /api/artifacts/<id>/<filename> mengunduh nama persis 'login.app' dan menolak path traversal."""
        test_file = [{"filename": "login.app", "basename": "login.app", "content": "#!/usr/bin/env python3\nprint('ok')\n", "language": "python"}]
        arts = pk.create_file_artifacts(test_file, base_dir=pk.GENERATED_ARTIFACTS_DIR)
        self.assertEqual(len(arts), 1)
        art = arts[0]
        self.assertEqual(art["filename"], "login.app")
        bundle_folder = os.path.join(pk.GENERATED_ARTIFACTS_DIR, art["download_url"].split("/")[3])

        try:
            with self.client.get(art["download_url"]) as resp:
                self.assertEqual(resp.status_code, 200)
                disp = resp.headers.get("Content-Disposition", "")
                self.assertIn("login.app", disp)
                self.assertIn("print('ok')", resp.data.decode("utf-8"))

            with self.client.get(f"/api/artifacts/{art['download_url'].split('/')[3]}/../secret.txt") as bad_resp:
                self.assertEqual(bad_resp.status_code, 404)
        finally:
            shutil.rmtree(bundle_folder, ignore_errors=True)

    def test_stream_emits_antigravity_english_analysis_and_history_zip_packaging(self):
        """Saat diminta 'jadikan zip semua shiro!!', Shiro mengekstrak kode turn sebelumnya, membuat zip nyata, & streaming analisis English."""
        mem = state.init_memory()
        with mem.lock:
            mem.short_term_history.append({
                "role": "assistant",
                "content": (
                    "Ini dia kedua filenya:\n"
                    "### File: `app.py`\n```python\nprint('hello pondok kayu')\n```\n"
                    "### File: `index.html`\n```html\n<h1>Halo</h1>\n```\n"
                ),
            })

        class EnglishThinkLLM:
            model_path = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"
            _shiro_fast_chatml = True

            def n_ctx(self):
                return 700000

            def create_completion(self, prompt, stream=False, **kwargs):
                # Pastikan prompt tidak mengatakan tidak bisa zip dan menyertakan mode analisis English di Extra High
                self.last_prompt = prompt
                def _gen():
                    yield {"choices": [{"text": "<thi"}]}
                    yield {"choices": [{"text": "nk>1. Intent: User wants previous app.py and index.html compressed into a zip archive.\n"}]}
                    yield {"choices": [{"text": "2. Verification: Real zip archive is already generated and attached.</think>\n\n"}]}
                    yield {"choices": [{"text": "Siap Kakak! Arsip zip berisi `app.py` dan `index.html` sudah jadi dan bisa langsung diunduh di bawah ya."}]}
                return _gen()

        fake_llm = EnglishThinkLLM()
        state.llm = fake_llm
        created_bundles = []
        try:
            with patch("shiro.models.get_gpu_layers", return_value=-1), \
                 patch("shiro.models.resolve_lyra_tier", return_value={
                     "id": "extra_high", "label": "ShiroHaru-Lyra Extra High",
                     "tokens": 700000, "max_output": 24576,
                     "thinking_mode": "deep", "max_history_turns": 128, "top_k": 40
                 }):
                events = list(stream_shiro_reply("jadikan zip semua shiro!!", lyra_tier="extra_high"))

            trace_steps = [e["step"] for e in events if e.get("type") == "agent_trace_step"]
            thought_evs = [e["token"] for e in events if e.get("type") == "thought"]
            thought_done_evs = [e for e in events if e.get("type") == "thought_done"]
            token_evs = [e["token"] for e in events if e.get("type") == "token"]
            done_evs = [e for e in events if e.get("type") == "done"]

            self.assertTrue(any("700,000 tokens" in (s.get("feedback") or "") for s in trace_steps))
            self.assertTrue(any("app.py" in (s.get("feedback") or "") or ".zip" in (s.get("feedback") or "").lower() for s in trace_steps))
            full_thought = "".join(thought_evs)
            self.assertIn("User wants previous app.py", full_thought)
            self.assertEqual(len(thought_done_evs), 1)
            # Pastikan isi <think> tidak bocor ke token jawaban akhir
            full_ans = "".join(token_evs)
            self.assertNotIn("User wants previous", full_ans)
            self.assertIn("Siap Kakak!", full_ans)

            self.assertEqual(len(done_evs), 1)
            done = done_evs[0]
            self.assertGreaterEqual(len(done.get("artifacts", [])), 1)
            arch = done["artifacts"][0]
            self.assertEqual(arch["kind"], "archive")
            self.assertTrue(arch["filename"].endswith(".zip"))
            self.assertEqual(sorted(arch["files_included"]), ["app.py", "index.html"])
            created_bundles.append(os.path.join(pk.GENERATED_ARTIFACTS_DIR, arch["id"]))
        finally:
            for b in created_bundles:
                shutil.rmtree(b, ignore_errors=True)

    def test_post_llm_same_turn_login_app_plus_tar_gz_packaging(self):
        """Permintaan dalam 1 giliran ('buatkan login.app lalu kompres tar.gz') mengemas output LLM otomatis dengan nama persis."""
        class SingleTurnCodeLLM:
            model_path = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"
            _shiro_fast_chatml = True

            def n_ctx(self):
                return 500000

            def create_completion(self, prompt, stream=False, **kwargs):
                def _gen():
                    yield {"choices": [{"text": "<think>Analyzing: user wants login.app packaged as tar.gz.</think>\n"}]}
                    yield {"choices": [{"text": "Ini dia berkasnya:\n\n### File: `login.app`\n```python\nprint('Login module')\n```\n"}]}
                return _gen()

        with self.mem.lock:
            self.mem.short_term_history = []
        state.llm = SingleTurnCodeLLM()
        created_bundles = []
        try:
            with patch("shiro.models.get_gpu_layers", return_value=-1):
                events = list(stream_shiro_reply("buatkan login.app lalu kompres tar.gz", lyra_tier="high"))
            done = [e for e in events if e.get("type") == "done"][-1]
            self.assertEqual(len(done["artifacts"]), 1)
            arch = done["artifacts"][0]
            self.assertTrue(arch["filename"].endswith(".tar.gz"))
            self.assertEqual(arch["files_included"], ["login.app"])
            created_bundles.append(os.path.join(pk.GENERATED_ARTIFACTS_DIR, arch["id"]))
            tar_disk = os.path.join(pk.GENERATED_ARTIFACTS_DIR, arch["id"], arch["filename"])
            with tarfile.open(tar_disk, "r:gz") as tf:
                self.assertEqual(tf.getnames(), ["login.app"])
        finally:
            for b in created_bundles:
                shutil.rmtree(b, ignore_errors=True)

    def test_index_html_cache_version_updated(self):
        idx_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "index.html")
        with open(idx_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("script.js?v=3.4.0", html)
        self.assertIn("style.css?v=3.4.0", html)


if __name__ == "__main__":
    unittest.main()
