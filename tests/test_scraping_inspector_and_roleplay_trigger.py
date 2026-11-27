# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

from shiro.web.reader import (
    analyze_html_structure,
    detect_scraping_target_urls,
    inspect_target_website_for_scraping,
)


class TestScrapingInspectorAndRoleplayTrigger(unittest.TestCase):
    def test_detect_scraping_target_urls_ignores_localhost_and_extracts_templates(self):
        prompt = (
            "Buatkan aplikasi web lokal full-stack Next.js untuk scraping anime dari "
            "https://otakudesu.blog/ langsung di browser lokal (http://localhost:3000). "
            "Endpoint search: https://otakudesu.blog/?s={query}&post_type=anime "
            "dan jadikan zip."
        )
        is_scrape, base_urls, template_urls = detect_scraping_target_urls(prompt)
        self.assertTrue(is_scrape)
        self.assertIn("https://otakudesu.blog/", base_urls)
        self.assertNotIn("http://localhost:3000", base_urls)
        self.assertEqual(template_urls, ["https://otakudesu.blog/?s={query}&post_type=anime"])

    def test_analyze_html_structure_extracts_real_dom_selectors_and_forms(self):
        sample_html = """
        <html>
          <head><title>OtakuDesu - Nonton Anime</title></head>
          <body>
            <form action="https://otakudesu.blog/" method="GET">
              <input type="text" name="s" value="" />
              <input type="hidden" name="post_type" value="anime" />
            </form>
            <ul class="chivsrc">
              <li>
                <img src="https://otakudesu.blog/img/naruto.jpg" />
                <h2><a href="https://otakudesu.blog/anime/naruto-sub-indo/">Naruto Shippuden</a></h2>
                <div class="set">Genres: Action, Adventure</div>
              </li>
              <li>
                <img src="https://otakudesu.blog/img/bleach.jpg" />
                <h2><a href="https://otakudesu.blog/anime/bleach-sub-indo/">Bleach</a></h2>
                <div class="set">Genres: Action</div>
              </li>
            </ul>
          </body>
        </html>
        """
        dom = analyze_html_structure(sample_html, "https://otakudesu.blog/?s=naruto&post_type=anime")
        self.assertEqual(dom["title"], "OtakuDesu - Nonton Anime")
        self.assertTrue(any("s(" in ",".join(f["inputs"]) for f in dom["forms"]))
        self.assertTrue(any("ul.chivsrc" in c["selector"] for c in dom["repeating_containers"]))
        self.assertTrue(any("naruto-sub-indo" in lk["url"] for lk in dom["sample_detail_links"]))

    def test_inspect_target_website_runs_multi_pass_home_search_detail(self):
        home_html = (
            "<html><head><title>OtakuDesu Home</title></head><body>"
            "<form action='/' method='GET'><input name='s' /></form>"
            "</body></html>"
        )
        search_html = (
            "<html><head><title>Search Naruto</title></head><body>"
            "<ul class='chivsrc'>"
            "<li><img data-src='https://otakudesu.blog/thumb.jpg' />"
            "<h2><a href='https://otakudesu.blog/anime/naruto/'>Naruto</a></h2></li>"
            "<li><img data-src='https://otakudesu.blog/thumb2.jpg' />"
            "<h2><a href='https://otakudesu.blog/anime/boruto/'>Boruto</a></h2></li>"
            "</ul></body></html>"
        )
        detail_html = (
            "<html><head><title>Naruto Detail</title></head><body>"
            "<div class='sinopc'><p>Kisah ninja Konoha.</p></div>"
            "<div class='episodelist'><ul>"
            "<li><a href='https://otakudesu.blog/eps/naruto-1/'>Episode 1</a></li>"
            "<li><a href='https://otakudesu.blog/eps/naruto-2/'>Episode 2</a></li>"
            "</ul></div></body></html>"
        )

        def _fake_fetch(url, timeout=10, referer=None):
            if "?s=" in url:
                html = search_html
            elif "/anime/naruto" in url:
                html = detail_html
            else:
                html = home_html
            return {
                "success": True,
                "url": url,
                "final_url": url,
                "status_code": 200,
                "html": html,
                "server": "cloudflare",
                "cookies_count": 1,
                "is_cloudflare": False,
                "anti_bot_signals": ["Cloudflare"],
                "error": None,
            }

        prompt = (
            "Buatkan scraper Next.js untuk https://otakudesu.blog/ "
            "dengan search https://otakudesu.blog/?s={query}&post_type=anime "
            "dan detail sinopsis serta daftar episode."
        )
        with patch("shiro.web.reader.fetch_raw_html", side_effect=_fake_fetch):
            report = inspect_target_website_for_scraping(prompt, timeout=5)

        self.assertIsNotNone(report)
        self.assertEqual(len(report["steps"]), 3)
        self.assertIn("ul.chivsrc", report["prompt_context"])
        self.assertIn("div.sinopc", report["prompt_context"])
        self.assertIn("div.episodelist", report["prompt_context"])

    def test_auto_trigger_disabled_when_roleplay_off_backend_and_frontend(self):
        # 1. Backend /api/trigger check
        from flask import Flask
        from shiro.server_state import state
        from shiro.routes.chat import chat_bp

        app = Flask(__name__)
        app.register_blueprint(chat_bp)
        client = app.test_client()

        mem = state.init_memory()
        prev_rp = mem.system_metadata.get("roleplay_enabled", True)
        prev_sq = state.serial_questions
        try:
            mem.system_metadata["roleplay_enabled"] = False
            state.serial_questions = 0
            with patch("shiro.routes.chat.get_shiro_reply") as mock_reply:
                resp = client.post("/api/trigger")
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                self.assertEqual(data.get("status"), "idle")
                self.assertEqual(data.get("reason"), "roleplay_disabled")
                mock_reply.assert_not_called()
        finally:
            mem.system_metadata["roleplay_enabled"] = prev_rp
            state.serial_questions = prev_sq

        # 2. Frontend script.js check
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "static", "script.js"), "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("if (!roleplayEnabled) return;", js)
        self.assertIn("if (!roleplayEnabled && typeof triggerTimer !== 'undefined')", js)


if __name__ == "__main__":
    unittest.main()
