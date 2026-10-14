# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch

from shiro.memory.gating import (
    gate_facts,
    is_web_fact,
    find_ungrounded_domains,
    tokenize
)
from shiro.agent.moe_router import (
    parse_evidence_json,
    format_evidence_block,
    parse_moe_command,
    get_orchestrator,
    MoEOrchestrator
)
from web import app

class TestMoEDualBrainAndGating(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()

    def test_tokenize(self):
        tokens = tokenize("arsitektur neural transformer project")
        self.assertIn("project", tokens)
        self.assertIn("arsitektur", tokens)
        self.assertIn("transformer", tokens)

    def test_is_web_fact(self):
        f1 = {"subject": "Kakak", "predicate": "membuka situs", "object": "cosplaytele.com/kisaki/7"}
        f2 = {"subject": "Kakak", "predicate": "suka", "object": "kopi hitam manis"}
        self.assertTrue(is_web_fact(f1))
        self.assertFalse(is_web_fact(f2))

    def test_gate_facts_quarantines_web_facts_on_image(self):
        facts = [
            {"subject": "Kakak", "predicate": "membuka situs", "object": "cosplaytele.com/kisaki/7", "confidence": 0.95},
            {"subject": "Kakak", "predicate": "melihat web", "object": "nekopoi.care", "confidence": 0.9},
            {"subject": "Kakak", "predicate": "bernama", "object": "Renn", "confidence": 0.95},
            {"subject": "Kakak", "predicate": "suka", "object": "desain poster anime", "confidence": 0.85},
        ]
        # Saat has_image=True, fakta tentang web/URL harus 100% dibuang
        filtered = gate_facts(facts, query="shiro coba lihat poster ini", has_image=True)
        filtered_texts = [f"{f['subject']} {f['predicate']} {f['object']}" for f in filtered]
        self.assertFalse(any("cosplaytele" in t for t in filtered_texts))
        self.assertFalse(any("nekopoi" in t for t in filtered_texts))
        # Fakta identitas atau relevan dengan poster tetap ada
        self.assertTrue(any("desain poster" in t or "Renn" in t for t in filtered_texts))

    def test_find_ungrounded_domains(self):
        reply = 'Kakak sepertinya membuka cosplaytele.com untuk melihat karakter Kisaki.'
        allowed = ["Ini adalah poster Project Shiro AI v2 karya Renn-devBI"]
        ungrounded = find_ungrounded_domains(reply, allowed)
        self.assertIn("cosplaytele.com", ungrounded)

        # Jika domain memang disebut di pesan user, tidak dianggap ungrounded
        allowed_with_user = ["Tolong buka github.com untuk cek kodenya"]
        reply2 = "Baik Kakak, ini link github.com yang Kakak maksud."
        self.assertEqual(find_ungrounded_domains(reply2, allowed_with_user), [])

    def test_parse_evidence_json(self):
        json_blob = """
        ```json
        {
          "image_type": "poster/banner",
          "is_webpage_screenshot": false,
          "primary_subject": "Project Shiro AI v2",
          "detected_texts": ["PROJECT SHIRO AI v2", "Renn-devBI"],
          "visual_details": "Neon sci-fi theme"
        }
        ```
        """
        parsed = parse_evidence_json(json_blob)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.get("primary_subject"), "Project Shiro AI v2")
        self.assertIn("Renn-devBI", parsed.get("detected_texts", []))

    def test_format_evidence_block(self):
        contract = {
            "image_type": "poster",
            "primary_subject": "Logo Shiro",
            "detected_texts": ["PROJECT SHIRO AI", "Renn-devBI"],
            "is_webpage_screenshot": False
        }
        block = format_evidence_block(contract, "#1")
        self.assertIn("Jenis: poster", block)
        self.assertIn("Logo Shiro", block)
        self.assertIn("PROJECT SHIRO AI", block)
        self.assertIn("BUKAN tangkapan layar", block)

    def test_parse_moe_command(self):
        self.assertEqual(parse_moe_command("/moe on"), "concurrent")
        self.assertEqual(parse_moe_command("/moe off"), "off")
        self.assertEqual(parse_moe_command("/moe auto"), "auto")
        self.assertEqual(parse_moe_command("/moe swap"), "swap")
        self.assertEqual(parse_moe_command("/moe status"), "status")
        self.assertEqual(parse_moe_command("/moe"), "status")
        self.assertIsNone(parse_moe_command("halo shiro apa kabar?"))

    def test_moe_api_endpoints(self):
        # GET /api/moe
        res = self.app.get('/api/moe')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("mode", data)
        self.assertIn("valid_modes", data)

        # POST /api/moe
        res_post = self.app.post('/api/moe', json={"mode": "auto"})
        self.assertEqual(res_post.status_code, 200)
        self.assertEqual(res_post.get_json().get("mode"), "auto")

        # Invalid mode returns 400
        res_invalid = self.app.post('/api/moe', json={"mode": "invalid_mode_xyz"})
        self.assertEqual(res_invalid.status_code, 400)

    def test_moe_chat_command_handling(self):
        res = self.app.post('/api/chat', json={"message": "/moe status"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("system_command"))
        self.assertIn("[MoE]", data.get("reply", ""))

if __name__ == '__main__':
    unittest.main()
