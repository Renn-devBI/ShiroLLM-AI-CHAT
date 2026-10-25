# -*- coding: utf-8 -*-
import unittest
import os
from unittest.mock import patch, MagicMock
from shiro.models import (
    read_gguf_metadata,
    sort_models_by_priority,
    load_model_config,
    instantiate_llama_model_with_autodetect,
    detect_chat_format
)

class TestModelAutodetect(unittest.TestCase):
    def test_read_gguf_metadata(self):
        """Memastikan pembacaan header metadata GGUF bekerja akurat"""
        llama_path = "model/Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf"
        if os.path.exists(llama_path):
            meta = read_gguf_metadata(llama_path)
            self.assertEqual(meta.get("general.architecture"), "llama")
            self.assertIn("Llama", meta.get("general.name", ""))

    def test_sort_models_by_priority(self):
        """Memastikan model dengan arsitektur yang didukung diprioritaskan di atas model asing/rusak"""
        models = [
            "model/Qwen3-4B-Q4_K_M.gguf",
            "model/Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf"
        ]
        existing = [m for m in models if os.path.exists(m)]
        if len(existing) == 2:
            sorted_m = sort_models_by_priority(existing)
            # Llama-3.2 (arch: llama) harus diprioritaskan di atas Qwen3 (arch: qwen3 yang belum didukung)
            self.assertEqual(sorted_m[0], "model/Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf")

    def test_load_model_config_autodetect(self):
        """Memastikan load_model_config secara otomatis memilih model valid tanpa terkunci default kaku"""
        cfg = load_model_config()
        self.assertTrue(cfg.get("auto_detect"))
        self.assertTrue(len(cfg.get("available_models", [])) > 0)
        # current_model harus berupa model yang berkasnya benar-benar ada di disk
        cur = cfg.get("current_model")
        self.assertTrue(os.path.exists(cur))
        self.assertIn(cur, cfg.get("available_models"))

    def test_autodetect_fallback_on_failure(self):
        """Memastikan sistem otomatis mencoba model berikutnya jika model awal gagal"""
        # Simulasikan model pertama gagal (misal corrupt/unsupported arch), model kedua berhasil
        dummy_llm = MagicMock()
        with patch("shiro.models.instantiate_llama_model") as mock_inst:
            mock_inst.side_effect = [
                ValueError("Failed to load model from file: corrupt.gguf"),
                (dummy_llm, None)
            ]
            with patch("shiro.models.get_available_gguf_models", return_value=["model/bad.gguf", "model/good.gguf"]):
                with patch("shiro.models.sort_models_by_priority", return_value=["model/bad.gguf", "model/good.gguf"]):
                    with patch("os.path.exists", return_value=True):
                        llm, vision, loaded_path = instantiate_llama_model_with_autodetect(preferred_model_path="model/bad.gguf")
                        self.assertEqual(loaded_path, "model/good.gguf")
                        self.assertEqual(llm, dummy_llm)

if __name__ == '__main__':
    unittest.main()
