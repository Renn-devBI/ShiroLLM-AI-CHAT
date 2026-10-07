import unittest
import os
import shutil
import tempfile
import json
from shiro.memory.manager import AdvancedMemoryManager
from web import app, _format_message_for_api

class TestFilePreview(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mem_file = os.path.join(self.test_dir, "test_ingatan.json")
        self.world_file = os.path.join(self.test_dir, "test_world.json")
        self.manager = AdvancedMemoryManager(memory_file=self.mem_file, world_file=self.world_file)
        self.client = app.test_client()

        # Buat temporary dummy upload file
        self.uploads_dir = os.path.join("data", "uploads")
        os.makedirs(self.uploads_dir, exist_ok=True)
        self.dummy_doc_name = "test_laporan_unit.txt"
        self.dummy_doc_path = os.path.join(self.uploads_dir, self.dummy_doc_name)
        with open(self.dummy_doc_path, "w", encoding="utf-8") as f:
            f.write("Ini adalah berkas laporan uji unit dokumen Shiro.")

        # Buat temporary dummy vision image
        self.vision_dir = os.path.join("training_data", "vision", "images")
        os.makedirs(self.vision_dir, exist_ok=True)
        self.dummy_img_name = "test_img_unit.jpg"
        self.dummy_img_path = os.path.join(self.vision_dir, self.dummy_img_name)
        with open(self.dummy_img_path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        if os.path.exists(self.dummy_doc_path):
            os.remove(self.dummy_doc_path)
        if os.path.exists(self.dummy_img_path):
            os.remove(self.dummy_img_path)

    def test_add_message_with_document_metadata(self):
        self.manager.add_message(
            role="user",
            content="Tolong cek dokumen ini",
            image_path="/images/test.jpg",
            document_name="skripsi.pdf",
            document_url="/api/files/skripsi.pdf",
            document_type="pdf",
            document_text="Isi abstrak skripsi"
        )
        msg = self.manager.short_term_history[-1]
        self.assertEqual(msg["document_name"], "skripsi.pdf")
        self.assertEqual(msg["document_url"], "/api/files/skripsi.pdf")
        self.assertEqual(msg["document_type"], "pdf")
        self.assertEqual(msg["image"], "/images/test.jpg")

    def test_format_message_for_api(self):
        raw_msg = {
            "role": "user",
            "content": "Halo",
            "image": "images/screenshot.jpg",
            "document_name": "data.csv"
        }
        formatted = _format_message_for_api(raw_msg)
        self.assertEqual(formatted["image"], "/images/screenshot.jpg")
        self.assertEqual(formatted["document_url"], "/api/files/data.csv")

    def test_api_files_route(self):
        res = self.client.get(f"/api/files/{self.dummy_doc_name}")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"laporan uji unit", res.data)

    def test_api_document_preview_route(self):
        res = self.client.get(f"/api/document/preview?filename={self.dummy_doc_name}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("laporan uji unit", data.get("text", ""))

    def test_api_images_route(self):
        res = self.client.get(f"/images/{self.dummy_img_name}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data[:2], b"\xff\xd8")

if __name__ == "__main__":
    unittest.main()
