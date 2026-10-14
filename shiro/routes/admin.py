# -*- coding: utf-8 -*-
"""
Shiro Admin, Model Switching, and Profile Management Routes
"""

import os
import gc
import re
import json
import shutil
import base64
from datetime import datetime
from flask import Blueprint, request, jsonify

from shiro.config import PROFILE_DIR, MODEL_DIR
from shiro.auth import get_active_api_key, get_or_create_api_key
from shiro.server_state import state
from shiro.models import (
    load_model_config,
    save_model_config,
    is_running_in_colab,
    instantiate_llama_model
)

admin_bp = Blueprint("admin_bp", __name__)

@admin_bp.route('/api/key', methods=['GET'])
def get_api_key_info():
    """Get active API Key and connection info for external bots/clients (v1, v2, v3)"""
    key = get_active_api_key()
    host_url = request.host_url.rstrip('/')
    return jsonify({
        "api_key": key,
        "openai_base_url": f"{host_url}/v1",
        "chat_completions_url": f"{host_url}/v1/chat/completions",
        "direct_chat_url": f"{host_url}/api/chat",
        "endpoints": {
            "v1": {
                "name": "Default Shiro (Bahasa Indonesia)",
                "base_url": f"{host_url}/v1",
                "chat_completions": f"{host_url}/v1/chat/completions",
                "description": "Karakter adik manja Shiro dalam 100% Bahasa Indonesia"
            },
            "v2": {
                "name": "VTuber Engine (Japanese VoiceVox)",
                "base_url": f"{host_url}/v2",
                "chat_completions": f"{host_url}/v2/chat/completions",
                "description": "Karakter VTuber Waifu Shiro dalam 100% Bahasa Jepang dengan format tag [Tag] untuk VoiceVox TTS"
            },
            "v3": {
                "name": "Custom Base Prompt",
                "base_url": f"{host_url}/v3",
                "chat_completions": f"{host_url}/v3/chat/completions",
                "description": "Kustom base prompt bebas mengikuti instruksi system klien tanpa paksaan bahasa"
            }
        },
        "documentation": {
            "auth_header": f"Authorization: Bearer {key}",
            "x_api_key": f"X-API-Key: {key}"
        }
    })

@admin_bp.route('/api/key/regenerate', methods=['POST'])
def regenerate_api_key_route():
    """Hasilkan API Key baru secara dinamis dan simpan ke riwayat valid"""
    new_key = get_or_create_api_key(force_new=True)
    host_url = request.host_url.rstrip('/')
    return jsonify({
        "success": True,
        "api_key": new_key,
        "message": "API Key baru berhasil di-generate!",
        "openai_base_url": f"{host_url}/v1",
        "endpoints": {
            "v1": {
                "name": "Default Shiro (Bahasa Indonesia)",
                "base_url": f"{host_url}/v1",
                "chat_completions": f"{host_url}/v1/chat/completions"
            },
            "v2": {
                "name": "VTuber Engine (Japanese VoiceVox)",
                "base_url": f"{host_url}/v2",
                "chat_completions": f"{host_url}/v2/chat/completions"
            },
            "v3": {
                "name": "Custom Base Prompt",
                "base_url": f"{host_url}/v3",
                "chat_completions": f"{host_url}/v3/chat/completions"
            }
        },
        "documentation": {
            "auth_header": f"Authorization: Bearer {new_key}",
            "x_api_key": f"X-API-Key: {new_key}"
        }
    })

@admin_bp.route('/api/gemini-key', methods=['GET', 'POST'])
def handle_gemini_key():
    """Mendapatkan status atau mengatur Gemini API Key untuk Visual Bridge"""
    from shiro.vision.bridge import get_gemini_api_key
    if request.method == 'GET':
        key = get_gemini_api_key() or ""
        masked = (key[:6] + "..." + key[-4:]) if len(key) > 10 else ("***" if key else "")
        return jsonify({
            "is_configured": bool(key),
            "masked_key": masked,
            "has_key": bool(key)
        })

    data = request.json or {}
    new_key = data.get("gemini_key", "").strip()
    config = load_model_config()
    if new_key:
        os.environ["GEMINI_API_KEY"] = new_key
        config["gemini_api_key"] = new_key
        save_model_config(config)
        return jsonify({
            "success": True,
            "message": "Gemini API Key berhasil disimpan untuk Visual Bridge!",
            "is_configured": True
        })
    else:
        os.environ.pop("GEMINI_API_KEY", None)
        config.pop("gemini_api_key", None)
        save_model_config(config)
        return jsonify({
            "success": True,
            "message": "Gemini API Key berhasil dihapus.",
            "is_configured": False
        })

