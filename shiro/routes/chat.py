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
    return m

@chat_bp.route('/api/history', methods=['GET'])
def get_history():
    memory = state.init_memory()
    with memory.lock:
        memory._ensure_message_ids(memory.short_term_history)
        valid_history = [
            _format_message_for_api(m) for m in memory.short_term_history
            if (m.get("content") or "").strip() or m.get("image") or m.get("document_name") or m.get("document_text")
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
        document_text = data.get('document_text', None)
        document_name = data.get('document_name', None)
        user_max_tokens = data.get('max_tokens') or data.get('max_completion_tokens')
        
        document_info = None
        if document_text:
            document_info = {
                "text": document_text,
                "filename": document_name or "Dokumen"
            }

        if not user_message and not image_base64 and not document_info:
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
        
        # Fleksibel mendukung teks panjang / kode pemrograman hingga 120.000 karakter
        if len(user_message) > 120000:
            return jsonify({
                "error": "Pesan terlalu panjang (Maksimal 120.000 karakter)",
                "reply": "Pesan Kakak melampaui batas aman konteks (120.000 karakter). Mohon persingkat sedikit atau kirim dalam berkas dokumen ya, Kak!"
            }), 400

        memory = state.init_memory()
        training_enabled = memory.system_metadata.get("enable_training_logging", True)
        
        saved_img_rel = None
        if image_base64:
            try:
                if training_enabled:
                    v_dir = os.path.join("training_data", "vision", "images")
                else:
                    v_dir = os.path.join("data", "uploads")
                os.makedirs(v_dir, exist_ok=True)
                fn = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
                fp = os.path.join(v_dir, fn)
                raw = image_base64.split(",", 1)[1] if "," in image_base64 else image_base64
                with open(fp, "wb") as f_out:
                    f_out.write(base64.b64decode(raw))
                saved_img_rel = os.path.join("images", fn).replace("\\", "/")
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
                if image_base64:
                    log_msg = "[Gambar Dikirim]"
                elif document_name:
                    log_msg = f"[Dokumen: {document_name}]"

            img_url = f"/{saved_img_rel}" if saved_img_rel else None
            doc_url = f"/api/files/{document_name}" if document_name else None
            doc_type = os.path.splitext(document_name)[1].lower().replace(".", "") if document_name else None

            user_msg_id = memory.add_message(
                "user", 
                log_msg, 
                image_path=img_url,
                document_name=document_name,
                document_url=doc_url,
                document_type=doc_type,
                document_text=document_text
            )
            active_sess_id = getattr(memory, "active_session_id", "default")
            if hasattr(memory, "sessions_store") and active_sess_id in memory.sessions_store:
                memory.sessions_store[active_sess_id]["messages"] = list(memory.short_term_history)
                memory.sessions_store[active_sess_id]["last_active"] = datetime.now().isoformat()
            memory.save_memory()

        # 2. NON-STREAMING FALLBACK (Jika client eksplisit meminta stream: false)
        if not stream_mode:
            reply, trace = get_shiro_reply(
                user_message,
                image_base64=image_base64,
                document_info=document_info,
                max_tokens=user_max_tokens,
                return_trace=True
            )
            
            assistant_img_url = None
            if trace and isinstance(trace.get("agent_action"), dict):
                assistant_img_url = trace["agent_action"].get("image_url")

            with memory.lock:
                assistant_msg_id = memory.add_message("assistant", reply, image_path=assistant_img_url)
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
                "agent_action": trace.get("agent_action")
            })

        # 3. STREAMING REAL-TIME SSE (text/event-stream)
        import json as py_json
        def generate_chat_stream():
            full_reply = ""
            trace = None
            assistant_img_url = None
            agent_action = None

            # Kirim metadata awal segera agar UI mendapatkan user_msg_id
            init_payload = {
                "type": "init",
                "user_message_id": user_msg_id,
                "active_session_id": active_sess_id,
                "image_url": img_url,
                "document_name": document_name
            }
            yield f"data: {py_json.dumps(init_payload)}\n\n"

            try:
                for event in stream_shiro_reply(
                    user_message,
                    image_base64=image_base64,
                    document_info=document_info,
                    max_tokens=user_max_tokens
                ):
                    ev_type = event.get("type")
                    if ev_type == "ping":
                        yield ": ping\n\n"
                    elif ev_type == "token":
                        token = event.get("token", "")
                        full_reply += token
                        yield f"data: {py_json.dumps({'type': 'token', 'token': token})}\n\n"
                    elif ev_type == "status":
                        yield f"data: {py_json.dumps({'type': 'status', 'status': event.get('status', '')})}\n\n"
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
                        if trace and isinstance(trace.get("agent_action"), dict):
                            assistant_img_url = trace["agent_action"].get("image_url")
            except (GeneratorExit, BrokenPipeError, ConnectionResetError):
                print("[Stream] Client disconnected or aborted by user.")
            except Exception as e_stream:
                print(f"[Stream Error]: {e_stream}")
                if not full_reply:
                    full_reply = f"*menatap cemas* Maaf Kakak, ada kendala: {str(e_stream)[:60]}"
                yield f"data: {py_json.dumps({'type': 'error', 'error': str(e_stream)})}\n\n"
            finally:
                # Simpan jawaban ke memori bahkan jika koneksi terputus di tengah jalan
                try:
                    if full_reply and full_reply.strip():
                        with memory.lock:
                            assistant_msg_id = memory.add_message("assistant", full_reply, image_path=assistant_img_url)
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
                                "count": memory.system_metadata["total_turns"],
                                "mood": memory.agent_persona.get("current_mood", "Neutral")
                            }
                            yield f"data: {py_json.dumps(done_payload)}\n\n"
                except Exception as e_fin:
                    print(f"[Stream Finalize Error]: {e_fin}")

        stream_resp = Response(generate_chat_stream(), mimetype="text/event-stream")
        stream_resp.headers["Cache-Control"] = "no-cache"
        stream_resp.headers["X-Accel-Buffering"] = "no"
        return stream_resp
    
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return jsonify({"error": str(e)}), 500
