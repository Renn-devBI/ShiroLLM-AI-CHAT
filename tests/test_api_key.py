import unittest
import json
import os
import tempfile
import shutil
import web

class TestApiKeyManagement(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_api_key_file = web.API_KEY_FILE
        self.test_key_file = os.path.join(self.test_dir, "test_api_key.json")
        web.API_KEY_FILE = self.test_key_file
        
        # Test client
        web.app.config['TESTING'] = True
        self.client = web.app.test_client()

    def tearDown(self):
        web.API_KEY_FILE = self.orig_api_key_file
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_dynamic_key_generation_and_uniqueness(self):
        """Pastikan key yang di-generate selalu dinamis, berawalan shiro-sk-, dan berbeda"""
        key1 = web.get_or_create_api_key(force_new=True)
        self.assertTrue(key1.startswith("shiro-sk-"))
        self.assertGreater(len(key1), 16)

        key2 = web.get_or_create_api_key(force_new=True)
        self.assertTrue(key2.startswith("shiro-sk-"))
        self.assertNotEqual(key1, key2, "API Key baru harus dinamis dan tidak sama dengan sebelumnya")

        # Key aktif harus key2
        self.assertEqual(web.get_active_api_key(), key2)

        # Keduanya harus tetap valid di get_all_valid_api_keys()
        all_valid = web.get_all_valid_api_keys()
        self.assertIn(key1, all_valid)
        self.assertIn(key2, all_valid)

    def test_api_key_routes(self):
        """Test GET /api/key dan POST /api/key/regenerate"""
        # 1. Regenerate
        resp_regen = self.client.post('/api/key/regenerate')
        self.assertEqual(resp_regen.status_code, 200)
        data_regen = resp_regen.get_json()
        self.assertTrue(data_regen.get("success"))
        new_k = data_regen.get("api_key")
        self.assertTrue(new_k.startswith("shiro-sk-"))

        # 2. Get active key
        resp_get = self.client.get('/api/key')
        self.assertEqual(resp_get.status_code, 200)
        data_get = resp_get.get_json()
        self.assertEqual(data_get.get("api_key"), new_k)

    def test_api_key_verification_auth_headers(self):
        """Test verifikasi header Bearer dan X-API-Key"""
        k1 = web.get_or_create_api_key(force_new=True)
        k2 = web.get_or_create_api_key(force_new=True)

        with web.app.test_request_context(headers={"Authorization": f"Bearer {k1}"}):
            self.assertTrue(web.verify_api_key(allow_web_ui=False))

        with web.app.test_request_context(headers={"Authorization": f"Bearer {k2}"}):
            self.assertTrue(web.verify_api_key(allow_web_ui=False))

        with web.app.test_request_context(headers={"X-API-Key": k1}):
            self.assertTrue(web.verify_api_key(allow_web_ui=False))

        with web.app.test_request_context(headers={"Authorization": "Bearer invalid-key"}):
            self.assertFalse(web.verify_api_key(allow_web_ui=False))

if __name__ == '__main__':
    unittest.main()
