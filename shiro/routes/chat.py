# -*- coding: utf-8 -*-
"""
Shiro Chat & Memory Interaction Routes
Handles Web UI chat interaction, conversation history, memory counts, and idle triggers.
"""

import os
import uuid
import base64
from datetime import datetime
from flask import Blueprint, request, jsonify, Response

from shiro.auth import verify_api_key
from shiro.server_state import state
from shiro.nlp.emotion import detect_emotion_category
from shiro.memory.optimization import compress_old_messages
from shiro.pipeline.inference import get_shiro_reply, stream_shiro_reply

chat_bp = Blueprint("chat_bp", __name__)

def _format_message_for_api(msg):
    """Format single message dictionary to ensure valid URLs and pin metadata for frontend viewing"""
    m = dict(msg)
    if not m.get("id"):
        m["id"] = f"msg-{uuid.uuid4().hex[:10]}"
    if "pinned" not in m:
        m["pinned"] = False
    img = m.get("image")
    if img and not img.startswith("data:") and not img.startswith("http://") and not img.startswith("https://") and not img.startswith("/"):
        m["image"] = "/" + img
    doc = m.get("document_name")
    if doc and not m.get("document_url"):
        m["document_url"] = f"/api/files/{doc}"
    if m.get("thought_content") is None:
        m.pop("thought_content", None)
    if m.get("agent_steps") and not isinstance(m.get("agent_steps"), list):
        m["agent_steps"] = []
    if m.get("artifacts") and not isinstance(m.get("artifacts"), list):
        m["artifacts"] = []
    return m

@chat_bp.route('/api/history', methods=['GET'])
def get_history():
    memory = state.init_memory()
    with memory.lock:
        memory._ensure_message_ids(memory.short_term_history)
        valid_history = [
            _format_message_for_api(m) for m in memory.short_term_history
            if (m.get("content") or "").strip() or m.get("image") or m.get("images") or m.get("videos") or m.get("document_name") or m.get("documents") or m.get("document_text") or m.get("artifacts")
        ]
        return jsonify({
            "history": valid_history,
            "count": len(memory.short_term_history),
            "metadata": memory.system_metadata,
            "user_profile": memory.user_profile,
            "agent_persona": memory.agent_persona,
            "topics": memory.system_metadata.get("topics_discussed", []),
            "enable_training_logging": memory.system_metadata.get("enable_training_logging", True),
            "ui_language": memory.system_metadata.get("ui_language", "id")
        })

