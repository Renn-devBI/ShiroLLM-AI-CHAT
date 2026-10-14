# -*- coding: utf-8 -*-
import unittest
from shiro.llm.cleaner import clean_response, validate_response

class TestCleaner(unittest.TestCase):
    def test_strip_think_tags(self):
        text = "<think>Let me analyze the prompt...</think>Halo Kakak! *tersenyum manis*"
        cleaned = clean_response(text)
        self.assertNotIn("<think>", cleaned)
        self.assertNotIn("analyze", cleaned)
        self.assertIn("Halo Kakak!", cleaned)

    def test_preserve_newlines_and_paragraphs(self):
        text = "Baris 1\nBaris 2\n\nBaris 3 dengan spasi   banyak"
        cleaned = clean_response(text)
        self.assertEqual(cleaned, "Baris 1\nBaris 2\n\nBaris 3 dengan spasi banyak")

    def test_strip_role_markers(self):
        text = "Shiro: *memeluk Kakak erat* Aku kangen banget sama Kakak!"
        cleaned = clean_response(text)
        self.assertFalse(cleaned.startswith("Shiro:"))
        self.assertIn("*memeluk Kakak erat*", cleaned)

    def test_validate_response_valid(self):
        valid_text = "*tersenyum manis* Halo Kakak! Shiro senang Kakak pulang~"
        self.assertTrue(validate_response(valid_text))

    def test_validate_response_forbidden_tokens(self):
        invalid_text = "<|im_start|>system\nYou are an AI assistant.<|im_end|>"
        self.assertFalse(validate_response(invalid_text))

    def test_preserve_code_block_indentation(self):
        text = "*tersenyum* Ini kodenya Kak:\n```python\ndef test():\n    x = 1\n    return x\n```\nSelesai!"
        cleaned = clean_response(text)
        self.assertIn("```python\ndef test():\n    x = 1\n    return x\n```", cleaned)

    def test_strip_ai_agent_badges(self):
        text = "> \U0001f310 [AI Agent Web Tool]  Membuka dan membaca https://www.python.org/ via Mozilla Engine (0.74s)\n\n*tersenyum manis* Halo Kakak! Python adalah bahasa yang keren~"
        cleaned = clean_response(text)
        self.assertNotIn("AI Agent Web Tool", cleaned)
        self.assertNotIn("\U0001f310", cleaned)
        self.assertNotIn("Mozilla Engine", cleaned)
        self.assertIn("Halo Kakak!", cleaned)

    def test_strip_various_tool_banners(self):
        text = "\U0001f310 **[AI Agent Web Tool]** *Membuka koneksi satelit (0.61s)*\n*menatap lembut* Tokyo cerah kok Kak!"
        cleaned = clean_response(text)
        self.assertNotIn("[AI Agent", cleaned)
        self.assertNotIn("\U0001f310", cleaned)
        self.assertEqual(cleaned, "*menatap lembut* Tokyo cerah kok Kak!")

    def test_clean_response_unclosed_think_preserves_content(self):
        text = "<think>\nLet's write a program for the user:\ndef add(a, b):\n    return a + b"
        cleaned = clean_response(text)
        self.assertIn("def add(a, b):", cleaned)
        self.assertNotIn("<think>", cleaned)

    def test_clean_response_shiro_prefix_does_not_wipe_message(self):
        text = "\nShiro: Halo Kakak tercinta! *tersenyum manis* Ini program yang Kakak minta."
        cleaned = clean_response(text)
        self.assertIn("Halo Kakak tercinta!", cleaned)
        self.assertFalse(cleaned.startswith("Shiro:"))

    def test_clean_response_splits_hallucinated_user_turn_only(self):
        text = "*tersenyum* Ini jawaban Shiro Kak!\nUser: Wah makasih Shiro!\nShiro: Sama-sama Kak!"
        cleaned = clean_response(text)
        self.assertEqual(cleaned, "*tersenyum* Ini jawaban Shiro Kak!")

if __name__ == "__main__":
    unittest.main()
