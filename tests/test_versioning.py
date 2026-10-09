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
        self.assertEqual(ver, 1)
        name = get_next_model_name(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(name, "ShiroAI-LLM-V1")

    def test_version_increments_to_v2(self):
        # Buat file tiruan ShiroAI-LLM-V1.gguf di folder model
        v1_file = os.path.join(self.model_dir, "ShiroAI-LLM-V1.gguf")
        with open(v1_file, "w") as f:
            f.write("mock model v1")

        versions = get_existing_trained_versions(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(versions, [1])

        ver = get_next_training_version(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(ver, 2)
        name = get_next_model_name(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(name, "ShiroAI-LLM-V2")

    def test_version_increments_to_v3(self):
        # Buat folder ShiroAI-LLM-V1 dan ShiroAI-LLM-V2 di lora
        os.makedirs(os.path.join(self.lora_dir, "ShiroAI-LLM-V1"), exist_ok=True)
        os.makedirs(os.path.join(self.lora_dir, "ShiroAI-LLM-V2"), exist_ok=True)

        versions = get_existing_trained_versions(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(versions, [1, 2])

        ver = get_next_training_version(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(ver, 3)
        name = get_next_model_name(search_dirs=[self.model_dir, self.lora_dir])
        self.assertEqual(name, "ShiroAI-LLM-V3")

if __name__ == "__main__":
    unittest.main()
