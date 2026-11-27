# -*- coding: utf-8 -*-
import io
import os
import sys
import zipfile
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import web
from shiro.server_state import state
from shiro.document.reader import build_multi_document_prompt
from shiro.pipeline.inference import stream_shiro_reply
from shiro.vision.video import (
    is_video_filename,
    extract_video_frames_and_metadata,
    detect_video_generation_request,
    render_video_artifact,
)


class TestMultiFileAndVideo(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()
        self.prev_llm = state.llm
        self.prev_vis = state.vision_chat_handler
        self.mem = state.init_memory()
        self.prev_history = list(self.mem.short_term_history)
        self.tmp_dir = tempfile.mkdtemp(prefix="shiro_mfv_test_")

    def tearDown(self):
        state.llm = self.prev_llm
        state.vision_chat_handler = self.prev_vis
        with self.mem.lock:
            self.mem.short_term_history = list(self.prev_history)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_sample_mp4(self, path: str, n_frames: int = 18, fps: int = 12):
        import cv2
        import numpy as np
        w, h = 160, 120
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        try:
            for i in range(n_frames):
                frame = np.zeros((h, w, 3), dtype=np.uint8)
                frame[:, :, 0] = (i * 12) % 255
                frame[:, :, 2] = 200
                cv2.rectangle(frame, (10 + i * 4, 30), (45 + i * 4, 80), (255, 255, 255), -1)
                writer.write(frame)
        finally:
            writer.release()

    def test_unlimited_simultaneous_multi_file_and_zip_upload(self):
        """POST /api/upload/documents menerima banyak file sekaligus (kode + .app + .zip) tanpa batas 1 file."""
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("src/auth.py", "def check_login(u, p):\n    return u == 'admin'\n")
            zf.writestr("src/routes.js", "export const home = '/dashboard';\n")
        zip_buf.seek(0)

        payload_files = [
            (io.BytesIO(b"print('login app entrypoint')\n"), "login.app"),
            (io.BytesIO(b"from auth import check_login\n"), "app.py"),
            (io.BytesIO(b'{"port": 7474}\n'), "config.json"),
            (io.BytesIO(b"# Readme\nDocs\n"), "README.md"),
            (zip_buf, "bundle.zip"),
        ]
        try:
            with self.client.post(
                "/api/upload/documents",
                data={"files": payload_files},
                content_type="multipart/form-data",
            ) as resp:
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()

            self.assertTrue(data["success"])
            names = [d["filename"] for d in data["documents"]]
            self.assertIn("login.app", names)
            self.assertIn("app.py", names)
            self.assertIn("config.json", names)
            self.assertIn("README.md", names)
            self.assertIn("src/auth.py", names)
            self.assertIn("src/routes.js", names)
            self.assertEqual(len(names), 6)
        finally:
            for fn in ("login.app", "app.py", "config.json", "README.md", "bundle.zip"):
                p = os.path.join("data", "uploads", fn)
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    def test_multi_document_read_all_and_plan_protocol(self):
        """build_multi_document_prompt & stream_shiro_reply memaksa baca semua berkas lalu rancang plan sebelum memperbaiki."""
        docs = [
            {"filename": "login.app", "text": "def auth():\n    return broken_var\n", "file_type": "app"},
            {"filename": "server.py", "text": "from login import auth\nauth()\n", "file_type": "py"},
        ]
        prompt_blk = build_multi_document_prompt(docs, "perbaiki error di kedua file ini!")
        self.assertIn("INVENTARIS 2 BERKAS", prompt_blk)
        self.assertIn("BERKAS 1/2: login.app", prompt_blk)
        self.assertIn("BERKAS 2/2: server.py", prompt_blk)
        self.assertIn("READ ALL FIRST", prompt_blk)
        self.assertIn("ANALYZE & PLAN", prompt_blk)

        class PlanThenFixLLM:
            model_path = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"
            _shiro_fast_chatml = True

            def n_ctx(self):
                return 500000

            def create_completion(self, prompt, stream=False, **kwargs):
                def _gen():
                    yield {"choices": [{"text": "<think>1. Read both login.app and server.py. 2. Root cause: undefined broken_var in login.app. 3. Plan: define default False in auth().</think>\n"}]}
                    yield {"choices": [{"text": "**Rencana Perbaikan:** Definisikan nilai return di `login.app`.\n\n### File: `login.app`\n```python\ndef auth():\n    return True\n```\n"}]}
                return _gen()

        state.llm = PlanThenFixLLM()
        with patch("shiro.models.get_gpu_layers", return_value=-1):
            events = list(stream_shiro_reply("tolong baca semua lalu perbaiki errornya", documents=docs, lyra_tier="high"))

        step_ids = [e["step"]["id"] for e in events if e.get("type") == "agent_trace_step"]
        self.assertIn("read_files", step_ids)
        self.assertIn("plan", step_ids)
        thought_txt = "".join(e["token"] for e in events if e.get("type") == "thought")
        self.assertIn("Read both login.app and server.py", thought_txt)

    def test_video_understanding_extraction_upload_and_qwen38_multimodal_stream(self):
        """Video MP4 diekstrak keyframe kronologisnya dan dikirim ke Qwen3.8-27B bersamaan dengan banyak file."""
        self.assertTrue(is_video_filename("demo_clip.mp4"))
        self.assertTrue(is_video_filename("rekaman.webm"))
        self.assertFalse(is_video_filename("login.app"))

        vid_path = os.path.join(self.tmp_dir, "demo_clip.mp4")
        self._create_sample_mp4(vid_path, n_frames=16, fps=10)
        vid_meta = extract_video_frames_and_metadata(vid_path, filename="demo_clip.mp4", max_frames=6)
        self.assertTrue(vid_meta["success"])
        self.assertEqual(vid_meta["sampled_frame_count"], 6)
        self.assertEqual(len(vid_meta["frames"]), 6)
        self.assertEqual(vid_meta["resolution"], "160x120")
        self.assertGreater(vid_meta["duration_sec"], 1.0)

        # Test upload endpoint bersamaan (1 video + 2 file kode sekaligus)
        with open(vid_path, "rb") as vf:
            vid_bytes = vf.read()
        uploaded_vid_disk = os.path.join("data", "uploads", "videos", "demo_clip.mp4")
        uploaded_py_disk = os.path.join("data", "uploads", "app.py")
        try:
            with self.client.post(
                "/api/upload/documents",
                data={
                    "files": [
                        (io.BytesIO(vid_bytes), "demo_clip.mp4"),
                        (io.BytesIO(b"print('hi')\n"), "app.py"),
                    ]
                },
                content_type="multipart/form-data",
            ) as resp:
                self.assertEqual(resp.status_code, 200)
                up_data = resp.get_json()
            self.assertEqual(len(up_data["videos"]), 1)
            self.assertEqual(len(up_data["documents"]), 1)
            self.assertEqual(up_data["videos"][0]["filename"], "demo_clip.mp4")
            # Unggahan video tidak lagi mengekstrak frame base64 saat upload agar cepat dan ringan
            self.assertFalse(up_data["videos"][0].get("frames"))
            self.assertEqual(up_data["videos"][0]["resolution"], "160x120")
            self.assertGreater(up_data["videos"][0]["duration_sec"], 1.0)
            vid_url = up_data["videos"][0]["url"]
            self.assertTrue(vid_url.startswith("/api/videos/"))

            # Video harus dapat diputar langsung via HTTP GET dengan Content-Type video/mp4
            with self.client.get(vid_url) as vid_resp:
                self.assertEqual(vid_resp.status_code, 200)
                self.assertIn("video/mp4", vid_resp.content_type)
                self.assertEqual(vid_resp.data, vid_bytes)

            # Verifikasi stream_shiro_reply melakukan lazy extraction dari disk & mengirim bersamaan file app.py ke vision chat handler
            captured_msgs = []

            class MockVisionQwen38:
                model_path = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"
                chat_handler = MagicMock()

                def n_ctx(self):
                    return 500000

                def create_chat_completion(self, messages, stream=False, **kwargs):
                    captured_msgs.append(messages)
                    def _gen():
                        yield {"choices": [{"delta": {"content": "Shiro sudah menonton video demo_clip.mp4 dan membaca app.py."}}]}
                    return _gen()

            state.llm = MockVisionQwen38()
            state.vision_chat_handler = state.llm.chat_handler
            with patch("shiro.models.get_gpu_layers", return_value=-1), \
                 patch.dict(os.environ, {"SHIRO_VIDEO_MAX_FRAMES": "6"}):
                events = list(stream_shiro_reply(
                    "analisa video dan file app.py ini bersamaan",
                    documents=[{"filename": "app.py", "text": "print('hi')\n", "file_type": "py"}],
                    videos=[up_data["videos"][0]],
                    lyra_tier="high",
                ))

            step_ids = [e["step"]["id"] for e in events if e.get("type") == "agent_trace_step"]
            self.assertIn("read_video", step_ids)
            self.assertIn("read_files", step_ids)
            self.assertEqual(len(captured_msgs), 1)
            last_user = captured_msgs[0][-1]
            self.assertIsInstance(last_user["content"], list)
            img_parts = [p for p in last_user["content"] if isinstance(p, dict) and p.get("type") == "image_url"]
            self.assertEqual(len(img_parts), 6)
            sys_txt = captured_msgs[0][0]["content"]
            self.assertIn("demo_clip.mp4", sys_txt)
            self.assertIn("app.py", sys_txt)
        finally:
            for p in (uploaded_vid_disk, uploaded_py_disk):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    def test_programmatic_video_generation_and_intent_guard(self):
        """detect_video_generation_request dan render_video_artifact membuat video MP4 nyata."""
        self.assertIsNone(detect_video_generation_request("tonton dan analisa video demo ini"))
        req = detect_video_generation_request("buatkan video animasi promo_shiro.mp4 durasi 3 detik")
        self.assertIsNotNone(req)
        self.assertEqual(req["output_name"], "promo_shiro.mp4")
        self.assertEqual(req["duration_sec"], 3.0)

        art = render_video_artifact(
            title="Shiro AI Demo",
            scenes=["Halo Kakak", "Video Render OK"],
            output_name="promo_shiro.mp4",
            duration_sec=2.0,
            fps=10,
            size=(320, 180),
            base_dir=self.tmp_dir,
        )
        self.assertEqual(art["kind"], "video")
        self.assertEqual(art["filename"], "promo_shiro.mp4")
        vid_disk = os.path.join(self.tmp_dir, art["id"], "promo_shiro.mp4")
        self.assertTrue(os.path.exists(vid_disk))
        self.assertGreater(os.path.getsize(vid_disk), 1000)


if __name__ == "__main__":
    unittest.main()
