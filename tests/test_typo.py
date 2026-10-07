# -*- coding: utf-8 -*-
import unittest
from shiro.nlp.typo import normalize_typos, get_typo_understanding_prompt

class TestTypoHelper(unittest.TestCase):
    def test_normalize_common_slang(self):
        text = "cba shrio bca lgi ya"
        norm, corr = normalize_typos(text)
        self.assertEqual(norm, "coba shiro baca lagi ya")
        self.assertEqual(len(corr), 4)

    def test_url_protection(self):
        text = "bca https://id.wikipedia.org/wiki/Umamusume:_Cinderella_Gray skrg"
        norm, corr = normalize_typos(text)
        self.assertIn("https://id.wikipedia.org/wiki/Umamusume:_Cinderella_Gray", norm)
        self.assertTrue(norm.startswith("baca https://"))
        self.assertTrue(norm.endswith("sekarang"))

    def test_typo_prompt_generation(self):
        _, corr = normalize_typos("bca klo bsa")
        prompt_addon = get_typo_understanding_prompt(corr)
        self.assertIn("Catatan Pemahaman Bahasa", prompt_addon)
        self.assertIn("baca", prompt_addon)

if __name__ == "__main__":
    unittest.main()
