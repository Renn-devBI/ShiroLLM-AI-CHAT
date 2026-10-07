# -*- coding: utf-8 -*-
import unittest
from shiro.web.reader import extract_urls, detect_web_intent, clean_html_content

class TestWebReader(unittest.TestCase):
    def test_extract_urls(self):
        text = "baca web https://id.wikipedia.org/wiki/Kucing ya Shiro!"
        urls = extract_urls(text)
        self.assertEqual(urls, ["https://id.wikipedia.org/wiki/Kucing"])

    def test_detect_web_intent_url(self):
        text = "baca https://no-game-no-life.fandom.com/id/wiki/Shiro"
        res = detect_web_intent(text)
        self.assertEqual(res["type"], "url")
        self.assertIn("https://no-game-no-life.fandom.com/id/wiki/Shiro", res["urls"])

    def test_detect_web_intent_search_with_typo(self):
        text = "coba cri di web ttg kecerdasan buatan"
        res = detect_web_intent(text)
        self.assertEqual(res["type"], "search")
        self.assertIn("kecerdasan buatan", res["query"])

    def test_clean_html_content(self):
        raw_html = "<html><head><title>Test Page</title></head><body><script>alert(1);</script><article><p>Ini adalah artikel berita penting.</p></article></body></html>"
        title, text = clean_html_content(raw_html)
        self.assertEqual(title, "Test Page")
        self.assertIn("Ini adalah artikel berita penting.", text)
        self.assertNotIn("alert(1)", text)

if __name__ == "__main__":
    unittest.main()
