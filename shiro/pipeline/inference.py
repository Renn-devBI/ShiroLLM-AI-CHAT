# -*- coding: utf-8 -*-
"""
Shiro Neural Inference Engine & Dynamic Pipeline
Executes prompt synthesis, multimodal ingestion, neural inference,
and telemetry broadcasting without canned fallback scripts.
"""

import os
import re
import json
import time
import base64
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Union

from shiro.config import CONTEXT_SIZE
from shiro.server_state import state
from shiro.models import get_active_model_ctx
from shiro.persona import (
    build_system_prompt,
    build_vtuber_system_prompt,
    build_custom_system_prompt
)
from shiro.nlp.emotion import detect_emotion_category
from shiro.nlp.typo import normalize_typos, get_typo_understanding_prompt
from shiro.llm.cleaner import clean_response, clean_vtuber_response
from shiro.pipeline.trace import global_pipeline_manager

def calculate_messages_tokens(messages: List[Dict[str, Any]], llm_instance: Any) -> int:
    """Menghitung perkiraan jumlah token dari daftar pesan"""
    if not llm_instance:
        return sum(len(str(m.get('content', '')).split()) for m in messages)
    try:
        if hasattr(llm_instance, 'tokenize'):
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
    return sum(len(str(m.get('content', '')).split()) for m in messages)

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
    max_tokens: Optional[int] = None
) -> Union[str, Tuple[str, Any]]:
    """
    Eksekusi pipeline kognitif Shiro:
    - user_input: Teks murni yang diketik oleh pengguna (tidak dimanipulasi dengan prompt buatan)
    - Output AI adalah murni hasil neural generation model (bukan template/fallback buatan program)
    - Base prompt murni untuk persona/role Shiro
    """
    t_start_total = time.perf_counter()
    nodes = []
    llm = state.llm
    vision_chat_handler = state.vision_chat_handler
    memory = state.init_memory()
    web_reader = state.init_web_reader()

    # Pastikan user_input adalah string bersih
    raw_user_typed = (user_input or "").strip()

    try:
        active_model_name = os.path.basename(getattr(llm, 'model_path', '')).lower() if hasattr(llm, 'model_path') else ""
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
                agent_intent_res = detect_agent_intent(raw_user_typed)
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
                        tool_name = "google_web_search"
                        q = agent_params.get("query", raw_user_typed)
                        tool_desc = f"Membuka browser Mozilla & mencari di Google/Web via Cloudflare 1.1.1.1: '{q}'"
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
        # Semantic Memory Gating: hanya fakta relevan yang masuk prompt;
        # saat ada gambar baru, fakta web/URL lama dikarantina agar tidak mencemari observasi visual.
        from shiro.memory.gating import gate_facts
        relevant_facts = gate_facts(facts, raw_user_typed, has_image=has_image)
            
        traits = memory.user_profile.get("personality_traits", []) if (memory and hasattr(memory, "user_profile")) else []
        # Temporal separation: saat ada gambar baru, contoh dialog lama & konteks lintas sesi tidak disertakan
        exemplars = memory.get_relevant_exemplars(raw_user_typed, max_count=2) if (not has_image and memory and hasattr(memory, "get_relevant_exemplars") and raw_user_typed) else []
        
        cross_session_addon = memory.get_cross_session_context(raw_user_typed) if (not has_image and memory and hasattr(memory, "get_cross_session_context") and raw_user_typed) else ""
        has_cross_session = bool(cross_session_addon)

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
            # Cegah duplikasi: jika giliran terakhir di memory adalah pesan user saat ini yang baru ditambahkan di chat(),
            # potong agar tidak dikirim dua kali beruntun
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

        # Dynamic Token Budget Guard:
        # Menjaga seluruh percakapan masuk secara utuh menyesuaikan kapasitas model aktif.
        # Semakin besar model dan context window-nya, semakin banyak riwayat obrolan yang ditampung.
        active_ctx = get_active_model_ctx(llm)
        from shiro.models import get_optimal_model_tokens
        active_model_path = getattr(llm, 'model_path', '') if hasattr(llm, 'model_path') else ''
        _, model_max_out = get_optimal_model_tokens(active_model_path or active_model_name)
        
        # Alokasi cadangan untuk system prompt dan respon lengkap (agar penulisan kode tidak terpotong)
        reserved_budget = max(4096, min(16384, model_max_out + 2048))
        max_history_tokens = max(2000, active_ctx - reserved_budget)
        while len(clean_context) > 2 and calculate_messages_tokens(clean_context, llm) > max_history_tokens:
            clean_context.pop(0)

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
            active_ctx = get_active_model_ctx(llm)
            # Alokasi kuota teks dokumen dinamis menyesuaikan context window model
            max_doc_chars = max(10000, min(60000, (active_ctx - 2000) * 3))
            doc_full_text = document_info.get("text", "")
            if len(doc_full_text) > max_doc_chars:
                doc_full_text = doc_full_text[:max_doc_chars] + f"\n\n... [Sisa teks dokumen dipotong karena melampaui batas {max_doc_chars} karakter]"
            doc_prompt_addon = build_document_prompt(
                {"filename": doc_name, "text": doc_full_text},
                user_query=raw_user_typed
            )

        # Agentic Tools Schema injection
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

        # Controlled Reasoning directive
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

        visual_guidance_addon = ""
        if has_image:
            visual_guidance_addon = (
                "\n\n### PANDUAN PENGAMATAN GAMBAR BARU:\n"
                "- Kakak sedang melampirkan berkas gambar BARU pada giliran pesan ini.\n"
                "- Amati dan baca informasi, teks, diagram, serta objek pada gambar baru ini secara teliti dan langsung.\n"
                "- DILARANG KERAS mengaitkan atau berasumsi bahwa gambar baru ini adalah situs web, link, atau halaman dari percakapan masa lalu jika tidak disebutkan secara eksplisit oleh Kakak.\n"
            )

        # Susun System Prompt berdasarkan persona Shiro (v1, v2, atau v3)
        if api_version == "v2":
            system_prompt = build_vtuber_system_prompt() + tools_addon + reasoning_addon + web_prompt_addon + doc_prompt_addon + visual_guidance_addon
        elif api_version == "v3":
            base_p = custom_system_prompt or ""
            system_prompt = build_custom_system_prompt(base_p) + tools_addon + reasoning_addon + web_prompt_addon + doc_prompt_addon + visual_guidance_addon
        else:
            system_prompt = build_system_prompt(
                conversation_summary=conversation_summary,
                facts_summary=facts_summary,
                exemplar_prompt=exemplar_prompt,
                web_prompt_addon=web_prompt_addon,
                typo_prompt_addon=typo_prompt_addon,
                document_prompt_addon=doc_prompt_addon,
                cross_session_addon=cross_session_addon
            ) + tools_addon + reasoning_addon + visual_guidance_addon

        # Susun Pesan Giliran Pengguna (User Turn)
        visual_evidence_text = ""
        has_vision_handler = bool(
            getattr(state, "vision_chat_handler", None) or 
            (llm and getattr(llm, "chat_handler", None))
        )
        if has_image:
            if has_vision_handler:
                # Mode Vision Native (Qwen2.5-VL-7B, Qwen2.5-VL-32B) dengan vision projector aktif:
                content_parts = []
                for img in all_images[:8]:
                    clean_img = img if img.startswith("data:image/") else f"data:image/jpeg;base64,{img}"
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": clean_img}
                    })
                user_text = raw_user_typed if raw_user_typed else "Shiro, coba lihat dan analisis gambar yang Kakak kirim ini ya."
                if has_doc:
                    user_text = f"[Melampirkan Dokumen: {doc_name}]\n{user_text}"
                content_parts.append({"type": "text", "text": user_text})
                user_turn_msg = {"role": "user", "content": content_parts}
            else:
                # Mode MoE Dual-Brain: model chat (mis. Qwen3.8-27B) buta visual.
                # Visual Cortex Expert (Qwen2.5-VL) mengamati gambar -> Visual Evidence Contract.
                # Bila expert tidak tersedia / mode off -> fallback OCR lokal.
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
                    f"[OBSERVASI VISUAL GAMBAR YANG DILAMPIRKAN KAKAK — sumber: {source_label}]:",
                    visual_evidence_text,
                    "\n[ATURAN]: Jawab berdasarkan observasi di atas saja. Jika sesuatu tidak tercatat di observasi, katakan tidak terlihat jelas. JANGAN mengaitkan gambar ini dengan situs web atau topik dari ingatan lama.",
                    f"\n{raw_user_typed}" if raw_user_typed else "Shiro, coba jelaskan apa yang terlihat pada gambar di atas."
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

            user_text = "\n".join(parts_user)
            user_turn_msg = {"role": "user", "content": user_text}

        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(clean_context)
        msgs.append(user_turn_msg)

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

        # -------------------------------------------------------------
        # NODE 5: Neural Inference Engine
        # -------------------------------------------------------------
        # Penentuan batas token output maksimal dinamis menyesuaikan model yang terdeteksi
        from shiro.models import get_optimal_model_tokens
        active_model_path = getattr(llm, 'model_path', '') if hasattr(llm, 'model_path') else ''
        _, model_max_out = get_optimal_model_tokens(active_model_path or active_model_name)

        if max_tokens:
            desired_max = int(max_tokens)
        elif api_version == "v2":
            desired_max = 2048
        elif is_reasoning_enabled or tools:
            desired_max = max(model_max_out, 8192)
        else:
            # Model besar (27B/32B) -> 8192-16384, Model sedang (7B/VL) -> 4096, Model ringan -> 2048
            desired_max = model_max_out

        prompt_tokens_est = calculate_messages_tokens(msgs, llm)
        remaining_space = max(1024, active_ctx - prompt_tokens_est - 64)
        max_output_tokens = min(desired_max, remaining_space)

        stop_tokens = [
            "<|im_end|>", "<|im_start|>", "<|eot_id|>", "<|end|>", "<|end_of_text|>",
            "\nUser:", "\nKakak:", "\nuser:", "\nAssistant:", "\nassistant:",
            "\n<|im_start|>user", "\n<|im_start|>assistant"
        ]
        if not is_reasoning_enabled:
            stop_tokens.extend(["\nOkay, let me", "\nThe user is"])

        gen_params = {
            "temperature": 0.45 if has_image else (0.70 if api_version == "v2" else 0.65),
            "repeat_penalty": 1.15 if has_image else 1.2,
            "frequency_penalty": 0.2 if has_image else 0.3,
            "presence_penalty": 0.0,
            "top_p": 0.92,
            "top_k": 40,
            "max_tokens": max_output_tokens,
            "stop": stop_tokens
        }

        call_kwargs = dict(gen_params)
        res = None
        if llm is None:
            raise RuntimeError("Model LLM belum dimuat di memori server.")

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
                # Pemangkasan darurat konteks
                emergency_msgs = [{"role": "system", "content": system_prompt[:1200]}]
                emergency_msgs.append(user_turn_msg)
                res = llm.create_chat_completion(messages=emergency_msgs, **call_kwargs)
            elif has_image and any(k in err_str for k in ["image", "list", "content", "dict", "str", "iterable"]):
                # Fallback teks lokal jika runtime llama-cpp belum memiliki chat_handler terpasang
                from shiro.vision.bridge import extract_local_image_text_and_info
                local_obs = extract_local_image_text_and_info(all_images) or "Gambar visual terlampir"
                text_user = f"[Pengamatan Gambar Visual: {local_obs}]\n{raw_user_typed}"
                msgs[-1] = {"role": "user", "content": text_user}
                res = llm.create_chat_completion(messages=msgs, **call_kwargs)
            else:
                raise inf_err

        raw_reply = res['choices'][0]['message'].get('content', '') or ''
        raw_reply = raw_reply.strip()

        # Grounding Verifier Loop (giliran bergambar):
        # Jika balasan menyebut domain/situs yang tidak ada di pesan Kakak, bukti visual, atau hasil tool,
        # regenerasi sekali dengan koreksi eksplisit.
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
                "finish_reason": res['choices'][0].get('finish_reason', 'stop'),
                "usage": res.get("usage", {}),
                "grounding": grounding_info
            }
        })

        # -------------------------------------------------------------
        # NODE 6: Neural Filter & Output Processing
        # (Murni hasil pemikiran model, tanpa penimpaan fallback buatan program)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        
        # 1. Ekstrak tool_calls
        native_tool_calls = res['choices'][0]['message'].get('tool_calls', None)
        parsed_tool_calls = list(native_tool_calls) if native_tool_calls else []

        # 2. Ekstrak reasoning (<think>...</think>)
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

        # Penting: Jika model meletakkan seluruh jawaban di dalam blok <think> atau terpotong sebelum </think>,
        # jangan biarkan raw_reply kosong! Ambil reasoning_content sebagai raw_reply.
        if not raw_reply and reasoning_content:
            raw_reply = reasoning_content

        # 3. Ekstrak tool_calls berbasis JSON dari teks jika ada
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

        # Bersihkan response sesuai versi endpoint
        if api_version == "v2":
            cleaned_reply = clean_vtuber_response(raw_reply, raw_user_typed)
        elif api_version == "v3":
            cleaned_reply = clean_response(raw_reply)
        else:
            cleaned_reply = clean_response(raw_reply)

        # Jika cleaner menghasilkan teks kosong padahal raw_reply memiliki teks substansial
        if not cleaned_reply and raw_reply:
            cleaned_reply = raw_reply.strip()

        # Respon murni dari model AI tanpa teks feedback atau basa-basi robotik buatan program
        if not cleaned_reply:
            cleaned_reply = raw_reply.strip() if raw_reply else ""

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

        if return_details:
            return delivery_reply, {
                "reasoning_content": reasoning_content,
                "tool_calls": parsed_tool_calls,
                "finish_reason": "tool_calls" if parsed_tool_calls else "stop",
                "trace": trace,
                "agent_action": agent_action_data
            }
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
            "user_input": raw_user_typed,
            "reply": err_msg,
            "error": str(e),
            "nodes": nodes
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
