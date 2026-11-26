# -*- coding: utf-8 -*-
"""
Shiro Neural Inference Engine & Dynamic Pipeline
Executes prompt synthesis, multimodal ingestion, neural inference,
Server-Sent Events (SSE) token streaming, and telemetry broadcasting without canned fallback scripts.
"""

import os
import re
import json
import time
import queue
import base64
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Union, Generator

# Interval heartbeat SSE (detik) saat menunggu lock / prompt prefill agar Cloudflare Tunnel tidak timeout (batas 100s)
SSE_HEARTBEAT_INTERVAL = float(os.environ.get("SHIRO_SSE_PING_INTERVAL", "5.0"))

from shiro.config import CONTEXT_SIZE
from shiro.server_state import state
from shiro.models import (
    get_active_model_ctx,
    get_optimal_model_tokens,
    is_qwen38_27b_uncensored,
    get_model_display_name,
    resolve_lyra_tier,
    get_saved_lyra_tier,
    is_valid_lyra_tier,
)
from shiro.persona import (
    build_system_prompt,
    build_vtuber_system_prompt,
    build_custom_system_prompt,
    load_active_profiles
)
from shiro.nlp.emotion import detect_emotion_category
from shiro.nlp.typo import normalize_typos, get_typo_understanding_prompt
from shiro.llm.cleaner import clean_response, clean_vtuber_response
from shiro.pipeline.trace import global_pipeline_manager

