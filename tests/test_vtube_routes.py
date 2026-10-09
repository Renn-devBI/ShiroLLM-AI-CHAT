import unittest
import json
import os
import tempfile
import shutil
from unittest.mock import MagicMock
import web
from shiro.llm.cleaner import is_japanese_text, clean_vtuber_response

class TestVTuberAndMultiVersionRoutes(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_api_key_file = web.API_KEY_FILE
        self.test_key_file = os.path.join(self.test_dir, "test_api_key.json")
        web.API_KEY_FILE = self.test_key_file
        
        web.app.config['TESTING'] = True
        self.client = web.app.test_client()
        self.api_key = web.get_or_create_api_key(force_new=True)

        self.orig_llm = getattr(web, 'llm', None)
        self.mock_llm = MagicMock()
        web.llm = self.mock_llm

        self.orig_memory = web.memory
        self.test_mem_file = os.path.join(self.test_dir, "test_mem.json")
        self.test_world_file = os.path.join(self.test_dir, "test_world.json")
        web.memory = web.AdvancedMemoryManager(self.test_mem_file, self.test_world_file)

    def tearDown(self):
        web.llm = self.orig_llm
        web.memory = self.orig_memory
        web.API_KEY_FILE = self.orig_api_key_file
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_vtuber_response_guarantees_japanese_and_tag(self):
        """Memastikan filter VTuber selalu menghasilkan tag ekspresi [Tag] dan karakter Jepang"""
        # 1. Output sudah dalam bahasa Jepang tanpa tag: harus otomatis diberi tag
        raw_jp = "シロもレンクさんのこと大好きだよ〜！"
        cleaned1 = clean_vtuber_response(raw_jp, "shiro aku sayang kamu")
        self.assertTrue(cleaned1.startswith("["), "Harus diawali tag ekspresi")
        self.assertTrue(is_japanese_text(cleaned1), "Harus mengandung karakter Jepang")

        # 2. Output bahasa Indonesia: harus diawali [Tag] dan mempertahankan isi dialog cerdas Shiro
        raw_id = "Aduh... Renku bilang apa lagi? Tapi Shiro tahu banget kamu sayang aku!"
        cleaned2 = clean_vtuber_response(raw_id, "shiro kaka sayang kamu")
        self.assertTrue(cleaned2.startswith("["), "Harus diawali tag ekspresi")
        self.assertIn("Shiro", cleaned2, "Respon asli Shiro harus dipertahankan")

        # 3. Output dengan tag di tengah: harus dipindahkan ke awal
        raw_mid = '何言ってるのよ！ふんだ！ [Angry]'
        cleaned3 = clean_vtuber_response(raw_mid, "kamu jelek")
        self.assertTrue(cleaned3.startswith("[Angry]"), "Tag harus berada di awal kalimat")

    def test_routes_models_compatibility(self):
        """Memastikan route GET models bekerja untuk /v1, /v2, /v2/v1, /v3"""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for path in ['/v1/models', '/v2/models', '/v2/v1/models', '/v3/models']:
            resp = self.client.get(path, headers=headers)
            self.assertEqual(resp.status_code, 200, f"Route {path} harus return 200")
            data = resp.get_json()
            self.assertEqual(data.get("object"), "list")
            self.assertGreater(len(data.get("data", [])), 0)

    def test_v2_vtuber_chat_completions(self):
        """Memastikan route /v2/chat/completions memproses payload VTuber dan menghasilkan balasan Jepang ber-tag"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "Qwen2.5-VL-7B",
            "messages": [
                {"role": "system", "content": 'You are "Shiro" (シロ), an AI Waifu Virtual YouTuber... Always respond in native JAPANESE! Example: [Mouth Smile] "はぁ？"'},
                {"role": "user", "content": "shiro kaka sayang kamu"}
            ]
        }
        
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{
                "message": {"content": '[Eye Smile] "ふふっ、レンクさん、シロも大好きだよ〜！💕"'},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35}
        }

        # Test route /v2/chat/completions
        resp_v2 = self.client.post('/v2/chat/completions', headers=headers, json=payload)
        self.assertEqual(resp_v2.status_code, 200)
        data_v2 = resp_v2.get_json()
        reply_v2 = data_v2["choices"][0]["message"]["content"]
        self.assertTrue(reply_v2.startswith("["), "Respons VTuber wajib ber-tag")
        self.assertTrue(is_japanese_text(reply_v2), "Respons VTuber wajib bahasa Jepang")

        # Test route /v2/v1/chat/completions (URL builder dari run.py)
        resp_v2_v1 = self.client.post('/v2/v1/chat/completions', headers=headers, json=payload)
        self.assertEqual(resp_v2_v1.status_code, 200)

    def test_v3_custom_chat_completions(self):
        """Memastikan route /v3/chat/completions menggunakan custom system prompt"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "Qwen3-32B",
            "messages": [
                {"role": "system", "content": "You are a professional Python engineer. Answer in English."},
                {"role": "user", "content": "How do I reverse a string in Python?"}
            ]
        }
        self.mock_llm.create_chat_completion.return_value = {
            "choices": [{
                "message": {"content": "You can reverse a string using slicing: `s[::-1]`."},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35}
        }

        resp_v3 = self.client.post('/v3/chat/completions', headers=headers, json=payload)
        self.assertEqual(resp_v3.status_code, 200)
        data_v3 = resp_v3.get_json()
        reply_v3 = data_v3["choices"][0]["message"]["content"]
        self.assertIn("s[::-1]", reply_v3)
        self.assertEqual(data_v3.get("api_version"), "v3")

    def test_dynamic_models_detection(self):
        """Memastikan endpoint /v1/models dan /v2/models mengembalikan current_model dan list model terdeteksi"""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = self.client.get('/v2/models', headers=headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("current_model", data)
        self.assertIn("data", data)
        models = data["data"]
        self.assertGreater(len(models), 0)
        # Pastikan setiap model memiliki key 'id' dan 'name'
        for m in models:
            self.assertIn("id", m)
            self.assertIn("name", m)

    def test_models_switch_routes(self):
        """Memastikan route /v1/models/switch dan /v2/models/switch merespon dengan benar"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        # Model tidak ada di disk
        resp = self.client.post('/v2/models/switch', headers=headers, json={"model": "NonExistentModel-99B"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

if __name__ == '__main__':
    unittest.main()
