# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import web
from shiro.server_state import state
from shiro.persona import build_system_prompt, build_vtuber_system_prompt
from shiro.llm.cleaner import clean_response
from shiro.web.realtime_intel import get_research_config_for_tier, build_queries
from shiro.pipeline.inference import (
    get_max_agent_rounds,
    stream_shiro_reply,
)


class TestCreatorRoleplayVideoAndDepth(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()
        self.mem = state.init_memory()
        self._orig_llm = state.llm
        self._orig_vh = state.vision_chat_handler
        self._orig_roleplay = self.mem.system_metadata.get("roleplay_enabled", True)

    def tearDown(self):
        state.llm = self._orig_llm
        state.vision_chat_handler = self._orig_vh
        self.client.post("/api/settings/privacy", json={"roleplay_enabled": self._orig_roleplay})

    def test_creator_identity_and_model_awareness_prompts(self):
        """Identitas pencipta (Tim Renn ShiroHaru / Renn) dan model aktif hadir di prompt v1 dan VTuber v2."""
        sys_p = build_system_prompt(active_model_name="ShiroHaru-Lyra High", roleplay_enabled=True)
        self.assertIn("Tim Renn ShiroHaru", sys_p)
        self.assertIn("Renn", sys_p)
        self.assertIn("ShiroHaru-Lyra High", sys_p)
        self.assertIn("DILARANG KERAS mengaku dibuat oleh Alibaba", sys_p)
        self.assertNotIn("Qwen3.8-27B", sys_p)

        vtuber_p = build_vtuber_system_prompt(owner_name="Renn", active_model_name="ShiroHaru-Lyra Ultra High")
        self.assertIn("Tim Renn ShiroHaru", vtuber_p)
        self.assertIn("ShiroHaru-Lyra Ultra High", vtuber_p)

    def test_roleplay_toggle_endpoint_and_full_agent_mode(self):
        """Toggle Roleplay ON/OFF tersimpan di privacy settings dan memengaruhi prompt + cleaner."""
        resp_off = self.client.post("/api/settings/privacy", json={"roleplay_enabled": False})
        self.assertEqual(resp_off.status_code, 200)
        self.assertFalse(resp_off.get_json()["roleplay_enabled"])

        hist_resp = self.client.get("/api/history")
        self.assertEqual(hist_resp.status_code, 200)
        self.assertFalse(hist_resp.get_json()["roleplay_enabled"])

        prompt_off = build_system_prompt(active_model_name="ShiroHaru-Lyra High", roleplay_enabled=False)
        self.assertIn("PEDOMAN MODE FULL AGENT (ROLEPLAY NONAKTIF):", prompt_off)
        self.assertNotIn("adik perempuan kesayangan", prompt_off)

        # Cleaner ketika roleplay OFF mempertahankan sapaan formal ("Anda") tanpa mengganti menjadi "Kakak"
        cleaned_off = clean_response("Saya siap membantu Anda menganalisis file tersebut.", roleplay_enabled=False)
        self.assertIn("Anda", cleaned_off)
        self.assertNotIn("Kakak", cleaned_off)

        # Kembalikan ke ON
        resp_on = self.client.post("/api/settings/privacy", json={"roleplay_enabled": True})
        self.assertEqual(resp_on.status_code, 200)
        self.assertTrue(resp_on.get_json()["roleplay_enabled"])

    def test_casual_chat_and_vtuber_skip_reasoning_synthesis(self):
        """Obrolan santai dan mode VTuber v2 menjawab langsung tanpa Reasoning & Solution Synthesis."""
        captured_prompts = []

        class DirectReplyLLM:
            model_path = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"
            _shiro_fast_chatml = True

            def n_ctx(self):
                return 500000

            def create_completion(self, prompt, stream=False, **kwargs):
                captured_prompts.append(prompt)
                def _gen():
                    yield {"choices": [{"text": "Hehe, makasih ya Kakak! Shiro senang banget dipuji begitu."}]}
                return _gen()

        state.llm = DirectReplyLLM()
        with patch("shiro.models.get_gpu_layers", return_value=-1):
            casual_events = list(stream_shiro_reply("oke kamu hebat", lyra_tier="high"))

        self.assertFalse(any(e.get("type") == "agent_trace_step" for e in casual_events))
        self.assertFalse(any(e.get("type") == "thought" for e in casual_events))
        done_ev = [e for e in casual_events if e.get("type") == "done"][0]
        self.assertEqual(done_ev["agent_steps"], [])
        self.assertIn("/no_think", captured_prompts[0])

        # VTuber AI v2 juga langsung menjawab tanpa Reasoning & Solution Synthesis bahkan untuk prompt panjang
        with patch("shiro.models.get_gpu_layers", return_value=-1):
            vtube_events = list(stream_shiro_reply(
                "analisa kondisi hari ini dan buatkan rencana website singkat ya shiro",
                api_version="v2",
                lyra_tier="ultra_high",
            ))
        self.assertFalse(any(e.get("type") == "agent_trace_step" for e in vtube_events))
        self.assertFalse(any(e.get("type") == "thought" for e in vtube_events))

    def test_dynamic_uncapped_reasoning_and_tier_scaled_deep_search(self):
        """Tugas agen kompleks bisa memancarkan >3 step analisis dan deep search berskala sesuai tier."""
        self.assertLess(get_max_agent_rounds("low"), get_max_agent_rounds("high"))
        self.assertGreaterEqual(get_max_agent_rounds("ultra_high"), 50)

        cfg_low = get_research_config_for_tier("low")
        cfg_high = get_research_config_for_tier("high")
        cfg_ultra = get_research_config_for_tier("ultra_high")
        self.assertLess(cfg_low.max_queries, cfg_high.max_queries)
        self.assertLess(cfg_high.max_queries, cfg_ultra.max_queries)
        self.assertGreaterEqual(cfg_ultra.max_sources, 30)

        q_ultra = build_queries("performa arsitektur microkernel modern", max_queries=cfg_ultra.max_queries)
        self.assertGreater(len(q_ultra), 3)

        class DeepMultiStageLLM:
            model_path = "model/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"
            _shiro_fast_chatml = True

            def n_ctx(self):
                return 500000

            def create_completion(self, prompt, stream=False, **kwargs):
                def _gen():
                    yield {"choices": [{"text": (
                        "<think>\n"
                        "1. Parse architecture requirements and constraints\n"
                        "2. Evaluate authentication & session token design\n"
                        "3. Design database schema & indexing strategy\n"
                        "4. Plan frontend layout without excessive glow\n"
                        "5. Verify error handling & edge cases\n"
                        "6. Final quality verification checklist\n"
                        "</think>\n"
                        "Berikut rancangan lengkap websitenya.\n"
                    )}]}
                return _gen()

        state.llm = DeepMultiStageLLM()
        with patch("shiro.models.get_gpu_layers", return_value=-1):
            events = list(stream_shiro_reply(
                "buatkan website login modern dengan arsitektur aman",
                lyra_tier="ultra_high",
            ))

        step_ids = {e["step"]["id"] for e in events if e.get("type") == "agent_trace_step"}
        think_stages = [sid for sid in step_ids if sid.startswith("think_stage_")]
        self.assertGreaterEqual(len(think_stages), 5)

    def test_ui_composer_3_buttons_lightbox_video_and_roleplay_controls(self):
        """UI memiliki tepat 3 tombol composer (Berkas, Gambar, Kamera), video lightbox, loading upload, & toggle roleplay."""
        root = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(root, "templates", "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        with open(os.path.join(root, "static", "script.js"), "r", encoding="utf-8") as f:
            js = f.read()

        self.assertIn('id="upload-doc-btn"', html)
        self.assertIn('id="upload-image-btn"', html)
        self.assertIn('id="open-camera-btn"', html)
        self.assertNotIn('id="upload-video-btn"', html)
        self.assertNotIn('id="video-file-input"', html)
        self.assertIn('id="lightbox-video"', html)
        self.assertIn('id="roleplay-enabled-toggle"', html)

        self.assertIn("function openVideoLightbox", js)
        self.assertIn("function toggleRoleplayMode", js)
        self.assertIn("pendingUploads", js)
        self.assertIn("ph-play-circle", js)
        self.assertNotIn("Mengekstrak frame video", js)


if __name__ == "__main__":
    unittest.main()
