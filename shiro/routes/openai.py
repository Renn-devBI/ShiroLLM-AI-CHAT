# -*- coding: utf-8 -*-
"""
Shiro OpenAI-Compatible API Endpoints (/v1, /v2, /v3)
Provides Chat Completions and Models listing compatible with OpenAI SDK,
Cursor, LibreChat, Open WebUI, and external VTuber software.
"""

import os
import time
import base64
import secrets
from datetime import datetime
from flask import Blueprint, request, jsonify

from shiro.auth import verify_api_key
from shiro.server_state import state
from shiro.models import load_model_config
from shiro.memory.optimization import compress_old_messages
from shiro.pipeline.inference import get_shiro_reply

openai_bp = Blueprint("openai_bp", __name__)

def handle_openai_chat_completions(api_version="v1"):
    """
    OpenAI-compatible Chat Completions API endpoint handler:
    - v1: Default Shiro (100% Bahasa Indonesia, Persona Adik Manja)
    - v2: VTuber Engine (100% Japanese with [Tag] Expression Selector untuk VoiceVox TTS)
    - v3: Custom Base Prompt (Bebas mengikuti system prompt dari payload client tanpa paksaan bahasa)
    """
    if not verify_api_key(allow_web_ui=False):
        return jsonify({
            "error": {
                "message": "Invalid or missing API Key. Provide 'Authorization: Bearer <SHIRO_API_KEY>' or 'X-API-Key: <SHIRO_API_KEY>'",
                "type": "invalid_request_error",
                "code": "unauthorized"
            }
        }), 401
        
    try:
        data = request.json or {}
        messages = data.get("messages", [])
        model_name = data.get("model", "Qwen3.8-27B-Uncensored")
        
        if not messages:
            return jsonify({
                "error": {
                    "message": "No messages provided in request",
                    "type": "invalid_request_error"
                }
            }), 400

        # Ekstrak custom system prompt jika disertakan
        client_system_prompt = data.get("custom_system_prompt") or data.get("system_prompt")
        for msg in messages:
            if msg.get("role") == "system":
                client_system_prompt = msg.get("content", "")
                break

        # Deteksi otomatis VTuber jika client masih memanggil route /v1 tapi membawa prompt VTuber
        effective_version = api_version
        if api_version == "v1" and client_system_prompt:
            lower_sys = client_system_prompt.lower()
            if any(k in lower_sys for k in ["virtual youtuber", "vtuber", "native japanese", "voicevox", "suisei", "[tag]"]):
                effective_version = "v2"

        # Ambil pesan user terakhir & ekstrak teks murni serta gambar multimodal
        user_message = ""
        incoming_images = []
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict):
                            p_type = part.get("type", "")
                            if p_type == "text":
                                text_parts.append(part.get("text", ""))
                            elif p_type == "image_url":
                                img_url_obj = part.get("image_url", {})
                                if isinstance(img_url_obj, dict):
                                    url_val = img_url_obj.get("url", "")
                                    if url_val:
                                        incoming_images.append(url_val)
                                elif isinstance(img_url_obj, str) and img_url_obj:
                                    incoming_images.append(img_url_obj)
                    user_message = " ".join(text_parts).strip()
                elif isinstance(content, str):
                    user_message = content.strip()
                break

        # Gambar tambahan dari field images / frames (video sequence)
        extra_imgs = data.get("images") or data.get("frames") or []
        if isinstance(extra_imgs, list):
            for extra in extra_imgs:
                if isinstance(extra, str) and extra not in incoming_images:
                    incoming_images.append(extra)

        primary_image = incoming_images[0] if incoming_images else None

        # Agentic tools & tool choice
        tools = data.get("tools")
        tool_choice = data.get("tool_choice")

        # Controlled reasoning parameters
        reasoning_effort = data.get("reasoning_effort") or data.get("thinking_budget")
        include_reasoning = bool(
            data.get("include_reasoning") or 
            (data.get("thinking") is not None) or 
            (reasoning_effort and str(reasoning_effort).lower() not in ["none", "false", "0"])
        )

        # Token output limit parameter
        client_max_tokens = data.get("max_tokens") or data.get("max_completion_tokens")

        saved_img_rel = None
        if primary_image:
            try:
                import uuid
                v_dir = os.path.join("training_data", "vision", "images")
                os.makedirs(v_dir, exist_ok=True)
                fn = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
                fp = os.path.join(v_dir, fn)
                raw = primary_image.split(",", 1)[1] if "," in primary_image else primary_image
                with open(fp, "wb") as f_out:
                    f_out.write(base64.b64decode(raw))
                saved_img_rel = os.path.join("images", fn).replace("\\", "/")
            except Exception as e_img:
                print(f"[Completions] Warning saving image: {e_img}")

        memory = state.init_memory()
        with memory.lock:
            log_msg = user_message if user_message else ("[Visual Sent]" if primary_image else "")
            if log_msg:
                memory.add_message("user", log_msg, image_path=saved_img_rel)

            reply_result = get_shiro_reply(
                user_message,
                image_base64=primary_image,
                images_base64=incoming_images if len(incoming_images) > 1 else None,
                api_version=effective_version,
                custom_system_prompt=client_system_prompt,
                incoming_messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                reasoning_effort=reasoning_effort,
                include_reasoning=include_reasoning,
                max_tokens=client_max_tokens,
                return_details=True
            )
            if isinstance(reply_result, tuple):
                reply, details = reply_result
            else:
                reply = reply_result
                details = {}

            memory.add_message("assistant", reply)
            if effective_version == "v1" and (not primary_image or "poster tersebut" not in reply.lower()):
                memory.record_learned_pattern(log_msg, reply, image_path=saved_img_rel)
            memory.update_emotional_state_from_response(reply)
            memory.update_mood_from_emotions()
            compress_old_messages(memory, keep_count=15)
            memory.save_memory()
            
        response_id = f"chatcmpl-shiro-{effective_version}-{secrets.token_hex(8)}"
        created_time = int(time.time())
        prompt_tokens = len(user_message.split()) if user_message else 1
        comp_tokens = len(reply.split()) if reply else 1

        msg_obj = {
            "role": "assistant",
            "content": reply
        }
        if details.get("reasoning_content"):
            msg_obj["reasoning_content"] = details["reasoning_content"]
        if details.get("tool_calls"):
            msg_obj["tool_calls"] = details["tool_calls"]

        finish_reason = details.get("finish_reason") or ("tool_calls" if details.get("tool_calls") else "stop")
        
        return jsonify({
            "id": response_id,
            "object": "chat.completion",
            "created": created_time,
            "model": model_name,
            "api_version": effective_version,
            "choices": [
                {
                    "index": 0,
                    "message": msg_obj,
                    "finish_reason": finish_reason
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": comp_tokens,
                "total_tokens": prompt_tokens + comp_tokens
            }
        })
    except Exception as e:
        print(f"Error in /{api_version}/chat/completions: {e}")
        return jsonify({
            "error": {
                "message": str(e),
                "type": "server_error"
            }
        }), 500

@openai_bp.route('/v1/chat/completions', methods=['POST'])
def openai_chat_completions_v1():
    return handle_openai_chat_completions(api_version="v1")

@openai_bp.route('/v2/chat/completions', methods=['POST'])
@openai_bp.route('/v2/v1/chat/completions', methods=['POST'])
def openai_chat_completions_v2():
    return handle_openai_chat_completions(api_version="v2")

@openai_bp.route('/v3/chat/completions', methods=['POST'])
@openai_bp.route('/v3/v1/chat/completions', methods=['POST'])
def openai_chat_completions_v3():
    return handle_openai_chat_completions(api_version="v3")

@openai_bp.route('/v1/models', methods=['GET'])
@openai_bp.route('/v2/models', methods=['GET'])
@openai_bp.route('/v2/v1/models', methods=['GET'])
@openai_bp.route('/v3/models', methods=['GET'])
@openai_bp.route('/v3/v1/models', methods=['GET'])
def openai_models():
    """List available models for OpenAI SDK compatibility"""
    config = load_model_config()
    current = config.get("current_model", "")
    current_name = os.path.basename(current).replace(".gguf", "") if current else ""
    raw_models = config.get("available_models", [])
    
    try:
        from shiro.training.versioning import get_existing_trained_versions
        trained_versions = get_existing_trained_versions()
    except Exception:
        trained_versions = []

    model_ids = []
    if current_name and current_name not in model_ids:
        model_ids.append(current_name)

    for m_path in raw_models:
        m_name = os.path.basename(m_path).replace(".gguf", "")
        if m_name and m_name not in model_ids:
            model_ids.append(m_name)

    for v in trained_versions:
        t_name = f"ShiroAI-LLM-V{v}"
        if t_name not in model_ids:
            model_ids.append(t_name)

    if not model_ids:
        model_ids = ["Qwen3.8-27B-Uncensored", "Qwen3-32B", "Qwen2.5-VL-7B"]

    data = []
    now_ts = int(time.time())
    for mid in model_ids:
        data.append({
            "id": mid,
            "name": mid,
            "object": "model",
            "created": now_ts,
            "owned_by": "shiro",
            "is_current": (mid == current_name)
        })

    active_model = current_name or (model_ids[0] if model_ids else "Qwen3.8-27B-Uncensored")
    return jsonify({
        "object": "list",
        "data": data,
        "current_model": active_model
    })
