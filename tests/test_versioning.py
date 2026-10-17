# -*- coding: utf-8 -*-
import os
import unittest
import tempfile
import shutil
from shiro.training.versioning import (
    get_existing_trained_versions,
    get_next_training_version,
    get_next_model_name
)

class TestModelVersioning(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.model_dir = os.path.join(self.test_dir, "model")
        self.lora_dir = os.path.join(self.test_dir, "lora")
        os.makedirs(self.model_dir, exist_ok=True)
        os.makedirs(self.lora_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_version_initial_v1(self):
        # Saat belum ada model apa pun
        ver = get_next_training_version(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(ver, "1.0")
        name = get_next_model_name(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(name, "ShiroHaru-1.0-Agent")

    def test_version_increments_to_v2(self):
        # Buat file tiruan ShiroHaru-1.0-Agent.gguf di folder model
        v1_file = os.path.join(self.model_dir, "ShiroHaru-1.0-Agent.gguf")
        with open(v1_file, "w") as f:
            f.write("mock model v1")

        versions = get_existing_trained_versions(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(versions, [1.0])

        ver = get_next_training_version(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(ver, "2.0")
        name = get_next_model_name(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(name, "ShiroHaru-2.0-Agent")

    def test_version_increments_to_v3(self):
        # Buat folder ShiroHaru-1.0-Agent dan ShiroHaru-2.0-Agent di lora
        os.makedirs(os.path.join(self.lora_dir, "ShiroHaru-1.0-Agent"), exist_ok=True)
        os.makedirs(os.path.join(self.lora_dir, "ShiroHaru-2.0-Agent"), exist_ok=True)

        versions = get_existing_trained_versions(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(versions, [1.0, 2.0])

        ver = get_next_training_version(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(ver, "3.0")
        name = get_next_model_name(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(name, "ShiroHaru-3.0-Agent")

    def test_legacy_model_backward_compatibility(self):
        # Uji kompatibilitas jika ada model lama ShiroAI-LLM-V1
        v1_legacy = os.path.join(self.model_dir, "ShiroAI-LLM-V1.gguf")
        with open(v1_legacy, "w") as f:
            f.write("mock legacy model v1")

        versions = get_existing_trained_versions(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(versions, [1.0])

        ver = get_next_training_version(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(ver, "2.0")
        name = get_next_model_name(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(name, "ShiroHaru-2.0-Agent")

if __name__ == "__main__":
    unittest.main()