@chat_bp.route('/api/chat/pin', methods=['POST'])
def pin_chat_message():
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json or {}
        message_id = data.get("message_id")
        pinned = data.get("pinned", None)
        content_match = data.get("content", None)

        memory = state.init_memory()
        with memory.lock:
            updated = memory.toggle_pin_message(message_id=message_id, pinned=pinned, content_match=content_match)
            if not updated:
                return jsonify({"success": False, "error": "Pesan tidak ditemukan dalam sesi ini."}), 404
            pinned_msgs = [_format_message_for_api(m) for m in memory.short_term_history if m.get("pinned")]
            return jsonify({
                "success": True,
                "message": _format_message_for_api(updated),
                "pinned": bool(updated.get("pinned")),
                "pinned_count": len(pinned_msgs),
                "pinned_messages": pinned_msgs
            })
    except Exception as e:
        print(f"[Pin Error]: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@chat_bp.route('/api/memory-count', methods=['GET'])
def get_memory_count():
    memory = state.init_memory()
    return jsonify({
        "count": memory.system_metadata["total_turns"],
        "facts_count": len(memory.knowledge_base.get("facts", [])),
        "topics_count": len(memory.system_metadata.get("topics_discussed", [])),
        "metadata": memory.system_metadata
    })

@chat_bp.route('/api/stats', methods=['GET'])
def get_stats():
    memory = state.init_memory()
    user_msgs = len([m for m in memory.short_term_history if m.get('role') == 'user'])
    assistant_msgs = len([m for m in memory.short_term_history if m.get('role') == 'assistant'])
    
    return jsonify({
        "total_messages": memory.system_metadata["total_turns"],
        "user_messages": user_msgs,
        "assistant_messages": assistant_msgs,
        "facts_count": len(memory.knowledge_base.get("facts", [])),
        "topics_count": len(memory.system_metadata.get("topics_discussed", [])),
        "user_profile": memory.user_profile,
        "agent_mood": memory.agent_persona.get("current_mood", "Neutral"),
        "agent_emotions": memory.agent_persona.get("emotional_state", {}),
        "relationship_status": memory.agent_persona.get("relationship_status", {}),
        "metadata": memory.system_metadata
    })

@chat_bp.route('/api/trigger', methods=['POST'])
def auto_trigger():
    memory = state.init_memory()
    try:
        with memory.lock:
            if state.serial_questions >= 1:
                return jsonify({"status": "idle", "reason": "already_initiated"})

        trigger_prompt = (
            "Kakak sudah lama tidak bersuara. Sebagai Shiro (adik perempuan), berikan SATU sapaan santai atau perhatian kecil "
            "dengan maksimal 1-2 kalimat pendek sudut pandang Shiro."
        )
        
        reply = get_shiro_reply(trigger_prompt)
        
        with memory.lock:
            msg_id = memory.add_message("assistant", reply)
            if len(memory.short_term_history) > 500:
                compress_old_messages(memory, keep_count=500)
            memory.save_memory()
            state.serial_questions += 1
            
            return jsonify({
                "reply": reply,
                "assistant_message_id": msg_id,
                "count": memory.system_metadata["total_turns"],
                "mood": memory.agent_persona.get("current_mood", "Neutral")
            })
    except Exception as e:
        print(f"[Trigger Error]: {e}")
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized: Invalid or missing API Key."}), 401
        
    try:
        data = request.json or {}
        # Murni teks yang diketik pengguna
        user_message = data.get('message', '').strip()
        image_base64 = data.get('image', None)
        images_list = data.get('images') if isinstance(data.get('images'), list) else None
        document_text = data.get('document_text', None)
        document_name = data.get('document_name', None)
        documents_list = data.get('documents') if isinstance(data.get('documents'), list) else None
        videos_list = data.get('videos') if isinstance(data.get('videos'), list) else None
        user_max_tokens = data.get('max_tokens') or data.get('max_completion_tokens')
        
        document_info = None
        if document_text:
            document_info = {
                "text": document_text,
                "filename": document_name or "Dokumen"
            }

        has_any_docs = bool(document_info or (documents_list and any(isinstance(d, dict) and (d.get("text") or "").strip() for d in documents_list)))
        has_any_imgs = bool(image_base64 or (images_list and any(images_list)))
        has_any_vids = bool(videos_list and any(isinstance(v, dict) and (v.get("frames") or v.get("thumbnail")) for v in videos_list))

        if not user_message and not has_any_imgs and not has_any_docs and not has_any_vids:
            return jsonify({"error": "Empty message"}), 400

        # Perintah eksplisit: /moe on|off|auto|concurrent|swap|status
        from shiro.agent.moe_router import parse_moe_command, get_orchestrator
        moe_cmd = parse_moe_command(user_message)
        if moe_cmd:
            moe = get_orchestrator()
            try:
                st = moe.status() if moe_cmd == "status" else moe.set_mode(moe_cmd)
                expert = os.path.basename(st["vision_expert_path"]) if st.get("vision_expert_path") else "tidak ditemukan"
                reply = f"[MoE] mode: {st['mode']} • visual expert: {expert} • dimuat: {'ya' if st['vision_expert_loaded'] else 'tidak'}"
            except ValueError as e_mode:
                reply = f"[MoE] {e_mode}"
            return jsonify({"reply": reply, "system_command": True, "moe": moe.status()})

        # Perintah kontrol cepat Local PC Agent: /agent status|mode|admin|on|off
        from shiro.agent.local_agent import (
            parse_agent_command,
            get_agent_status,
            save_agent_settings,
            should_route_to_local_agent,
        )
        agent_ctrl = parse_agent_command(user_message)
        if agent_ctrl and agent_ctrl.get("cmd") != "run":
            cmd_type = agent_ctrl["cmd"]
            if cmd_type == "mode":
                st = save_agent_settings({"approval_mode": agent_ctrl["value"]})
                reply = f"[Agent PC] Mode persetujuan diatur ke `{st['approval_mode']}`."
            elif cmd_type == "admin":
                st = save_agent_settings({"allow_admin": agent_ctrl["value"]})
                reply = f"[Agent PC] Pre-otorisasi Administrator (UAC): `{'AKTIF' if st['allow_admin'] else 'NONAKTIF'}`."
            elif cmd_type == "enabled":
                st = save_agent_settings({"enabled": agent_ctrl["value"]})
                reply = f"[Agent PC] Mode Agen Otonom PC Lokal: `{'AKTIF' if st['enabled'] else 'NONAKTIF'}`."
            else:
                st = get_agent_status()
                env_lbl = "PC Lokal (Aktif)" if st["is_local_pc"] else "Google Colab (Dinonaktifkan otomatis)"
                reply = (
                    f"[Agent PC] Lingkungan: {env_lbl} • Status: {'AKTIF' if st['effective_enabled'] else 'NONAKTIF'} "
                    f"• Mode: `{st['approval_mode']}` • Admin UAC Pre-Auth: `{'YA' if st['allow_admin'] else 'TIDAK'}` "
                    f"• Workspace: `{st['effective_workspace']}`"
                )
            return jsonify({"reply": reply, "system_command": True, "agent_status": st})
        
        # Fleksibel mendukung teks panjang / kode pemrograman hingga 120.000 karakter (atau dinamis hingga 3.000.000 khusus ShiroHaru-Lyra-Agent 190K-1M)
        from shiro.models import (
            is_qwen38_27b_uncensored,
            get_active_model_ctx,
            is_valid_lyra_tier,
            resolve_lyra_tier,
            save_lyra_tier,
            get_gpu_layers,
            instantiate_llama_model,
        )
        active_model_path = getattr(state.llm, 'model_path', '') if state.llm else ''
        req_lyra_tier = data.get('lyra_tier')
        lyra_tier_obj = None
        if (
            req_lyra_tier
            and is_qwen38_27b_uncensored(active_model_path)
            and is_valid_lyra_tier(req_lyra_tier)
        ):
            lyra_tier_obj = resolve_lyra_tier(req_lyra_tier)
            save_lyra_tier(lyra_tier_obj["id"])

        if is_qwen38_27b_uncensored(active_model_path):
            active_ctx_chars = (lyra_tier_obj["tokens"] * 3) if lyra_tier_obj else (get_active_model_ctx(state.llm) * 3 if state.llm else 1_500_000)
            max_msg_chars = max(500_000, min(3_000_000, active_ctx_chars))
        else:
            max_msg_chars = 120_000
        if len(user_message) > max_msg_chars:
            return jsonify({
                "error": f"Pesan terlalu panjang (Maksimal {max_msg_chars:,} karakter)",
                "reply": f"Pesan Kakak melampaui batas aman konteks ({max_msg_chars:,} karakter). Mohon persingkat sedikit atau kirim dalam berkas dokumen ya, Kak!"
            }), 400

        memory = state.init_memory()
        training_enabled = memory.system_metadata.get("enable_training_logging", True)
        
        primary_img_b64 = image_base64 or (images_list[0] if images_list else None)
        saved_img_rel = None
        saved_images_urls = []
        raw_images_to_save = []
        if image_base64:
            raw_images_to_save.append(image_base64)
        if images_list:
            for im_item in images_list:
                if im_item and im_item not in raw_images_to_save:
                    raw_images_to_save.append(im_item)

        if raw_images_to_save:
            try:
                if training_enabled:
                    v_dir = os.path.join("training_data", "vision", "images")
                else:
                    v_dir = os.path.join("data", "uploads")
                os.makedirs(v_dir, exist_ok=True)
                for im_b64 in raw_images_to_save:
                    fn = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
                    fp = os.path.join(v_dir, fn)
                    raw = im_b64.split(",", 1)[1] if "," in im_b64 else im_b64
                    with open(fp, "wb") as f_out:
                        f_out.write(base64.b64decode(raw))
                    rel_u = "/" + os.path.join("images", fn).replace("\\", "/")
                    saved_images_urls.append(rel_u)
                if saved_images_urls:
                    saved_img_rel = saved_images_urls[0].lstrip("/")
            except Exception as e_img:
                print(f"[Chat] Warning saving image: {e_img}")

        stream_mode = data.get('stream', True)

        # 1. Catat giliran pesan user dalam lock singkat (< 1ms)
        with memory.lock:
            state.serial_questions = 0
            user_emotion = detect_emotion_category(user_message) if user_message else "neutral"
            
            # Log message murni dari apa yang dikirim user
            log_msg = user_message
            if not log_msg:
                if has_any_vids:
                    v_names = ", ".join(str(v.get("filename", "video")) for v in (videos_list or [])[:3])
                    log_msg = f"[Video: {v_names}]"
                elif has_any_imgs:
                    log_msg = "[Gambar Dikirim]" if len(raw_images_to_save) <= 1 else f"[{len(raw_images_to_save)} Gambar Dikirim]"
                elif has_any_docs:
                    if documents_list and len(documents_list) > 1:
                        log_msg = f"[{len(documents_list)} Berkas Dokumen]"
                    else:
                        d_nm = document_name or (documents_list[0].get("filename") if documents_list else "Dokumen")
                        log_msg = f"[Dokumen: {d_nm}]"

            img_url = f"/{saved_img_rel}" if saved_img_rel else None
            first_doc_name = document_name or (documents_list[0].get("filename") if (documents_list and isinstance(documents_list[0], dict)) else None)
            doc_url = f"/api/files/{first_doc_name}" if first_doc_name else None
            doc_type = os.path.splitext(first_doc_name)[1].lower().replace(".", "") if first_doc_name else None

            user_msg_id = memory.add_message(
                "user", 
                log_msg, 
                image_path=img_url,
                document_name=first_doc_name if not (documents_list and len(documents_list) > 1) else None,
                document_url=doc_url if not (documents_list and len(documents_list) > 1) else None,
                document_type=doc_type if not (documents_list and len(documents_list) > 1) else None,
                document_text=document_text,
                documents=documents_list,
                images=saved_images_urls if len(saved_images_urls) > 1 else None,
                videos=videos_list,
            )
            active_sess_id = getattr(memory, "active_session_id", "default")
            if hasattr(memory, "sessions_store") and active_sess_id in memory.sessions_store:
                memory.sessions_store[active_sess_id]["messages"] = list(memory.short_term_history)
                memory.sessions_store[active_sess_id]["last_active"] = datetime.now().isoformat()
            memory.save_memory()

        # 2. NON-STREAMING FALLBACK (Jika client eksplisit meminta stream: false)
        agent_route = should_route_to_local_agent(user_message, has_image=bool(has_any_imgs or has_any_vids))

        def _needs_lyra_ctx_reload(llm_inst, target_ctx: int) -> bool:
            if llm_inst is None:
                return False
            from shiro.models import _get_gpu_vram_gb
            active_ctx = get_active_model_ctx(llm_inst)
            kv_type = getattr(llm_inst, "_shiro_kv_type", None)
            if active_ctx + 1024 < target_ctx:
                return True
            if target_ctx <= 500000 and kv_type in ("q4_0", "q8_0"):
                vram_gb = _get_gpu_vram_gb()
                if vram_gb is None or vram_gb >= 35.0:
                    return True
            if active_ctx > 262144 and target_ctx <= 262144:
                vram_gb = _get_gpu_vram_gb()
                if vram_gb is not None and vram_gb < 50.0:
                    return True
            return False

        def _ensure_lyra_tier_loaded():
            if not (lyra_tier_obj and state.llm is not None and get_gpu_layers() != 0):
                return
            target_ctx = lyra_tier_obj["tokens"]
            if not _needs_lyra_ctx_reload(state.llm, target_ctx):
                return
            with state.llm_lock:
                if not _needs_lyra_ctx_reload(state.llm, target_ctx):
                    return
                old_llm = state.llm
                old_vis = state.vision_chat_handler
                try:
                    import gc
                    if hasattr(old_llm, 'close'):
                        old_llm.close()
                    state.llm = None
                    gc.collect()
                    new_llm, new_vis = instantiate_llama_model(active_model_path, target_ctx_override=target_ctx)
                    state.set_llm(new_llm, new_vis)
                except Exception as e_tier:
                    print(f"[Chat] Warning reloading Lyra tier {lyra_tier_obj['id']}: {e_tier}")
                    if state.llm is None and old_llm is not None:
                        state.set_llm(old_llm, old_vis)

        if not stream_mode:
            if not agent_route.get("route"):
                _ensure_lyra_tier_loaded()
            if agent_route.get("route"):
                from shiro.agent.autonomous_runner import autonomous_runner
                ag_res = autonomous_runner.run_task(
                    agent_route["task"],
                    state.llm,
                    session_id=active_sess_id,
                )
                reply = ag_res.get("reply", "")
                assistant_msg_id = None
                if ag_res.get("status") in ("completed", "rejected") and reply:
                    with memory.lock:
                        assistant_msg_id = memory.add_message("assistant", reply)
                        memory.update_emotional_state_from_response(reply)
                        memory.update_mood_from_emotions()
                        if training_enabled:
                            memory.record_learned_pattern(log_msg, reply)
                        if hasattr(memory, "sessions_store") and active_sess_id in memory.sessions_store:
                            memory.sessions_store[active_sess_id]["messages"] = list(memory.short_term_history)
                            memory.sessions_store[active_sess_id]["last_active"] = datetime.now().isoformat()
                        if len(memory.short_term_history) > 500:
                            compress_old_messages(memory, keep_count=500)
                        memory.save_memory()
                return jsonify({
                    "reply": reply,
                    "status": ag_res.get("status"),
                    "task_id": ag_res.get("task_id"),
                    "plan": ag_res.get("plan"),
                    "pending_action": ag_res.get("pending_action"),
                    "agent_action": ag_res.get("agent_action"),
                    "user_message_id": user_msg_id,
                    "assistant_message_id": assistant_msg_id,
                    "count": memory.system_metadata["total_turns"],
                    "active_session_id": active_sess_id,
                })

            reply, details = get_shiro_reply(
                user_message,
                image_base64=image_base64,
                images_base64=images_list,
                document_info=document_info,
                documents=documents_list,
                videos=videos_list,
                max_tokens=user_max_tokens,
                lyra_tier=req_lyra_tier,
                return_details=True
            )
            trace = details.get("trace", {}) if isinstance(details, dict) else {}
            thought_content = details.get("reasoning_content") if isinstance(details, dict) else None
            thought_duration_sec = details.get("thought_duration_sec") if isinstance(details, dict) else None
            agent_steps = details.get("agent_steps") if isinstance(details, dict) else None
            artifacts = details.get("artifacts") if isinstance(details, dict) else None
            saved_agent_action = (
                details.get("agent_action")
                if (isinstance(details, dict) and details.get("agent_action"))
                else (trace.get("agent_action") if isinstance(trace, dict) else None)
            )
            
            assistant_img_url = None
            if isinstance(saved_agent_action, dict):
                assistant_img_url = saved_agent_action.get("image_url")

            with memory.lock:
                assistant_msg_id = memory.add_message(
                    "assistant",
                    reply,
                    image_path=assistant_img_url,
                    thought_content=thought_content,
                    thought_duration_sec=thought_duration_sec,
                    agent_steps=agent_steps,
                    artifacts=artifacts,
                    agent_action=saved_agent_action,
                )
                memory.update_emotional_state_from_response(reply)
                memory.update_mood_from_emotions()
                
                if training_enabled and (not image_base64 or "poster tersebut" not in reply.lower()):
                    memory.record_learned_pattern(log_msg, reply, image_path=saved_img_rel)
                
                session_title = None
                if hasattr(memory, "auto_update_session_title"):
                    session_title = memory.auto_update_session_title(
                        session_id=active_sess_id,
                        user_message=user_message,
                        document_name=document_name
                    )

                if hasattr(memory, "sessions_store") and active_sess_id in memory.sessions_store:
                    memory.sessions_store[active_sess_id]["messages"] = list(memory.short_term_history)
                    memory.sessions_store[active_sess_id]["last_active"] = datetime.now().isoformat()

                if len(memory.short_term_history) > 500:
                    compress_old_messages(memory, keep_count=500)
                memory.save_memory()
                
            return jsonify({
                "reply": reply,
                "user_message_id": user_msg_id,
                "assistant_message_id": assistant_msg_id,
                "assistant_image_url": assistant_img_url,
                "count": memory.system_metadata["total_turns"],
                "emotion": user_emotion,
                "mood": memory.agent_persona.get("current_mood", "Neutral"),
                "topics": memory.system_metadata.get("topics_discussed", []),
                "has_image": bool(image_base64),
                "image_url": img_url,
                "has_document": bool(document_info),
                "document_name": document_name,
                "document_url": doc_url,
                "document_type": doc_type,
                "active_session_id": active_sess_id,
                "session_title": session_title,
                "pipeline_trace": trace,
                "agent_action": trace.get("agent_action"),
                "thought_content": thought_content,
                "thought_duration_sec": thought_duration_sec,
                "agent_steps": agent_steps or [],
                "artifacts": artifacts or []
            })

        # 3. STREAMING REAL-TIME SSE (text/event-stream)
        import json as py_json
        def generate_chat_stream():
            full_reply = ""
            trace = None
            assistant_img_url = None
            agent_action = None
            agent_plan = None
            agent_status = None
            thought_content = None
            thought_duration_sec = None
            agent_steps = None
            artifacts = None
            client_disconnected = False
            active_stream_gen = None

            # Kirim metadata awal segera agar UI mendapatkan user_msg_id
            init_payload = {
                "type": "init",
                "user_message_id": user_msg_id,
                "active_session_id": active_sess_id,
                "image_url": img_url,
                "document_name": document_name,
                "images": saved_images_urls if len(saved_images_urls) > 1 else None,
            }
            yield f"data: {py_json.dumps(init_payload)}\n\n"

            try:
                if (
                    not agent_route.get("route")
                    and lyra_tier_obj
                    and state.llm is not None
                    and get_gpu_layers() != 0
                    and _needs_lyra_ctx_reload(state.llm, lyra_tier_obj["tokens"])
                ):
                    import threading
                    tier_prep_label = lyra_tier_obj["label"]
                    prep_msg = (
                        f"Memperluas kapasitas konteks {tier_prep_label}..."
                        if get_active_model_ctx(state.llm) + 1024 < lyra_tier_obj["tokens"]
                        else f"Mengoptimalkan {tier_prep_label}..."
                    )
                    yield f"data: {py_json.dumps({'type': 'status', 'status': prep_msg})}\n\n"
                    yield ": ping\n\n"
                    reload_thread = threading.Thread(target=_ensure_lyra_tier_loaded, daemon=True)
                    reload_thread.start()
                    while reload_thread.is_alive():
                        reload_thread.join(timeout=4.0)
                        if reload_thread.is_alive():
                            yield ": ping\n\n"

                if agent_route.get("route"):
                    from shiro.agent.autonomous_runner import autonomous_runner
                    active_stream_gen = autonomous_runner.run_task_stream(
                        agent_route["task"],
                        state.llm,
                        session_id=active_sess_id,
                    )
                    for event in active_stream_gen:
                        ev_type = event.get("type")
                        if ev_type == "token":
                            token = event.get("token", "")
                            full_reply += token
                            yield f"data: {py_json.dumps({'type': 'token', 'token': token})}\n\n"
                        elif ev_type == "status":
                            yield f"data: {py_json.dumps({'type': 'status', 'status': event.get('status', '')})}\n\n"
                        elif ev_type in ("agent_plan", "agent_step", "approval_required"):
                            if event.get("plan"):
                                agent_plan = event.get("plan")
                            yield f"data: {py_json.dumps(event)}\n\n"
                        elif ev_type == "agent_action":
                            agent_action = event.get("agent_action")
                            yield f"data: {py_json.dumps({'type': 'agent_action', 'agent_action': agent_action})}\n\n"
                        elif ev_type == "error":
                            err_text = event.get("error", "Terjadi kesalahan internal.")
                            err_reply = f"*menatap cemas* Maaf Kakak, ada kendala teknis: {str(err_text)[:80]}"
                            if not full_reply:
                                full_reply = err_reply
                            yield f"data: {py_json.dumps({'type': 'error', 'error': err_text, 'reply': err_reply})}\n\n"
                        elif ev_type == "done":
                            full_reply = event.get("reply", full_reply)
                            trace = event.get("trace")
                            agent_plan = event.get("plan", agent_plan)
                            agent_status = event.get("status", agent_status)
                else:
                    active_stream_gen = stream_shiro_reply(
                        user_message,
                        image_base64=image_base64,
                        images_base64=images_list,
                        document_info=document_info,
                        documents=documents_list,
                        videos=videos_list,
                        max_tokens=user_max_tokens,
                        lyra_tier=req_lyra_tier
                    )
                    for event in active_stream_gen:
                        ev_type = event.get("type")
                        if ev_type == "ping":
                            yield ": ping\n\n"
                        elif ev_type == "token":
                            token = event.get("token", "")
                            full_reply += token
                            yield f"data: {py_json.dumps({'type': 'token', 'token': token})}\n\n"
                        elif ev_type == "status":
                            yield f"data: {py_json.dumps({'type': 'status', 'status': event.get('status', '')})}\n\n"
                        elif ev_type == "agent_trace_step":
                            yield f"data: {py_json.dumps({'type': 'agent_trace_step', 'step': event.get('step')})}\n\n"
                        elif ev_type == "thought":
                            yield f"data: {py_json.dumps({'type': 'thought', 'token': event.get('token', '')})}\n\n"
                        elif ev_type == "thought_done":
                            thought_duration_sec = event.get("duration_sec")
                            yield f"data: {py_json.dumps({'type': 'thought_done', 'duration_sec': thought_duration_sec})}\n\n"
                        elif ev_type == "artifacts":
                            artifacts = event.get("artifacts") or []
                            yield f"data: {py_json.dumps({'type': 'artifacts', 'artifacts': artifacts})}\n\n"
                        elif ev_type == "agent_action":
                            agent_action = event.get("agent_action")
                            if agent_action and agent_action.get("image_url"):
                                assistant_img_url = agent_action.get("image_url")
                            yield f"data: {py_json.dumps({'type': 'agent_action', 'agent_action': agent_action})}\n\n"
                        elif ev_type == "error":
                            err_text = event.get("error", "Terjadi kesalahan internal.")
                            err_reply = event.get("reply", f"*menatap cemas* Maaf Kakak, ada kendala teknis: {str(err_text)[:60]}")
                            if not full_reply:
                                full_reply = err_reply
                            yield f"data: {py_json.dumps({'type': 'error', 'error': err_text, 'reply': err_reply})}\n\n"
                        elif ev_type == "done":
                            full_reply = event.get("reply", full_reply)
                            trace = event.get("trace")
                            if event.get("thought_content"):
                                thought_content = event.get("thought_content")
                            if event.get("thought_duration_sec") is not None:
                                thought_duration_sec = event.get("thought_duration_sec")
                            if event.get("agent_steps"):
                                agent_steps = event.get("agent_steps")
                            if event.get("artifacts"):
                                artifacts = event.get("artifacts")
                            if event.get("agent_action"):
                                agent_action = event.get("agent_action")
                            if trace and isinstance(trace.get("agent_action"), dict):
                                if not agent_action:
                                    agent_action = trace.get("agent_action")
                                assistant_img_url = trace["agent_action"].get("image_url")
            except (GeneratorExit, BrokenPipeError, ConnectionResetError):
                client_disconnected = True
                print("[Stream] Client disconnected or aborted by user.")
                if active_stream_gen is not None:
                    try:
                        active_stream_gen.close()
                    except Exception:
                        pass
            except Exception as e_stream:
                print(f"[Stream Error]: {e_stream}")
                if not full_reply:
                    full_reply = f"*menatap cemas* Maaf Kakak, ada kendala: {str(e_stream)[:60]}"
                if not client_disconnected:
                    yield f"data: {py_json.dumps({'type': 'error', 'error': str(e_stream)})}\n\n"
            finally:
                if active_stream_gen is not None:
                    try:
                        active_stream_gen.close()
                    except Exception:
                        pass
                # Simpan jawaban ke memori bahkan jika koneksi terputus di tengah jalan
                done_payload = None
                try:
                    if full_reply and full_reply.strip():
                        with memory.lock:
                            resolved_action = agent_action or (trace.get("agent_action") if trace else None)
                            assistant_msg_id = memory.add_message(
                                "assistant",
                                full_reply,
                                image_path=assistant_img_url,
                                thought_content=thought_content,
                                thought_duration_sec=thought_duration_sec,
                                agent_steps=agent_steps,
                                artifacts=artifacts,
                                agent_action=resolved_action,
                            )
                            memory.update_emotional_state_from_response(full_reply)
                            memory.update_mood_from_emotions()
                            
                            if training_enabled and (not image_base64 or "poster tersebut" not in full_reply.lower()):
                                memory.record_learned_pattern(log_msg, full_reply, image_path=saved_img_rel)
                            
                            session_title = None
                            if hasattr(memory, "auto_update_session_title"):
                                session_title = memory.auto_update_session_title(
                                    session_id=active_sess_id,
                                    user_message=user_message,
                                    document_name=document_name
                                )

                            if hasattr(memory, "sessions_store") and active_sess_id in memory.sessions_store:
                                memory.sessions_store[active_sess_id]["messages"] = list(memory.short_term_history)
                                memory.sessions_store[active_sess_id]["last_active"] = datetime.now().isoformat()

                            if len(memory.short_term_history) > 500:
                                compress_old_messages(memory, keep_count=500)
                            memory.save_memory()

                            done_payload = {
                                "type": "done",
                                "reply": full_reply,
                                "assistant_message_id": assistant_msg_id,
                                "assistant_image_url": assistant_img_url,
                                "session_title": session_title,
                                "pipeline_trace": trace,
                                "agent_action": agent_action or (trace.get("agent_action") if trace else None),
                                "thought_content": thought_content,
                                "thought_duration_sec": thought_duration_sec,
                                "agent_steps": agent_steps or [],
                                "artifacts": artifacts or [],
                                "plan": agent_plan,
                                "status": agent_status,
                                "count": memory.system_metadata["total_turns"],
                                "mood": memory.agent_persona.get("current_mood", "Neutral")
                            }
                except Exception as e_fin:
                    print(f"[Stream Finalize Error]: {e_fin}")
                if done_payload is not None and not client_disconnected:
                    try:
                        yield f"data: {py_json.dumps(done_payload)}\n\n"
                    except (GeneratorExit, BrokenPipeError, ConnectionResetError):
                        pass

        stream_resp = Response(generate_chat_stream(), mimetype="text/event-stream")
        stream_resp.headers["Cache-Control"] = "no-cache"
        stream_resp.headers["X-Accel-Buffering"] = "no"
        return stream_resp
    
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return jsonify({"error": str(e)}), 500