def calculate_messages_tokens(messages: List[Dict[str, Any]], llm_instance: Any) -> int:
    """Menghitung perkiraan jumlah token dari daftar pesan secara thread-safe"""
    if not llm_instance:
        return sum(len(str(m.get('content', '')).split()) for m in messages)
    # Gunakan non-blocking lock agar tidak pernah balapan dengan llama_decode / llm.close()
    acquired = False
    try:
        if hasattr(llm_instance, 'tokenize'):
            acquired = state.llm_lock.acquire(blocking=False)
            if acquired:
                total = 0
                for m in messages:
                    c = m.get('content', '')
                    if isinstance(c, list):
                        for p in c:
                            if isinstance(p, dict) and p.get('type') == 'text':
                                total += len(llm_instance.tokenize(p.get('text', '').encode('utf-8')))
                    elif isinstance(c, str):
                        total += len(llm_instance.tokenize(c.encode('utf-8')))
                return total
    except Exception:
        pass
    finally:
        if acquired:
            try:
                state.llm_lock.release()
            except RuntimeError:
                pass
    total_est = 0
    for m in messages:
        s = str(m.get('content', ''))
        total_est += max(len(s.split()), len(s) // 3)
    return total_est

def _prepare_inference_payload(
    user_input: str,
    image_base64: Optional[Union[str, List[str]]] = None,
    images_base64: Optional[List[str]] = None,
    document_info: Optional[Dict[str, Any]] = None,
    api_version: str = "v1",
    custom_system_prompt: Optional[str] = None,
    incoming_messages: Optional[List[Dict[str, Any]]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None,
    include_reasoning: bool = False,
    max_tokens: Optional[int] = None,
    lyra_tier: Optional[str] = None,
    t_start_total: Optional[float] = None
) -> Dict[str, Any]:
    """
    Menyiapkan Node 1 s/d Node 4: Ingestion, Agent tools, Tone, Memory, Prompt synthesis, dan Token Budget.
    """
    if t_start_total is None:
        t_start_total = time.perf_counter()
    nodes = []
    llm = state.llm
    vision_chat_handler = state.vision_chat_handler
    memory = state.init_memory()
    web_reader = state.init_web_reader()

    raw_user_typed = (user_input or "").strip()
    active_model_path = getattr(llm, 'model_path', '') if hasattr(llm, 'model_path') else ""
    active_model_name = get_model_display_name(
        active_model_path,
        raw_fallback=os.path.basename(active_model_path).lower() if active_model_path else ""
    )
    has_vision = bool(getattr(llm, 'chat_handler', None) is not None or vision_chat_handler is not None)

    # -------------------------------------------------------------
    # NODE 1: Input Ingestion
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    all_images = []
    if isinstance(image_base64, list):
        all_images.extend(image_base64)
    elif image_base64:
        all_images.append(image_base64)
    if isinstance(images_base64, list):
        for img in images_base64:
            if img not in all_images:
                all_images.append(img)

    has_image = bool(all_images)
    is_video_stream = len(all_images) > 1
    has_doc = bool(document_info and document_info.get("text"))
    doc_name = document_info.get("filename", "Dokumen") if has_doc else None

    # AI Agent Autonomous Execution (Weather, Google/Web Search, Browser, Math via Cloudflare 1.1.1.1 & Mozilla)
    agent_action_data = None
    web_data = None
    web_prompt_addon = ""

    if raw_user_typed:
        try:
            from shiro.agent.tools import (
                detect_agent_intent,
                check_weather,
                search_google_web,
                open_and_read_webpage,
                calculate_math,
                get_current_time_info,
                take_web_screenshot,
                execute_powershell_command
            )
            agent_intent_res = detect_agent_intent(raw_user_typed, conversation_history=getattr(memory, 'short_term_history', None))
            agent_intent = agent_intent_res.get("intent", "none")
            agent_params = agent_intent_res.get("params", {})

            if agent_intent != "none":
                t_tool_start = time.perf_counter()
                tool_name = ""
                tool_desc = ""
                obs_summary = ""
                structured_obs = None

                if agent_intent == "weather":
                    tool_name = "weather_sat_check"
                    locs = agent_params.get("locations", ["Jakarta", "Tokyo"])
                    tool_desc = f"Membuka koneksi satelit cuaca via Cloudflare 1.1.1.1 untuk lokasi: {', '.join(locs)}"
                    w_res = check_weather(locs)
                    obs_summary = w_res.get("summary", "")
                    structured_obs = w_res.get("data")
                elif agent_intent == "search":
                    tool_name = "multi_source_web_research"
                    q = agent_params.get("query", raw_user_typed)
                    tool_desc = f"Riset multi-sumber adaptif & verifikasi silang: '{q}'"
                    try:
                        from shiro.web.realtime_intel import research, wrap_search_fn, default_fetcher
                        res_intel = research(
                            user_query=q,
                            search_fn=wrap_search_fn(search_google_web),
                            fetch_fn=default_fetcher
                        )
                        obs_summary = res_intel.summary_text
                        structured_obs = {
                            "topic": res_intel.topic,
                            "confidence": res_intel.confidence,
                            "independent_sources": res_intel.independent_sources_count,
                            "verified_facts": [
                                {"claim": f.claim, "status": f.status, "sources": f.supporting_sources}
                                for f in res_intel.verified_facts
                            ],
                            "storable_facts": res_intel.storable_facts()
                        }
                        web_prompt_addon = f"\n\n{res_intel.prompt_block}\n"
                    except Exception as e_intel:
                        print(f"[Research Error Fallback]: {e_intel}")
                        s_res = search_google_web(q)
                        obs_summary = s_res.get("summary", "")
                        structured_obs = s_res.get("results")
                elif agent_intent == "browse":
                    tool_name = "web_browser_reader"
                    target_url = agent_params.get("url", "")
                    tool_desc = f"Membuka dan membaca halaman web via Mozilla Headers: {target_url}"
                    b_res = open_and_read_webpage(target_url)
                    obs_summary = f"Judul Halaman: {b_res.get('title')}\nIsi Teks:\n{b_res.get('content')}"
                    structured_obs = b_res
                elif agent_intent == "screenshot":
                    tool_name = "web_screenshot"
                    target_url = agent_params.get("url", "")
                    tool_desc = f"Mengambil tangkapan layar website: {target_url}"
                    ss_res = take_web_screenshot(target_url)
                    obs_summary = ss_res.get("summary", "")
                    structured_obs = ss_res
                elif agent_intent == "powershell":
                    tool_name = "powershell_terminal"
                    ps_cmd = agent_params.get("command", "")
                    tool_desc = f"Mengeksekusi perintah PowerShell di PC: `{ps_cmd}`"
                    ps_res = execute_powershell_command(ps_cmd)
                    obs_summary = ps_res.get("summary", "")
                    structured_obs = ps_res
                elif agent_intent == "math":
                    tool_name = "safe_calculator"
                    expr = agent_params.get("expression", "")
                    tool_desc = f"Mengeksekusi perhitungan presisi: `{expr}`"
                    m_res = calculate_math(expr)
                    obs_summary = m_res.get("summary", "")
                    structured_obs = m_res.get("result")
                elif agent_intent == "time":
                    tool_name = "realtime_clock"
                    tool_desc = "Memeriksa jam dan kalender dunia saat ini"
                    t_res = get_current_time_info()
                    obs_summary = t_res.get("summary", "")
                    structured_obs = t_res

                t_tool_dur = round(time.perf_counter() - t_tool_start, 2)
                is_tool_success = bool(obs_summary)
                if isinstance(structured_obs, dict) and "success" in structured_obs:
                    is_tool_success = structured_obs["success"]

                agent_action_data = {
                    "tool": tool_name,
                    "description": tool_desc,
                    "observation": obs_summary,
                    "details": structured_obs,
                    "image_url": structured_obs.get("image_url") if isinstance(structured_obs, dict) else None,
                    "execution_time_sec": t_tool_dur,
                    "status": "success" if is_tool_success else "failed"
                }

                web_prompt_addon = (
                    f"\n\n[Informasi / Fakta Web Nyata Real-time]:\n"
                    f"{obs_summary}\n\n"
                    f"[Instruksi Karakter]:\n"
                    f"1. Jawab pertanyaan Kakak secara akurat menggunakan fakta di atas.\n"
                    f"2. Jangan pernah mengatakan 'loading', 'tunggu sebentar', atau pura-pura mengecek di HP karena datanya SUDAH ada di atas.\n"
                    f"3. DILARANG KERAS menyertakan header teknis, badge, nama tool/alat, browser Mozilla, Cloudflare, atau awalan '> 🌐'. Sampaikan murni dengan gaya bicara manis dan hangat khas Shiro.\n"
                )
        except Exception as e_agent:
            print(f"[Inference Agent Warning]: {e_agent}")

    t_input_dur = (time.perf_counter() - t0) * 1000
    summary_node1 = f"{len(raw_user_typed)} Karakter"
    if has_image:
        summary_node1 += f" • {len(all_images)} Frame Visual"
    if has_doc:
        summary_node1 += f" • Dokumen ({doc_name})"
    if agent_action_data:
        summary_node1 += f" • Agent Tool ({agent_action_data['tool']})"

    nodes.append({
        "id": "node_input",
        "name": "Input Ingestion",
        "type": "trigger",
        "icon": "ph-chat-circle-dots",
        "color": "#3b82f6",
        "status": "success",
        "duration_ms": round(t_input_dur, 2),
        "summary": summary_node1,
        "data_in": {
            "raw_text": raw_user_typed,
            "has_image": has_image,
            "frames_count": len(all_images),
            "has_doc": has_doc
        },
        "data_out": {
            "text_length": len(raw_user_typed),
            "is_video_sequence": is_video_stream
        }
    })

    if agent_action_data:
        nodes.append({
            "id": "node_agent_tool",
            "name": "AI Agent Tool Execution",
            "type": "tool",
            "icon": "ph-globe-simple",
            "color": "#10b981",
            "status": agent_action_data.get("status", "success"),
            "duration_ms": agent_action_data.get("execution_time_sec", 0) * 1000,
            "summary": f"{agent_action_data.get('tool')}: {agent_action_data.get('description')}",
            "data_in": {"user_query": raw_user_typed},
            "data_out": agent_action_data
        })

    # -------------------------------------------------------------
    # NODE 2: Emotion & Tone Classifier
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    user_emotion = detect_emotion_category(raw_user_typed) if raw_user_typed else "neutral"
    corrected_text, corrections = normalize_typos(raw_user_typed) if raw_user_typed else ("", [])
    had_typos = bool(corrections)
    typo_prompt_addon = get_typo_understanding_prompt(corrections)

    t_emo_dur = (time.perf_counter() - t0) * 1000
    nodes.append({
        "id": "node_emotion",
        "name": "Emotion & Tone Classifier",
        "type": "analyzer",
        "icon": "ph-heartbeat",
        "color": "#ec4899",
        "status": "success",
        "duration_ms": round(t_emo_dur, 2),
        "summary": f"{user_emotion.capitalize()}" + (" • Typo Handled" if had_typos else ""),
        "data_in": {"user_input": raw_user_typed},
        "data_out": {
            "detected_emotion": user_emotion,
            "typo_detected": had_typos,
            "interpreted_query": corrected_text if had_typos else raw_user_typed
        }
    })

    # -------------------------------------------------------------
    # NODE 3: Cognitive Memory & RDF Retrieval
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    facts = memory.knowledge_base.get("facts", []) if (memory and hasattr(memory, "knowledge_base")) else []
    from shiro.memory.gating import gate_facts
    relevant_facts = gate_facts(facts, raw_user_typed, has_image=has_image)
        
    traits = memory.user_profile.get("personality_traits", []) if (memory and hasattr(memory, "user_profile")) else []
    exemplars = memory.get_relevant_exemplars(raw_user_typed, max_count=2) if (not has_image and memory and hasattr(memory, "get_relevant_exemplars") and raw_user_typed) else []
    
    cross_session_addon = memory.get_cross_session_context(raw_user_typed) if (not has_image and memory and hasattr(memory, "get_cross_session_context") and raw_user_typed) else ""

    clean_context = []
    if incoming_messages and len(incoming_messages) > 1:
        for m in incoming_messages[:-1]:
            role = m.get("role", "")
            if role in ["user", "assistant"]:
                c = m.get("content", "")
                if isinstance(c, list):
                    c = " ".join([p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"]).strip()
                if c:
                    clean_context.append({"role": role, "content": c})
    elif memory and hasattr(memory, "short_term_history"):
        history_slice = list(memory.short_term_history)
        if history_slice and history_slice[-1].get("role") == "user" and history_slice[-1].get("content") == raw_user_typed:
            history_slice = history_slice[:-1]
        for m in history_slice:
            r = m.get("role", "")
            c = m.get("content", "")
            if r in ["user", "assistant"] and c:
                clean_context.append({"role": r, "content": str(c)})
    elif memory and hasattr(memory, "get_memory_context"):
        raw_context = list(memory.get_memory_context(limit=None))
        if raw_context and raw_context[-1].get("role") == "user" and raw_context[-1].get("content") == raw_user_typed:
            raw_context = raw_context[:-1]
        for m in raw_context:
            r = m.get("role", "")
            c = m.get("content", "")
            if r in ["user", "assistant"] and c:
                clean_context.append({"role": r, "content": str(c)})

    # Dynamic Token Budget Guard & Tier History Cap
    active_ctx = get_active_model_ctx(llm)
    active_model_path = getattr(llm, 'model_path', '') if hasattr(llm, 'model_path') else ''
    is_lyra_model = is_qwen38_27b_uncensored(active_model_path or active_model_name)
    lyra_tier_info = None
    if is_lyra_model:
        chosen_tier_id = lyra_tier if is_valid_lyra_tier(lyra_tier) else get_saved_lyra_tier()
        lyra_tier_info = resolve_lyra_tier(chosen_tier_id)
        max_turns = lyra_tier_info.get("max_history_turns")
        if isinstance(max_turns, int) and max_turns > 0 and len(clean_context) > max_turns:
            clean_context = clean_context[-max_turns:]
        _, model_max_out = get_optimal_model_tokens(
            active_model_path or active_model_name,
            tier_override=lyra_tier_info["id"]
        )
    else:
        _, model_max_out = get_optimal_model_tokens(active_model_path or active_model_name)
    
    reserved_budget = max(4096, min(16384, model_max_out + 512))
    max_history_tokens = max(1024, active_ctx - reserved_budget)
    while len(clean_context) > 1 and calculate_messages_tokens(clean_context, llm) > max_history_tokens:
        clean_context.pop(0)

    # Sanitisasi riwayat pesan (Context Anti-Poisoning):
    # Jika pengguna saat ini tidak menggunakan bahasa Inggris/asing, pastikan riwayat asisten yang meleset atau tercampur bahasa Inggris dinetralkan
    from shiro.llm.cleaner import is_user_input_foreign_or_english, contains_english_segments, translate_to_indonesian_fast
    is_user_english_query = bool(raw_user_typed and is_user_input_foreign_or_english(raw_user_typed))
    if not is_user_english_query:
        for idx_c, ctx_msg in enumerate(clean_context):
            if ctx_msg.get("role") == "assistant":
                c_str = ctx_msg.get("content", "")
                if contains_english_segments(c_str):
                    t_str = translate_to_indonesian_fast(c_str)
                    if t_str and len(t_str.strip()) > 5:
                        clean_context[idx_c]["content"] = t_str.strip()

    t_mem_dur = (time.perf_counter() - t0) * 1000
    nodes.append({
        "id": "node_memory",
        "name": "Cognitive Memory & RDF Retrieval",
        "type": "database",
        "icon": "ph-brain",
        "color": "#8b5cf6",
        "status": "success",
        "duration_ms": round(t_mem_dur, 2),
        "summary": f"{len(relevant_facts)} Fakta • {len(clean_context)} Riwayat",
        "data_in": {"query": raw_user_typed},
        "data_out": {
            "relevant_facts_count": len(relevant_facts),
            "context_turns": len(clean_context)
        }
    })

    # -------------------------------------------------------------
    # NODE 4: Dynamic Prompt Synthesizer
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    conversation_summary = ""
    if relevant_facts:
        conversation_summary = "\nFAKTA YANG DIINGAT:\n"
        for fact in relevant_facts:
            conversation_summary += f"- {fact.get('subject')}: {fact.get('predicate')} {fact.get('object')}\n"

    facts_summary = f"\nKARAKTERISTIK KAKAK: {', '.join(traits)}\n" if traits else ""
    exemplar_prompt = ""
    if exemplars:
        exemplar_prompt = "\nCONTOH DIALOG SEBELUMNYA:\n"
        for ex in exemplars:
            exemplar_prompt += f"Kakak: \"{ex.get('user')}\"\nShiro: \"{ex.get('assistant')}\"\n"

    doc_prompt_addon = ""
    if has_doc and document_info:
        from shiro.document.reader import build_document_prompt
        if is_qwen38_27b_uncensored(active_model_path or active_model_name) and active_ctx > 65536:
            doc_token_budget = max(20000, active_ctx - reserved_budget - 4096)
            max_doc_chars = min(3_000_000, doc_token_budget * 3)
        else:
            max_doc_chars = max(10000, min(60000, (active_ctx - 2000) * 3))
        doc_full_text = document_info.get("text", "")
        if len(doc_full_text) > max_doc_chars:
            doc_full_text = doc_full_text[:max_doc_chars] + f"\n\n... [Sisa teks dokumen dipotong karena melampaui batas {max_doc_chars} karakter]"
        doc_prompt_addon = build_document_prompt(
            {"filename": doc_name, "text": doc_full_text},
            user_query=raw_user_typed
        )

    tools_addon = ""
    if tools:
        try:
            tools_str = json.dumps(tools, indent=2, ensure_ascii=False)
            tools_addon = (
                f"\n\n### SISTEM TOOLS & FUNCTION CALLING:\n"
                f"Daftar tool yang tersedia:\n{tools_str}\n\n"
                f"Panduan: Jika memerlukan pemanggilan tool, format output JSON:\n"
                f"```json\n"
                f'{{"tool_calls": [{{"id": "call_1", "type": "function", "function": {{"name": "<nama_tool>", "arguments": {{<argumen>}}}}}}]}}\n'
                f"```\n"
            )
        except Exception:
            pass

    reasoning_addon = ""
    is_reasoning_enabled = bool(
        include_reasoning or 
        (reasoning_effort and str(reasoning_effort).lower() not in ["none", "false", "0"])
    )
    if is_reasoning_enabled:
        reasoning_addon = (
            "\n\n### MODE PENALARAN AKTIF:\n"
            "Uraikan proses penalaran logis Anda di dalam blok <think>...</think> sebelum memberikan jawaban akhir.\n"
        )

    ai_name, custom_persona, user_name, user_context = load_active_profiles()
    if custom_system_prompt and custom_system_prompt.strip():
        custom_persona = custom_system_prompt.strip()

    visual_guidance_addon = ""
    if has_image:
        visual_guidance_addon = (
            f"\n\n### PANDUAN PENGAMATAN GAMBAR BARU:\n"
            f"- {user_name} sedang melampirkan berkas gambar BARU pada giliran pesan ini.\n"
            f"- Amati dan baca informasi, teks, diagram, serta objek pada gambar baru ini secara teliti dan langsung.\n"
            f"- DILARANG KERAS mengaitkan atau berasumsi bahwa gambar baru ini adalah situs web, link, atau halaman dari percakapan masa lalu jika tidak disebutkan secara eksplisit oleh {user_name}.\n"
        )

    time_ctx_addon = ""
    try:
        from shiro.web.realtime_intel import time_prompt_block
        time_ctx_addon = f"\n\n{time_prompt_block()}\n"
    except Exception:
        pass

    if api_version == "v2":
        system_prompt = build_vtuber_system_prompt(
            owner_name=user_name,
            custom_instruction=custom_persona
        ) + tools_addon + reasoning_addon + time_ctx_addon + web_prompt_addon + doc_prompt_addon + visual_guidance_addon
    elif api_version == "v3":
        base_p = custom_system_prompt or custom_persona or ""
        system_prompt = build_custom_system_prompt(base_p) + tools_addon + reasoning_addon + time_ctx_addon + web_prompt_addon + doc_prompt_addon + visual_guidance_addon
    else:
        system_prompt = build_system_prompt(
            home_location=getattr(state, "home_location", "Pondok Kayu"),
            conversation_summary=conversation_summary,
            facts_summary=facts_summary,
            exemplar_prompt=exemplar_prompt,
            web_prompt_addon=web_prompt_addon,
            typo_prompt_addon=typo_prompt_addon,
            document_prompt_addon=doc_prompt_addon,
            cross_session_addon=cross_session_addon,
            assistant_name=ai_name,
            custom_persona=custom_persona,
            user_name=user_name,
            user_context=user_context
        ) + tools_addon + reasoning_addon + time_ctx_addon + visual_guidance_addon

    # Mode Kecepatan & Penalaran khusus per-tier ShiroHaru-Lyra-Agent
    lyra_thinking_mode = lyra_tier_info.get("thinking_mode", "standard") if lyra_tier_info else None
    if is_lyra_model and not is_reasoning_enabled and api_version != "v3":
        if lyra_thinking_mode == "off":
            system_prompt += (
                "\n\n[Mode Cepat ShiroHaru-Lyra Low]: Jawab cepat, padat, langsung ke inti, "
                "dan tetap fungsional tanpa bertele-tele."
            )
        elif lyra_thinking_mode == "light":
            system_prompt += (
                "\n\n[Mode Seimbang ShiroHaru-Lyra Medium]: Jawab langsung dengan cepat, jelas, "
                "dan lengkap tanpa proses berpikir berpanjang-panjang."
            )

    visual_evidence_text = ""
    has_vision_handler = bool(
        getattr(state, "vision_chat_handler", None) or 
        (llm and getattr(llm, "chat_handler", None))
    )
    if has_image:
        is_english_query = False
        is_japanese_query = False
        if raw_user_typed:
            from shiro.llm.cleaner import is_user_input_foreign_or_english, is_japanese_text
            is_japanese_query = is_japanese_text(raw_user_typed)
            if not is_japanese_query and is_user_input_foreign_or_english(raw_user_typed):
                is_english_query = True
        
        if is_english_query:
            lang_fact_rule = f"\n[LANGUAGE & FACTS]: Answer in English as requested by {user_name}. Observe the photo factually without fabricating fictional ages or relations."
        elif is_japanese_query:
            lang_fact_rule = f"\n[言語と事実のルール]: {user_name}に合わせて日本語で自然に答えてください。写真にない架空の年齢や関係を捏造しないでください。"
        else:
            lang_fact_rule = f"\n[PANDUAN BAHASA & FAKTA]: Jawab dalam BAHASA INDONESIA santai khas {ai_name}. Amati foto apa adanya secara faktual tanpa mengarang umur atau relasi fiktif."

        if has_vision_handler:
            content_parts = []
            for img_b64 in all_images:
                data_uri = img_b64 if img_b64.startswith("data:") else f"data:image/jpeg;base64,{img_b64}"
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": data_uri}
                })
            
            prompt_parts = []
            if has_doc:
                prompt_parts.append(f"[Melampirkan Dokumen: {doc_name}]")
            if raw_user_typed:
                prompt_parts.append(raw_user_typed)
            else:
                prompt_parts.append(f"{ai_name}, coba perhatikan dan jelaskan gambar visual yang {user_name} lampirkan ini ya!")
            prompt_parts.append(lang_fact_rule)
            
            content_parts.append({
                "type": "text",
                "text": "\n".join(prompt_parts)
            })
            user_turn_msg = {"role": "user", "content": content_parts}
        else:
            t_vis = time.perf_counter()
            from shiro.agent.moe_router import get_orchestrator
            moe = get_orchestrator()
            if moe.should_route(has_image=True, chat_has_vision=False):
                evidence = moe.extract_visual_evidence(all_images, raw_user_typed)
            else:
                from shiro.vision.bridge import extract_local_image_text_and_info
                ocr = extract_local_image_text_and_info(all_images)
                evidence = {"ok": bool(ocr), "source": "ocr",
                            "evidence_text": ocr or "Berkas gambar terlampir (tidak ada teks terdeteksi)."}
            visual_evidence_text = evidence.get("evidence_text", "")
            source_label = "Visual Cortex Expert" if evidence.get("source") == "vl_expert" else "OCR lokal"
            nodes.append({
                "id": "node_moe_vision",
                "name": "MoE Visual Cortex Expert",
                "type": "ai_model",
                "icon": "ph-eye",
                "color": "#22c55e",
                "status": "success" if evidence.get("ok") else "warning",
                "duration_ms": round((time.perf_counter() - t_vis) * 1000, 2),
                "summary": f"{source_label}" + (f" • {evidence.get('expert')}" if evidence.get("expert") else ""),
                "data_in": {"images": len(all_images)},
                "data_out": {"source": evidence.get("source"), "evidence": visual_evidence_text[:2000]}
            })
            user_lines = [
                f"[OBSERVASI VISUAL GAMBAR YANG DILAMPIRKAN {user_name.upper()} — sumber: {source_label}]:",
                visual_evidence_text,
                lang_fact_rule,
                f"\n{raw_user_typed}" if raw_user_typed else f"{ai_name}, coba jelaskan apa yang terlihat pada gambar di atas."
            ]
            if has_doc:
                user_lines.insert(0, f"[Melampirkan Dokumen: {doc_name}]")
            user_text = "\n".join(user_lines)
            user_turn_msg = {"role": "user", "content": user_text}
    else:
        parts_user = []
        if has_doc:
            parts_user.append(f"[Melampirkan Dokumen: {doc_name}]")

        if raw_user_typed:
            parts_user.append(raw_user_typed)
        elif has_doc:
            parts_user.append(f"Shiro, tolong pelajari dokumen '{doc_name}' yang Kakak lampirkan ya!")
        else:
            parts_user.append(" ")

        # Anti-drift anchor: kunci bahasa sesuai bahasa pengguna dan larang code-switching di tengah kalimat/narasi
        if not is_user_english_query and raw_user_typed:
            parts_user.append(
                f"\n[Pedoman Bahasa]: {user_name} berbicara dalam Bahasa Indonesia. "
                f"Jawab 100% dalam Bahasa Indonesia santai khas {ai_name} dari awal sampai akhir. "
                f"DILARANG KERAS mencampur atau beralih ke Bahasa Inggris pada narasi tindakan *...* maupun dialog "
                f"(jangan menulis frasa seperti 'my head against his shoulder', 'Shiro here', 'you don\'t gotta', 'swallows hard', 'whispers', dll; gunakan Bahasa Indonesia alami sepenuhnya)."
            )

        user_text = "\n".join(parts_user)
        user_turn_msg = {"role": "user", "content": user_text}

    # Soft-switch resmi Qwen3/Qwen3.8 (/no_think) pada mode Low & Medium agar respons langsung keluar tanpa blok <think> panjang
    if is_lyra_model and not is_reasoning_enabled and api_version != "v3" and lyra_thinking_mode in ("off", "light"):
        c_val = user_turn_msg.get("content")
        if isinstance(c_val, list):
            new_parts = list(c_val)
            appended = False
            for idx_p in range(len(new_parts) - 1, -1, -1):
                if isinstance(new_parts[idx_p], dict) and new_parts[idx_p].get("type") == "text":
                    new_parts[idx_p] = dict(new_parts[idx_p])
                    new_parts[idx_p]["text"] = str(new_parts[idx_p].get("text", "")) + "\n/no_think"
                    appended = True
                    break
            if not appended:
                new_parts.append({"type": "text", "text": "/no_think"})
            user_turn_msg["content"] = new_parts
        else:
            user_turn_msg["content"] = str(c_val or "") + "\n/no_think"

    msgs = [{"role": "system", "content": system_prompt}]
    msgs.extend(clean_context)
    msgs.append(user_turn_msg)

    # Dynamic Token Budget & Context Safety Guard
    prompt_tokens_est = calculate_messages_tokens(msgs, llm)
    while clean_context and (prompt_tokens_est + 512 > active_ctx):
        clean_context.pop(0)
        msgs = [{"role": "system", "content": system_prompt}] + clean_context + [user_turn_msg]
        prompt_tokens_est = calculate_messages_tokens(msgs, llm)

    t_prompt_dur = (time.perf_counter() - t0) * 1000
    nodes.append({
        "id": "node_prompt",
        "name": "Dynamic Prompt Synthesizer",
        "type": "transform",
        "icon": "ph-brackets-curly",
        "color": "#06b6d4",
        "status": "success",
        "duration_ms": round(t_prompt_dur, 2),
        "summary": f"{len(msgs)} Pesan ({api_version.upper()})",
        "data_in": {
            "api_version": api_version,
            "has_tools": bool(tools),
            "is_reasoning_enabled": is_reasoning_enabled
        },
        "data_out": {
            "system_prompt_chars": len(system_prompt),
            "total_messages": len(msgs)
        }
    })

    # Generation Parameters
    if max_tokens:
        desired_max = int(max_tokens)
    elif is_lyra_model:
        desired_max = int(model_max_out)
    elif api_version == "v2":
        desired_max = max(model_max_out, 4096)
    elif is_reasoning_enabled or tools:
        desired_max = max(model_max_out, 8192)
    else:
        desired_max = max(model_max_out, 8192)

    remaining_space = max(256, active_ctx - prompt_tokens_est - 128)
    max_output_tokens = min(desired_max, remaining_space)

    stop_tokens = [
        "<|im_end|>", "<|im_start|>", "<|eot_id|>", "<|end|>", "<|end_of_text|>",
        "\nUser:", "\nKakak:", "\nuser:", "\nAssistant:", "\nassistant:",
        "\n<|im_start|>user", "\n<|im_start|>assistant"
    ]
    if not is_reasoning_enabled:
        stop_tokens.extend(["\nOkay, let me", "\nThe user is"])

    tier_top_k = int(lyra_tier_info.get("top_k", 40)) if lyra_tier_info else 40
    gen_params = {
        "temperature": 0.45 if has_image else (0.65 if api_version == "v2" else 0.55),
        "repeat_penalty": 1.08,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "top_p": 0.85,
        "top_k": tier_top_k,
        "max_tokens": max_output_tokens,
        "stop": stop_tokens
    }

    call_kwargs = dict(gen_params)

    return {
        "t_start_total": t_start_total,
        "nodes": nodes,
        "llm": llm,
        "active_model_name": active_model_name,
        "lyra_tier_info": lyra_tier_info,
        "raw_user_typed": raw_user_typed,
        "msgs": msgs,
        "call_kwargs": call_kwargs,
        "gen_params": gen_params,
        "active_ctx": active_ctx,
        "user_turn_msg": user_turn_msg,
        "system_prompt": system_prompt,
        "all_images": all_images,
        "has_image": has_image,
        "visual_evidence_text": visual_evidence_text,
        "web_prompt_addon": web_prompt_addon,
        "agent_action_data": agent_action_data,
        "web_data": web_data,
        "api_version": api_version,
        "tools": tools,
        "tool_choice": tool_choice,
        "is_reasoning_enabled": is_reasoning_enabled,
        "doc_name": doc_name,
        "ai_name": ai_name,
        "user_name": user_name,
        "custom_persona": custom_persona
    }

def _finalize_inference_output(
    prep: Dict[str, Any],
    raw_reply: str,
    t_llm_dur: float,
    res: Optional[Dict[str, Any]] = None,
    grounding_info: Optional[Dict[str, Any]] = None
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Menjalankan Node 5 s/d Node 8: Filter, State Persistence Sync, dan Response Delivery Stream.
    """
    nodes = prep["nodes"]
    raw_user_typed = prep["raw_user_typed"]
    active_model_name = prep["active_model_name"]
    gen_params = prep["gen_params"]
    api_version = prep["api_version"]
    agent_action_data = prep["agent_action_data"]
    web_data = prep["web_data"]
    t_start_total = prep["t_start_total"]

    memory = state.init_memory()
    web_reader = state.init_web_reader()

    raw_reply = (raw_reply or "").strip()
    if grounding_info is None:
        grounding_info = {"checked": False, "ungrounded": [], "regenerated": False}

    finish_reason = "stop"
    usage = {}
    if res and isinstance(res, dict) and res.get('choices'):
        finish_reason = res['choices'][0].get('finish_reason', 'stop')
        usage = res.get('usage', {})

    nodes.append({
        "id": "node_llm",
        "name": "Neural Inference Engine",
        "type": "ai_model",
        "icon": "ph-cpu",
        "color": "#f59e0b",
        "status": "success",
        "duration_ms": round(t_llm_dur, 2),
        "summary": f"{round(t_llm_dur)}ms • {active_model_name or 'Qwen'}",
        "data_in": {
            "model": active_model_name or "LLM",
            "parameters": gen_params
        },
        "data_out": {
            "raw_response": raw_reply,
            "finish_reason": finish_reason,
            "usage": usage,
            "grounding": grounding_info
        }
    })

    # -------------------------------------------------------------
    # NODE 6: Neural Filter & Output Processing
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    native_tool_calls = None
    if res and isinstance(res, dict) and res.get('choices'):
        native_tool_calls = res['choices'][0].get('message', {}).get('tool_calls', None)
    parsed_tool_calls = list(native_tool_calls) if native_tool_calls else []

    reasoning_content = None
    think_match = re.search(r'<think>(.*?)</think>', raw_reply, flags=re.DOTALL | re.IGNORECASE)
    if think_match:
        reasoning_content = think_match.group(1).strip()
        raw_reply = re.sub(r'<think>.*?</think>', '', raw_reply, flags=re.DOTALL | re.IGNORECASE).strip()
    elif "<think>" in raw_reply.lower():
        parts = re.split(r'<think>', raw_reply, flags=re.IGNORECASE)
        if len(parts) > 1:
            reasoning_content = parts[1].strip()
            raw_reply = parts[0].strip()

    if not raw_reply and reasoning_content:
        raw_reply = reasoning_content

    if not parsed_tool_calls and ("tool_calls" in raw_reply or "```json" in raw_reply):
        json_tc_match = re.search(r'```(?:json)?\s*(\{.*?"tool_calls".*?\})\s*```', raw_reply, flags=re.DOTALL)
        if not json_tc_match:
            json_tc_match = re.search(r'(\{.*?"tool_calls"\s*:\s*\[.*?\].*?\})', raw_reply, flags=re.DOTALL)
        if json_tc_match:
            try:
                tc_dict = json.loads(json_tc_match.group(1))
                if "tool_calls" in tc_dict and isinstance(tc_dict["tool_calls"], list):
                    parsed_tool_calls = tc_dict["tool_calls"]
                    raw_reply = raw_reply.replace(json_tc_match.group(0), "").strip()
            except Exception:
                pass

    if api_version == "v2":
        cleaned_reply = clean_vtuber_response(raw_reply, raw_user_typed)
    else:
        cleaned_reply = clean_response(raw_reply, assistant_name=prep.get("ai_name", "Shiro"), user_input=raw_user_typed)

    if not cleaned_reply and raw_reply:
        cleaned_reply = raw_reply.strip()

    t_filter_dur = (time.perf_counter() - t0) * 1000
    nodes.append({
        "id": "node_filter",
        "name": "Neural Output Filter",
        "type": "filter",
        "icon": "ph-shield-check",
        "color": "#10b981",
        "status": "success",
        "duration_ms": round(t_filter_dur, 2),
        "summary": "Murni Neural Model",
        "data_in": {"raw_length": len(raw_reply)},
        "data_out": {
            "cleaned_output": cleaned_reply,
            "has_reasoning": bool(reasoning_content),
            "tool_calls_count": len(parsed_tool_calls)
        }
    })

    # -------------------------------------------------------------
    # NODE 7: State & Persistence Sync
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    current_mood = memory.agent_persona.get("current_mood", "Neutral") if memory else "Neutral"
    emo_state = memory.agent_persona.get("emotional_state", {}) if memory else {}

    if web_data and memory:
        try:
            web_reader.integrate_web_knowledge(
                memory_manager=memory,
                user_input=raw_user_typed,
                assistant_reply=cleaned_reply,
                web_title=web_data["title"],
                url_or_query=web_data["source"],
                web_content=web_data["content"]
            )
        except Exception as e_web_save:
            print(f"[Inference] Warning integrating web knowledge: {e_web_save}")

    if memory and agent_action_data and agent_action_data.get("observation"):
        try:
            from shiro.web.reader import integrate_web_knowledge
            storable_facts = []
            if isinstance(agent_action_data.get("details"), dict):
                storable_facts = agent_action_data["details"].get("storable_facts", [])

            if storable_facts:
                for sf in storable_facts:
                    integrate_web_knowledge(
                        memory,
                        user_input=raw_user_typed,
                        assistant_reply=cleaned_reply,
                        web_title=sf.get("subject", "Fakta Riset"),
                        url_or_query=", ".join(sf.get("sources", []))[:100],
                        web_content=sf.get("object", "")
                    )
            elif agent_action_data.get("tool") != "multi_source_web_research":
                integrate_web_knowledge(
                    memory,
                    user_input=raw_user_typed,
                    assistant_reply=cleaned_reply,
                    web_title=agent_action_data.get("tool", "AI Agent"),
                    url_or_query=agent_action_data.get("description", ""),
                    web_content=agent_action_data.get("observation", "")
                )
        except Exception as e_web_save:
            print(f"[Inference] Warning integrating web knowledge: {e_web_save}")
    elif memory and web_data:
        try:
            from shiro.web.reader import integrate_web_knowledge
            integrate_web_knowledge(
                memory,
                user_input=raw_user_typed,
                assistant_reply=cleaned_reply,
                web_title=web_data["title"],
                url_or_query=web_data["source"],
                web_content=web_data["content"]
            )
        except Exception as e_web_save:
            print(f"[Inference] Warning integrating web knowledge: {e_web_save}")

    t_state_dur = (time.perf_counter() - t0) * 1000
    nodes.append({
        "id": "node_state",
        "name": "State & Persistence Sync",
        "type": "persistence",
        "icon": "ph-database",
        "color": "#6366f1",
        "status": "success",
        "duration_ms": round(t_state_dur, 2),
        "summary": f"Mood: {current_mood}",
        "data_in": {"reply_chars": len(cleaned_reply)},
        "data_out": {
            "current_mood": current_mood,
            "emotional_state": emo_state
        }
    })

    # -------------------------------------------------------------
    # NODE 8: Response Delivery Stream
    # -------------------------------------------------------------
    t_total_dur = (time.perf_counter() - t_start_total) * 1000
    delivery_reply = cleaned_reply

    nodes.append({
        "id": "node_output",
        "name": "Response Delivery Stream",
        "type": "output",
        "icon": "ph-paper-plane-right",
        "color": "#3b82f6",
        "status": "success",
        "duration_ms": 0.5,
        "summary": f"{round(t_total_dur)}ms Latency",
        "data_in": {"chars_count": len(delivery_reply)},
        "data_out": {
            "final_reply": delivery_reply,
            "total_duration_ms": round(t_total_dur, 2)
        }
    })

    trace = {
        "id": f"trace-{int(time.time()*1000)}",
        "timestamp": datetime.now().isoformat(),
        "status": "completed",
        "total_duration_ms": round(t_total_dur, 2),
        "user_input": raw_user_typed,
        "reply": delivery_reply,
        "agent_action": agent_action_data,
        "nodes": nodes
    }
    global_pipeline_manager.broadcast(trace)

    details = {
        "reasoning_content": reasoning_content,
        "tool_calls": parsed_tool_calls,
        "finish_reason": "tool_calls" if parsed_tool_calls else finish_reason,
        "trace": trace,
        "agent_action": agent_action_data
    }
    return delivery_reply, trace, details

def get_shiro_reply(
    user_input: str,
    image_base64: Optional[Union[str, List[str]]] = None,
    images_base64: Optional[List[str]] = None,
    document_info: Optional[Dict[str, Any]] = None,
    return_trace: bool = False,
    return_details: bool = False,
    api_version: str = "v1",
    custom_system_prompt: Optional[str] = None,
    incoming_messages: Optional[List[Dict[str, Any]]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None,
    include_reasoning: bool = False,
    max_tokens: Optional[int] = None,
    lyra_tier: Optional[str] = None
) -> Union[str, Tuple[str, Any]]:
    """
    Eksekusi pipeline kognitif Shiro (Synchronous Non-Streaming).
    """
    t_start_total = time.perf_counter()
    try:
        prep = _prepare_inference_payload(
            user_input=user_input,
            image_base64=image_base64,
            images_base64=images_base64,
            document_info=document_info,
            api_version=api_version,
            custom_system_prompt=custom_system_prompt,
            incoming_messages=incoming_messages,
            tools=tools,
            tool_choice=tool_choice,
            reasoning_effort=reasoning_effort,
            include_reasoning=include_reasoning,
            max_tokens=max_tokens,
            lyra_tier=lyra_tier,
            t_start_total=t_start_total
        )
        llm = prep["llm"]
        msgs = prep["msgs"]
        call_kwargs = prep["call_kwargs"]
        user_turn_msg = prep["user_turn_msg"]
        system_prompt = prep["system_prompt"]
        all_images = prep["all_images"]
        raw_user_typed = prep["raw_user_typed"]
        has_image = prep["has_image"]
        visual_evidence_text = prep["visual_evidence_text"]
        web_prompt_addon = prep["web_prompt_addon"]
        tools = prep["tools"]
        tool_choice = prep["tool_choice"]

        if llm is None:
            raise RuntimeError("Model LLM belum dimuat di memori server.")

        t0 = time.perf_counter()
        with state.llm_lock:
            try:
                if tools:
                    try:
                        res = llm.create_chat_completion(
                            messages=msgs,
                            tools=tools,
                            tool_choice=tool_choice,
                            **call_kwargs
                        )
                    except (TypeError, Exception):
                        res = llm.create_chat_completion(messages=msgs, **call_kwargs)
                else:
                    res = llm.create_chat_completion(messages=msgs, **call_kwargs)
            except Exception as inf_err:
                err_str = str(inf_err).lower()
                if "exceed" in err_str and ("context" in err_str or "token" in err_str or "window" in err_str):
                    emergency_msgs = [{"role": "system", "content": system_prompt[:1200]}]
                    emergency_msgs.append(user_turn_msg)
                    res = llm.create_chat_completion(messages=emergency_msgs, **call_kwargs)
                elif has_image and any(k in err_str for k in ["image", "list", "content", "dict", "str", "iterable"]):
                    from shiro.vision.bridge import extract_local_image_text_and_info
                    local_obs = extract_local_image_text_and_info(all_images) or "Gambar visual terlampir"
                    text_user = f"[Pengamatan Gambar Visual: {local_obs}]\n{raw_user_typed}"
                    msgs[-1] = {"role": "user", "content": text_user}
                    res = llm.create_chat_completion(messages=msgs, **call_kwargs)
                else:
                    raise inf_err

            raw_reply = res['choices'][0]['message'].get('content', '') or ''
            raw_reply = raw_reply.strip()

            grounding_info = {"checked": False, "ungrounded": [], "regenerated": False}
            if has_image and raw_reply:
                from shiro.memory.gating import find_ungrounded_domains
                grounding_info["checked"] = True
                ungrounded = find_ungrounded_domains(raw_reply, [raw_user_typed, visual_evidence_text, web_prompt_addon])
                grounding_info["ungrounded"] = ungrounded
                if ungrounded:
                    correction = (
                        f"\n\n[KOREKSI]: Jawaban sebelumnya menyebut {', '.join(ungrounded)} yang TIDAK ada di gambar maupun pesan Kakak. "
                        "Jawab ulang hanya berdasarkan isi gambar ini."
                    )
                    fixed_turn = dict(user_turn_msg)
                    if isinstance(fixed_turn.get("content"), list):
                        fixed_turn["content"] = list(fixed_turn["content"]) + [{"type": "text", "text": correction}]
                    else:
                        fixed_turn["content"] = str(fixed_turn.get("content", "")) + correction
                    try:
                        res_retry = llm.create_chat_completion(messages=msgs[:-1] + [fixed_turn], **call_kwargs)
                        retry_reply = (res_retry['choices'][0]['message'].get('content', '') or '').strip()
                        if retry_reply:
                            res, raw_reply = res_retry, retry_reply
                            grounding_info["regenerated"] = True
                    except Exception as e_retry:
                        print(f"[Grounding Verifier] Regenerasi gagal: {e_retry}")

        t_llm_dur = (time.perf_counter() - t0) * 1000
        delivery_reply, trace, details = _finalize_inference_output(
            prep=prep,
            raw_reply=raw_reply,
            t_llm_dur=t_llm_dur,
            res=res,
            grounding_info=grounding_info
        )

        if return_details:
            return delivery_reply, details
        if return_trace:
            return delivery_reply, trace
        return delivery_reply

    except Exception as e:
        print(f"[Inference Error]: {e}")
        if api_version == "v2":
            err_msg = f'[Sad] "エラーが発生しました: {str(e)[:40]}"'
        elif api_version == "v3":
            err_msg = f"Error processing request: {str(e)[:80]}"
        else:
            err_msg = f"*menatap cemas* Maaf Kakak... sistem AI mengalami kendala teknis: {str(e)[:80]}"

        err_trace = {
            "id": f"trace-err-{int(time.time()*1000)}",
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "total_duration_ms": round((time.perf_counter() - t_start_total) * 1000, 2),
            "user_input": (user_input or "").strip(),
            "reply": err_msg,
            "error": str(e),
            "nodes": []
        }
        global_pipeline_manager.broadcast(err_trace)

        if return_details:
            return err_msg, {
                "reasoning_content": None,
                "tool_calls": [],
                "finish_reason": "stop",
                "trace": err_trace
            }
        if return_trace:
            return err_msg, err_trace
        return err_msg

def stream_shiro_reply(
    user_input: str,
    image_base64: Optional[Union[str, List[str]]] = None,
    images_base64: Optional[List[str]] = None,
    document_info: Optional[Dict[str, Any]] = None,
    api_version: str = "v1",
    custom_system_prompt: Optional[str] = None,
    incoming_messages: Optional[List[Dict[str, Any]]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None,
    include_reasoning: bool = False,
    max_tokens: Optional[int] = None,
    lyra_tier: Optional[str] = None
) -> Generator[Dict[str, Any], None, None]:
    """
    Eksekusi streaming token neural real-time (Server-Sent Events generator).
    Yields events:
    - {'type': 'status', 'status': '...'}
    - {'type': 'agent_action', 'agent_action': ...}
    - {'type': 'token', 'token': '...'}
    - {'type': 'ping'}
    - {'type': 'done', 'reply': '...', 'trace': ...}
    """
    t_start_total = time.perf_counter()
    try:
        # Pre-detect intent untuk memancarkan status langsung ke antarmuka pengguna
        raw_user_typed = (user_input or "").strip()
        if raw_user_typed:
            try:
                from shiro.agent.tools import detect_agent_intent
                mem_inst = state.init_memory()
                intent_info = detect_agent_intent(raw_user_typed, conversation_history=getattr(mem_inst, 'short_term_history', None))
                intent = intent_info.get("intent", "none")
                if intent == "screenshot":
                    target_u = intent_info.get("params", {}).get("url", "")
                    yield {"type": "status", "status": f"Sedang mengambil tangkapan layar website ({target_u or 'web'})..."}
                elif intent == "search":
                    q = intent_info.get("params", {}).get("query", raw_user_typed)
                    yield {"type": "status", "status": f"Sedang mencari di Google/Web: '{q[:32]}'..."}
                elif intent == "browse":
                    target_u = intent_info.get("params", {}).get("url", "")
                    yield {"type": "status", "status": f"Sedang membaca isi halaman web: {target_u[:32]}..."}
                elif intent == "weather":
                    yield {"type": "status", "status": "Sedang memeriksa data satelit cuaca..."}
                elif intent == "powershell":
                    yield {"type": "status", "status": "Sedang menjalankan perintah terminal PC..."}
                elif intent == "math":
                    yield {"type": "status", "status": "Sedang menghitung kalkulasi matematika..."}
                elif intent == "time":
                    yield {"type": "status", "status": "Sedang mengecek jam dan kalender dunia..."}
                else:
                    try:
                        from shiro.persona import load_active_profiles
                        _ai_name, _, _, _ = load_active_profiles()
                    except Exception:
                        _ai_name = "Shiro"
                    yield {"type": "status", "status": f"{_ai_name} sedang berpikir..."}
            except Exception:
                yield {"type": "status", "status": "Sedang berpikir..."}
        else:
            try:
                from shiro.persona import load_active_profiles
                _ai_name, _, _, _ = load_active_profiles()
            except Exception:
                _ai_name = "Shiro"
            yield {"type": "status", "status": f"{_ai_name} sedang memproses berkas/gambar..."}

        prep = _prepare_inference_payload(
            user_input=user_input,
            image_base64=image_base64,
            images_base64=images_base64,
            document_info=document_info,
            api_version=api_version,
            custom_system_prompt=custom_system_prompt,
            incoming_messages=incoming_messages,
            tools=tools,
            tool_choice=tool_choice,
            reasoning_effort=reasoning_effort,
            include_reasoning=include_reasoning,
            max_tokens=max_tokens,
            lyra_tier=lyra_tier,
            t_start_total=t_start_total
        )
        if prep.get("agent_action_data"):
            yield {"type": "agent_action", "agent_action": prep["agent_action_data"]}

        llm = prep["llm"]
        msgs = prep["msgs"]
        call_kwargs = dict(prep["call_kwargs"])
        is_reasoning_enabled = prep["is_reasoning_enabled"]

        if llm is None:
            raise RuntimeError("Model LLM belum dimuat di memori server.")

        t0 = time.perf_counter()
        raw_reply = ""
        ping_interval = max(0.05, float(SSE_HEARTBEAT_INTERVAL))
        last_ping_time = time.perf_counter()

        # Kirim heartbeat ping awal agar Cloudflare Tunnel tetap hidup
        yield {"type": "ping"}

        # Serialisasi akses ke llama_context via global lock (mencegah GGML_ASSERT / SIGABRT paralel)
        # Sambil menunggu lock, terus kirim heartbeat ping berkala agar koneksi tunnel tidak terputus
        lock_acquired = state.llm_lock.acquire(blocking=False)
        if not lock_acquired:
            yield {"type": "status", "status": "Shiro sedang menyelesaikan proses sebelumnya, mohon tunggu sebentar..."}
            wait_last_ping = time.perf_counter()
            while not lock_acquired:
                lock_acquired = state.llm_lock.acquire(timeout=min(0.5, ping_interval))
                if not lock_acquired:
                    now_wait = time.perf_counter()
                    if now_wait - wait_last_ping >= ping_interval:
                        yield {"type": "ping"}
                        wait_last_ping = now_wait

        # Jalankan inferensi llama.cpp pada worker thread terpisah agar generator SSE bisa terus
        # memancarkan ': ping' setiap beberapa detik selama prompt prefill (mencegah timeout 100s Cloudflare)
        chunk_queue: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        cancel_event = threading.Event()
        worker_started = False

        def _llm_stream_worker():
            stream_iter = None
            try:
                stream_kwargs = dict(call_kwargs)
                stream_kwargs["stream"] = True
                try:
                    if tools:
                        try:
                            stream_iter = llm.create_chat_completion(
                                messages=msgs,
                                tools=tools,
                                tool_choice=tool_choice,
                                **stream_kwargs
                            )
                        except (TypeError, Exception):
                            stream_iter = llm.create_chat_completion(messages=msgs, **stream_kwargs)
                    else:
                        stream_iter = llm.create_chat_completion(messages=msgs, **stream_kwargs)

                    for ch in stream_iter:
                        if cancel_event.is_set():
                            break
                        chunk_queue.put(("chunk", ch))
                except Exception as e_stream_inner:
                    if cancel_event.is_set():
                        return
                    print(f"[Inference Stream Fallback]: {e_stream_inner}")
                    # Fallback jika model/wrapper tidak mendukung generator stream=True
                    if tools:
                        try:
                            res_sync = llm.create_chat_completion(
                                messages=msgs,
                                tools=tools,
                                tool_choice=tool_choice,
                                **call_kwargs
                            )
                        except (TypeError, Exception):
                            res_sync = llm.create_chat_completion(messages=msgs, **call_kwargs)
                    else:
                        res_sync = llm.create_chat_completion(messages=msgs, **call_kwargs)
                    if not cancel_event.is_set():
                        chunk_queue.put(("sync_result", res_sync))
            except Exception as e_worker:
                if not cancel_event.is_set():
                    chunk_queue.put(("error", e_worker))
            finally:
                if stream_iter is not None and hasattr(stream_iter, "close"):
                    try:
                        stream_iter.close()
                    except Exception:
                        pass
                try:
                    state.llm_lock.release()
                except RuntimeError:
                    pass
                chunk_queue.put(("end", None))

        try:
            worker_thread = threading.Thread(
                target=_llm_stream_worker,
                name="shiro-llm-stream-worker",
                daemon=True
            )
            worker_thread.start()
            worker_started = True

            from shiro.llm.cleaner import (
                is_user_input_foreign_or_english,
                contains_english_segments,
                translate_to_indonesian_fast,
                replace_inline_english_idioms,
                is_predominantly_english,
            )
            should_guard_id = bool(raw_user_typed and not is_user_input_foreign_or_english(raw_user_typed) and api_version != "v3")
            lyra_tier_info = prep.get("lyra_tier_info")
            lyra_tier_id = lyra_tier_info["id"] if lyra_tier_info else "high"
            clause_buf = ""
            streamed_reply_acc = ""

            def _flush_stream_seg(seg: str) -> str:
                if not seg or not seg.strip():
                    return seg
                if should_guard_id and "```" not in seg and contains_english_segments(seg):
                    replaced = replace_inline_english_idioms(seg)
                    # Di mode Low atau kalimat campuran istilah teknis, hindari blocking HTTP translate tiap baris
                    if lyra_tier_id != "low" and is_predominantly_english(replaced.strip()):
                        lead_ws = re.match(r'^\s*', replaced).group(0)
                        trail_ws = re.search(r'\s*$', replaced).group(0)
                        tr = translate_to_indonesian_fast(replaced.strip())
                        if tr and tr.strip():
                            return lead_ws + tr.strip() + trail_ws
                    return replaced
                return seg

            in_think = False
            thinking_status_sent = False
            while True:
                try:
                    ev_kind, ev_val = chunk_queue.get(timeout=ping_interval)
                except queue.Empty:
                    yield {"type": "ping"}
                    last_ping_time = time.perf_counter()
                    continue

                if ev_kind == "end":
                    break
                elif ev_kind == "error":
                    raise ev_val
                elif ev_kind == "sync_result":
                    res_sync = ev_val
                    sync_text = ""
                    if isinstance(res_sync, dict) and res_sync.get("choices"):
                        sync_text = res_sync["choices"][0].get("message", {}).get("content", "") or ""
                    if sync_text:
                        raw_reply = sync_text
                        streamed_reply_acc = sync_text
                        yield {"type": "token", "token": sync_text}
                    continue

                chunk = ev_val
                choices = chunk.get("choices", []) if isinstance(chunk, dict) else []
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    raw_reply += token
                    if not is_reasoning_enabled:
                        if "<think>" in token or ("<think>" in raw_reply and "</think>" not in raw_reply):
                            in_think = True
                            if not thinking_status_sent:
                                thinking_status_sent = True
                                yield {"type": "status", "status": f"{prep.get('ai_name', 'Shiro')} sedang menalar mendalam..."}
                            now = time.perf_counter()
                            if now - last_ping_time > ping_interval:
                                yield {"type": "ping"}
                                last_ping_time = now
                            continue
                        elif in_think and "</think>" in token:
                            in_think = False
                            after_think = token.split("</think>", 1)[-1]
                            if after_think:
                                token = after_think
                            else:
                                continue

                    # Jangan kirim spasi/newline kosong sebelum karakter terlihat pertama keluar (agar status UI tetap akurat)
                    if not streamed_reply_acc and not clause_buf and not token.strip():
                        continue

                    if not should_guard_id or (raw_reply.count("```") % 2 == 1):
                        if clause_buf:
                            flushed = _flush_stream_seg(clause_buf)
                            streamed_reply_acc += flushed
                            yield {"type": "token", "token": flushed}
                            clause_buf = ""
                        streamed_reply_acc += token
                        yield {"type": "token", "token": token}
                        last_ping_time = time.perf_counter()
                    else:
                        clause_buf += token
                        if "\n" in clause_buf:
                            head, sep, tail = clause_buf.rpartition("\n")
                            to_flush = head + sep
                            if to_flush.count("*") % 2 == 0:
                                flushed = _flush_stream_seg(to_flush)
                                streamed_reply_acc += flushed
                                yield {"type": "token", "token": flushed}
                                clause_buf = tail
                                last_ping_time = time.perf_counter()
                        elif clause_buf.count("*") % 2 == 0 and len(clause_buf) >= 35:
                            m_sent = re.search(r'^([\s\S]*?[.!?~]["\'*)]?\s+)([\s\S]*)$', clause_buf)
                            if m_sent:
                                head_part, tail_part = m_sent.group(1), m_sent.group(2)
                                if head_part.count("*") % 2 == 0:
                                    flushed = _flush_stream_seg(head_part)
                                    streamed_reply_acc += flushed
                                    yield {"type": "token", "token": flushed}
                                    clause_buf = tail_part
                                    last_ping_time = time.perf_counter()
                        elif len(clause_buf) >= 120:
                            flushed = _flush_stream_seg(clause_buf)
                            streamed_reply_acc += flushed
                            yield {"type": "token", "token": flushed}
                            clause_buf = ""
                            last_ping_time = time.perf_counter()

                now = time.perf_counter()
                if now - last_ping_time > ping_interval:
                    yield {"type": "ping"}
                    last_ping_time = now

            if clause_buf:
                flushed = _flush_stream_seg(clause_buf)
                streamed_reply_acc += flushed
                yield {"type": "token", "token": flushed}
                clause_buf = ""
            if should_guard_id and streamed_reply_acc.strip():
                raw_reply = streamed_reply_acc
        finally:
            cancel_event.set()
            if lock_acquired and not worker_started:
                try:
                    state.llm_lock.release()
                except RuntimeError:
                    pass

        t_llm_dur = (time.perf_counter() - t0) * 1000
        delivery_reply, trace, details = _finalize_inference_output(
            prep=prep,
            raw_reply=raw_reply,
            t_llm_dur=t_llm_dur
        )

        yield {
            "type": "done",
            "reply": delivery_reply,
            "raw_reply": raw_reply,
            "trace": trace,
            "agent_action": prep.get("agent_action_data")
        }

    except Exception as e:
        print(f"[Inference Stream Error]: {e}")
        err_msg = f"*menatap cemas* Maaf Kakak... sistem AI mengalami kendala teknis: {str(e)[:80]}"
        yield {
            "type": "error",
            "error": str(e),
            "reply": err_msg
        }
