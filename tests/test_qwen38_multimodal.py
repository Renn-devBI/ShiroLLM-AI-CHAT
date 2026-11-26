# -*- coding: utf-8 -*-
import os
import sys
import types
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from shiro.models import (
    is_vision_model,
    init_vision_handler,
    is_qwen38_27b_uncensored,
    build_qwen38_500k_llama_kwargs,
    instantiate_llama_model,
    QWEN38_27B_NATIVE_CTX,
    QWEN38_27B_EXTENDED_CTX
)
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

    def test_is_qwen38_27b_uncensored_strict_matching(self):
        """Pastikan deteksi 500K hanya cocok secara ketat untuk Qwen3.8-27B-Uncensored"""
        self.assertTrue(is_qwen38_27b_uncensored("model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"))
        self.assertTrue(is_qwen38_27b_uncensored("model/Qwen3.8-27B-Uncensored-Q4_K_M.gguf"))
        self.assertTrue(is_qwen38_27b_uncensored("model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-IQ4_XS.gguf"))

        # Model lain TIDAK boleh dianggap Qwen3.8-27B-Uncensored
        self.assertFalse(is_qwen38_27b_uncensored("model/Qwen3-32B-Q4_K_M.gguf"))
        self.assertFalse(is_qwen38_27b_uncensored("model/Qwen3.8-27B-Instruct-Q4_K_M.gguf"))
        self.assertFalse(is_qwen38_27b_uncensored("model/Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"))
        self.assertFalse(is_qwen38_27b_uncensored("model/Qwen3-4B-Q4_K_M.gguf"))
        self.assertFalse(is_qwen38_27b_uncensored("model/Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf"))
        self.assertFalse(is_qwen38_27b_uncensored("model/Lumimaid-v0.2-8B-Q5_K_M-imat.gguf"))

    def test_qwen38_500k_yarn_kwargs_only_for_qwen38_27b_uncensored(self):
        """Pastikan YaRN RoPE scaling + FlashAttn + KV Cache hanya dibuat untuk Qwen3.8-27B-Uncensored"""
        fake_mod = types.SimpleNamespace(
            LLAMA_ROPE_SCALING_TYPE_YARN=2,
            GGML_TYPE_Q8_0=8,
            GGML_TYPE_Q4_0=2
        )
        kw = build_qwen38_500k_llama_kwargs(
            "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf",
            500000,
            llama_cpp_mod=fake_mod
        )
        self.assertEqual(kw["rope_scaling_type"], 2)
        self.assertEqual(kw["yarn_orig_ctx"], QWEN38_27B_NATIVE_CTX)
        self.assertAlmostEqual(kw["rope_freq_scale"], round(262144 / 500000.0, 6), places=6)
        self.assertTrue(kw["flash_attn"])
        self.assertIn("type_k", kw)
        self.assertIn("type_v", kw)

        # Model lain harus menerima dict kosong {}
        self.assertEqual(build_qwen38_500k_llama_kwargs("model/Qwen3-32B-Q4_K_M.gguf", 32768, llama_cpp_mod=fake_mod), {})
        self.assertEqual(build_qwen38_500k_llama_kwargs("model/Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf", 8192, llama_cpp_mod=fake_mod), {})

    def test_instantiate_llama_model_500k_only_for_qwen38_uncensored(self):
        """Pastikan instantiate_llama_model memberi n_ctx=500000 + YaRN hanya untuk Qwen3.8-27B-Uncensored"""
        calls = []

        def fake_llama(**kwargs):
            calls.append(kwargs)
            m = MagicMock()
            m.n_ctx = lambda: kwargs["n_ctx"]
            return m

        fake_mod = types.ModuleType("llama_cpp")
        fake_mod.Llama = fake_llama
        fake_mod.LLAMA_ROPE_SCALING_TYPE_YARN = 2
        fake_mod.GGML_TYPE_Q8_0 = 8
        fake_mod.GGML_TYPE_Q4_0 = 2

        with patch.dict(sys.modules, {"llama_cpp": fake_mod}), \
             patch.dict(os.environ, {"SHIRO_CONTEXT_SIZE": "32768"}), \
             patch("shiro.models.init_vision_handler", return_value=None), \
             patch("shiro.models.find_active_lora_path", return_value=None), \
             patch("shiro.models.get_gpu_layers", return_value=-1):
            # 1. Qwen3.8-27B-Uncensored -> wajib 500000 + YaRN walaupun SHIRO_CONTEXT_SIZE=32768
            instantiate_llama_model("model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["n_ctx"], QWEN38_27B_EXTENDED_CTX)
            self.assertEqual(calls[0]["rope_scaling_type"], 2)
            self.assertEqual(calls[0]["yarn_orig_ctx"], 262144)
            self.assertAlmostEqual(calls[0]["rope_freq_scale"], 0.524288, places=6)
            self.assertTrue(calls[0]["flash_attn"])

            # 2. Model lain (mis. Qwen3-32B) tetap 32768 tanpa YaRN
            instantiate_llama_model("model/Qwen3-32B-Q4_K_M.gguf")
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[1]["n_ctx"], 32768)
            self.assertNotIn("rope_scaling_type", calls[1])
            self.assertNotIn("yarn_orig_ctx", calls[1])

    def test_instantiate_llama_model_qwen38_oom_fallback_ladder(self):
        """Jika GPU kehabisan VRAM pada 500K, model Qwen3.8-27B-Uncensored fallback bertahap ke 262K tanpa YaRN"""
        attempted_ctx = []

        def fake_llama_oom(**kwargs):
            attempted_ctx.append((kwargs["n_ctx"], "rope_scaling_type" in kwargs))
            if kwargs["n_ctx"] > 262144:
                raise RuntimeError("CUDA out of memory")
            m = MagicMock()
            m.n_ctx = lambda: kwargs["n_ctx"]
            return m

        fake_mod = types.ModuleType("llama_cpp")
        fake_mod.Llama = fake_llama_oom
        fake_mod.LLAMA_ROPE_SCALING_TYPE_YARN = 2
        fake_mod.GGML_TYPE_Q8_0 = 8
        fake_mod.GGML_TYPE_Q4_0 = 2

        with patch.dict(sys.modules, {"llama_cpp": fake_mod}), \
             patch("shiro.models.init_vision_handler", return_value=None), \
             patch("shiro.models.find_active_lora_path", return_value=None), \
             patch("shiro.models.get_gpu_layers", return_value=-1), \
             patch("shiro.models._get_gpu_vram_gb", return_value=40.0):
            llm, _ = instantiate_llama_model("model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf")
            self.assertEqual(llm.n_ctx(), 262144)
            # Di A100 40GB, sistem mencoba 500K Q8_0 dulu, lalu 500K Q4_0, lalu step-down ke 262K tanpa YaRN
            self.assertEqual(attempted_ctx, [(500000, True), (500000, True), (262144, False)])

        attempted_ctx_16g = []
        def fake_llama_oom_16g(**kwargs):
            attempted_ctx_16g.append((kwargs["n_ctx"], "rope_scaling_type" in kwargs))
            if kwargs["n_ctx"] > 262144:
                raise RuntimeError("CUDA out of memory")
            m = MagicMock()
            m.n_ctx = lambda: kwargs["n_ctx"]
            return m

        fake_mod.Llama = fake_llama_oom_16g
        with patch.dict(sys.modules, {"llama_cpp": fake_mod}), \
             patch("shiro.models.init_vision_handler", return_value=None), \
             patch("shiro.models.find_active_lora_path", return_value=None), \
             patch("shiro.models.get_gpu_layers", return_value=-1), \
             patch("shiro.models._get_gpu_vram_gb", return_value=16.0):
            llm_16g, _ = instantiate_llama_model("model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf")
            self.assertEqual(llm_16g.n_ctx(), 262144)
            self.assertEqual(attempted_ctx_16g, [(500000, True), (262144, False)])

if __name__ == '__main__':
    unittest.main()