@admin_bp.route('/api/reset', methods=['POST'])
def reset():
    memory = state.init_memory()
    try:
        with memory.lock:
            memory.finalize_session()
            memory.reset_memory()
            return jsonify({
                "success": True,
                "message": "Memory reset successfully"
            })
    except Exception as e:
        print(f"[Admin] Error in reset: {e}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/api/export', methods=['GET'])
def export_memory():
    memory = state.init_memory()
    try:
        return jsonify({
            "system_metadata": memory.system_metadata,
            "user_profile": memory.user_profile,
            "agent_persona": memory.agent_persona,
            "knowledge_base": memory.knowledge_base,
            "episodic_memory": memory.episodic_memory,
            "short_term_history": memory.short_term_history,
            "world": memory.world,
            "exported_at": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/api/profile', methods=['GET'])
def get_profile():
    user_profile = None
    ai_profile = None
    user_file = os.path.join(PROFILE_DIR, 'user.json')
    ai_file = os.path.join(PROFILE_DIR, 'ai.json')
    
    if os.path.exists(user_file):
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                user_profile = json.load(f)
        except Exception:
            pass
    
    if os.path.exists(ai_file):
        try:
            with open(ai_file, 'r', encoding='utf-8') as f:
                ai_profile = json.load(f)
        except Exception:
            pass
    
    return jsonify({
        "user": user_profile,
        "ai": ai_profile
    })

@admin_bp.route('/api/profile/upload', methods=['POST'])
def upload_profile():
    try:
        profile_type = request.form.get('type')
        if profile_type not in ['user', 'ai']:
            return jsonify({"error": "Invalid profile type"}), 400
        
        name = request.form.get('name', 'Unknown')
        description = request.form.get('description', '')
        
        image_data = None
        if 'image' in request.files:
            file = request.files['image']
            if file:
                image_bytes = file.read()
                image_data = base64.b64encode(image_bytes).decode('utf-8')
        
        profile = {
            "name": name,
            "description": description,
            "image": image_data,
            "image_mime": request.form.get('image_mime', 'image/png')
        }
        
        os.makedirs(PROFILE_DIR, exist_ok=True)
        profile_file = os.path.join(PROFILE_DIR, f'{profile_type}.json')
        with open(profile_file, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        
        drive_dir = os.environ.get("SHIRO_DRIVE_DIR")
        if not drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
            drive_dir = "/content/drive/MyDrive/Shiro_Memory"
        if drive_dir and os.path.exists(drive_dir):
            try:
                drive_prof_dir = os.path.join(drive_dir, "profile")
                os.makedirs(drive_prof_dir, exist_ok=True)
                shutil.copy2(profile_file, os.path.join(drive_prof_dir, f'{profile_type}.json'))
            except Exception:
                pass
        
        return jsonify({
            "success": True,
            "message": f"Profile {profile_type} updated",
            "profile": profile
        })
    except Exception as e:
        print(f"[Admin] Error upload profile: {e}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/api/models', methods=['GET'])
def get_models():
    config = load_model_config()
    return jsonify({
        "current_model": config.get("current_model"),
        "available_models": config.get("available_models", []),
        "model_info": config.get("model_info", {}),
        "is_colab": is_running_in_colab()
    })

@admin_bp.route('/api/models/switch', methods=['POST'])
@admin_bp.route('/v1/models/switch', methods=['POST'])
@admin_bp.route('/v2/models/switch', methods=['POST'])
@admin_bp.route('/v3/models/switch', methods=['POST'])
def switch_model():
    try:
        data = request.json or {}
        model_path = data.get('model')
        if not model_path:
            return jsonify({"error": "Parameter 'model' harus disertakan"}), 400

        config = load_model_config()
        available = config.get("available_models", [])

        target_path = None
        target_lora_ver = None

        if os.path.exists(model_path):
            target_path = model_path
        elif os.path.exists(os.path.join(MODEL_DIR, f"{model_path}.gguf")):
            target_path = os.path.join(MODEL_DIR, f"{model_path}.gguf").replace("\\", "/")
        elif os.path.exists(os.path.join(MODEL_DIR, model_path)):
            target_path = os.path.join(MODEL_DIR, model_path).replace("\\", "/")
        else:
            for cand in available:
                bname = os.path.basename(cand)
                bname_no_ext = os.path.splitext(bname)[0]
                if model_path.lower() in (bname.lower(), bname_no_ext.lower()):
                    target_path = cand
                    break

        if not target_path:
            m_ver = re.search(r'V(\d+)', model_path, re.IGNORECASE)
            if m_ver:
                target_lora_ver = int(m_ver.group(1))
                target_path = config.get("current_model") or (available[0] if available else None)

        if not target_path or not os.path.exists(target_path):
            return jsonify({"error": f"Model '{model_path}' tidak ditemukan di disk atau daftar model"}), 400

        model_path = target_path
        model_name = os.path.basename(model_path)
        file_size_gb = os.path.getsize(model_path) / (1024 * 1024 * 1024)
        print(f"\n[Admin] Switching model ke: {model_name} ({file_size_gb:.2f} GB)")
        
        if file_size_gb < 0.1:
            return jsonify({"error": f"File model '{model_name}' rusak atau belum selesai diunduh"}), 400

        old_llm = state.llm
        try:
            if state.llm is not None:
                try:
                    if hasattr(state.llm, 'close'):
                        state.llm.close()
                except Exception as e_close:
                    print(f"Warning closing previous LLM: {e_close}")
                state.llm = None
                gc.collect()

            new_llm, vision_handler = instantiate_llama_model(model_path, lora_version=target_lora_ver)
            state.set_llm(new_llm, vision_handler)

            config["current_model"] = model_path
            save_model_config(config)

            print(f"[Admin] Berhasil beralih ke model: {model_name}")
            return jsonify({
                "success": True,
                "message": f"Model switched to {model_name}",
                "current_model": model_path,
                "has_vision": bool(vision_handler is not None)
            })

        except Exception as load_error:
            print(f"[Admin] Error loading model: {load_error}")
            if state.llm is None and old_llm is not None:
                state.llm = old_llm
            return jsonify({"error": f"Gagal load model: {str(load_error)[:120]}"}), 500

    except Exception as e:
        print(f"[Admin] Error in switch_model: {e}")
        return jsonify({"error": str(e)}), 500
