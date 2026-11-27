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
    detect_chat_format,
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


def _format_chatml_prompt(messages: List[Dict[str, Any]], disable_thinking: bool = False) -> str:
    """
    Merakit prompt ChatML secara langsung (<|im_start|>role\\n...<|im_end|>) untuk inferensi teks cepat
    tanpa melewati Qwen25VLChatHandler yang mengosongkan KV cache setiap giliran.
    """
    parts: List[str] = []
    for msg in messages:
        role = str(msg.get("role", "user")).strip() or "user"
        raw_content = msg.get("content", "")
        if isinstance(raw_content, list):
            text_chunks = [
                str(p.get("text", ""))
                for p in raw_content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            text = "\n".join([c for c in text_chunks if c])
        else:
            text = str(raw_content or "")
        parts.append(f"<|im_start|>{role}\n{text}<|im_end|>\n")

    if disable_thinking:
        parts.append("<|im_start|>assistant\n<think>\n\n</think>\n")
    else:
        parts.append("<|im_start|>assistant\n")
    return "".join(parts)


def _should_use_fast_text_completion(
    llm: Any,
    has_image: bool,
    tools: Any,
    active_model_path: str
) -> bool:
    """
    Menentukan apakah giliran teks murni aman menggunakan llama.create_completion (ChatML native
    dengan KV prefix caching) agar tidak mereset cache via Qwen25VLChatHandler.
    """
    if llm is None or has_image or tools:
        return False
    if not (hasattr(llm, "create_completion") and callable(llm.create_completion)):
        return False
    if getattr(llm, "_shiro_fast_chatml", None) is True:
        return True
    try:
        mod_name = type(llm).__module__ or ""
    except Exception:
        mod_name = ""
    if mod_name.startswith("llama_cpp"):
        target_path = active_model_path or getattr(llm, "model_path", "") or ""
        return detect_chat_format(target_path) == "chatml"
    return False


def _build_completion_kwargs(call_kwargs: Dict[str, Any], stream: bool = False) -> Dict[str, Any]:
    """Menyaring parameter aman untuk llama.create_completion."""
    allowed = (
        "max_tokens", "temperature", "top_p", "top_k",
        "repeat_penalty", "frequency_penalty", "presence_penalty", "stop"
    )
    out = {k: call_kwargs[k] for k in allowed if k in call_kwargs}
    out["stream"] = stream
    return out


_AGENT_TOOL_TAG_RE = re.compile(r'\[\[AGENT_TOOL:([A-Za-z0-9_]+)(?:\|([^\]]*))?\]\]', re.IGNORECASE)


def _parse_agent_tool_calls(text: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    Mengekstrak tag alat otonom `[[AGENT_TOOL:nama|k=v|...]]` dari keluaran model
    dan mengembalikan (daftar_panggilan, teks_bersih_tanpa_tag).
    """
    if not text or "AGENT_TOOL:" not in text:
        return [], text or ""
    calls: List[Dict[str, Any]] = []
    for m in _AGENT_TOOL_TAG_RE.finditer(text):
        tool_name = (m.group(1) or "").strip().lower()
        raw_args = (m.group(2) or "").strip()
        args: Dict[str, str] = {}
        if raw_args:
            for seg in raw_args.split("|"):
                if "=" in seg:
                    k, v = seg.split("=", 1)
                    args[k.strip().lower()] = v.strip()
        calls.append({"name": tool_name, "args": args, "raw": m.group(0)})
    cleaned = _AGENT_TOOL_TAG_RE.sub("", text)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return calls, cleaned


def _split_partial_agent_tag(buf: str) -> Tuple[str, str]:
    """Menahan potongan tag `[[AGENT_TOOL:...]]` agar sintaks mentah alat tidak berkedip di UI stream."""
    if not buf:
        return "", ""
    # Jika ada pembuka tag yang belum tertutup `]]`, tahan seluruh sisanya
    open_idx = buf.rfind("[[")
    if open_idx != -1:
        after_open = buf[open_idx:]
        if "]]" not in after_open:
            upper_after = after_open.upper()
            if len(after_open) <= 13 and "[[AGENT_TOOL:".startswith(upper_after):
                return buf[:open_idx], after_open
            if upper_after.startswith("[[AGENT_TOOL:"):
                return buf[:open_idx], after_open
    if buf.endswith("["):
        return buf[:-1], "["
    return buf, ""


def get_max_agent_rounds(tier_id: Optional[str] = None) -> int:
    """Mengembalikan batas iterasi reasoning/pencarian agen yang berskala dinamis sesuai level konteks."""
    budgets = {
        "low": 3,
        "medium": 8,
        "high": 24,
        "extra_high": 45,
        "ultra_high": 64,
    }
    return budgets.get(str(tier_id or "").lower(), 16)


_HEAVY_TASK_RE = re.compile(
    r'(?:\b(?:kode|code|script|skrip|website|html|css|javascript|typescript|python|flask|fastapi|'
    r'react|vue|sql|database|db|api|endpoint|bug|error|traceback|exception|debug|fix|perbaiki|'
    r'buatkan|buatin|bikinkan|bikinin|bikin|create|build|develop|implement|refactor|optimasi|optimize|deploy|server|'
    r'docker|zip|tar|rar|7z|compress|kompres|arsip|analisa|analisis|analyze|audit|review|bandingkan|compare|'
    r'arsitektur|algoritma|hitung|rumus|carikan|cariin|cari\s+di|search|google|browsing|browse|render|generate)\b'
    r'|\b[\w\-]+\.(?:py|js|ts|html|css|json|sql|sh|app|jsx|tsx|java|cpp|go|rs)\b)',
    re.IGNORECASE,
)

_CASUAL_OR_META_Q_RE = re.compile(
    r'^(?:'
    r'(?:halo|hai|hi|hello|hey|selamat\s+(?:pagi|siang|sore|malam))(?:\s+(?:shiro|kak|semua))?[\s,!?.]*$'
    r'|(?:oke|ok|sip|mantap|keren|hebat|bagus|terima\s+kasih|makasih|thanks|thank\s+you)(?:\s+(?:shiro|kak|ya|banget))?[\s,!?.]*$'
    r'|(?:siapa|siapakah)\s+(?:kamu|kau|anda|shiro|namamu|nama\s+kamu|pencipta(?:mu|\s+kamu)?|pembuat(?:mu|\s+kamu)?|developer(?:mu|\s+kamu)?|pengembang(?:mu|\s+kamu)?)\b'
    r'|(?:kamu|kau|anda|shiro)\s+(?:itu\s+)?siapa\b'
    r'|siapa\s+yang\s+(?:buat|bikin|membuat|menciptakan|mengembangkan)\s+(?:kamu|shiro)\b'
    r'|(?:apa\s+kabar|gimana\s+kabar(?:mu)?|kamu\s+(?:sedang|lagi)\s+apa|lagi\s+ngapain|shiro\s+(?:kamu\s+)?(?:sedang|lagi)\s+apa)\b'
    r'|(?:who\s+are\s+you|what\s+are\s+you|who\s+(?:made|created|built|developed)\s+you|how\s+are\s+you|what\s+can\s+you\s+do)\b'
    r'|(?:kamu|shiro|anda)\s+bisa\s+apa(?:\s+aja|\s+saja)?[\s?!.,]*$'
    r'|(?:apakah\s+)?(?:kamu|shiro|kau|anda)\s+(?:bisa|dapat|mampu|support|mendukung|punya\s+fitur)\b'
    r'|(?:can\s+you|do\s+you\s+support|are\s+you\s+able\s+to)\b'
    r')',
    re.IGNORECASE,
)


def _is_heavy_agent_task(
    raw_user_typed: str,
    agent_intent: str = "none",
    has_doc: bool = False,
    has_image: bool = False,
    has_video: bool = False,
    api_version: str = "v1",
    tools: Optional[List[Dict[str, Any]]] = None,
    include_reasoning: bool = False,
    reasoning_effort: Optional[str] = None,
) -> bool:
    """
    Menentukan apakah permintaan membutuhkan alur agen & penalaran penuh (`Reasoning & Solution Synthesis`)
    atau cukup dijawab langsung secara natural (misalnya obrolan santai atau mode VTuber v2).
    """
    if api_version == "v2":
        return False
    if include_reasoning or (reasoning_effort and str(reasoning_effort).lower() not in ("none", "false", "0")):
        return True
    if tools or has_doc or has_image or has_video:
        return True
    if agent_intent and agent_intent != "none":
        return True
    txt = (raw_user_typed or "").strip()
    if not txt:
        return False
    if "\n" not in txt and len(txt) <= 130 and _CASUAL_OR_META_Q_RE.search(txt):
        return False
    if "\n" in txt or len(txt) > 130 or "```" in txt:
        return True
    if _HEAVY_TASK_RE.search(txt):
        return True
    return False


def _execute_live_research_tool(
    tool_call: Dict[str, Any],
    tier_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Menjalankan alat penelusuran web/browser (`web_search`, `open_url`, `screenshot`) secara langsung."""
    from shiro.agent.tools import search_google_web, open_and_read_webpage, take_web_screenshot
    from shiro.web.realtime_intel import get_research_config_for_tier
    cfg = get_research_config_for_tier(tier_id)
    max_res = max(4, min(12, int(cfg.max_sources)))
    max_imgs = max(2, min(8, int(cfg.max_images)))
    name = (tool_call.get("name") or "").lower()
    args = tool_call.get("args") or {}
    t0 = time.perf_counter()

    if name == "web_search":
        q = (args.get("query") or args.get("q") or "").strip()
        res = search_google_web(q, max_results=max_res, include_images=True)
        sources = [
            {
                "title": str(r.get("title") or "Sumber Web"),
                "url": str(r.get("url") or ""),
                "domain": "",
                "snippet": str(r.get("snippet") or "")[:200],
            }
            for r in (res.get("results") or [])[:max_res]
            if isinstance(r, dict) and r.get("url")
        ]
        images = list((res.get("images") or [])[:max_imgs])
        return {
            "tool": "multi_source_web_research",
            "title": f"Browser Web Search ({q[:40]})",
            "status": "success" if res.get("success") else "failed",
            "observation": res.get("summary") or "",
            "sources": sources,
            "web_images": images,
            "duration_sec": round(time.perf_counter() - t0, 2),
        }
    elif name == "open_url":
        u = (args.get("url") or "").strip()
        res = open_and_read_webpage(u)
        sources = [{"title": res.get("title") or u, "url": u, "domain": "", "snippet": (res.get("content") or "")[:200]}] if u else []
        images = list((res.get("images") or [])[:max_imgs])
        img_lines = "\n".join(f"- ![{im.get('title', 'Image')}]({im.get('url')})" for im in images if im.get("url"))
        obs = f"Judul: {res.get('title')}\nURL: {u}\nKonten:\n{res.get('content')}"
        if img_lines:
            obs += f"\n\nGambar pada halaman:\n{img_lines}"
        return {
            "tool": "web_browser_reader",
            "title": f"Read Webpage ({u[:40]})",
            "status": "success" if res.get("success") else "failed",
            "observation": obs,
            "sources": sources,
            "web_images": images,
            "duration_sec": round(time.perf_counter() - t0, 2),
        }
    elif name == "screenshot":
        u = (args.get("url") or "").strip()
        res = take_web_screenshot(u)
        return {
            "tool": "web_screenshot",
            "title": f"Browser Screenshot ({u[:40]})",
            "status": "success" if res.get("success") else "failed",
            "observation": res.get("summary") or "",
            "image_url": res.get("image_url"),
            "sources": [{"title": u, "url": u, "domain": ""}] if u else [],
            "web_images": [],
            "duration_sec": round(time.perf_counter() - t0, 2),
        }
    return {"tool": name, "title": name, "status": "failed", "observation": "", "sources": [], "web_images": [], "duration_sec": 0.0}

def _prepare_inference_payload(
    user_input: str,
    image_base64: Optional[Union[str, List[str]]] = None,
    images_base64: Optional[List[str]] = None,
    document_info: Optional[Dict[str, Any]] = None,
    documents: Optional[List[Dict[str, Any]]] = None,
    videos: Optional[List[Dict[str, Any]]] = None,
    api_version: str = "v1",
    custom_system_prompt: Optional[str] = None,
    incoming_messages: Optional[List[Dict[str, Any]]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None,
    include_reasoning: bool = False,
    max_tokens: Optional[int] = None,
    lyra_tier: Optional[str] = None,
    session_id: Optional[str] = None,
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
    roleplay_enabled = (
        bool(memory.system_metadata.get("roleplay_enabled", True))
        if (memory and hasattr(memory, "system_metadata") and isinstance(memory.system_metadata, dict))
        else True
    )

    raw_user_typed = (user_input or "").strip()
    active_model_path = getattr(llm, 'model_path', '') if hasattr(llm, 'model_path') else ""
    active_model_name = get_model_display_name(
        active_model_path,
        raw_fallback=os.path.basename(active_model_path).lower() if active_model_path else ""
    )
    has_vision = bool(getattr(llm, 'chat_handler', None) is not None or vision_chat_handler is not None)

    # -------------------------------------------------------------
    # NODE 1: Input Ingestion (Multi-Image + Multi-Video + Multi-Document)
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    raw_images: List[str] = []
    if isinstance(image_base64, list):
        raw_images.extend([x for x in image_base64 if x])
    elif image_base64:
        raw_images.append(image_base64)
    if isinstance(images_base64, list):
        for img in images_base64:
            if img and img not in raw_images:
                raw_images.append(img)

    all_videos: List[Dict[str, Any]] = [
        v for v in (videos or [])
        if isinstance(v, dict)
        and (
            v.get("frames")
            or v.get("thumbnail")
            or v.get("url")
            or v.get("saved_filename")
            or v.get("filename")
        )
    ]
    video_frames_pool: List[str] = []
    video_meta_lines: List[str] = []
    video_upload_dir = os.path.abspath(os.path.join("data", "uploads", "videos"))
    for v_idx, v_item in enumerate(all_videos, 1):
        v_name = v_item.get("filename") or f"video_{v_idx}.mp4"
        v_dur = v_item.get("duration_sec")
        v_res = v_item.get("resolution") or "unknown"
        v_fps = v_item.get("fps")
        v_frames = list(v_item.get("frames") or ([v_item["thumbnail"]] if v_item.get("thumbnail") else []))
        v_ts = list(v_item.get("frame_timestamps") or [])

        # Lazy on-demand extraction saat inference saja (unggah video tetap instan tanpa ekstrak frame)
        if not v_frames:
            cand_names = []
            for raw_n in (
                v_item.get("saved_filename"),
                os.path.basename(str(v_item.get("url") or "").split("?")[0]),
                v_item.get("filename"),
            ):
                if raw_n and raw_n not in cand_names:
                    cand_names.append(os.path.basename(str(raw_n)))
            disk_path = None
            for cand_n in cand_names:
                probe_path = os.path.abspath(os.path.join(video_upload_dir, cand_n))
                try:
                    if os.path.commonpath([probe_path, video_upload_dir]) == video_upload_dir and os.path.isfile(probe_path):
                        disk_path = probe_path
                        break
                except ValueError:
                    continue
            if disk_path:
                try:
                    from shiro.vision.video import extract_video_frames_and_metadata
                    max_vid_frames = int(os.environ.get("SHIRO_VIDEO_MAX_FRAMES", "12"))
                    lazy_meta = extract_video_frames_and_metadata(
                        disk_path,
                        filename=v_name,
                        max_frames=max_vid_frames,
                    )
                    v_frames = list(lazy_meta.get("frames") or ([lazy_meta["thumbnail"]] if lazy_meta.get("thumbnail") else []))
                    v_ts = list(lazy_meta.get("frame_timestamps") or v_ts)
                    if v_dur is None:
                        v_dur = lazy_meta.get("duration_sec")
                    if v_res == "unknown" and lazy_meta.get("resolution"):
                        v_res = lazy_meta["resolution"]
                    if v_fps is None:
                        v_fps = lazy_meta.get("fps")
                    v_item["sampled_frame_count"] = len(v_frames)
                except Exception as e_vid_lazy:
                    print(f"[Lazy Video Extraction Warning]: {e_vid_lazy}")

        ts_preview = ", ".join(f"{t}s" for t in v_ts[:12]) if v_ts else f"{len(v_frames)} segmen"
        dur_lbl = f"{v_dur}s" if v_dur is not None else "unknown duration"
        fps_lbl = f", {v_fps} fps" if v_fps else ""
        video_meta_lines.append(
            f"- Video #{v_idx} `{v_name}` ({v_res}, durasi {dur_lbl}{fps_lbl}): "
            f"{len(v_frames)} titik adegan kronologis [{ts_preview}]"
        )
        video_frames_pool.extend(v_frames)

    # Batasi total visual frames agar VRAM & waktu prefill tetap responsif (maks 16 frame gabungan)
    MAX_MULTIMODAL_FRAMES = 16
    all_images: List[str] = list(raw_images[:MAX_MULTIMODAL_FRAMES])
    remaining_frame_slots = max(0, MAX_MULTIMODAL_FRAMES - len(all_images))
    if video_frames_pool and remaining_frame_slots > 0:
        if len(video_frames_pool) <= remaining_frame_slots:
            chosen_vid_frames = video_frames_pool
        else:
            step = (len(video_frames_pool) - 1) / float(max(1, remaining_frame_slots - 1))
            chosen_vid_frames = [
                video_frames_pool[min(len(video_frames_pool) - 1, int(round(i * step)))]
                for i in range(remaining_frame_slots)
            ]
        all_images.extend(chosen_vid_frames)

    has_image = bool(all_images)
    has_video = bool(all_videos)
    is_video_stream = has_video or len(all_images) > 1

    all_docs: List[Dict[str, Any]] = []
    if isinstance(documents, list):
        for d_item in documents:
            if isinstance(d_item, dict) and (d_item.get("text") or "").strip():
                all_docs.append(d_item)
    if document_info and isinstance(document_info, dict) and (document_info.get("text") or "").strip():
        existing_names = {d.get("filename") for d in all_docs}
        if document_info.get("filename") not in existing_names:
            all_docs.append(document_info)

    has_doc = bool(all_docs)
    doc_name = (
        f"{len(all_docs)} berkas ({', '.join(d.get('filename', 'Dokumen') for d in all_docs[:4])}{'...' if len(all_docs) > 4 else ''})"
        if len(all_docs) > 1
        else (all_docs[0].get("filename", "Dokumen") if has_doc else None)
    )

    # AI Agent Autonomous Execution (Weather, Google/Web Search, Browser, Math, File/Archive Packager)
    agent_action_data = None
    web_data = None
    web_prompt_addon = ""
    agent_intent_detected = "none"
    generated_artifacts: List[Dict[str, Any]] = []
    pending_archive_request: Optional[Dict[str, Any]] = None
    pending_video_request: Optional[Dict[str, Any]] = None
    available_archive_files: List[Dict[str, str]] = []
    inferred_project_name: Optional[str] = None
    research_substeps: List[Dict[str, Any]] = []
    all_docs_files: List[Dict[str, str]] = [
        {
            "filename": d.get("filename") or f"file_{i}.txt",
            "basename": os.path.basename(d.get("filename") or f"file_{i}.txt"),
            "content": str(d.get("text") or ""),
            "language": str(d.get("file_type") or "text"),
        }
        for i, d in enumerate(all_docs, 1)
    ]

    if raw_user_typed:
        try:
            from shiro.agent.tools import (
                detect_agent_intent,
                check_weather,
                search_google_web,
                search_web_images,
                open_and_read_webpage,
                calculate_math,
                get_current_time_info,
                take_web_screenshot,
                execute_powershell_command
            )
            sess_hist_src = (
                memory.get_session_history(session_id)
                if (memory and hasattr(memory, "get_session_history"))
                else list(getattr(memory, "short_term_history", []) or [])
            )
            agent_intent_res = detect_agent_intent(raw_user_typed, conversation_history=sess_hist_src)
            agent_intent = agent_intent_res.get("intent", "none")
            if api_version == "v2" and agent_intent in ("archive", "generate_video", "powershell"):
                agent_intent = "none"
            agent_intent_detected = agent_intent
            agent_params = agent_intent_res.get("params", {})

            if agent_intent != "none":
                t_tool_start = time.perf_counter()
                tool_name = ""
                tool_desc = ""
                obs_summary = ""
                structured_obs = None
                custom_agent_prompt = ""

                if agent_intent == "archive":
                    from shiro.agent.packager import (
                        extract_requested_filenames,
                        extract_files_from_conversation,
                        merge_file_collections,
                    )
                    tool_name = "archive_packager"
                    req_fmt = agent_params.get("format", "zip")
                    req_arch_name = agent_params.get("archive_name")
                    req_files = extract_requested_filenames(raw_user_typed)
                    hist_src = (
                        incoming_messages[:-1]
                        if (incoming_messages and len(incoming_messages) > 1)
                        else sess_hist_src
                    )
                    # Jika user meminta membuat berkas/proyek BARU tanpa menyebut berkas lama, abaikan arsip lama
                    low_req = raw_user_typed.lower()
                    wants_new_generation = bool(
                        re.search(r'\b(?:lalu|terus|kemudian|and\s+then|then)\b', low_req)
                        or (
                            re.search(r'\b(?:buatkan|buat|bikin|create|generate|write|tulis)\b', low_req)
                            and (
                                re.search(r'\b[A-Za-z0-9_\-]+\.(?!zip\b|tar\b|gz\b|7z\b|rar\b|tgz\b)[A-Za-z0-9]{1,12}\b', raw_user_typed, re.IGNORECASE)
                                or any(k in low_req for k in ("website", "aplikasi", "program", "script", "skrip", "kode", "halaman", "login"))
                            )
                        )
                    )
                    extracted_hist, inferred_proj = (
                        ([], None)
                        if (wants_new_generation and not req_files)
                        else extract_files_from_conversation(
                            hist_src,
                            max_lookback=40,
                            requested_filenames=req_files or None,
                        )
                    )
                    inferred_project_name = inferred_proj
                    available_archive_files = merge_file_collections(
                        all_docs_files,
                        extracted_hist,
                        requested_filenames=req_files or None,
                    )
                    # Tunda pembuatan arsip hingga SETELAH model AI selesai berpikir & merespons
                    pending_archive_request = {
                        **agent_params,
                        "requested_filenames": req_files,
                    }
                    found_names = [f["filename"] for f in available_archive_files]
                    found_low = {f["filename"].lower() for f in available_archive_files} | {f["basename"].lower() for f in available_archive_files}
                    missing_req = [r for r in req_files if r.lower() not in found_low and r.split("/")[-1].lower() not in found_low]

                    tool_desc = f"Scanning conversation workspace for .{req_fmt.upper()} packaging"
                    obs_summary = (
                        f"Terdeteksi {len(found_names)} berkas siap dikemas ({', '.join(found_names) if found_names else 'belum ada'}); "
                        f"pengemasan .{req_fmt} akan dieksekusi setelah AI Agent menyelesaikan respons."
                    )
                    structured_obs = {
                        "pending": True,
                        "format": req_fmt,
                        "requested_filenames": req_files,
                        "found_files": found_names,
                        "missing_files": missing_req,
                    }
                    found_line = ", ".join(f"`{n}`" for n in found_names) if found_names else "(belum ada file di riwayat/unggahan)"
                    missing_line = (
                        f"\n- Berkas yang diminta namun belum ditemukan di riwayat: {', '.join(f'`{m}`' for m in missing_req)} "
                        f"(buatkan/tuliskan berkas tersebut dengan nama persisnya jika diperlukan)."
                        if missing_req else ""
                    )
                    custom_agent_prompt = (
                        f"\n\n[INVENTARIS BERKAS WORKSPACE UNTUK PENGARSIPAN (.{req_fmt})]:\n"
                        f"- Berkas tersedia dari riwayat percakapan & unggahan: {found_line}{missing_line}\n"
                        f"- Pengemasan arsip `.{req_fmt}` akan dijalankan OTOMATIS SETELAH responsmu selesai (jangan mengklaim file sudah jadi sebelum kamu menjawab, dan jangan menolak membuat arsip).\n"
                        f"- Bertindaklah sebagai AI Agent sejati: jelaskan berkas yang akan dikemas secara alami, lengkapi/perbarui berkas bila ada yang kurang atau diminta diperbaiki menggunakan blok kode dengan nama file eksplisit (`### File: nama.ext`), atau panggil `[[AGENT_TOOL:create_archive|format={req_fmt}|files={','.join(req_files or found_names)}]]`.\n"
                    )
                elif agent_intent == "generate_video":
                    tool_name = "video_renderer"
                    vid_dur = float(agent_params.get("duration_sec") or 5.0)
                    vid_out_name = agent_params.get("output_name")
                    raw_scenes = [s.strip() for s in re.split(r'[;\n]+|->|\|', raw_user_typed) if s.strip()]
                    if len(raw_scenes) <= 1 and len(raw_user_typed) > 65:
                        raw_scenes = [p.strip() for p in re.split(r'[,.]', raw_user_typed) if len(p.strip()) > 6][:5]
                    pending_video_request = {
                        "title": raw_user_typed,
                        "scenes": raw_scenes,
                        "input_images_b64": list(raw_images) if raw_images else [],
                        "output_name": vid_out_name,
                        "duration_sec": vid_dur,
                    }
                    tool_desc = f"Preparing MP4 video render ({vid_dur}s) after AI reasoning"
                    obs_summary = (
                        f"Menyiapkan render video MP4 programatik ({vid_out_name or 'otomatis.mp4'}, durasi {vid_dur}s) "
                        "yang akan dijalankan setelah AI Agent selesai menyusun respons."
                    )
                    structured_obs = {"pending": True, **agent_params}
                    custom_agent_prompt = (
                        f"\n\n[PERMINTAAN RENDER VIDEO MP4 (.mp4)]:\n"
                        f"Sistem akan merender video MP4 programatik berdurasi {vid_dur} detik SETELAH responsmu selesai.\n"
                        f"Jelaskan rencana visual/adegan video untuk pengguna dengan alami. "
                        f"Catatan jujur bila diminta video sinematik AI/foto bergerak realistis: sistem memahami input video/visual secara multimodal dan merender MP4 motion-graphic / slideshow programatik.\n"
                    )
                elif agent_intent == "weather":
                    tool_name = "weather_sat_check"
                    locs = agent_params.get("locations", ["Jakarta", "Tokyo"])
                    tool_desc = f"Membuka koneksi satelit cuaca via Cloudflare 1.1.1.1 untuk lokasi: {', '.join(locs)}"
                    w_res = check_weather(locs)
                    obs_summary = w_res.get("summary", "")
                    structured_obs = w_res.get("data")
                elif agent_intent == "search":
                    tool_name = "multi_source_web_research"
                    q = agent_params.get("query", raw_user_typed)
                    chosen_search_tier = lyra_tier if is_valid_lyra_tier(lyra_tier) else get_saved_lyra_tier()
                    tool_desc = f"Riset browser multi-sumber ({chosen_search_tier}) & pencarian gambar web: '{q}'"
                    from shiro.web.realtime_intel import get_research_config_for_tier
                    search_cfg = get_research_config_for_tier(chosen_search_tier)
                    try:
                        from shiro.web.realtime_intel import research, wrap_search_fn, default_fetcher

                        def _on_research_progress(ev_msg: str):
                            if not ev_msg:
                                return
                            idx_s = len(research_substeps) + 1
                            research_substeps.append({
                                "id": f"web_sub_{idx_s}",
                                "title": f"Deep Search Pass #{idx_s}",
                                "status": "done",
                                "feedback": str(ev_msg)[:160],
                            })

                        res_intel = research(
                            user_query=q,
                            search_fn=wrap_search_fn(search_google_web),
                            fetch_fn=default_fetcher,
                            image_search_fn=lambda q_str: search_web_images(q_str, max_images=search_cfg.max_images),
                            cfg=search_cfg,
                            progress_cb=_on_research_progress,
                        )
                        obs_summary = res_intel.summary_text
                        structured_obs = {
                            "topic": res_intel.topic,
                            "confidence": res_intel.confidence,
                            "independent_sources": res_intel.independent_sources_count,
                            "sources": res_intel.sources,
                            "images": res_intel.images,
                            "verified_facts": [
                                {"claim": f.claim, "status": f.status, "sources": f.supporting_sources}
                                for f in res_intel.verified_facts
                            ],
                            "storable_facts": res_intel.storable_facts()
                        }
                        web_prompt_addon = f"\n\n{res_intel.prompt_block}\n"
                    except Exception as e_intel:
                        print(f"[Research Error Fallback]: {e_intel}")
                        s_res = search_google_web(q, max_results=max(6, search_cfg.max_sources), include_images=True)
                        obs_summary = s_res.get("summary", "")
                        structured_obs = {
                            "sources": s_res.get("results") or [],
                            "images": s_res.get("images") or [],
                            "results": s_res.get("results") or [],
                        }
                elif agent_intent == "browse":
                    tool_name = "web_browser_reader"
                    target_url = agent_params.get("url", "")
                    tool_desc = f"Membuka dan membaca halaman web via Browser Headers: {target_url}"
                    b_res = open_and_read_webpage(target_url)
                    b_imgs = list((b_res.get("images") or [])[:4])
                    img_lines = "\n".join(f"- ![{im.get('title', 'Web Image')}]({im.get('url')})" for im in b_imgs if im.get("url"))
                    obs_summary = f"Judul Halaman: {b_res.get('title')}\nURL: {target_url}\nIsi Teks:\n{b_res.get('content')}"
                    if img_lines:
                        obs_summary += f"\n\nGambar pada halaman:\n{img_lines}"
                    structured_obs = {
                        **b_res,
                        "sources": [{"title": b_res.get("title") or target_url, "url": target_url, "domain": ""}] if target_url else [],
                        "images": b_imgs,
                    }
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
                elif isinstance(structured_obs, dict) and tool_name == "multi_source_web_research":
                    is_tool_success = bool(structured_obs.get("sources") or structured_obs.get("images") or structured_obs.get("verified_facts"))

                agent_action_data = {
                    "tool": tool_name,
                    "description": tool_desc,
                    "observation": obs_summary,
                    "details": structured_obs,
                    "image_url": structured_obs.get("image_url") if isinstance(structured_obs, dict) else None,
                    "sources": structured_obs.get("sources", []) if isinstance(structured_obs, dict) else [],
                    "web_images": structured_obs.get("images", []) if isinstance(structured_obs, dict) else [],
                    "execution_time_sec": t_tool_dur,
                    "status": "success" if is_tool_success else "failed"
                }

                if custom_agent_prompt:
                    web_prompt_addon = custom_agent_prompt
                elif not web_prompt_addon:
                    style_hint = (
                        "sampaikan dengan gaya bicara santai dan hangat khas Shiro tanpa menyebut nama tool internal."
                        if roleplay_enabled
                        else "sampaikan secara profesional, objektif, dan lugas sebagai AI Agent tanpa menyebut nama tool internal."
                    )
                    web_prompt_addon = (
                        f"\n\n[Informasi / Fakta Web Nyata Real-time]:\n"
                        f"{obs_summary}\n\n"
                        f"[Instruksi Penyajian]:\n"
                        f"1. Jawab pertanyaan pengguna secara akurat menggunakan fakta & tautan sumber di atas.\n"
                        f"2. Jangan pernah mengatakan 'loading', 'tunggu sebentar', atau pura-pura mengecek karena datanya SUDAH tersedia di atas.\n"
                        f"3. Cantumkan tautan sumber `[Judul](URL)` atau gambar `![Judul](url)` yang tersedia jika relevan, dan {style_hint}\n"
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
    elif memory and hasattr(memory, "get_session_history"):
        history_slice = memory.get_session_history(session_id)
        if history_slice and history_slice[-1].get("role") == "user" and history_slice[-1].get("content") == raw_user_typed:
            history_slice = history_slice[:-1]
        for m in history_slice:
            r = m.get("role", "")
            c = m.get("content", "")
            if r in ["user", "assistant"] and c:
                clean_context.append({"role": r, "content": str(c)})
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
    effective_ctx = active_ctx
    if is_lyra_model:
        chosen_tier_id = lyra_tier if is_valid_lyra_tier(lyra_tier) else get_saved_lyra_tier()
        lyra_tier_info = resolve_lyra_tier(chosen_tier_id)
        effective_ctx = min(active_ctx, int(lyra_tier_info["tokens"]))
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
    max_history_tokens = max(1024, effective_ctx - reserved_budget)
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
    if has_doc and all_docs:
        from shiro.document.reader import build_document_prompt, build_multi_document_prompt
        if is_qwen38_27b_uncensored(active_model_path or active_model_name) and effective_ctx > 65536:
            doc_token_budget = max(20000, effective_ctx - reserved_budget - 4096)
            max_doc_chars = min(3_000_000, doc_token_budget * 3)
        else:
            max_doc_chars = max(12000, min(120000, (effective_ctx - 2000) * 3))
        if len(all_docs) > 1 or any(
            kw in (raw_user_typed or "").lower()
            for kw in ("perbaiki", "fix", "bug", "error", "debug", "analisa", "analisis", "audit", "rencana", "plan", "kode", "masalah")
        ):
            doc_prompt_addon = build_multi_document_prompt(
                all_docs,
                user_query=raw_user_typed,
                max_total_chars=max_doc_chars,
            )
        else:
            single_doc = all_docs[0]
            doc_full_text = single_doc.get("text", "")
            if len(doc_full_text) > max_doc_chars:
                doc_full_text = doc_full_text[:max_doc_chars] + f"\n\n... [Sisa teks dokumen dipotong karena melampaui batas {max_doc_chars} karakter]"
            doc_prompt_addon = build_document_prompt(
                {"filename": single_doc.get("filename", "Dokumen"), "text": doc_full_text},
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
        if has_video:
            vid_summary_blk = "\n".join(video_meta_lines)
            visual_guidance_addon = (
                f"\n\n### 🎬 PANDUAN PENGAMATAN VIDEO & VISUAL MULTIMODAL:\n"
                f"- {user_name} melampirkan VIDEO nyata berikut:\n{vid_summary_blk}\n"
                f"- Seluruh {len(all_images)} frame gambar yang masuk adalah potongan adegan KRONOLOGIS dari awal hingga akhir (ditambah gambar tambahan jika ada).\n"
                f"- Amati transisi gerakan, kejadian, teks di layar, serta perubahan antar frame secara berurutan untuk memahami keseluruhan isi video secara faktual.\n"
            )
        else:
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

    active_model_display = (
        f"{lyra_tier_info['label']} (seri {active_model_name})"
        if (lyra_tier_info and active_model_name and lyra_tier_info.get("label") != active_model_name)
        else ((lyra_tier_info or {}).get("label") or active_model_name or "ShiroHaru-Lyra-Agent")
    )

    if api_version == "v2":
        system_prompt = build_vtuber_system_prompt(
            owner_name=user_name,
            custom_instruction=custom_persona,
            active_model_name=active_model_display,
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
            user_context=user_context,
            active_model_name=active_model_display,
            roleplay_enabled=roleplay_enabled,
        ) + tools_addon + reasoning_addon + time_ctx_addon + visual_guidance_addon

    is_heavy_task = _is_heavy_agent_task(
        raw_user_typed=raw_user_typed,
        agent_intent=agent_intent_detected,
        has_doc=has_doc,
        has_image=has_image,
        has_video=has_video,
        api_version=api_version,
        tools=tools,
        include_reasoning=include_reasoning,
        reasoning_effort=reasoning_effort,
    )

    # Mode Kecepatan & Penalaran khusus per-tier ShiroHaru-Lyra-Agent
    lyra_thinking_mode = lyra_tier_info.get("thinking_mode", "standard") if lyra_tier_info else None
    if is_lyra_model and not is_reasoning_enabled and api_version not in ("v2", "v3"):
        if not is_heavy_task:
            system_prompt += (
                "\n\n[Mode Respons Langsung]: Ini adalah obrolan/pertanyaan ringan tanpa tugas agen berat. "
                "Jawab langsung secara natural, hangat, dan ringkas tanpa blok analisis panjang."
            )
        elif lyra_thinking_mode == "off":
            system_prompt += (
                "\n\n[Mode Cepat ShiroHaru-Lyra Low]: Jawab cepat, padat, langsung ke inti, "
                "dan tetap fungsional tanpa bertele-tele."
            )
        elif lyra_thinking_mode == "light":
            system_prompt += (
                "\n\n[Mode Seimbang ShiroHaru-Lyra Medium]: Jawab langsung dengan cepat, jelas, "
                "dan lengkap tanpa proses berpikir berpanjang-panjang."
            )
        else:
            system_prompt += (
                "\n\n[Antigravity Internal Analysis Mode]:\n"
                "Before writing your final response, analyze the user's request carefully inside <think>...</think> "
                "in clear, structured ENGLISH organized into numbered reasoning stages (1., 2., 3., ... up to as many stages as the task genuinely requires) covering: "
                "Request & Intent, Multi-Angle Technical/Research Plan, Exact Filenames & Verification. "
                "Wait until after </think> to write your user-facing answer in the user's language (100% Indonesian for Indonesian input)."
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
            if has_video:
                prompt_parts.append(f"[Melampirkan Video ({len(all_images)} frame kronologis):\n" + "\n".join(video_meta_lines) + "]")
            if raw_user_typed:
                prompt_parts.append(raw_user_typed)
            elif has_video:
                prompt_parts.append(f"{ai_name}, tolong tonton, amati rangkaian frame video, dan jelaskan isi video yang {user_name} lampirkan ini secara menyeluruh!")
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
            if roleplay_enabled and api_version != "v3":
                parts_user.append(
                    f"\n[Pedoman Bahasa]: {user_name} berbicara dalam Bahasa Indonesia. "
                    f"Jawab 100% dalam Bahasa Indonesia santai khas {ai_name} dari awal sampai akhir. "
                    f"DILARANG KERAS mencampur atau beralih ke Bahasa Inggris pada narasi tindakan *...* maupun dialog "
                    f"(jangan menulis frasa seperti 'my head against his shoulder', 'Shiro here', 'you don\'t gotta', 'swallows hard', 'whispers', dll; gunakan Bahasa Indonesia alami sepenuhnya)."
                )
            elif api_version != "v3":
                parts_user.append(
                    f"\n[Pedoman Bahasa]: Pengguna berbicara dalam Bahasa Indonesia. "
                    f"Jawab 100% dalam Bahasa Indonesia profesional yang bersih, langsung, dan bebas narasi roleplay (*...*) maupun sapaan 'Kakak'."
                )

        user_text = "\n".join(parts_user)
        user_turn_msg = {"role": "user", "content": user_text}

    if api_version == "v2":
        disable_thinking = True
    elif is_lyra_model and not is_reasoning_enabled and api_version != "v3":
        disable_thinking = bool((not is_heavy_task) or (lyra_thinking_mode in ("off", "light")))
    else:
        disable_thinking = False

    # Soft-switch (/no_think) pada mode cepat, obrolan ringan, atau VTuber v2 agar respons langsung keluar tanpa blok <think>
    if is_lyra_model and disable_thinking and api_version != "v3":
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
    while clean_context and (prompt_tokens_est + 512 > effective_ctx):
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

    remaining_space = max(256, effective_ctx - prompt_tokens_est - 128)
    max_output_tokens = min(desired_max, remaining_space)

    stop_tokens = [
        "<|im_end|>", "<|im_start|>", "<|eot_id|>", "<|end|>", "<|end_of_text|>",
        "\nUser:", "\nKakak:", "\nuser:", "\nAssistant:", "\nassistant:",
        "\n<|im_start|>user", "\n<|im_start|>assistant"
    ]
    if disable_thinking and not is_reasoning_enabled:
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

    tier_lbl_en = lyra_tier_info["label"] if lyra_tier_info else (active_model_name or "Standard")
    mode_en = "Fast Agent Path" if disable_thinking else f"English Analysis ({lyra_thinking_mode or 'standard'})"
    max_agent_rounds = (
        1
        if api_version == "v2"
        else get_max_agent_rounds(lyra_tier_info["id"] if lyra_tier_info else None)
    )

    if api_version == "v2" or not is_heavy_task:
        agent_steps: List[Dict[str, Any]] = []
    else:
        agent_steps = [
            {
                "id": "analyze",
                "title": "Analyze Request & Context",
                "status": "done",
                "feedback": (
                    f"Intent: {agent_intent_detected} · Profile: {tier_lbl_en} · "
                    f"Memory: {len(relevant_facts)} fact(s), {len(clean_context)} turn(s) · Mode: {mode_en}"
                ),
            }
        ]
        if agent_action_data and agent_action_data.get("tool") not in ("archive_packager", "video_renderer"):
            t_key = agent_action_data.get("tool")
            if t_key in ("multi_source_web_research", "google_web_search"):
                for sub_s in research_substeps:
                    agent_steps.append(sub_s)
                src_cnt = len(agent_action_data.get("sources") or [])
                img_cnt = len(agent_action_data.get("web_images") or [])
                agent_steps.append({
                    "id": "web_search",
                    "title": "Search Web & Browser Sources",
                    "status": "done" if agent_action_data.get("status") == "success" else "failed",
                    "feedback": f"Collected {src_cnt} web source(s) & {img_cnt} image(s) for grounded synthesis.",
                })
            elif t_key == "web_browser_reader":
                src_cnt = len(agent_action_data.get("sources") or [])
                img_cnt = len(agent_action_data.get("web_images") or [])
                agent_steps.append({
                    "id": "web_browse",
                    "title": "Open & Read Webpage",
                    "status": "done" if agent_action_data.get("status") == "success" else "failed",
                    "feedback": f"Extracted webpage content ({src_cnt} URL, {img_cnt} image(s)).",
                })
            else:
                agent_steps.append({
                    "id": f"tool_{agent_action_data['tool']}",
                    "title": f"Execute Tool ({agent_action_data['tool']})",
                    "status": "done" if agent_action_data.get("status") == "success" else "failed",
                    "feedback": str(agent_action_data.get("description") or "")[:160],
                })
        elif pending_archive_request:
            found_cnt = len(available_archive_files)
            agent_steps.append({
                "id": "scan_files",
                "title": "Inspect Workspace & Conversation Files",
                "status": "done",
                "feedback": f"Found {found_cnt} file(s) across history/uploads; packaging will run after AI completes its response.",
            })

        if has_doc and all_docs:
            total_chars_read = sum(len(str(d.get("text") or "")) for d in all_docs)
            file_list_str = ", ".join(str(d.get("filename") or "doc") for d in all_docs[:6])
            if len(all_docs) > 6:
                file_list_str += f" (+{len(all_docs) - 6} more)"
            agent_steps.append({
                "id": "read_files",
                "title": f"Read All Uploaded Files ({len(all_docs)} file{'s' if len(all_docs) > 1 else ''})",
                "status": "done",
                "feedback": f"Loaded {total_chars_read:,} chars across: {file_list_str}",
            })
            agent_steps.append({
                "id": "plan",
                "title": "Diagnose Issues & Formulate Fix Plan",
                "status": "done",
                "feedback": f"Cross-referencing all {len(all_docs)} file(s) and planning targeted fixes before code output.",
            })

        if has_video and all_videos:
            vid_list_str = ", ".join(str(v.get("filename") or "video") for v in all_videos[:4])
            agent_steps.append({
                "id": "read_video",
                "title": f"Analyze Uploaded Video ({len(all_videos)} video)",
                "status": "done",
                "feedback": f"Inspecting video timeline & visual scenes from: {vid_list_str}",
            })

    return {
        "t_start_total": t_start_total,
        "nodes": nodes,
        "llm": llm,
        "active_model_name": active_model_name,
        "active_model_path": active_model_path,
        "is_lyra_model": is_lyra_model,
        "lyra_tier_info": lyra_tier_info,
        "disable_thinking": disable_thinking,
        "is_heavy_task": is_heavy_task,
        "roleplay_enabled": roleplay_enabled,
        "max_agent_rounds": max_agent_rounds,
        "raw_user_typed": raw_user_typed,
        "msgs": msgs,
        "call_kwargs": call_kwargs,
        "gen_params": gen_params,
        "active_ctx": active_ctx,
        "effective_ctx": effective_ctx,
        "user_turn_msg": user_turn_msg,
        "system_prompt": system_prompt,
        "all_images": all_images,
        "has_image": has_image,
        "visual_evidence_text": visual_evidence_text,
        "web_prompt_addon": web_prompt_addon,
        "agent_action_data": agent_action_data,
        "agent_intent_detected": agent_intent_detected,
        "generated_artifacts": generated_artifacts,
        "pending_archive_request": pending_archive_request,
        "pending_video_request": pending_video_request,
        "available_archive_files": available_archive_files,
        "inferred_project_name": inferred_project_name,
        "all_docs_files": all_docs_files,
        "agent_steps": agent_steps,
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
    grounding_info: Optional[Dict[str, Any]] = None,
    thought_content_override: Optional[str] = None,
    thought_duration_sec: Optional[float] = None
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
        "summary": f"{round(t_llm_dur)}ms • {active_model_name or 'ShiroHaru'}",
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

    if thought_content_override and str(thought_content_override).strip():
        reasoning_content = str(thought_content_override).strip()

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
        reasoning_content = None
        cleaned_reply = clean_vtuber_response(raw_reply, raw_user_typed)
    else:
        cleaned_reply = clean_response(
            raw_reply,
            assistant_name=prep.get("ai_name", "Shiro"),
            user_input=raw_user_typed,
            roleplay_enabled=prep.get("roleplay_enabled", True),
        )

    if not cleaned_reply and raw_reply:
        cleaned_reply = raw_reply.strip()

    inline_tool_calls, cleaned_reply = _parse_agent_tool_calls(cleaned_reply)
    if not cleaned_reply and raw_reply:
        _, cleaned_reply = _parse_agent_tool_calls(raw_reply)

    # Post-LLM Packaging, Deferred Video Rendering & Exact Filename Artifacts
    artifacts: List[Dict[str, Any]] = list(prep.get("generated_artifacts") or [])
    agent_steps: List[Dict[str, Any]] = (
        []
        if api_version == "v2"
        else [dict(s) for s in (prep.get("agent_steps") or [])]
    )
    pending_arch = prep.get("pending_archive_request")
    pending_video = prep.get("pending_video_request")
    ai_archive_call = next((tc for tc in reversed(inline_tool_calls) if tc.get("name") == "create_archive"), None)
    ai_video_call = next((tc for tc in reversed(inline_tool_calls) if tc.get("name") == "render_video"), None)

    try:
        from shiro.agent.packager import (
            extract_named_files_from_markdown,
            infer_project_name_from_text,
            merge_file_collections,
            create_archive_artifact,
            create_file_artifacts,
        )
        extracted_post = extract_named_files_from_markdown(cleaned_reply)
        has_archive_already = any(a.get("kind") == "archive" for a in artifacts)

        if (pending_arch or ai_archive_call) and not has_archive_already:
            arch_args = (ai_archive_call or {}).get("args") or {}
            req_files_ai = [
                s.strip() for s in str(arch_args.get("files") or "").split(",") if s.strip()
            ] if arch_args.get("files") else None
            eff_req_files = req_files_ai or (pending_arch or {}).get("requested_filenames") or None

            merged_arch_files = merge_file_collections(
                extracted_post,
                list(prep.get("all_docs_files") or []),
                list(prep.get("available_archive_files") or []),
                requested_filenames=eff_req_files,
            )
            if merged_arch_files:
                fmt_val = arch_args.get("format") or (pending_arch or {}).get("format", "zip")
                arch_name_val = arch_args.get("name") or (pending_arch or {}).get("archive_name")
                proj_name = (
                    prep.get("inferred_project_name")
                    or infer_project_name_from_text(cleaned_reply, merged_arch_files)
                )
                arch_art = create_archive_artifact(
                    merged_arch_files,
                    fmt=fmt_val,
                    archive_name=arch_name_val,
                    project_name=proj_name,
                )
                artifacts.append(arch_art)
                agent_steps.append({
                    "id": "package",
                    "title": f"Compress Archive ({arch_art['filename']})",
                    "status": "done",
                    "feedback": f"Packaged {arch_art['file_count']} file(s) into {arch_art['filename']} ({arch_art['format'].upper()}, {arch_art['size_label']})",
                })
        elif not artifacts and extracted_post:
            wants_file_download = bool(
                re.search(r'\b[A-Za-z0-9_\-]+\.[A-Za-z0-9]{1,12}\b', raw_user_typed or "")
                or any(
                    kw in (raw_user_typed or "").lower()
                    for kw in ("buatkan file", "buat file", "kirim file", "download", "unduh", "create file", "save as")
                )
            )
            if wants_file_download:
                file_arts = create_file_artifacts(extracted_post)
                if file_arts:
                    artifacts.extend(file_arts)
                    agent_steps.append({
                        "id": "files",
                        "title": "Prepare Exact File Downloads",
                        "status": "done",
                        "feedback": "Exact file(s) ready: " + ", ".join(a["filename"] for a in file_arts),
                    })
    except Exception as e_pkg:
        print(f"[Inference Packager Warning]: {e_pkg}")

    # Post-LLM Deferred MP4 Video Rendering
    if (pending_video or ai_video_call) and not any(a.get("kind") == "video" for a in artifacts):
        try:
            from shiro.vision.video import render_video_artifact
            v_args = (ai_video_call or {}).get("args") or {}
            v_title = v_args.get("title") or (pending_video or {}).get("title") or raw_user_typed or "Shiro AI Video"
            v_scenes = (
                [s.strip() for s in v_args["scenes"].split(";") if s.strip()]
                if v_args.get("scenes")
                else list((pending_video or {}).get("scenes") or [])
            )
            v_dur = float(v_args.get("duration") or (pending_video or {}).get("duration_sec") or 5.0)
            v_out = v_args.get("name") or (pending_video or {}).get("output_name")
            v_imgs = (pending_video or {}).get("input_images_b64") or None
            vid_art = render_video_artifact(
                title=v_title,
                scenes=v_scenes,
                input_images_b64=v_imgs,
                output_name=v_out,
                duration_sec=v_dur,
            )
            artifacts.append(vid_art)
            agent_steps.append({
                "id": "render_video",
                "title": f"Render MP4 Video ({vid_art['filename']})",
                "status": "done",
                "feedback": f"Rendered {vid_art['duration_sec']}s {vid_art['resolution']} MP4 ({vid_art['size_label']})",
            })
        except Exception as e_vid_post:
            print(f"[Inference Video Renderer Warning]: {e_vid_post}")

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
        "thought_content": reasoning_content,
        "thought_duration_sec": thought_duration_sec,
        "agent_steps": agent_steps,
        "artifacts": artifacts,
        "active_context_window": prep.get("effective_ctx", prep.get("active_ctx")),
        "agent_action": agent_action_data,
        "nodes": nodes
    }
    global_pipeline_manager.broadcast(trace)

    details = {
        "reasoning_content": reasoning_content,
        "thought_duration_sec": thought_duration_sec,
        "agent_steps": agent_steps,
        "artifacts": artifacts,
        "active_context_window": prep.get("effective_ctx", prep.get("active_ctx")),
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
    documents: Optional[List[Dict[str, Any]]] = None,
    videos: Optional[List[Dict[str, Any]]] = None,
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
    lyra_tier: Optional[str] = None,
    session_id: Optional[str] = None,
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
            documents=documents,
            videos=videos,
            api_version=api_version,
            custom_system_prompt=custom_system_prompt,
            incoming_messages=incoming_messages,
            tools=tools,
            tool_choice=tool_choice,
            reasoning_effort=reasoning_effort,
            include_reasoning=include_reasoning,
            max_tokens=max_tokens,
            lyra_tier=lyra_tier,
            session_id=session_id,
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
        max_agent_rounds = int(prep.get("max_agent_rounds", 12))
        sync_tier_id = (prep.get("lyra_tier_info") or {}).get("id")
        executed_tool_sigs = set()
        for react_round in range(max_agent_rounds):
            t_round = time.perf_counter()
            active_model_path = prep.get("active_model_path", "")
            disable_thinking = bool(prep.get("disable_thinking", False))
            use_fast_text = _should_use_fast_text_completion(llm, has_image, tools, active_model_path)

            with state.llm_lock:
                res = None
                if use_fast_text:
                    prompt_str = _format_chatml_prompt(msgs, disable_thinking=disable_thinking)
                    comp_kwargs = _build_completion_kwargs(call_kwargs, stream=False)
                    try:
                        if state.last_turn_had_image and hasattr(llm, "reset"):
                            llm.reset()
                            state.last_turn_had_image = False
                        comp_res = llm.create_completion(prompt=prompt_str, **comp_kwargs)
                    except Exception as e_fast_first:
                        comp_res = None
                        err_fast_str = str(e_fast_first).lower()
                        if "exceed" in err_fast_str and ("context" in err_fast_str or "token" in err_fast_str or "window" in err_fast_str):
                            try:
                                em_prompt = _format_chatml_prompt(
                                    [{"role": "system", "content": system_prompt[:1200]}, user_turn_msg],
                                    disable_thinking=disable_thinking
                                )
                                comp_res = llm.create_completion(prompt=em_prompt, **comp_kwargs)
                            except Exception:
                                comp_res = None
                        elif hasattr(llm, "reset"):
                            try:
                                llm.reset()
                                comp_res = llm.create_completion(prompt=prompt_str, **comp_kwargs)
                            except Exception:
                                comp_res = None
                        if comp_res is None:
                            print(f"[Inference Fast-Path Fallback]: {e_fast_first}")

                    if comp_res is not None:
                        comp_choice = (comp_res.get("choices") or [{}])[0] if isinstance(comp_res, dict) else {}
                        res = {
                            "choices": [{
                                "message": {"content": comp_choice.get("text", "") or ""},
                                "finish_reason": comp_choice.get("finish_reason", "stop"),
                            }],
                            "usage": comp_res.get("usage", {}) if isinstance(comp_res, dict) else {},
                        }

                if res is None:
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
                        if has_image:
                            state.last_turn_had_image = True
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

                raw_reply = (res['choices'][0]['message'].get('content', '') or '').strip()

            round_calls, _ = _parse_agent_tool_calls(raw_reply)
            research_calls = []
            for tc in round_calls:
                if tc.get("name") in ("web_search", "open_url", "screenshot"):
                    sig = f"{tc.get('name')}|{json.dumps(tc.get('args') or {}, sort_keys=True)}"
                    if sig not in executed_tool_sigs:
                        research_calls.append((tc, sig))
            if research_calls and react_round + 1 < max_agent_rounds:
                is_heavy_task_stream = True
                obs_chunks: List[str] = []
                agg_sources: List[Dict[str, Any]] = list((prep.get("agent_action_data") or {}).get("sources") or [])
                agg_images: List[Dict[str, Any]] = list((prep.get("agent_action_data") or {}).get("web_images") or [])
                last_img_url = (prep.get("agent_action_data") or {}).get("image_url")
                for tc, sig in research_calls[:4]:
                    executed_tool_sigs.add(sig)
                    tool_res = _execute_live_research_tool(tc, tier_id=sync_tier_id)
                    obs_chunks.append(f"[{tool_res['title']}]\n{tool_res['observation']}")
                    for src_it in tool_res.get("sources") or []:
                        if src_it.get("url") and not any(s.get("url") == src_it["url"] for s in agg_sources):
                            agg_sources.append(src_it)
                    for im_it in tool_res.get("web_images") or []:
                        if im_it.get("url") and not any(im.get("url") == im_it["url"] for im in agg_images):
                            agg_images.append(im_it)
                    if tool_res.get("image_url"):
                        last_img_url = tool_res["image_url"]
                    prep.setdefault("agent_steps", []).append({
                        "id": f"react_{react_round}_{tc.get('name')}",
                        "title": tool_res["title"],
                        "status": tool_res["status"],
                        "feedback": f"Retrieved {len(tool_res.get('sources') or [])} source(s) & {len(tool_res.get('web_images') or [])} image(s).",
                    })
                prep["agent_action_data"] = {
                    "tool": research_calls[0][0].get("name") if research_calls[0][0].get("name") != "web_search" else "multi_source_web_research",
                    "description": f"Live browser search round {react_round + 1}",
                    "observation": "\n\n".join(obs_chunks),
                    "details": {"sources": agg_sources, "images": agg_images, "image_url": last_img_url},
                    "image_url": last_img_url,
                    "sources": agg_sources,
                    "web_images": agg_images,
                    "execution_time_sec": round(time.perf_counter() - t_round, 2),
                    "status": "success" if obs_chunks else "failed",
                }
                msgs = list(msgs) + [
                    {"role": "assistant", "content": raw_reply},
                    {
                        "role": "user",
                        "content": (
                            "[HASIL PENELUSURAN BROWSER/WEB REAL-TIME]:\n"
                            + "\n\n".join(obs_chunks)
                            + "\n\nJawab pertanyaan Kakak secara langsung, lengkap, dan akurat menggunakan hasil di atas, sertakan link sumber `[Judul](URL)` serta gambar relevan `![Judul](url)` bila tersedia."
                        ),
                    },
                ]
                continue
            break

        with state.llm_lock:
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

        t_end = time.perf_counter()
        t_llm_dur = (t_end - t0) * 1000
        tier_lbl_sync = (prep.get("lyra_tier_info") or {}).get("id", "default")
        path_lbl_sync = "fast_chatml" if use_fast_text else "chat_handler"
        est_tok_sync = max(1, len(raw_reply) // 4)
        est_tps_sync = est_tok_sync / max(0.05, t_end - t0)
        print(
            f"⚡ [Inference] model={prep.get('active_model_name')} tier={tier_lbl_sync} "
            f"path={path_lbl_sync} ctx={prep.get('effective_ctx', prep.get('active_ctx')):,} "
            f"total={round(t_llm_dur)}ms chars={len(raw_reply)} (~{est_tps_sync:.1f} tok/s)"
        )
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

def _split_partial_think_suffix(buf: str) -> Tuple[str, str]:
    """Menahan sufiks parsial '<think>' atau '</think>' agar tag tidak terpotong antar-chunk SSE."""
    if not buf:
        return "", ""
    low = buf.lower()
    max_hold = 0
    for tag in ("<think>", "</think>"):
        for k in range(1, len(tag)):
            if low.endswith(tag[:k]):
                max_hold = max(max_hold, k)
    if max_hold > 0:
        return buf[:-max_hold], buf[-max_hold:]
    return buf, ""


def stream_shiro_reply(
    user_input: str,
    image_base64: Optional[Union[str, List[str]]] = None,
    images_base64: Optional[List[str]] = None,
    document_info: Optional[Dict[str, Any]] = None,
    documents: Optional[List[Dict[str, Any]]] = None,
    videos: Optional[List[Dict[str, Any]]] = None,
    api_version: str = "v1",
    custom_system_prompt: Optional[str] = None,
    incoming_messages: Optional[List[Dict[str, Any]]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None,
    include_reasoning: bool = False,
    max_tokens: Optional[int] = None,
    lyra_tier: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    Eksekusi streaming token neural real-time (Server-Sent Events generator).
    Yields events:
    - {'type': 'status', 'status': '...'}
    - {'type': 'agent_trace_step', 'step': {'id': ..., 'title': ..., 'status': ..., 'feedback': ...}}
    - {'type': 'thought', 'token': '...'}
    - {'type': 'thought_done', 'duration_sec': ...}
    - {'type': 'artifacts', 'artifacts': [...]}
    - {'type': 'agent_action', 'agent_action': ...}
    - {'type': 'token', 'token': '...'}
    - {'type': 'ping'}
    - {'type': 'done', 'reply': '...', 'trace': ...}
    """
    t_start_total = time.perf_counter()
    try:
        # Pre-detect intent: hanya tampilkan step agent berat bila benar-benar diperlukan (bukan casual chat / VTuber v2)
        raw_user_typed = (user_input or "").strip()
        pre_intent = "none"
        pre_has_doc = bool(document_info or documents)
        pre_has_image = bool(image_base64 or images_base64)
        pre_has_video = bool(videos)
        if raw_user_typed:
            try:
                from shiro.agent.tools import detect_agent_intent
                mem_inst = state.init_memory()
                pre_hist = (
                    mem_inst.get_session_history(session_id)
                    if (mem_inst and hasattr(mem_inst, "get_session_history"))
                    else getattr(mem_inst, 'short_term_history', None)
                )
                intent_info = detect_agent_intent(raw_user_typed, conversation_history=pre_hist)
                pre_intent = intent_info.get("intent", "none")
                if api_version == "v2" and pre_intent in ("archive", "generate_video", "powershell"):
                    pre_intent = "none"
                pre_is_heavy = _is_heavy_agent_task(
                    raw_user_typed=raw_user_typed,
                    agent_intent=pre_intent,
                    has_doc=pre_has_doc,
                    has_image=pre_has_image,
                    has_video=pre_has_video,
                    api_version=api_version,
                    tools=tools,
                    include_reasoning=include_reasoning,
                    reasoning_effort=reasoning_effort,
                )
                if pre_is_heavy:
                    yield {
                        "type": "agent_trace_step",
                        "step": {
                            "id": "analyze",
                            "title": "Analyzing Request & Intent",
                            "status": "running",
                            "feedback": "Inspecting prompt context, active memory, and available agent tools...",
                        },
                    }
                if pre_intent == "archive":
                    arch_fmt = intent_info.get("params", {}).get("format", "zip")
                    yield {"type": "status", "status": f"Menganalisis & mengompres berkas ke .{arch_fmt}..."}
                elif pre_intent == "generate_video":
                    yield {"type": "status", "status": "Sedang merender video MP4..."}
                elif pre_intent == "screenshot":
                    target_u = intent_info.get("params", {}).get("url", "")
                    yield {"type": "status", "status": f"Sedang mengambil tangkapan layar website ({target_u or 'web'})..."}
                elif pre_intent == "search":
                    q = intent_info.get("params", {}).get("query", raw_user_typed)
                    yield {"type": "status", "status": f"Sedang mencari di Google/Web: '{q[:32]}'..."}
                elif pre_intent == "browse":
                    target_u = intent_info.get("params", {}).get("url", "")
                    yield {"type": "status", "status": f"Sedang membaca isi halaman web: {target_u[:32]}..."}
                elif pre_intent == "weather":
                    yield {"type": "status", "status": "Sedang memeriksa data satelit cuaca..."}
                elif pre_intent == "powershell":
                    yield {"type": "status", "status": "Sedang menjalankan perintah terminal PC..."}
                elif pre_intent == "math":
                    yield {"type": "status", "status": "Sedang menghitung kalkulasi matematika..."}
                elif pre_intent == "time":
                    yield {"type": "status", "status": "Sedang mengecek jam dan kalender dunia..."}
                else:
                    try:
                        from shiro.persona import load_active_profiles
                        _ai_name, _, _, _ = load_active_profiles()
                    except Exception:
                        _ai_name = "Shiro"
                    yield {"type": "status", "status": f"{_ai_name} sedang merangkai jawaban..."}
            except Exception:
                yield {"type": "status", "status": "Sedang berpikir..."}
        else:
            pre_is_heavy = _is_heavy_agent_task(
                raw_user_typed="",
                agent_intent="none",
                has_doc=pre_has_doc,
                has_image=pre_has_image,
                has_video=pre_has_video,
                api_version=api_version,
                tools=tools,
                include_reasoning=include_reasoning,
                reasoning_effort=reasoning_effort,
            )
            if pre_is_heavy:
                yield {
                    "type": "agent_trace_step",
                    "step": {
                        "id": "analyze",
                        "title": "Analyzing Request & Intent",
                        "status": "running",
                        "feedback": "Inspecting uploaded files/media and workspace context...",
                    },
                }
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
            documents=documents,
            videos=videos,
            api_version=api_version,
            custom_system_prompt=custom_system_prompt,
            incoming_messages=incoming_messages,
            tools=tools,
            tool_choice=tool_choice,
            reasoning_effort=reasoning_effort,
            include_reasoning=include_reasoning,
            max_tokens=max_tokens,
            lyra_tier=lyra_tier,
            session_id=session_id,
            t_start_total=t_start_total
        )
        is_heavy_task_stream = bool(prep.get("is_heavy_task", False)) and api_version != "v2"
        if is_heavy_task_stream:
            for st_step in prep.get("agent_steps") or []:
                yield {"type": "agent_trace_step", "step": st_step}
        if prep.get("agent_action_data"):
            yield {"type": "agent_action", "agent_action": prep["agent_action_data"]}

        if is_heavy_task_stream:
            tier_lbl_live = (prep.get("lyra_tier_info") or {}).get("label") or (prep.get("active_model_name") or "Agent")
            reason_fb = (
                f"Running English reasoning & solution design ({tier_lbl_live})..."
                if not prep.get("disable_thinking")
                else f"Synthesizing direct response ({tier_lbl_live})..."
            )
            yield {
                "type": "agent_trace_step",
                "step": {
                    "id": "reason",
                    "title": "Reasoning & Solution Synthesis",
                    "status": "running",
                    "feedback": reason_fb,
                },
            }

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
        has_image_turn = bool(prep.get("has_image"))
        tools_turn = prep.get("tools")
        tool_choice_turn = prep.get("tool_choice")
        active_model_path = prep.get("active_model_path", "")
        disable_thinking = bool(prep.get("disable_thinking", False))
        use_fast_text = _should_use_fast_text_completion(llm, has_image_turn, tools_turn, active_model_path)
        path_used = "fast_chatml" if use_fast_text else "chat_handler"

        thought_acc = ""
        thought_duration_sec: Optional[float] = None
        t_first_token = None
        max_clause_len = 48 if lyra_tier_id == "low" else 80
        any_visible_streamed = False
        max_agent_rounds = int(prep.get("max_agent_rounds", 12))
        executed_tool_sigs = set()
        think_stage_idx = 0
        think_line_buf = ""
        seen_think_headings = set()

        def _flush_stream_seg(seg: str) -> str:
            if not seg or not seg.strip():
                return seg
            if should_guard_id and "```" not in seg and contains_english_segments(seg):
                replaced = replace_inline_english_idioms(seg)
                if lyra_tier_id != "low" and is_predominantly_english(replaced.strip()):
                    lead_ws = re.match(r'^\s*', replaced).group(0)
                    trail_ws = re.search(r'\s*$', replaced).group(0)
                    tr = translate_to_indonesian_fast(
                        replaced.strip(),
                        roleplay_enabled=prep.get("roleplay_enabled", True),
                    )
                    if tr and tr.strip():
                        return lead_ws + tr.strip() + trail_ws
                return replaced
            return seg

        def _extract_dynamic_think_stages(th_piece: str):
            nonlocal think_line_buf, think_stage_idx
            if not is_heavy_task_stream:
                return []
            ev_list = []
            think_line_buf += th_piece
            while "\n" in think_line_buf:
                line_raw, think_line_buf = think_line_buf.split("\n", 1)
                line_cln = line_raw.strip()
                m_stage = re.match(
                    r'^(?:(\d{1,2})[\.\)]\s+|\#{1,3}\s+|(?:Step|Phase|Stage|Analysis)\s+(\d{1,2})[:.\s-]+)(.{6,85})$',
                    line_cln,
                    flags=re.IGNORECASE,
                )
                if m_stage and think_stage_idx < max_agent_rounds:
                    heading = re.sub(r'[*_`]+', '', m_stage.group(3)).strip().rstrip(':')
                    norm_h = heading.lower()
                    if norm_h and norm_h not in seen_think_headings:
                        seen_think_headings.add(norm_h)
                        if think_stage_idx > 0:
                            ev_list.append({
                                "type": "agent_trace_step",
                                "step": {
                                    "id": f"think_stage_{think_stage_idx}",
                                    "status": "done",
                                },
                            })
                        think_stage_idx += 1
                        ev_list.append({
                            "type": "agent_trace_step",
                            "step": {
                                "id": f"think_stage_{think_stage_idx}",
                                "title": f"Analysis Step {think_stage_idx}: {heading[:58]}",
                                "status": "running",
                                "feedback": f"Deep reasoning step {think_stage_idx} ({tier_lbl_live if 'tier_lbl_live' in locals() else lyra_tier_id})...",
                            },
                        })
            return ev_list

        for react_round in range(max_agent_rounds):
            if react_round > 0 and any_visible_streamed:
                yield {"type": "reset_stream"}
                any_visible_streamed = False

            round_raw_reply = ""
            # Serialisasi akses ke llama_context via global lock sambil menjaga SSE heartbeat tetap hidup
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

            chunk_queue: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
            cancel_event = threading.Event()
            worker_started = False
            round_msgs = list(msgs)

            def _llm_stream_worker():
                nonlocal path_used
                stream_iter = None
                try:
                    fast_succeeded = False
                    if use_fast_text:
                        prompt_str = _format_chatml_prompt(round_msgs, disable_thinking=disable_thinking)
                        stream_comp_kwargs = _build_completion_kwargs(call_kwargs, stream=True)
                        emitted_fast = False
                        try:
                            if state.last_turn_had_image and hasattr(llm, "reset"):
                                llm.reset()
                                state.last_turn_had_image = False
                            stream_iter = llm.create_completion(prompt=prompt_str, **stream_comp_kwargs)
                            for ch in stream_iter:
                                if cancel_event.is_set():
                                    break
                                txt = ((ch.get("choices") or [{}])[0].get("text", "") or "") if isinstance(ch, dict) else ""
                                if txt:
                                    emitted_fast = True
                                    chunk_queue.put(("chunk", {"choices": [{"delta": {"content": txt}}]}))
                            fast_succeeded = True
                        except Exception as e_fast_stream:
                            if cancel_event.is_set():
                                return
                            if stream_iter is not None and hasattr(stream_iter, "close"):
                                try:
                                    stream_iter.close()
                                except Exception:
                                    pass
                            stream_iter = None
                            if not emitted_fast and hasattr(llm, "reset"):
                                try:
                                    llm.reset()
                                    stream_iter = llm.create_completion(prompt=prompt_str, **stream_comp_kwargs)
                                    for ch in stream_iter:
                                        if cancel_event.is_set():
                                            break
                                        txt = ((ch.get("choices") or [{}])[0].get("text", "") or "") if isinstance(ch, dict) else ""
                                        if txt:
                                            chunk_queue.put(("chunk", {"choices": [{"delta": {"content": txt}}]}))
                                    fast_succeeded = True
                                except Exception as e_fast_retry:
                                    if cancel_event.is_set():
                                        return
                                    print(f"[Inference Fast-Path Fallback]: {e_fast_retry}")
                            else:
                                print(f"[Inference Fast-Path Fallback]: {e_fast_stream}")
                            if not fast_succeeded:
                                path_used = "chat_handler"
                                if stream_iter is not None and hasattr(stream_iter, "close"):
                                    try:
                                        stream_iter.close()
                                    except Exception:
                                        pass
                                stream_iter = None

                    if not fast_succeeded:
                        stream_kwargs = dict(call_kwargs)
                        stream_kwargs["stream"] = True
                        try:
                            if tools_turn:
                                try:
                                    stream_iter = llm.create_chat_completion(
                                        messages=round_msgs,
                                        tools=tools_turn,
                                        tool_choice=tool_choice_turn,
                                        **stream_kwargs
                                    )
                                except (TypeError, Exception):
                                    stream_iter = llm.create_chat_completion(messages=round_msgs, **stream_kwargs)
                            else:
                                stream_iter = llm.create_chat_completion(messages=round_msgs, **stream_kwargs)
                            if has_image_turn:
                                state.last_turn_had_image = True

                            for ch in stream_iter:
                                if cancel_event.is_set():
                                    break
                                chunk_queue.put(("chunk", ch))
                        except Exception as e_stream_inner:
                            if cancel_event.is_set():
                                return
                            print(f"[Inference Stream Fallback]: {e_stream_inner}")
                            if tools_turn:
                                try:
                                    res_sync = llm.create_chat_completion(
                                        messages=round_msgs,
                                        tools=tools_turn,
                                        tool_choice=tool_choice_turn,
                                        **call_kwargs
                                    )
                                except (TypeError, Exception):
                                    res_sync = llm.create_chat_completion(messages=round_msgs, **call_kwargs)
                            else:
                                res_sync = llm.create_chat_completion(messages=round_msgs, **call_kwargs)
                            if has_image_turn:
                                state.last_turn_had_image = True
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

            clause_buf = ""
            streamed_reply_acc = ""
            agent_tag_carry = ""
            in_think = False
            thinking_status_sent = False
            thought_started_at: Optional[float] = None
            tag_carry = ""

            def _emit_visible_token(vis_tok: str):
                nonlocal clause_buf, streamed_reply_acc, last_ping_time, t_first_token, agent_tag_carry, any_visible_streamed
                if not vis_tok and not agent_tag_carry:
                    return []
                ready_vis, agent_tag_carry = _split_partial_agent_tag(agent_tag_carry + vis_tok)
                if ready_vis and "AGENT_TOOL:" in ready_vis:
                    _, ready_vis = _parse_agent_tool_calls(ready_vis)
                if not ready_vis:
                    return []
                vis_tok = ready_vis

                out_events = []
                if not streamed_reply_acc and not clause_buf:
                    if not vis_tok.strip():
                        return []
                    vis_tok = vis_tok.lstrip()
                if t_first_token is None and vis_tok.strip():
                    t_first_token = time.perf_counter()

                if not should_guard_id or (round_raw_reply.count("```") % 2 == 1):
                    if clause_buf:
                        flushed = _flush_stream_seg(clause_buf)
                        streamed_reply_acc += flushed
                        any_visible_streamed = True
                        out_events.append({"type": "token", "token": flushed})
                        clause_buf = ""
                    streamed_reply_acc += vis_tok
                    any_visible_streamed = True
                    out_events.append({"type": "token", "token": vis_tok})
                    last_ping_time = time.perf_counter()
                else:
                    clause_buf += vis_tok
                    is_first_emit = not streamed_reply_acc
                    buf_cap = 48 if is_first_emit else max_clause_len
                    if "\n" in clause_buf:
                        head, sep, tail = clause_buf.rpartition("\n")
                        to_flush = head + sep
                        if to_flush.count("*") % 2 == 0:
                            flushed = _flush_stream_seg(to_flush)
                            streamed_reply_acc += flushed
                            any_visible_streamed = True
                            out_events.append({"type": "token", "token": flushed})
                            clause_buf = tail
                            last_ping_time = time.perf_counter()
                    elif clause_buf.count("*") % 2 == 0 and len(clause_buf) >= (20 if is_first_emit else 35):
                        m_sent = re.search(r'^([\s\S]*?[.!?~]["\'*)]?\s+)([\s\S]*)$', clause_buf)
                        if m_sent:
                            head_part, tail_part = m_sent.group(1), m_sent.group(2)
                            if head_part.count("*") % 2 == 0:
                                flushed = _flush_stream_seg(head_part)
                                streamed_reply_acc += flushed
                                any_visible_streamed = True
                                out_events.append({"type": "token", "token": flushed})
                                clause_buf = tail_part
                                last_ping_time = time.perf_counter()
                        elif is_first_emit and re.search(r'\s$', clause_buf):
                            flushed = _flush_stream_seg(clause_buf)
                            streamed_reply_acc += flushed
                            any_visible_streamed = True
                            out_events.append({"type": "token", "token": flushed})
                            clause_buf = ""
                            last_ping_time = time.perf_counter()
                    elif len(clause_buf) >= buf_cap:
                        flushed = _flush_stream_seg(clause_buf)
                        streamed_reply_acc += flushed
                        any_visible_streamed = True
                        out_events.append({"type": "token", "token": flushed})
                        clause_buf = ""
                        last_ping_time = time.perf_counter()
                return out_events

            def _process_stream_piece(piece_str: str):
                nonlocal in_think, thinking_status_sent, thought_acc, thought_started_at, thought_duration_sec, last_ping_time
                events_out = []
                cur = piece_str
                while cur:
                    if not in_think:
                        m_open = re.search(r'<think>', cur, flags=re.IGNORECASE)
                        if m_open:
                            before = cur[:m_open.start()]
                            if before:
                                events_out.extend(_emit_visible_token(before))
                            in_think = True
                            if thought_started_at is None:
                                thought_started_at = time.perf_counter()
                            if not thinking_status_sent:
                                thinking_status_sent = True
                                events_out.append({"type": "status", "status": f"{prep.get('ai_name', 'Shiro')} sedang menganalisis..."})
                            cur = cur[m_open.end():]
                        else:
                            events_out.extend(_emit_visible_token(cur))
                            cur = ""
                    else:
                        m_close = re.search(r'</think>', cur, flags=re.IGNORECASE)
                        if m_close:
                            th_seg = cur[:m_close.start()]
                            if th_seg:
                                if thought_acc and not thought_acc.endswith("\n") and react_round > 0:
                                    thought_acc += "\n"
                                thought_acc += th_seg
                                if api_version != "v2":
                                    events_out.append({"type": "thought", "token": th_seg})
                                    events_out.extend(_extract_dynamic_think_stages(th_seg))
                            in_think = False
                            if think_stage_idx > 0 and is_heavy_task_stream:
                                events_out.append({
                                    "type": "agent_trace_step",
                                    "step": {"id": f"think_stage_{think_stage_idx}", "status": "done"},
                                })
                            dur_s = round(max(0.1, time.perf_counter() - (thought_started_at or time.perf_counter())), 1)
                            thought_duration_sec = round((thought_duration_sec or 0.0) + dur_s, 1) if react_round > 0 else dur_s
                            if api_version != "v2":
                                events_out.append({"type": "thought_done", "duration_sec": thought_duration_sec})
                            if is_heavy_task_stream:
                                events_out.append({
                                    "type": "agent_trace_step",
                                    "step": {
                                        "id": "reason",
                                        "title": "Reasoning & Solution Synthesis",
                                        "status": "running",
                                        "feedback": f"English analysis complete ({thought_duration_sec}s) — streaming response...",
                                    },
                                })
                            cur = cur[m_close.end():]
                        else:
                            thought_acc += cur
                            if api_version != "v2":
                                events_out.append({"type": "thought", "token": cur})
                                events_out.extend(_extract_dynamic_think_stages(cur))
                            now_th = time.perf_counter()
                            if now_th - last_ping_time > ping_interval:
                                events_out.append({"type": "ping"})
                                last_ping_time = now_th
                            cur = ""
                return events_out

            try:
                worker_thread = threading.Thread(
                    target=_llm_stream_worker,
                    name="shiro-llm-stream-worker",
                    daemon=True
                )
                worker_thread.start()
                worker_started = True

                while True:
                    try:
                        ev_kind, ev_val = chunk_queue.get(timeout=ping_interval)
                    except queue.Empty:
                        yield {"type": "ping"}
                        last_ping_time = time.perf_counter()
                        continue

                    if ev_kind == "end":
                        if tag_carry:
                            for ev_item in _process_stream_piece(tag_carry):
                                yield ev_item
                            tag_carry = ""
                        if agent_tag_carry:
                            _, leftover_vis = _parse_agent_tool_calls(agent_tag_carry)
                            agent_tag_carry = ""
                            if leftover_vis:
                                clause_buf += leftover_vis
                        if in_think and thought_started_at is not None and thought_duration_sec is None:
                            thought_duration_sec = round(max(0.1, time.perf_counter() - thought_started_at), 1)
                            yield {"type": "thought_done", "duration_sec": thought_duration_sec}
                        break
                    elif ev_kind == "error":
                        raise ev_val
                    elif ev_kind == "sync_result":
                        res_sync = ev_val
                        sync_text = ""
                        if isinstance(res_sync, dict) and res_sync.get("choices"):
                            sync_text = res_sync["choices"][0].get("message", {}).get("content", "") or ""
                        if sync_text:
                            round_raw_reply = sync_text
                            if not is_reasoning_enabled:
                                for ev_item in _process_stream_piece(sync_text):
                                    yield ev_item
                            else:
                                _, vis_sync = _parse_agent_tool_calls(sync_text)
                                if vis_sync:
                                    if t_first_token is None:
                                        t_first_token = time.perf_counter()
                                    streamed_reply_acc = vis_sync
                                    any_visible_streamed = True
                                    yield {"type": "token", "token": vis_sync}
                        continue

                    chunk = ev_val
                    choices = chunk.get("choices", []) if isinstance(chunk, dict) else []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        round_raw_reply += token
                        if not is_reasoning_enabled:
                            ready_piece, tag_carry = _split_partial_think_suffix(tag_carry + token)
                            if ready_piece:
                                for ev_item in _process_stream_piece(ready_piece):
                                    yield ev_item
                        else:
                            for ev_item in _emit_visible_token(token):
                                yield ev_item

                    now = time.perf_counter()
                    if now - last_ping_time > ping_interval:
                        yield {"type": "ping"}
                        last_ping_time = now

                if clause_buf:
                    _, clean_tail = _parse_agent_tool_calls(clause_buf)
                    if clean_tail:
                        flushed = _flush_stream_seg(clean_tail)
                        streamed_reply_acc += flushed
                        any_visible_streamed = True
                        yield {"type": "token", "token": flushed}
                    clause_buf = ""
            finally:
                cancel_event.set()
                if lock_acquired and not worker_started:
                    try:
                        state.llm_lock.release()
                    except RuntimeError:
                        pass

            round_calls, _ = _parse_agent_tool_calls(round_raw_reply)
            research_calls = []
            for tc in round_calls:
                if tc.get("name") in ("web_search", "open_url", "screenshot"):
                    sig = f"{tc.get('name')}|{json.dumps(tc.get('args') or {}, sort_keys=True)}"
                    if sig not in executed_tool_sigs:
                        research_calls.append((tc, sig))
            if research_calls and react_round + 1 < max_agent_rounds:
                is_heavy_task_stream = True
                obs_chunks: List[str] = []
                agg_sources: List[Dict[str, Any]] = list((prep.get("agent_action_data") or {}).get("sources") or [])
                agg_images: List[Dict[str, Any]] = list((prep.get("agent_action_data") or {}).get("web_images") or [])
                last_img_url = (prep.get("agent_action_data") or {}).get("image_url")
                t_react = time.perf_counter()
                for idx_rc, (tc, sig) in enumerate(research_calls[:4]):
                    executed_tool_sigs.add(sig)
                    step_id = f"react_{react_round}_{idx_rc}_{tc.get('name')}"
                    step_label = (
                        f"Searching Browser ({(tc.get('args') or {}).get('query', '')[:36]})"
                        if tc.get("name") == "web_search"
                        else f"Opening Webpage ({(tc.get('args') or {}).get('url', '')[:36]})"
                    )
                    if is_heavy_task_stream:
                        yield {
                            "type": "agent_trace_step",
                            "step": {
                                "id": step_id,
                                "title": step_label,
                                "status": "running",
                                "feedback": "Fetching live browser sources & images...",
                            },
                        }
                    yield {"type": "status", "status": "Menelusuri informasi & gambar di browser..."}
                    tool_res = _execute_live_research_tool(tc, tier_id=lyra_tier_id)
                    obs_chunks.append(f"[{tool_res['title']}]\n{tool_res['observation']}")
                    for src_it in tool_res.get("sources") or []:
                        if src_it.get("url") and not any(s.get("url") == src_it["url"] for s in agg_sources):
                            agg_sources.append(src_it)
                    for im_it in tool_res.get("web_images") or []:
                        if im_it.get("url") and not any(im.get("url") == im_it["url"] for im in agg_images):
                            agg_images.append(im_it)
                    if tool_res.get("image_url"):
                        last_img_url = tool_res["image_url"]
                    done_step = {
                        "id": step_id,
                        "title": tool_res["title"],
                        "status": tool_res["status"],
                        "feedback": f"Found {len(tool_res.get('sources') or [])} source(s) & {len(tool_res.get('web_images') or [])} image(s).",
                    }
                    if is_heavy_task_stream:
                        prep.setdefault("agent_steps", []).append(done_step)
                        yield {"type": "agent_trace_step", "step": done_step}

                prep["agent_action_data"] = {
                    "tool": research_calls[0][0].get("name") if research_calls[0][0].get("name") != "web_search" else "multi_source_web_research",
                    "description": f"Live browser search round {react_round + 1}",
                    "observation": "\n\n".join(obs_chunks),
                    "details": {"sources": agg_sources, "images": agg_images, "image_url": last_img_url},
                    "image_url": last_img_url,
                    "sources": agg_sources,
                    "web_images": agg_images,
                    "execution_time_sec": round(time.perf_counter() - t_react, 2),
                    "status": "success" if obs_chunks else "failed",
                }
                yield {"type": "agent_action", "agent_action": prep["agent_action_data"]}
                msgs = list(msgs) + [
                    {"role": "assistant", "content": round_raw_reply},
                    {
                        "role": "user",
                        "content": (
                            "[HASIL PENELUSURAN BROWSER/WEB REAL-TIME]:\n"
                            + "\n\n".join(obs_chunks)
                            + "\n\nSekarang jawab pertanyaan pengguna secara langsung, lengkap, dan akurat menggunakan fakta, link sumber `[Judul](URL)`, serta gambar relevan `![Judul](url)` di atas."
                        ),
                    },
                ]
                if is_heavy_task_stream:
                    yield {
                        "type": "agent_trace_step",
                        "step": {
                            "id": "reason",
                            "title": "Reasoning & Solution Synthesis",
                            "status": "running",
                            "feedback": f"Synthesizing grounded response from browser sources (round {react_round + 2})...",
                        },
                    }
                continue

            raw_reply = round_raw_reply
            if should_guard_id and streamed_reply_acc.strip():
                _, non_tool_raw = _parse_agent_tool_calls(round_raw_reply)
                # Pertahankan konten think di thought_acc dan jaga hasil stream yang sudah diterjemahkan bersih
                if non_tool_raw:
                    raw_reply = streamed_reply_acc
            break

        t_end = time.perf_counter()
        t_llm_dur = (t_end - t0) * 1000
        ttft_ms = round((t_first_token - t0) * 1000) if t_first_token else round(t_llm_dur)
        est_tok = max(1, len(raw_reply) // 4)
        gen_sec = max(0.05, t_end - (t_first_token or t0))
        est_tps = est_tok / gen_sec
        print(
            f"⚡ [Inference] model={prep.get('active_model_name')} tier={lyra_tier_id} "
            f"path={path_used} ctx={prep.get('effective_ctx', prep.get('active_ctx')):,} "
            f"ttft={ttft_ms}ms total={round(t_llm_dur)}ms chars={len(raw_reply)} (~{est_tps:.1f} tok/s)"
        )
        delivery_reply, trace, details = _finalize_inference_output(
            prep=prep,
            raw_reply=raw_reply,
            t_llm_dur=t_llm_dur,
            thought_content_override=None if api_version == "v2" else (thought_acc or None),
            thought_duration_sec=None if api_version == "v2" else thought_duration_sec,
        )

        final_steps = list(details.get("agent_steps") or []) if is_heavy_task_stream else []
        if is_heavy_task_stream:
            reason_done_step = {
                "id": "reason",
                "title": "Reasoning & Solution Synthesis",
                "status": "done",
                "feedback": (
                    f"English analysis ({thought_duration_sec}s) & answer complete ({round(t_llm_dur / 1000.0, 1)}s total)"
                    if thought_duration_sec is not None
                    else f"Response synthesized in {round(t_llm_dur / 1000.0, 1)}s"
                ),
            }
            replaced_reason = False
            for idx_s, s_item in enumerate(final_steps):
                if s_item.get("id") == "reason":
                    final_steps[idx_s] = reason_done_step
                    replaced_reason = True
                    break
            if not replaced_reason:
                final_steps.append(reason_done_step)

            for st_emit in final_steps:
                if st_emit.get("id") in ("reason", "package", "files", "render_video"):
                    yield {"type": "agent_trace_step", "step": st_emit}

        if details.get("artifacts"):
            yield {"type": "artifacts", "artifacts": details["artifacts"]}

        yield {
            "type": "done",
            "reply": delivery_reply,
            "raw_reply": raw_reply,
            "thought_content": None if api_version == "v2" else details.get("reasoning_content"),
            "thought_duration_sec": None if api_version == "v2" else thought_duration_sec,
            "agent_steps": final_steps,
            "artifacts": details.get("artifacts") or [],
            "active_context_window": details.get("active_context_window"),
            "trace": trace,
            "agent_action": details.get("agent_action") or prep.get("agent_action_data")
        }

    except Exception as e:
        print(f"[Inference Stream Error]: {e}")
        err_msg = f"Maaf, sistem AI mengalami kendala teknis: {str(e)[:80]}"
        yield {
            "type": "error",
            "error": str(e),
            "reply": err_msg
        }
