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
from shiro.vision.bridge import analyze_visual_bridge
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
    include_reasoning: bool = False
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

        visual_bridge_context = ""
        # Jika model teks biasa menerima visual, gunakan visual bridge sebagai konteks sistem objektif
        if has_image and not has_vision:
            vis_desc = analyze_visual_bridge(all_images, query_text=raw_user_typed)
            if vis_desc:
                visual_bridge_context = (
                    f"\n\n### INFORMASI HASIL OBSERVASI VISUAL KAMERA/LAYAR:\n"
                    f"{vis_desc}\n"
                    f"[Catatan: Informasi visual di atas adalah apa yang saat ini terlihat. "
                    f"Jawab pertanyaan Kakak sesuai fakta visual tersebut dengan persona Shiro.]\n"
                )

        # Online web reading & real-time browsing
        web_data = None
        web_prompt_addon = ""
        if web_reader and raw_user_typed:
            try:
                web_intent = web_reader.detect_web_intent(raw_user_typed)
                if web_intent.get("type") == "url" and web_intent.get("urls"):
                    target_url = web_intent["urls"][0]
                    fetch_res = web_reader.fetch_url(target_url)
                    if fetch_res.get("success"):
                        web_data = {
                            "source": target_url,
                            "title": fetch_res.get("title", "Halaman Web"),
                            "content": fetch_res.get("content", "")
                        }
                        web_prompt_addon = (
                            f"\n\n### INFORMASI DARI SITUS WEB ({target_url}):\n"
                            f"Judul: {web_data['title']}\n"
                            f"Konten:\n{web_data['content']}\n"
                        )
                elif web_intent.get("type") == "search" and web_intent.get("query"):
                    search_q = web_intent["query"]
                    s_res = web_reader.search_wikipedia_online(search_q)
                    if s_res.get("success") and s_res.get("results"):
                        snippets = "\n".join([f"- {r['title']}: {r['snippet']}" for r in s_res["results"]])
                        web_data = {
                            "source": f"Pencarian: {search_q}",
                            "title": f"Hasil: {search_q}",
                            "content": snippets
                        }
                        web_prompt_addon = (
                            f"\n\n### INFORMASI PENCARIAN ONLINE:\n"
                            f"Topik: {search_q}\n"
                            f"Ringkasan:\n{snippets}\n"
                        )
            except Exception as e_web:
                print(f"[Inference] Warning online web reader: {e_web}")

        t_input_dur = (time.perf_counter() - t0) * 1000
        summary_node1 = f"{len(raw_user_typed)} Karakter"
        if has_image:
            summary_node1 += f" • {len(all_images)} Frame Visual"
        if has_doc:
            summary_node1 += f" • Dokumen ({doc_name})"

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
        relevant_facts = memory.get_relevant_facts(raw_user_typed, limit=3) if (memory and raw_user_typed) else []
        traits = memory.get_user_traits() if memory else []
        exemplars = memory.get_exemplars(limit=2) if memory else []

        cross_session_addon = ""
        has_cross_session = False
        if memory and raw_user_typed:
            cross_history = memory.search_across_sessions(raw_user_typed, limit=3)
            if cross_history:
                has_cross_session = True
                cross_session_addon = "\n\n### INGATAN PERCAKAPAN TERDAHULU DARI SESI LAIN:\n"
                for item in cross_history:
                    cross_session_addon += f"- Kakak pernah berkata: \"{item.get('content', '')}\"\n"

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
            clean_context = clean_context[-12:]
        elif memory:
            clean_context = memory.get_context_messages(limit=10)

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
            doc_snip = document_info.get("text", "")[:4000]
            doc_prompt_addon = (
                f"\n\n### DOKUMEN AKTIF ({doc_name}):\n"
                f"{doc_snip}\n"
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

        # Susun System Prompt berdasarkan persona Shiro (v1, v2, atau v3)
        if api_version == "v2":
            system_prompt = build_vtuber_system_prompt() + tools_addon + reasoning_addon + visual_bridge_context
        elif api_version == "v3":
            base_p = custom_system_prompt or ""
            system_prompt = build_custom_system_prompt(base_p) + tools_addon + reasoning_addon + visual_bridge_context
        else:
            system_prompt = build_system_prompt(
                conversation_summary=conversation_summary,
                facts_summary=facts_summary,
                exemplar_prompt=exemplar_prompt,
                web_prompt_addon=web_prompt_addon + visual_bridge_context,
                typo_prompt_addon=typo_prompt_addon,
                document_prompt_addon=doc_prompt_addon,
                cross_session_addon=cross_session_addon
            ) + tools_addon + reasoning_addon

        # Susun Pesan Giliran Pengguna (MURNI teks yang diketik oleh pengguna)
        if has_image and has_vision:
            # Format multimodal vision native
            content_parts = []
            for img in all_images[:8]:
                clean_img = img if img.startswith("data:image/") else f"data:image/jpeg;base64,{img}"
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": clean_img}
                })
            # Teks giliran pengguna murni dari ketikan user (tanpa teks palsu buatan program)
            user_text = raw_user_typed if raw_user_typed else " "
            content_parts.append({"type": "text", "text": user_text})
            user_turn_msg = {"role": "user", "content": content_parts}
        else:
            # Teks murni yang diketik user
            user_text = raw_user_typed if raw_user_typed else " "
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
        t0 = time.perf_counter()
        max_output_tokens = 180 if api_version == "v2" else (1200 if (is_reasoning_enabled or tools) else 500)
        stop_tokens = [
            "User:", "Kakak:", "Shiro:", "assistant:", "\n\n\n", "###",
            "<|im_end|>", "<|im_start|>", "<|eot_id|>", "<|end|>", "<|end_of_text|>"
        ]
        if not is_reasoning_enabled:
            stop_tokens.extend(["Okay, let me", "The user is"])

        gen_params = {
            "temperature": 0.72 if has_image else (0.70 if api_version == "v2" else 0.65),
            "repeat_penalty": 1.25 if has_image else 1.2,
            "frequency_penalty": 0.5 if has_image else 0.3,
            "presence_penalty": 0.3 if has_image else 0.0,
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
            else:
                raise inf_err

        raw_reply = res['choices'][0]['message'].get('content', '') or ''
        raw_reply = raw_reply.strip()
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
                "usage": res.get("usage", {})
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

        # Jika model menghasilkan teks kosong padahal memanggil tool
        if not cleaned_reply and parsed_tool_calls:
            cleaned_reply = "Shiro sedang memproses perintah dengan tool yang sesuai ya, Kak!" if api_version == "v1" else ""

        # Jika model benar-benar menghasilkan output kosong tanpa tool
        if not cleaned_reply:
            cleaned_reply = "*tersenyum lembut menatap Kakak* Iya Kak? Shiro siap mendengarkan." if api_version == "v1" else "..."

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
        nodes.append({
            "id": "node_output",
            "name": "Response Delivery Stream",
            "type": "output",
            "icon": "ph-paper-plane-right",
            "color": "#3b82f6",
            "status": "success",
            "duration_ms": 0.5,
            "summary": f"{round(t_total_dur)}ms Latency",
            "data_in": {"chars_count": len(cleaned_reply)},
            "data_out": {
                "final_reply": cleaned_reply,
                "total_duration_ms": round(t_total_dur, 2)
            }
        })

        trace = {
            "id": f"trace-{int(time.time()*1000)}",
            "timestamp": datetime.now().isoformat(),
            "status": "completed",
            "total_duration_ms": round(t_total_dur, 2),
            "user_input": raw_user_typed,
            "reply": cleaned_reply,
            "nodes": nodes
        }
        global_pipeline_manager.broadcast(trace)

        if return_details:
            return cleaned_reply, {
                "reasoning_content": reasoning_content,
                "tool_calls": parsed_tool_calls,
                "finish_reason": "tool_calls" if parsed_tool_calls else "stop",
                "trace": trace
            }
        if return_trace:
            return cleaned_reply, trace
        return cleaned_reply

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
