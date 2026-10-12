# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock

from shiro.agent.network import MOZILLA_HEADERS, resolve_dns_cloudflare
from shiro.agent.tools import (
    detect_agent_intent,
    check_weather,
    search_google_web,
    open_and_read_webpage,
    calculate_math,
    get_current_time_info
)
from shiro.agent.engine import ShiroAgentExecutor

class TestShiroAIAgent(unittest.TestCase):

    def test_mozilla_headers_and_cloudflare_dns(self):
        """Memastikan header Mozilla Firefox dan Cloudflare 1.1.1.1 DoH siap"""
        self.assertIn("Firefox/128.0", MOZILLA_HEADERS["User-Agent"])
        self.assertIn("text/html", MOZILLA_HEADERS["Accept"])
        # Test DoH resolver untuk domain publik
        ip = resolve_dns_cloudflare("cloudflare.com")
        self.assertTrue(ip is not None and len(ip.split(".")) == 4)

    def test_detect_agent_intent_weather(self):
        """Deteksi intent cuaca dan ekstraksi multi-kota"""
        query = "Shiro, tolong cek cuaca sekarang di Tokyo dan Jakarta, apakah hujan?"
        intent = detect_agent_intent(query)
        self.assertEqual(intent["intent"], "weather")
        self.assertIn("Tokyo", intent["params"]["locations"])
        self.assertIn("Jakarta", intent["params"]["locations"])

    def test_detect_agent_intent_search(self):
        """Deteksi intent pencarian web / google"""
        query = "cari di google informasi pemenang nobel fisika 2026"
        intent = detect_agent_intent(query)
        self.assertEqual(intent["intent"], "search")
        self.assertIn("nobel fisika", intent["params"]["query"].lower())

    def test_detect_agent_intent_browse(self):
        """Deteksi URL web untuk dibaca langsung"""
        query = "buka https://id.wikipedia.org/wiki/Kucing dong"
        intent = detect_agent_intent(query)
        self.assertEqual(intent["intent"], "browse")
        self.assertEqual(intent["params"]["url"], "https://id.wikipedia.org/wiki/Kucing")

    def test_detect_agent_intent_math(self):
        """Deteksi ekspresi perhitungan matematika presisi"""
        query = "berapa hasil dari (1540 * 25) + 380 ?"
        intent = detect_agent_intent(query)
        self.assertEqual(intent["intent"], "math")
        self.assertIn("(1540 * 25) + 380", intent["params"]["expression"])

    def test_calculate_math_tool(self):
        """Uji perhitungan matematika aman"""
        res = calculate_math("(1540 * 25) + 380")
        self.assertTrue(res["success"])
        self.assertEqual(res["result"], 38880)

    def test_check_current_time(self):
        """Uji pengecekan waktu WIB dan JST"""
        res = get_current_time_info()
        self.assertTrue(res["success"])
        self.assertIn("WIB", res["wib"])
        self.assertIn("JST", res["jst"])

    def test_agent_executor_2step_loop(self):
        """Uji loop 2-step agent otonom dengan model percakapan"""
        executor = ShiroAgentExecutor()
        
        # Mock LLM generation function
        def mock_llm_fn(query, agent_context=""):
            self.assertIn("Fakta Web Nyata Real-time", agent_context)
            self.assertIn("Tokyo", agent_context)
            return "Kakak, Shiro udah cek! Di Tokyo cuacanya cerah dan nggak hujan kok~"

        user_q = "Shiro cek cuaca di Tokyo apakah hujan?"
        reply, action, badge = executor.run_agent_loop(user_q, mock_llm_fn)
        
        self.assertIn("Tokyo", reply)
        self.assertIsNotNone(action)
        self.assertEqual(action["tool"], "weather_sat_check")
        self.assertIn("AI Agent Web Tool", badge)

if __name__ == "__main__":
    unittest.main()
