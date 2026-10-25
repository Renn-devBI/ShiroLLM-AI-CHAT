# -*- coding: utf-8 -*-
import os
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from shiro.models import is_vision_model, init_vision_handler
from shiro.agent.moe_router import MoEOrchestrator
from download_model import COLAB_MODELS

class TestQwen38NativeMultimodal(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.model_dir = os.path.join(self.test_dir, "model")
        os.makedirs(self.model_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_is_vision_model_qwen38_with_mmproj(self):
        # Saat mmproj-BF16.gguf ada di folder
        qwen38_path = os.path.join(self.model_dir, "Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-Q4_K_P.gguf")
        mmproj_path = os.path.join(self.model_dir, "mmproj-BF16.gguf")
        
        with open(qwen38_path, "w") as f:
            f.write("mock qwen3.8")
        with open(mmproj_path, "w") as f:
            f.write("mock mmproj")

        self.assertTrue(is_vision_model(qwen38_path))

    def test_is_vision_model_qwen38_by_name(self):
        # Model dengan nama qwen3.8 otomatis dikenali sebagai multimodal vision model
        self.assertTrue(is_vision_model("model/Qwen3.8-27B-Uncensored-Q4_K_M.gguf"))
        self.assertTrue(is_vision_model("model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-Q4_K_P.gguf"))

    def test_moe_should_not_route_when_chat_has_vision(self):
        # Jika model chat memiliki kemampuan vision (seperti Qwen3.8 + mmproj),
        # MoE tidak boleh melakukan route/switch ke model lain
        moe = MoEOrchestrator()
        should = moe.should_route(has_image=True, chat_has_vision=True)
        self.assertFalse(should, "MoE seharusnya tidak melakukan routing jika model chat aktif sudah memiliki vision!")

    def test_download_model_config_has_mmproj(self):
        # Verifikasi bahwa preset 27b di download_model.py sudah memuat extra_file mmproj
        self.assertIn("27b", COLAB_MODELS)
        cfg_27b = COLAB_MODELS["27b"]
        self.assertIsNotNone(cfg_27b.get("extra_file"), "Preset 27b harus memiliki extra_file mmproj!")
        self.assertIn("mmproj", cfg_27b["extra_file"].lower())
        self.assertIn("bf16", cfg_27b["extra_file"].lower())
        self.assertEqual(cfg_27b.get("extra_alias"), "mmproj-BF16.gguf")

if __name__ == '__main__':
    unittest.main()
