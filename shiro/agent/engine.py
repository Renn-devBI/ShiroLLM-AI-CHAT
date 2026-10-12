# -*- coding: utf-8 -*-
"""
Shiro AI Agent Engine & Autonomous Execution Loop
Orchestrates multi-turn 2-step agent reasoning:
1. Intent & Action Selection (Thinking & Planning)
2. Autonomous Tool Execution via Cloudflare 1.1.1.1 & Mozilla Headers (Observation)
3. Conversational Synthesis via Shiro Persona (Final Answer)
"""

import time
from typing import Dict, Any, Optional, Tuple, List

from shiro.agent.tools import (
    detect_agent_intent,
    check_weather,
    search_google_web,
    open_and_read_webpage,
    calculate_math,
    get_current_time_info
)
from shiro.llm.cleaner import clean_response

class ShiroAgentExecutor:
    """
    Executor otonom yang menghubungkan model percakapan Shiro dengan kemampuan AI Agent
    untuk mencari informasi di Google/Web, memeriksa cuaca satelit, membuka URL,
    dan mengeksekusi perhitungan nyata di dunia nyata.
    """

    def __init__(self):
        pass

    def run_agent_loop(
        self,
        user_input: str,
        llm_generate_fn: Any,
        api_version: str = "v1"
    ) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
        """
        Menjalankan loop otonom 2-step AI Agent:
        Returns:
            - final_reply: Jawaban akhir dari Shiro yang bernuansa hangat dan ramah
            - agent_action: Metadata aksi tool (tool_name, query, observation, status)
            - agent_step_text: Catatan langkah perantara agen (untuk tampilan UI / status)
        """
        raw_text = (user_input or "").strip()
        if not raw_text:
            return llm_generate_fn(raw_text), None, None

        intent_data = detect_agent_intent(raw_text)
        intent = intent_data.get("intent", "none")
        params = intent_data.get("params", {})

        if intent == "none":
            # Percakapan santai biasa tanpa perlu alat eksternal
            reply = llm_generate_fn(raw_text)
            return reply, None, None

        tool_name = ""
        tool_desc = ""
        observation_text = ""
        structured_obs = None
        t_start = time.perf_counter()

        # Step 1: Eksekusi Tool Berdasarkan Intent
        if intent == "weather":
            tool_name = "weather_sat_check"
            locations = params.get("locations", ["Jakarta", "Tokyo"])
            tool_desc = f"Membuka koneksi satelit cuaca via Cloudflare 1.1.1.1 untuk lokasi: {', '.join(locations)}"
            res = check_weather(locations)
            observation_text = res.get("summary", "")
            structured_obs = res.get("data")

        elif intent == "search":
            tool_name = "google_web_search"
            query = params.get("query", raw_text)
            tool_desc = f"Membuka browser Mozilla & mencari di Google/Web via Cloudflare 1.1.1.1: '{query}'"
            res = search_google_web(query)
            observation_text = res.get("summary", "")
            structured_obs = res.get("results")

        elif intent == "browse":
            tool_name = "web_browser_reader"
            target_url = params.get("url", "")
            tool_desc = f"Membuka dan membaca halaman web via Mozilla Headers: {target_url}"
            res = open_and_read_webpage(target_url)
            title = res.get("title", "Halaman Web")
            body = res.get("content", "")
            observation_text = f"Judul Halaman: {title}\nIsi Teks:\n{body}"
            structured_obs = res

        elif intent == "math":
            tool_name = "safe_calculator"
            expr = params.get("expression", "")
            tool_desc = f"Mengeksekusi perhitungan matematika presisi: `{expr}`"
            res = calculate_math(expr)
            observation_text = res.get("summary", "")
            structured_obs = res.get("result")

        elif intent == "time":
            tool_name = "realtime_clock"
            tool_desc = "Memeriksa jam dan kalender dunia saat ini"
            res = get_current_time_info()
            observation_text = res.get("summary", "")
            structured_obs = res

        t_elapsed = round(time.perf_counter() - t_start, 2)

        agent_action = {
            "tool": tool_name,
            "description": tool_desc,
            "observation": observation_text,
            "details": structured_obs,
            "execution_time_sec": t_elapsed,
            "status": "success" if observation_text else "failed"
        }

        # Step 2: Format Konteks Observasi Nyata ke dalam Prompt Model Percakapan
        agent_context = (
            f"\n\n[Informasi / Fakta Web Nyata Real-time]:\n"
            f"{observation_text}\n\n"
            f"[Instruksi Karakter]:\n"
            f"1. Jawab pertanyaan Kakak secara akurat menggunakan fakta di atas.\n"
            f"2. Jangan pernah mengatakan 'loading', 'tunggu sebentar', atau pura-pura mengecek di HP karena datanya SUDAH ada di atas.\n"
            f"3. DILARANG KERAS menyertakan header teknis, badge, nama tool/alat, browser Mozilla, Cloudflare, atau awalan '> 🌐'. Sampaikan murni dengan suara dan kepribadian Shiro (adik perempuan manis/sayang).\n"
        )

        # Step 3: Sintesis Percakapan Shiro
        final_reply = llm_generate_fn(raw_text, agent_context=agent_context)
        final_reply = clean_response(final_reply)

        agent_step_text = f"🌐 **[AI Agent Web Tool]** *{tool_desc} ({t_elapsed}s)*"

        return final_reply, agent_action, agent_step_text

# Singleton Agent Executor
agent_executor = ShiroAgentExecutor()
