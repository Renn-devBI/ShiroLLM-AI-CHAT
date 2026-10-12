# -*- coding: utf-8 -*-
"""
Shiro Chat & Memory Interaction Routes
Handles Web UI chat interaction, conversation history, memory counts, and idle triggers.
"""

import os
import uuid
import base64
from datetime import datetime
from flask import Blueprint, request, jsonify

from shiro.auth import verify_api_key
from shiro.server_state import state
from shiro.nlp.emotion import detect_emotion_category
from shiro.memory.optimization import compress_old_messages
from shiro.pipeline.inference import get_shiro_reply

chat_bp = Blueprint("chat_bp", __name__)

def _format_message_for_api(msg):
    """Format single message dictionary to ensure valid URLs for frontend viewing"""
    m = dict(msg)
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
    return jsonify({
        "history": [_format_message_for_api(m) for m in memory.short_term_history],
        "count": len(memory.short_term_history),
        "metadata": memory.system_metadata,
        "user_profile": memory.user_profile,
        "agent_persona": memory.agent_persona,
        "topics": memory.system_metadata.get("topics_discussed", [])
    })

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
            
            memory.add_message("assistant", reply)
            compress_old_messages(memory, keep_count=15)
            memory.save_memory()
            state.serial_questions += 1
            
            return jsonify({
                "reply": reply,
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
        
        document_info = None
        if document_text:
            document_info = {
                "text": document_text,
                "filename": document_name or "Dokumen"
            }

        if not user_message and not image_base64 and not document_info:
            return jsonify({"error": "Empty message"}), 400
        
        if len(user_message) > 6000:
            return jsonify({
                "error": "Message too long (Maksimal 6000 karakter)",
                "reply": "*bingung* Kakak ngomong panjang banget lebih dari 6000 karakter... Shiro pusing! Singkat sedikit ya, Kak!"
            }), 400
        
        saved_img_rel = None
        if image_base64:
            try:
                v_dir = os.path.join("training_data", "vision", "images")
                os.makedirs(v_dir, exist_ok=True)
                fn = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
                fp = os.path.join(v_dir, fn)
                raw = image_base64.split(",", 1)[1] if "," in image_base64 else image_base64
                with open(fp, "wb") as f_out:
                    f_out.write(base64.b64decode(raw))
                saved_img_rel = os.path.join("images", fn).replace("\\", "/")
            except Exception as e_img:
                print(f"[Chat] Warning saving image: {e_img}")

        memory = state.init_memory()
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

            memory.add_message(
                "user", 
                log_msg, 
                image_path=img_url,
                document_name=document_name,
                document_url=doc_url,
                document_type=doc_type,
                document_text=document_text
            )
            
            # Eksekusi balasan neural AI (tanpa penimpaan fallback buatan)
            reply, trace = get_shiro_reply(
                user_message,
                image_base64=image_base64,
                document_info=document_info,
                return_trace=True
            )
            
            memory.add_message("assistant", reply)
            memory.update_emotional_state_from_response(reply)
            memory.update_mood_from_emotions()
            
            if not image_base64 or "poster tersebut" not in reply.lower():
                memory.record_learned_pattern(log_msg, reply, image_path=saved_img_rel)
            
            compress_old_messages(memory, keep_count=15)
            memory.save_memory()
            
            return jsonify({
                "reply": reply,
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
                "active_session_id": getattr(memory, "active_session_id", "default"),
                "pipeline_trace": trace
            })
    
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return jsonify({"error": str(e)}), 500
