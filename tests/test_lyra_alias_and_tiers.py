# -*- coding: utf-8 -*-
"""
Tests for ShiroHaru-Lyra-Agent UI/API Aliasing and 5-Tier Context Engine
(Low 190K / Medium 262K / High 500K / Extra High 700K / Ultra High 1M).
"""

import json
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import shiro.models as sm
from shiro.server_state import state
import web


LYRA_REAL_PATH = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"


class TestLyraAliasAndTiers(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_model_cfg = sm.MODEL_CONFIG_FILE
        self.test_model_cfg = os.path.join(self.test_dir, "model_config.json")
        sm.MODEL_CONFIG_FILE = self.test_model_cfg

        self.orig_llm = state.llm
        self.orig_vis = state.vision_chat_handler
        web.app.config["TESTING"] = True
        self.client = web.app.test_client()

    def tearDown(self):
        sm.MODEL_CONFIG_FILE = self.orig_model_cfg
        state.llm = self.orig_llm
        state.vision_chat_handler = self.orig_vis
        os.environ.pop("SHIRO_QWEN38_27B_CONTEXT_SIZE", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_display_name_masking_strictly_only_for_lyra(self):
        """Nama tampilan ShiroHaru-Lyra-Agent hanya untuk Qwen3.8-27B-Uncensored, model lain tetap utuh."""
        self.assertEqual(sm.get_model_display_name(LYRA_REAL_PATH), "ShiroHaru-Lyra-Agent")
        self.assertEqual(
            sm.get_model_display_name("model/Qwen3.8-27B-Uncensored-Q4_K_M.gguf"),
            "ShiroHaru-Lyra-Agent",
        )
        # Model lain TIDAK boleh berubah namanya
        self.assertEqual(sm.get_model_display_name("model/Qwen3-32B-Q4_K_M.gguf"), "Qwen3-32B-Q4_K_M")
        self.assertEqual(sm.get_model_display_name("model/Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"), "Qwen2.5-VL-7B-Instruct-Q4_K_M")
        self.assertEqual(sm.get_model_display_name("model/Qwen3-4B-Q4_K_M.gguf"), "Qwen3-4B-Q4_K_M")
        self.assertEqual(sm.get_model_display_name("model/Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf"), "Llama-3.2-3B-Instruct-uncensored-Q6_K")

    def test_load_model_config_overrides_stale_qwen38_cache(self):
        """load_model_config menimpa cache nama Qwen3.8-27B lama menjadi ShiroHaru-Lyra-Agent."""
        other_path = "model/Qwen3-4B-Q4_K_M.gguf"
        with open(self.test_model_cfg, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "current_model": LYRA_REAL_PATH,
                    "available_models": [LYRA_REAL_PATH, other_path],
                    "model_info": {
                        LYRA_REAL_PATH: {"name": "Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P", "size": "~16.8 GB"},
                        other_path: {"name": "Qwen3-4B-Q4_K_M", "size": "~2.5 GB"},
                    },
                },
                f,
            )

        with patch("shiro.models.get_available_gguf_models", return_value=[LYRA_REAL_PATH, other_path]), \
             patch("shiro.models.os.path.exists", return_value=True), \
             patch("shiro.models.os.path.getsize", return_value=16 * 1024 * 1024 * 1024):
            cfg = sm.load_model_config()

        self.assertEqual(cfg["model_info"][LYRA_REAL_PATH]["name"], "ShiroHaru-Lyra-Agent")
        self.assertTrue(cfg["model_info"][LYRA_REAL_PATH].get("is_lyra"))
        self.assertEqual(cfg["model_info"][other_path]["name"], "Qwen3-4B-Q4_K_M")
        self.assertEqual(cfg["lyra_tier"], "high")

    def test_all_five_tiers_instantiate_llama_accurately(self):
        """Semua 5 tier (190K / 262K / 500K / 700K / 1M) mengatur n_ctx, YaRN, FlashAttn, & KV cache secara tepat."""
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

        expected = [
            ("low", 190000, False, 8),       # native <= 262K, VRAM >= 70 -> q8_0
            ("medium", 262144, False, 8),    # native 262K, no YaRN
            ("high", 500000, True, 8),       # YaRN, VRAM >= 70 -> q8_0
            ("extra_high", 700000, True, 2), # YaRN + >500K -> q4_0
            ("ultra_high", 1000000, True, 2) # YaRN + 1M -> q4_0
        ]

        with patch.dict(sys.modules, {"llama_cpp": fake_mod}), \
             patch("shiro.models.init_vision_handler", return_value=None), \
             patch("shiro.models.find_active_lora_path", return_value=None), \
             patch("shiro.models.get_gpu_layers", return_value=-1), \
             patch("shiro.models._get_gpu_vram_gb", return_value=80.0):
            for tier_id, expected_ctx, expect_yarn, expected_kv in expected:
                tier_tokens = sm.resolve_lyra_tier(tier_id)["tokens"]
                self.assertEqual(tier_tokens, expected_ctx)
                llm, _ = sm.instantiate_llama_model(LYRA_REAL_PATH, target_ctx_override=tier_tokens)
                kw = calls[-1]
                self.assertEqual(llm.n_ctx(), expected_ctx)
                self.assertEqual(kw["n_ctx"], expected_ctx)
                self.assertTrue(kw["flash_attn"])
                self.assertEqual(kw["type_k"], expected_kv)
                self.assertEqual(kw["type_v"], expected_kv)
                if expect_yarn:
                    self.assertEqual(kw["rope_scaling_type"], 2)
                    self.assertEqual(kw["yarn_orig_ctx"], 262144)
                    self.assertAlmostEqual(kw["rope_freq_scale"], round(262144 / float(expected_ctx), 6), places=6)
                else:
                    self.assertNotIn("rope_scaling_type", kw)

    def test_oom_fallback_ladder_from_1m(self):
        """Jika 1M & 700K kehabisan VRAM, fallback bertahap ke 500K berhasil tanpa crash."""
        attempted = []

        def fake_llama_oom(**kwargs):
            attempted.append(kwargs["n_ctx"])
            if kwargs["n_ctx"] > 500000:
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
             patch("shiro.models._get_gpu_vram_gb", return_value=80.0):
            llm, _ = sm.instantiate_llama_model(LYRA_REAL_PATH, target_ctx_override=1000000)
            self.assertEqual(llm.n_ctx(), 500000)
            self.assertEqual(attempted, [1000000, 700000, 500000])

    def test_api_models_and_context_tier_endpoint(self):
        """GET /api/models & POST /api/models/context-tier bekerja end-to-end dengan aman."""
        fake_cur = MagicMock()
        fake_cur.model_path = LYRA_REAL_PATH
        fake_cur.n_ctx = lambda: 500000
        state.llm = fake_cur

        fake_cfg = {
            "current_model": LYRA_REAL_PATH,
            "auto_detect": True,
            "available_models": [LYRA_REAL_PATH, "model/Qwen3-4B-Q4_K_M.gguf"],
            "model_info": {
                LYRA_REAL_PATH: {"name": "ShiroHaru-Lyra-Agent", "size": "~16.8 GB", "is_lyra": True},
                "model/Qwen3-4B-Q4_K_M.gguf": {"name": "Qwen3-4B-Q4_K_M", "size": "~2.5 GB"},
            },
            "lyra_tier": "high",
        }

        with patch("shiro.routes.admin.load_model_config", return_value=fake_cfg), \
             patch("shiro.routes.admin.get_saved_lyra_tier", return_value="high"):
            resp_get = self.client.get("/api/models")
            self.assertEqual(resp_get.status_code, 200)
            g = resp_get.get_json()
            self.assertEqual(g["current_model_display_name"], "ShiroHaru-Lyra-Agent")
            self.assertTrue(g["is_lyra_active"])
            self.assertEqual(g["lyra_tier"], "high")
            self.assertEqual([t["label"] for t in g["lyra_tiers"]], [
                "ShiroHaru-Lyra Low",
                "ShiroHaru-Lyra Medium",
                "ShiroHaru-Lyra High",
                "ShiroHaru-Lyra Extra High",
                "ShiroHaru-Lyra Ultra High",
            ])

        # Reload tier ke ultra_high di GPU
        fake_1m = MagicMock()
        fake_1m.model_path = LYRA_REAL_PATH
        fake_1m.n_ctx = lambda: 1000000

        with patch("shiro.routes.admin.load_model_config", return_value=fake_cfg), \
             patch("shiro.routes.admin.save_lyra_tier") as mock_save, \
             patch("shiro.routes.admin.get_gpu_layers", return_value=-1), \
             patch("shiro.routes.admin.instantiate_llama_model", return_value=(fake_1m, None)) as mock_inst:
            resp_post = self.client.post("/api/models/context-tier", json={"tier": "ultra_high"})
            self.assertEqual(resp_post.status_code, 200)
            p = resp_post.get_json()
            self.assertTrue(p["success"])
            self.assertEqual(p["lyra_tier"], "ultra_high")
            self.assertEqual(p["active_context_window"], 1000000)
            self.assertTrue(p["reloaded"])
            self.assertFalse(p["cpu_capped"])
            mock_save.assert_called_once_with("ultra_high")
            mock_inst.assert_called_once_with(LYRA_REAL_PATH, target_ctx_override=1000000)

        # Skip reload jika sudah aktif di target context
        with patch("shiro.routes.admin.load_model_config", return_value=fake_cfg), \
             patch("shiro.routes.admin.save_lyra_tier"), \
             patch("shiro.routes.admin.get_gpu_layers", return_value=-1), \
             patch("shiro.routes.admin.instantiate_llama_model") as mock_inst_skip:
            resp_same = self.client.post("/api/models/context-tier", json={"tier": "ultra_high"})
            self.assertEqual(resp_same.status_code, 200)
            self.assertFalse(resp_same.get_json()["reloaded"])
            mock_inst_skip.assert_not_called()

        # Mode CPU tidak boleh crash / memaksa alokasi 1M
        with patch("shiro.routes.admin.load_model_config", return_value=fake_cfg), \
             patch("shiro.routes.admin.save_lyra_tier"), \
             patch("shiro.routes.admin.get_gpu_layers", return_value=0):
            resp_cpu = self.client.post("/api/models/context-tier", json={"tier": "low"})
            self.assertEqual(resp_cpu.status_code, 200)
            self.assertTrue(resp_cpu.get_json()["cpu_capped"])

        # Invalid tier -> 400
        resp_bad_tier = self.client.post("/api/models/context-tier", json={"tier": "super_mega"})
        self.assertEqual(resp_bad_tier.status_code, 400)

        # Model non-Lyra -> 400
        other_llm = MagicMock()
        other_llm.model_path = "model/Qwen3-4B-Q4_K_M.gguf"
        state.llm = other_llm
        resp_non_lyra = self.client.post("/api/models/context-tier", json={"tier": "high"})
        self.assertEqual(resp_non_lyra.status_code, 400)

    def test_index_html_composer_picker_order_and_no_token_text(self):
        """UI composer memiliki #lyra-tier-picker tepat sebelum #send-btn, berurutan, dan TANPA teks (190k tokens) di submenu."""
        idx_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "index.html")
        with open(idx_path, "r", encoding="utf-8") as f:
            html = f.read()

        picker_pos = html.find('id="lyra-tier-picker"')
        send_pos = html.find('id="send-btn"')
        self.assertGreater(picker_pos, 0)
        self.assertGreater(send_pos, picker_pos, "#lyra-tier-picker harus berada sebelum #send-btn")

        m_menu = re.search(r'<div id="lyra-tier-menu"[\s\S]*?</div>\s*</div>', html)
        self.assertIsNotNone(m_menu, "#lyra-tier-menu tidak ditemukan")
        menu_html = m_menu.group(0)

        labels = re.findall(r'<span class="lyra-opt-label">([^<]+)</span>', menu_html)
        self.assertEqual(labels, [
            "ShiroHaru-Lyra Low",
            "ShiroHaru-Lyra Medium",
            "ShiroHaru-Lyra High",
            "ShiroHaru-Lyra Extra High",
            "ShiroHaru-Lyra Ultra High",
        ])

        lower_menu = menu_html.lower()
        for forbidden in ("190k", "262", "500k", "700k", "1m", "tokens", "toknes", "("):
            self.assertNotIn(forbidden, lower_menu, f"Submenu tidak boleh mengandung '{forbidden}'")

    def test_tiers_have_distinct_speed_and_output_profiles(self):
        """Setiap tier harus punya kapasitas max_output dan thinking_mode yang benar-benar berbeda."""
        expected_profiles = [
            ("low", 2048, "off", 16, 20),
            ("medium", 4096, "light", 32, 30),
            ("high", 16384, "standard", 64, 40),
            ("extra_high", 24576, "deep", 128, 40),
            ("ultra_high", 32768, "ultra", None, 50),
        ]
        for tier_id, max_out, think_mode, max_hist, top_k in expected_profiles:
            t = sm.resolve_lyra_tier(tier_id)
            self.assertEqual(t["max_output"], max_out)
            self.assertEqual(t["thinking_mode"], think_mode)
            self.assertEqual(t["max_history_turns"], max_hist)
            self.assertEqual(t["top_k"], top_k)

    def test_prepare_payload_differentiates_low_vs_high_vs_ultra(self):
        """Low memakai /no_think, max_tokens <= 2048, history <= 16; High/Ultra High bebas menalar & max_tokens jauh lebih besar."""
        from shiro.pipeline.inference import _prepare_inference_payload

        fake_llm = MagicMock()
        fake_llm.model_path = LYRA_REAL_PATH
        fake_llm.n_ctx = lambda: 500000
        state.llm = fake_llm
        state.vision_chat_handler = None

        long_history = []
        for i in range(40):
            long_history.append({"role": "user", "content": f"Pesan {i}"})
            long_history.append({"role": "assistant", "content": f"Balasan {i}"})
        long_history.append({"role": "user", "content": "Buatkan website login modern"})

        with patch("shiro.models.get_gpu_layers", return_value=-1):
            prep_low = _prepare_inference_payload(
                "Buatkan website login modern",
                incoming_messages=long_history,
                lyra_tier="low",
            )
            prep_med = _prepare_inference_payload(
                "Buatkan website login modern",
                incoming_messages=long_history,
                lyra_tier="medium",
            )
            prep_high = _prepare_inference_payload(
                "Buatkan website login modern",
                incoming_messages=long_history,
                lyra_tier="high",
            )
            prep_ultra = _prepare_inference_payload(
                "Buatkan website login modern",
                incoming_messages=long_history,
                lyra_tier="ultra_high",
            )

        self.assertLessEqual(prep_low["call_kwargs"]["max_tokens"], 2048)
        self.assertEqual(prep_low["call_kwargs"]["top_k"], 20)
        self.assertIn("/no_think", prep_low["user_turn_msg"]["content"])
        # 1 system + <= 16 history turns + 1 user turn = <= 18
        self.assertLessEqual(len(prep_low["msgs"]), 18)

        self.assertLessEqual(prep_med["call_kwargs"]["max_tokens"], 4096)
        self.assertEqual(prep_med["call_kwargs"]["top_k"], 30)
        self.assertIn("/no_think", prep_med["user_turn_msg"]["content"])

        self.assertEqual(prep_high["call_kwargs"]["max_tokens"], 16384)
        self.assertNotIn("/no_think", prep_high["user_turn_msg"]["content"])

        self.assertEqual(prep_ultra["call_kwargs"]["max_tokens"], 32768)
        self.assertEqual(prep_ultra["call_kwargs"]["top_k"], 50)
        self.assertNotIn("/no_think", prep_ultra["user_turn_msg"]["content"])

    def test_context_tier_defer_reload_returns_instantly(self):
        """POST /api/models/context-tier dengan defer_reload=true menyimpan pilihan tanpa me-reload model secara memblokir."""
        fake_cur = MagicMock()
        fake_cur.model_path = LYRA_REAL_PATH
        fake_cur.n_ctx = lambda: 500000
        state.llm = fake_cur

        fake_cfg = {
            "current_model": LYRA_REAL_PATH,
            "auto_detect": True,
            "available_models": [LYRA_REAL_PATH],
            "model_info": {LYRA_REAL_PATH: {"name": "ShiroHaru-Lyra-Agent", "size": "~16.8 GB"}},
            "lyra_tier": "high",
        }
        with patch("shiro.routes.admin.load_model_config", return_value=fake_cfg), \
             patch("shiro.routes.admin.save_lyra_tier") as mock_save, \
             patch("shiro.routes.admin.get_gpu_layers", return_value=-1), \
             patch("shiro.routes.admin.instantiate_llama_model") as mock_inst:
            resp = self.client.post("/api/models/context-tier", json={"tier": "low", "defer_reload": True})
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertTrue(data["deferred"])
            self.assertFalse(data["reloaded"])
            self.assertEqual(data["lyra_tier"], "low")
            mock_save.assert_called_once_with("low")
            mock_inst.assert_not_called()

    def test_stream_skips_leading_whitespace_after_think(self):
        """Stream tidak boleh mengirim token spasi kosong sebelum teks nyata setelah </think>."""
        from shiro.pipeline.inference import stream_shiro_reply

        class FakeThinkStreamLLM:
            model_path = LYRA_REAL_PATH

            def n_ctx(self):
                return 500000

            def create_chat_completion(self, messages, stream=False, **kwargs):
                def _gen():
                    yield {"choices": [{"delta": {"content": "<think>"}}]}
                    yield {"choices": [{"delta": {"content": "berpikir..."}}]}
                    yield {"choices": [{"delta": {"content": "</think>"}}]}
                    yield {"choices": [{"delta": {"content": "\n\n"}}]}
                    yield {"choices": [{"delta": {"content": "Halo Kakak!\n"}}]}

                return _gen()

        state.llm = FakeThinkStreamLLM()
        with patch("shiro.models.get_gpu_layers", return_value=-1):
            events = list(stream_shiro_reply("halo", lyra_tier="high"))

        token_events = [e["token"] for e in events if e.get("type") == "token"]
        self.assertTrue(len(token_events) > 0)
        self.assertTrue(token_events[0].strip(), f"Token pertama tidak boleh hanya spasi kosong: {token_events!r}")


if __name__ == "__main__":
    unittest.main()
