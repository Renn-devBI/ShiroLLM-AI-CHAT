# -*- coding: utf-8 -*-
import base64
import io
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from shiro.agent.network import MOZILLA_HEADERS, get_firefox_headers, is_safe_external_url
from shiro.agent.tools import detect_agent_intent
from shiro.vision.reverse_search import (
    _decode_and_prepare_image,
    run_multi_engine_reverse_image_search,
    search_bing_visual,
    search_google_lens,
    search_iqdb,
    search_saucenao,
    search_tracemoe,
    search_yandex_images,
    should_run_reverse_image_search,
)


def _make_sample_jpeg_data_uri(w: int = 64, h: int = 64) -> str:
    from PIL import Image
    buf = io.BytesIO()
    im = Image.new("RGB", (w, h), (35, 180, 120))
    im.save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


class TestReverseImageSearchAndImageSending(unittest.TestCase):
    def test_should_run_reverse_image_search_universal_and_skips_code_debug(self):
        self.assertFalse(should_run_reverse_image_search("ini anime apa", has_image=False))
        self.assertTrue(should_run_reverse_image_search("shiro coba kamu cari tahu ini dari anime apa", has_image=True))
        self.assertTrue(should_run_reverse_image_search("siapa ini / tokoh apa ini?", has_image=True))
        self.assertTrue(should_run_reverse_image_search("ini produk apa ya dan merek apa?", has_image=True))
        self.assertTrue(should_run_reverse_image_search("", has_image=True))
        self.assertFalse(should_run_reverse_image_search("tolong debug traceback TypeError di script python ini", has_image=True))
        self.assertTrue(should_run_reverse_image_search("ini karakter anime apa, error ga nemu sumbernya", has_image=True))

    def test_firefox_headers_and_ssrf_guard(self):
        hdrs = get_firefox_headers(referer="https://lens.google.com/")
        self.assertIn("Firefox/", hdrs["User-Agent"])
        self.assertIn("Gecko/20100101", hdrs["User-Agent"])
        self.assertEqual(hdrs["Referer"], "https://lens.google.com/")
        self.assertIn("Firefox/", MOZILLA_HEADERS["User-Agent"])

        self.assertFalse(is_safe_external_url("http://127.0.0.1:5000/secret"))
        self.assertFalse(is_safe_external_url("http://localhost:3000/test.png"))
        self.assertFalse(is_safe_external_url("http://169.254.169.254/latest/meta-data"))
        self.assertFalse(is_safe_external_url("http://192.168.1.1/router.png"))
        self.assertFalse(is_safe_external_url("file:///etc/passwd"))
        self.assertTrue(is_safe_external_url("https://8.8.8.8/sample.jpg"))

    def test_decode_skips_1x1_placeholder_and_accepts_real_image(self):
        tiny_1x1 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        self.assertIsNone(_decode_and_prepare_image(tiny_1x1))

        real_uri = _make_sample_jpeg_data_uri(64, 64)
        decoded = _decode_and_prepare_image(real_uri)
        self.assertIsNotNone(decoded)
        raw_b, mime = decoded
        self.assertGreater(len(raw_b), 200)
        self.assertEqual(mime, "image/jpeg")

    def test_all_six_engine_parsers_with_mocked_firefox_sessions(self):
        img_bytes = b"\xff\xd8\xff\xe0dummyjpegbytes"

        # 1. trace.moe
        sess_tm = MagicMock()
        r_tm = MagicMock(status_code=200)
        r_tm.json.return_value = {
            "result": [
                {
                    "similarity": 0.942,
                    "episode": 7,
                    "from": 135.2,
                    "image": "https://api.trace.moe/image/preview.jpg",
                    "anilist": {
                        "id": 170732,
                        "title": {"romaji": "Mayonaka Punch", "english": "Midnight Punch"},
                    },
                }
            ]
        }
        sess_tm.post.return_value = r_tm
        with patch("shiro.vision.reverse_search.get_firefox_session", return_value=sess_tm):
            res_tm = search_tracemoe(img_bytes)
        self.assertEqual(len(res_tm), 1)
        self.assertIn("Mayonaka Punch", res_tm[0]["title"])
        self.assertEqual(res_tm[0]["similarity"], 94.2)
        self.assertIn("Firefox/", sess_tm.post.call_args.kwargs["headers"]["User-Agent"])

        # 2. Google Lens
        sess_gl = MagicMock()
        r_gl = MagicMock(
            status_code=200,
            url="https://lens.google.com/search?p=1",
            text='<html><body><a href="https://myanimelist.net/anime/57845/Mayonaka_Punch">Mayonaka Punch (Midnight Punch)<img src="https://cdn.example.com/mp.jpg"/></a></body></html>',
        )
        sess_gl.post.return_value = r_gl
        with patch("shiro.vision.reverse_search.get_firefox_session", return_value=sess_gl):
            res_gl = search_google_lens(img_bytes)
        self.assertTrue(any("Mayonaka Punch" in x["title"] for x in res_gl))
        self.assertEqual(res_gl[0]["engine"], "Google Lens")

        # 3. Yandex Visual
        sess_yx = MagicMock()
        r_yx = MagicMock(
            status_code=200,
            text=json.dumps({
                "items": [{"title": "Mayonaka Punch Anime Frame", "url": "https://anilist.co/anime/170732"}]
            }),
        )
        sess_yx.post.return_value = r_yx
        with patch("shiro.vision.reverse_search.get_firefox_session", return_value=sess_yx):
            res_yx = search_yandex_images(img_bytes)
        self.assertTrue(any("Mayonaka Punch" in x["title"] for x in res_yx))

        # 4. IQDB
        sess_iq = MagicMock()
        r_iq = MagicMock(
            status_code=200,
            text='<div id="pages"><div><table><tr><th>Best match</th></tr><tr><td class="image"><a href="//danbooru.donmai.us/posts/123"><img src="/thu/123.jpg" alt="Tags: mayonaka_punch fuu"/></a></td></tr><tr><td>91% similarity</td></tr></table></div></div>',
        )
        sess_iq.post.return_value = r_iq
        with patch("shiro.vision.reverse_search.get_firefox_session", return_value=sess_iq):
            res_iq = search_iqdb(img_bytes)
        self.assertEqual(len(res_iq), 1)
        self.assertEqual(res_iq[0]["similarity"], 91.0)
        self.assertTrue(res_iq[0]["url"].startswith("https://"))

        # 5. SauceNAO
        sess_sn = MagicMock()
        r_sn = MagicMock(status_code=200)
        r_sn.json.return_value = {
            "results": [
                {
                    "header": {"similarity": "89.5", "thumbnail": "https://saucenao.com/thumb.jpg", "index_name": "AniDB"},
                    "data": {"source": "Mayonaka Punch", "part": "07", "ext_urls": ["https://anidb.net/anime/18432"]},
                }
            ]
        }
        sess_sn.post.return_value = r_sn
        with patch("shiro.vision.reverse_search.get_firefox_session", return_value=sess_sn):
            res_sn = search_saucenao(img_bytes)
        self.assertEqual(len(res_sn), 1)
        self.assertEqual(res_sn[0]["title"], "Mayonaka Punch")

        # 6. Bing Visual
        sess_bg = MagicMock()
        r_bg = MagicMock(
            status_code=200,
            text='{"name":"Mayonaka Punch Episode 7","hostPageUrl":"https://animecorner.me/mayonaka","thumbnailUrl":"https://bing.com/th/mp.jpg"}',
        )
        sess_bg.post.return_value = r_bg
        with patch("shiro.vision.reverse_search.get_firefox_session", return_value=sess_bg):
            res_bg = search_bing_visual(img_bytes)
        self.assertEqual(len(res_bg), 1)
        self.assertIn("Mayonaka Punch", res_bg[0]["title"])

    def test_multi_engine_consensus_anti_hallucination_and_saved_resend_url(self):
        real_uri = _make_sample_jpeg_data_uri(64, 64)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("shiro.agent.packager.GENERATED_ARTIFACTS_DIR", tmpdir), \
                 patch("shiro.vision.reverse_search.search_google_lens", return_value=[{"engine": "Google Lens", "title": "Mayonaka Punch", "raw_title": "Mayonaka Punch", "similarity": None, "url": "https://myanimelist.net/anime/57845", "image_url": "https://cdn.myanimelist.net/mp.jpg", "details": "Google Lens visual match"}]), \
                 patch("shiro.vision.reverse_search.search_tracemoe", return_value=[{"engine": "trace.moe", "title": "Mayonaka Punch", "raw_title": "Mayonaka Punch", "similarity": 93.4, "url": "https://anilist.co/anime/170732", "image_url": "https://api.trace.moe/mp.jpg", "details": "Episode 7 · Timestamp 04:12"}]), \
                 patch("shiro.vision.reverse_search.search_yandex_images", return_value=[]), \
                 patch("shiro.vision.reverse_search.search_iqdb", return_value=[]), \
                 patch("shiro.vision.reverse_search.search_saucenao", return_value=[]), \
                 patch("shiro.vision.reverse_search.search_bing_visual", return_value=[]), \
                 patch("shiro.agent.tools.search_google_web", return_value={"success": True, "summary": "Mayonaka Punch by P.A. Works", "results": [{"title": "Mayonaka Punch - Wikipedia", "url": "https://en.wikipedia.org/wiki/Mayonaka_Punch", "snippet": "Original anime", "source": "Wikipedia"}], "images": []}):
                report = run_multi_engine_reverse_image_search([real_uri], user_query="ini dari anime apa?")

            self.assertTrue(report["success"])
            self.assertEqual(report["engines_tried"], 6)
            self.assertEqual(report["engines_succeeded"], 2)
            self.assertIsNotNone(report["uploaded_image_url"])
            self.assertIn("/api/artifacts/", report["uploaded_image_url"])
            self.assertGreaterEqual(report["candidates"][0]["engine_votes"], 2)
            self.assertIn("ATURAN MUTLAK ANTI-HALUSINASI", report["prompt_context"])
            self.assertIn("DILARANG KERAS mengarang", report["prompt_context"])
            self.assertIn("Mayonaka Punch", report["prompt_context"])

    def test_image_proxy_endpoint_serves_valid_external_image_and_blocks_ssrf(self):
        from flask import Flask
        from shiro.routes.documents import documents_bp

        app = Flask(__name__)
        app.register_blueprint(documents_bp)
        client = app.test_client()

        # SSRF blocked
        resp_local = client.get("/api/image-proxy?url=http://127.0.0.1:5000/secret.png")
        self.assertEqual(resp_local.status_code, 400)

        # Valid external image proxied with Mozilla Firefox headers
        sample_bytes = b"\x89PNG\r\n\x1a\nfake_png_bytes"
        with patch("shiro.agent.network.is_safe_external_url", return_value=True), \
             patch("shiro.agent.network.fetch_image_bytes", return_value=(True, sample_bytes, "image/png", None)):
            resp_ok = client.get("/api/image-proxy?url=https://example.com/anime.png")
        self.assertEqual(resp_ok.status_code, 200)
        self.assertEqual(resp_ok.data, sample_bytes)
        self.assertEqual(resp_ok.mimetype, "image/png")
        self.assertIn("max-age=", resp_ok.headers.get("Cache-Control", ""))

    def test_image_search_and_send_image_tools_and_frontend_proxy(self):
        # 1. Intent detection for sending / searching / resending images
        i1 = detect_agent_intent("tolong kirim gambar Mayonaka Punch")
        self.assertEqual(i1["intent"], "image_search")
        i1b = detect_agent_intent("tolong carikan gambar Mayonaka Punch")
        self.assertEqual(i1b["intent"], "search")
        self.assertTrue(i1b["params"].get("wants_images"))
        i2 = detect_agent_intent("kirim ulang gambar tadi dong")
        self.assertEqual(i2["intent"], "resend_image")

        # 2. _execute_live_research_tool for send_image & search_image
        from shiro.pipeline.inference import _execute_live_research_tool

        res_send = _execute_live_research_tool(
            {"name": "send_image", "args": {"url": "last_uploaded", "caption": "Foto Kamu"}},
            uploaded_image_url="/api/artifacts/uimg_abc/uploaded_image.jpg?inline=1",
        )
        self.assertEqual(res_send["status"], "success")
        self.assertEqual(res_send["web_images"][0]["url"], "/api/artifacts/uimg_abc/uploaded_image.jpg?inline=1")

        with patch("shiro.agent.tools.search_web_images", return_value=[{"url": "https://cdn.example.com/fuu.jpg", "title": "Fuu", "source_url": "https://example.com", "source": "Bing Images"}]):
            res_search = _execute_live_research_tool({"name": "search_image", "args": {"query": "Mayonaka Punch"}})
        self.assertEqual(res_search["status"], "success")
        self.assertEqual(res_search["web_images"][0]["url"], "https://cdn.example.com/fuu.jpg")

        # 3. Frontend proxy wiring
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "static", "script.js"), "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("function resolveDisplayImageUrl", js)
        self.assertIn("/api/image-proxy?url=", js)


if __name__ == "__main__":
    unittest.main()
