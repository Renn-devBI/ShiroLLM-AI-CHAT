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
from shiro.auth import get_active_api_key, get_or_create_api_key, verify_api_key
from shiro.server_state import state
from shiro.models import (
    LYRA_DISPLAY_NAME,
    LYRA_CONTEXT_TIERS,
    load_model_config,
    save_model_config,
    is_running_in_colab,
    is_qwen38_27b_uncensored,
    get_model_display_name,
    is_valid_lyra_tier,
    resolve_lyra_tier,
    get_saved_lyra_tier,
    save_lyra_tier,
    instantiate_llama_model,
    instantiate_llama_model_with_autodetect,
    get_active_model_ctx,
    get_gpu_layers
)

admin_bp = Blueprint("admin_bp", __name__)

@admin_bp.route('/api/health', methods=['GET'])
def health_check():
    """Lightweight health check endpoint untuk watchdog Colab & monitoring server"""
    model_path = getattr(state.llm, 'model_path', '') if state.llm else ''
    is_lyra = is_qwen38_27b_uncensored(model_path)
    raw_offload = getattr(state.llm, "_shiro_gpu_offload_verified", None) if state.llm is not None else None
    raw_kv = getattr(state.llm, "_shiro_kv_type", None) if state.llm is not None else None
    raw_max_gpu = getattr(state.llm, "_shiro_colab_max_gpu", None) if state.llm is not None else None
    is_max_gpu_active = raw_max_gpu if isinstance(raw_max_gpu, bool) else False
    return jsonify({
        "status": "ok" if state.llm is not None else "degraded",
        "model_loaded": state.llm is not None,
        "model_name": os.path.basename(model_path) if model_path else None,
        "model_display_name": get_model_display_name(model_path) if model_path else None,
        "is_lyra_active": is_lyra,
        "lyra_tier": get_saved_lyra_tier() if is_lyra else None,
        "busy": state.is_llm_busy(),
        "gpu_layers": get_gpu_layers(),
        "gpu_offload_supported": raw_offload if isinstance(raw_offload, bool) else None,
        "kv_cache_type": raw_kv if isinstance(raw_kv, str) else None,
        "colab_max_gpu_mode": is_max_gpu_active,
        "runtime_profile": "colab_max_gpu" if is_max_gpu_active else "local_pc_adaptive",
        "active_context_window": get_active_model_ctx(state.llm) if state.llm is not None else 0,
        "is_colab": is_running_in_colab(),
        "timestamp": datetime.now().isoformat()
    })

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
            if file and getattr(file, 'filename', ''):
                image_bytes = file.read()
                if image_bytes:
                    image_data = base64.b64encode(image_bytes).decode('utf-8')
        
        os.makedirs(PROFILE_DIR, exist_ok=True)
        profile_file = os.path.join(PROFILE_DIR, f'{profile_type}.json')
        
        # Pertahankan gambar lama jika user tidak mengunggah file gambar baru
        image_mime = request.form.get('image_mime', 'image/png')
        if image_data is None and os.path.exists(profile_file):
            try:
                with open(profile_file, 'r', encoding='utf-8') as f_old:
                    old_p = json.load(f_old)
                    image_data = old_p.get("image")
                    image_mime = old_p.get("image_mime", image_mime)
            except Exception:
                pass
        
        profile = {
            "name": name,
            "description": description,
            "image": image_data,
            "image_mime": image_mime
        }
        
        with open(profile_file, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

        # Sinkronisasi nama dan persona kustom ke memory server
        try:
            from shiro.server_state import state
            mem = state.init_memory()
            with mem.lock:
                if profile_type == 'user':
                    mem.user_profile["name"] = name
                    mem.system_metadata["user_name"] = name
                    if description:
                        mem.user_profile["preferences"]["context_notes"] = description
                elif profile_type == 'ai':
                    mem.agent_persona["name"] = name
                    if description:
                        mem.agent_persona["custom_roleplay"] = description
                    else:
                        mem.agent_persona.pop("custom_roleplay", None)
                mem.save_memory()
        except Exception as e_mem:
            print(f"[Admin] Warning syncing profile to memory: {e_mem}")
        
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
    current_model = config.get("current_model") or ""
    active_path = (getattr(state.llm, "model_path", "") if state.llm else "") or current_model
    is_lyra = is_qwen38_27b_uncensored(active_path)
    return jsonify({
        "current_model": current_model,
        "current_model_display_name": get_model_display_name(active_path),
        "is_lyra_active": is_lyra,
        "lyra_tier": get_saved_lyra_tier(),
        "lyra_tiers": LYRA_CONTEXT_TIERS,
        "auto_detect": config.get("auto_detect", True),
        "available_models": config.get("available_models", []),
        "model_info": config.get("model_info", {}),
        "active_context_window": get_active_model_ctx(state.llm),
        "is_colab": is_running_in_colab()
    })

@admin_bp.route('/api/models/context-tier', methods=['POST'])
@admin_bp.route('/v1/models/context-tier', methods=['POST'])
def set_lyra_context_tier():
    """Ubah tingkat panjang token (Low 190K / Medium 262K / High 500K / Extra High 700K / Ultra High 1M) khusus ShiroHaru-Lyra-Agent."""
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.json or {}
        req_tier = data.get("tier") or data.get("lyra_tier")
        defer_reload = bool(data.get("defer_reload", False))
        if not is_valid_lyra_tier(req_tier):
            valid_ids = [t["id"] for t in LYRA_CONTEXT_TIERS]
            return jsonify({"error": f"Tier tidak valid. Pilihan: {', '.join(valid_ids)}"}), 400

        config = load_model_config()
        active_path = (getattr(state.llm, "model_path", "") if state.llm else "") or config.get("current_model", "")
        if not is_qwen38_27b_uncensored(active_path):
            return jsonify({"error": f"Pilihan tingkat token ini khusus untuk model {LYRA_DISPLAY_NAME}."}), 400

        tier_info = resolve_lyra_tier(req_tier)
        tier_id = tier_info["id"]
        tier_label = tier_info["label"]
        target_tokens = tier_info["tokens"]

        save_lyra_tier(tier_id)
        os.environ.pop("SHIRO_QWEN38_27B_CONTEXT_SIZE", None)

        if defer_reload:
            actual_ctx = get_active_model_ctx(state.llm) if state.llm is not None else target_tokens
            return jsonify({
                "success": True,
                "lyra_tier": tier_id,
                "tier_label": tier_label,
                "display_name": LYRA_DISPLAY_NAME,
                "requested_tokens": target_tokens,
                "active_context_window": actual_ctx,
                "reloaded": False,
                "deferred": True,
                "cpu_capped": (get_gpu_layers() == 0),
                "fallback_applied": False,
                "message": f"{tier_label} dipilih."
            })

        with state.llm_lock:
            gpu_layers = get_gpu_layers()
            if gpu_layers == 0:
                actual_ctx = get_active_model_ctx(state.llm)
                return jsonify({
                    "success": True,
                    "lyra_tier": tier_id,
                    "tier_label": tier_label,
                    "display_name": LYRA_DISPLAY_NAME,
                    "requested_tokens": target_tokens,
                    "active_context_window": actual_ctx,
                    "reloaded": False,
                    "cpu_capped": True,
                    "fallback_applied": True,
                    "message": f"{tier_label} disimpan. Mode CPU membatasi konteks agar stabil; aktifkan GPU untuk kapasitas penuh."
                })

            if state.llm is not None and abs(get_active_model_ctx(state.llm) - target_tokens) <= 1024:
                actual_ctx = get_active_model_ctx(state.llm)
                return jsonify({
                    "success": True,
                    "lyra_tier": tier_id,
                    "tier_label": tier_label,
                    "display_name": LYRA_DISPLAY_NAME,
                    "requested_tokens": target_tokens,
                    "active_context_window": actual_ctx,
                    "reloaded": False,
                    "cpu_capped": False,
                    "fallback_applied": False,
                    "message": f"{tier_label} sudah aktif ({actual_ctx:,} tokens)."
                })

            old_llm = state.llm
            old_vis = state.vision_chat_handler
            try:
                if state.llm is not None:
                    try:
                        if hasattr(state.llm, 'close'):
                            state.llm.close()
                    except Exception as e_close:
                        print(f"Warning closing previous LLM: {e_close}")
                    state.llm = None
                    gc.collect()

                new_llm, new_vis = instantiate_llama_model(active_path, target_ctx_override=target_tokens)
                state.set_llm(new_llm, new_vis)
                actual_ctx = get_active_model_ctx(new_llm)
                fallback_applied = abs(actual_ctx - target_tokens) > 2048
                return jsonify({
                    "success": True,
                    "lyra_tier": tier_id,
                    "tier_label": tier_label,
                    "display_name": LYRA_DISPLAY_NAME,
                    "requested_tokens": target_tokens,
                    "active_context_window": actual_ctx,
                    "reloaded": True,
                    "cpu_capped": False,
                    "fallback_applied": fallback_applied,
                    "has_vision": bool(new_vis is not None),
                    "message": f"{tier_label} aktif ({actual_ctx:,} tokens)."
                })
            except Exception as load_error:
                print(f"[Admin] Error switching context tier to {tier_label}: {load_error}")
                if state.llm is None and old_llm is not None:
                    state.set_llm(old_llm, old_vis)
                return jsonify({"error": f"Gagal menerapkan {tier_label}: {str(load_error)[:120]}"}), 500
    except Exception as e:
        print(f"[Admin] Error in set_lyra_context_tier: {e}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/api/models/switch', methods=['POST'])
@admin_bp.route('/v1/models/switch', methods=['POST'])
@admin_bp.route('/v2/models/switch', methods=['POST'])
@admin_bp.route('/v3/models/switch', methods=['POST'])
def switch_model():
    try:
        data = request.json or {}
        model_path = data.get('model')
        req_tier = data.get('tier') or data.get('lyra_tier')
        if not model_path:
            return jsonify({"error": "Parameter 'model' harus disertakan"}), 400

        config = load_model_config()
        available = config.get("available_models", [])

        # Opsi Auto-Detect: Pilih dan aktifkan model terbaik secara otomatis
        if model_path.lower() in ("auto", "autodetect", "auto-detect"):
            with state.llm_lock:
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

                    new_llm, vision_handler, active_path = instantiate_llama_model_with_autodetect(None)
                    state.set_llm(new_llm, vision_handler)

                    config["current_model"] = active_path
                    config["auto_detect"] = True
                    save_model_config(config)

                    display_name = get_model_display_name(active_path)
                    active_ctx = get_active_model_ctx(new_llm)
                    is_lyra = is_qwen38_27b_uncensored(active_path)
                    print(f"[Admin] Autodetect berhasil beralih ke: {display_name} (Context Window: {active_ctx:,} tokens)")
                    return jsonify({
                        "success": True,
                        "message": f"Model switched to {display_name} (Auto-detected)",
                        "current_model": active_path,
                        "display_name": display_name,
                        "is_lyra_active": is_lyra,
                        "lyra_tier": get_saved_lyra_tier() if is_lyra else None,
                        "active_context_window": active_ctx,
                        "has_vision": bool(vision_handler is not None)
                    })
                except Exception as load_error:
                    print(f"[Admin] Error in autodetect switch: {load_error}")
                    if state.llm is None and old_llm is not None:
                        state.llm = old_llm
                    return jsonify({"error": f"Gagal autodetect model: {str(load_error)[:120]}"}), 500

        target_path = None
        target_lora_ver = None

        if os.path.exists(model_path):
            target_path = model_path
        elif model_path.lower() == LYRA_DISPLAY_NAME.lower():
            for cand in available:
                if is_qwen38_27b_uncensored(cand):
                    target_path = cand
                    break
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
        display_name = get_model_display_name(model_path)
        is_lyra = is_qwen38_27b_uncensored(model_path)
        file_size_gb = os.path.getsize(model_path) / (1024 * 1024 * 1024)
        print(f"\n[Admin] Switching model ke: {display_name} ({file_size_gb:.2f} GB)")
        
        if file_size_gb < 0.1:
            return jsonify({"error": f"File model '{display_name}' rusak atau belum selesai diunduh"}), 400

        target_ctx_override = None
        if is_lyra and is_valid_lyra_tier(req_tier):
            tier_info = save_lyra_tier(req_tier)
            target_ctx_override = tier_info["tokens"]

        with state.llm_lock:
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

                new_llm, vision_handler = instantiate_llama_model(
                    model_path,
                    lora_version=target_lora_ver,
                    target_ctx_override=target_ctx_override,
                )
                state.set_llm(new_llm, vision_handler)

                config["current_model"] = model_path
                save_model_config(config)

                active_ctx = get_active_model_ctx(new_llm)
                print(f"[Admin] Berhasil beralih ke model: {display_name} (Context Window: {active_ctx:,} tokens)")
                return jsonify({
                    "success": True,
                    "message": f"Model switched to {display_name}",
                    "current_model": model_path,
                    "display_name": display_name,
                    "is_lyra_active": is_lyra,
                    "lyra_tier": get_saved_lyra_tier() if is_lyra else None,
                    "active_context_window": active_ctx,
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


@admin_bp.route('/api/moe', methods=['GET', 'POST'])
@admin_bp.route('/v1/moe', methods=['GET', 'POST'])
def moe_settings():
    """Lihat atau ubah mode MoE Dual-Brain (off / auto / concurrent / swap)."""
    from shiro.agent.moe_router import get_orchestrator
    moe = get_orchestrator()
    if request.method == 'GET':
        return jsonify(moe.status())
    data = request.json or {}
    try:
        status = moe.set_mode(data.get("mode", ""), data.get("vision_expert"))
        if status["mode"] == "concurrent" and data.get("preload") and status["vision_expert_path"]:
            moe._get_expert(status["vision_expert_path"])
            status = moe.status()
        return jsonify({"success": True, **status})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Gagal mengatur MoE: {str(e)[:160]}"}), 500


@admin_bp.route('/api/settings/privacy', methods=['GET', 'POST'])
def privacy_and_ui_settings():
    """Get or update training data logging toggle, roleplay toggle, and UI language preference."""
    memory = state.init_memory()
    if request.method == 'GET':
        with memory.lock:
            return jsonify({
                "enable_training_logging": bool(memory.system_metadata.get("enable_training_logging", True)),
                "roleplay_enabled": bool(memory.system_metadata.get("roleplay_enabled", True)),
                "ui_language": memory.system_metadata.get("ui_language", "id"),
                "learned_patterns_count": len(getattr(memory, "learned_patterns", [])),
                "archived_training_count": len(getattr(memory, "archived_training_history", []))
            })
    try:
        data = request.json or {}
        with memory.lock:
            if "enable_training_logging" in data:
                memory.system_metadata["enable_training_logging"] = bool(data["enable_training_logging"])
            if "roleplay_enabled" in data:
                memory.system_metadata["roleplay_enabled"] = bool(data["roleplay_enabled"])
            if "ui_language" in data and data["ui_language"] in ("id", "en"):
                memory.system_metadata["ui_language"] = data["ui_language"]
                memory.user_profile["language"] = data["ui_language"]
            memory.save_memory()
            return jsonify({
                "success": True,
                "enable_training_logging": bool(memory.system_metadata.get("enable_training_logging", True)),
                "roleplay_enabled": bool(memory.system_metadata.get("roleplay_enabled", True)),
                "ui_language": memory.system_metadata.get("ui_language", "id")
            })
    except Exception as e:
        print(f"[Admin] Error updating privacy settings: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

