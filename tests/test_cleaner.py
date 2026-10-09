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

    def test_validate_code_response(self):
        code_resp = "*tersenyum manis* Tentu Kakak! Ini Shiro buatin programnya:\n```python\nimport random\nangka = random.randint(1, 10)\nprint('Halo')\n```\nSemoga membantu ya Kak!"
        self.assertTrue(validate_response(code_resp, "buatin program dong"))

if __name__ == "__main__":
    unittest.main()
