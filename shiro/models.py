# -*- coding: utf-8 -*-
"""
Shiro Model Management & Configuration
Handles model scanning, GGUF detection, vision handler initialization,
LoRA adapter discovery, and model loading.
"""

import os
import re
import json
import glob
from typing import Optional, List, Dict, Any, Tuple
from shiro.config import MODEL_DIR, MODEL_CONFIG_FILE, CONTEXT_SIZE, DEFAULT_MAX_TOKENS

# Deteksi GPU CUDA
def get_gpu_layers() -> int:
    gpu_layers_env = os.environ.get("SHIRO_GPU_LAYERS")
    if gpu_layers_env is not None:
        try:
            return int(gpu_layers_env)
        except ValueError:
            pass

    try:
        import torch
        if torch.cuda.is_available():
            return -1  # Offload semua layer ke GPU
    except Exception:
        pass
    return 0

def get_optimal_model_tokens(model_path: str) -> Tuple[int, int]:
    """
    Menentukan batas context window (n_ctx) dan max output tokens secara dinamis
    menyesuaikan ukuran dan arsitektur model yang terdeteksi:
    - Model Besar (27B - 32B+ / A100): n_ctx 16384 s/d 32768, output hingga 8192 token
    - Model Sedang (7B - 14B / VL): n_ctx 8192 s/d 16384, output hingga 4096 token
    - Model Ringan (3B - 4B / T4): n_ctx 4096 s/d 8192, output hingga 2048 token
    """
    if not model_path:
        return (CONTEXT_SIZE, DEFAULT_MAX_TOKENS)

    name = os.path.basename(model_path).lower()
    gpu_layers = get_gpu_layers()
    is_gpu = gpu_layers != 0

    # 1. Model Besar: 27B, 32B, 70B, dll.
    if any(k in name for k in ["27b", "32b", "70b", "34b"]):
        n_ctx = 32768 if (is_gpu or is_running_in_colab()) else 16384
        max_output = 16384 if (is_gpu or is_running_in_colab()) else 8192
        return (n_ctx, max_output)

    # 2. Model Sedang: 7B, 8B, 14B, VL
    elif any(k in name for k in ["7b", "8b", "9b", "12b", "13b", "14b", "vl"]):
        n_ctx = 16384 if is_gpu else 8192
        max_output = 4096
        return (n_ctx, max_output)

    # 3. Model Ringan: 3B, 3.2B, 4B, Phi-3 mini
    elif any(k in name for k in ["3b", "3.2b", "4b", "phi-3", "mini"]):
        n_ctx = 8192 if is_gpu else 4096
        max_output = 2048
        return (n_ctx, max_output)

    # Default fallback
    n_ctx = 8192 if is_gpu else 4096
    max_output = 2048
    return (n_ctx, max_output)

def get_active_model_ctx(llm_instance) -> int:
    """Mengambil batas context token aktif dari model instance"""
    if llm_instance is None:
        return CONTEXT_SIZE
    try:
        if hasattr(llm_instance, 'n_ctx'):
            val = getattr(llm_instance, 'n_ctx')
            if callable(val):
                return int(val())
            return int(val)
        if hasattr(llm_instance, '_n_ctx'):
            return int(getattr(llm_instance, '_n_ctx'))
        if hasattr(llm_instance, 'context_params') and hasattr(llm_instance.context_params, 'n_ctx'):
            return int(llm_instance.context_params.n_ctx)
    except Exception:
        pass
    return CONTEXT_SIZE

def is_running_in_colab() -> bool:
    """Mendeteksi apakah program sedang berjalan di Google Colab"""
    return os.path.exists("/content") or "COLAB_GPU" in os.environ

def get_available_gguf_models() -> List[str]:
    """Scan folder model/ dan subfoldernya untuk mencari semua file .gguf"""
    models = []
    if not os.path.exists(MODEL_DIR):
        return models
    for root, _, files in os.walk(MODEL_DIR):
        for f in files:
            # Kecualikan mmproj projector dari daftar pilihan model LLM
            if f.endswith(".gguf") and not f.startswith("mmproj-"):
                rel_path = os.path.relpath(os.path.join(root, f), ".").replace("\\", "/")
                models.append(rel_path)
    return models

def is_vision_model(model_path: str) -> bool:
    """Mendeteksi apakah model mendukung multimodal vision (Qwen, 27B, 32B, VL, Llava)"""
    if not model_path:
        return False
    name = os.path.basename(model_path).lower()
    return any(k in name for k in ["qwen", "vl", "vision", "llava", "27b", "32b"])

def init_vision_handler(model_path: str):
    """
    Inisialisasi Vision Chat Handler (multimodal projector) untuk model vision.
    Mendukung Qwen (Qwen3.8-27B, Qwen3-32B, Qwen2.5-VL) via Qwen25VLChatHandler dan Llava via Llava15ChatHandler.
    """
    if not model_path:
        return None
        
    name = os.path.basename(model_path).lower()
    if not is_vision_model(model_path):
        return None
        
    model_dir = os.path.dirname(model_path) if model_path else MODEL_DIR
    search_dirs = [
        model_dir,
        MODEL_DIR,
        "model",
        "/content",
        "/content/model",
        "/content/drive/MyDrive/model",
        "/content/drive/MyDrive/Shiro_Memory/model",
        "."
    ]

    mmproj_candidates = [
        os.path.join(MODEL_DIR, "mmproj-F16.gguf"),
        os.path.join(MODEL_DIR, "mmproj-BF16.gguf"),
        os.path.join(MODEL_DIR, "mmproj-model-f16.gguf"),
    ]
    for s_dir in search_dirs:
        if s_dir and os.path.exists(s_dir):
            try:
                for f in os.listdir(s_dir):
                    if "mmproj" in f.lower() and f.endswith(".gguf"):
                        cand = os.path.join(s_dir, f)
                        if cand not in mmproj_candidates:
                            mmproj_candidates.append(cand)
            except Exception:
                pass
                    
    mmproj_file = None
    for cand in mmproj_candidates:
        if os.path.exists(cand):
            mmproj_file = cand
            break

    # 1. Arsitektur Qwen (Qwen3.8-27B, Qwen3-32B, Qwen2.5-VL):
    if any(k in name for k in ["qwen", "vl", "27b", "32b"]):
        try:
            from llama_cpp.llama_chat_format import Qwen25VLChatHandler
            if mmproj_file:
                vision_chat_handler = Qwen25VLChatHandler(clip_model_path=mmproj_file)
                print(f"👁️ Vision Chat Handler (Qwen25VL) aktif dengan projector: {mmproj_file}")
                return vision_chat_handler
        except Exception as e1:
            print(f"[Vision Notice] Qwen25VLChatHandler fallback: {e1}")

    # 2. Khusus Llava / Model Vision Standar:
    if mmproj_file:
        try:
            from llama_cpp.llama_chat_format import Llava15ChatHandler
            vision_chat_handler = Llava15ChatHandler(clip_model_path=mmproj_file)
            print(f"👁️ Vision Chat Handler (Llava15) aktif dengan projector: {mmproj_file}")
            return vision_chat_handler
        except Exception as e2:
            print(f"[Vision Notice] Llava15ChatHandler fallback: {e2}")

    return None

def find_active_lora_path(version: Optional[int] = None) -> Optional[str]:
    """
    Mendeteksi file bobot LoRA adapter (.gguf atau .bin) hasil fine-tuning jika tersedia.
    """
    custom_lora = os.environ.get("SHIRO_LORA_PATH", "").strip()
    if not version and custom_lora and os.path.exists(custom_lora):
        return custom_lora

    drive_dir = os.environ.get("SHIRO_DRIVE_DIR")
    if not drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
        drive_dir = "/content/drive/MyDrive/Shiro_Memory"

    search_dirs = ["lora", os.path.join(MODEL_DIR, "lora")]
    if drive_dir and os.path.exists(os.path.join(drive_dir, "lora")):
        search_dirs.append(os.path.join(drive_dir, "lora"))

    found_loras = []
    for d in search_dirs:
        if os.path.exists(d):
            found_loras.extend(glob.glob(os.path.join(d, "*.gguf")) + glob.glob(os.path.join(d, "*.bin")))
            found_loras.extend(glob.glob(os.path.join(d, "*", "*.gguf")) + glob.glob(os.path.join(d, "*", "*.bin")))

    if not found_loras:
        return None

    def _get_ver_key(p):
        m = re.search(r'V(\d+)', os.path.basename(p), re.IGNORECASE)
        if not m:
            m = re.search(r'V(\d+)', os.path.dirname(p), re.IGNORECASE)
        return int(m.group(1)) if m else 0

    if version is not None:
        for p in found_loras:
            if _get_ver_key(p) == int(version):
                return p

    found_loras = sorted(list(set(found_loras)), key=_get_ver_key, reverse=True)
    return found_loras[0] if found_loras else None

def load_model_config() -> Dict[str, Any]:
    """Load model config, return dict dengan available models & current model"""
    scanned_models = get_available_gguf_models()
    
    config = {
        "current_model": "",
        "local_default_model": "model/Qwen3-4B-Q4_K_M.gguf",
        "available_models": [],
        "model_info": {}
    }
    
    if os.path.exists(MODEL_CONFIG_FILE):
        try:
            with open(MODEL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    config.update(saved)
        except Exception as e:
            print(f"Error loading model config: {e}")

    current_list = list(config.get("available_models", []))
    for m in scanned_models:
        if m not in current_list:
            current_list.append(m)
    config["available_models"] = current_list
    
    if "model_info" not in config:
        config["model_info"] = {}
    for m in config["available_models"]:
        if m not in config["model_info"]:
            basename = os.path.basename(m).replace(".gguf", "")
            size_gb = 0
            if os.path.exists(m):
                size_gb = os.path.getsize(m) / (1024 * 1024 * 1024)
            size_str = f"~{size_gb:.1f} GB" if size_gb > 0 else "GGUF"
            is_trained = "shiroai-llm-v" in basename.lower()
            quant = "Fine-Tuned (LoRA)" if is_trained else "Manual/Auto"
            desc = f"Model Pelatihan Mandiri: {basename} ({size_str})" if is_trained else f"Model Lokal: {basename} ({size_str})"
            config["model_info"][m] = {
                "name": basename,
                "size": size_str,
                "quantization": quant,
                "description": desc
            }

    in_colab = is_running_in_colab()
    current_model = config.get("current_model", "")
    
    if not in_colab:
        local_default = config.get("local_default_model", "model/Qwen3-4B-Q4_K_M.gguf")
        if not current_model or not os.path.exists(current_model) or ("32b" in current_model.lower() and not os.path.exists(current_model)):
            if os.path.exists(local_default):
                config["current_model"] = local_default
            elif scanned_models:
                sorted_by_size = sorted(scanned_models, key=lambda p: os.path.getsize(p) if os.path.exists(p) else 999999999999)
                config["current_model"] = sorted_by_size[0]
            else:
                config["current_model"] = local_default
    else:
        colab_default = "model/Qwen3.8-27B-Uncensored-Q4_K_M.gguf"
        if not os.path.exists(colab_default):
            colab_default = "model/Qwen3-32B-Q4_K_M.gguf"
        if not current_model or not os.path.exists(current_model):
            if os.path.exists(colab_default):
                config["current_model"] = colab_default
            elif scanned_models:
                config["current_model"] = scanned_models[0]
            else:
                config["current_model"] = colab_default
                
    return config

def save_model_config(config: Dict[str, Any]):
    """Save model config"""
    try:
        with open(MODEL_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving model config: {e}")

def detect_chat_format(model_path: str) -> str:
    """Mendeteksi chat template yang sesuai untuk model GGUF"""
    if not model_path:
        return "chatml"
    name = os.path.basename(model_path).lower()
    if "qwen2.5" in name or "qwen-2.5" in name:
        return "chatml"
    elif "llama-3" in name or "llama3" in name or "lumimaid" in name:
        return "llama-3"
    elif "qwen" in name:
        return "chatml"
    elif "phi-3" in name or "phi3" in name:
        return "chatml"
    else:
        return "chatml"

def instantiate_llama_model(model_path: str, lora_version: Optional[int] = None) -> Tuple[Any, Any]:
    """
    Instantiate Llama model instance dan vision handler.
    Mengembalikan (llm_instance, vision_handler).
    """
    from llama_cpp import Llama
    gpu_layers = get_gpu_layers()
    vision_handler = init_vision_handler(model_path)
    
    optimal_ctx, optimal_out = get_optimal_model_tokens(model_path)
    env_ctx = os.environ.get("SHIRO_CONTEXT_SIZE")
    if env_ctx:
        try:
            chosen_ctx = max(int(env_ctx), optimal_ctx)
        except Exception:
            chosen_ctx = optimal_ctx
    else:
        chosen_ctx = optimal_ctx

    llama_kwargs = {
        "model_path": model_path,
        "n_ctx": chosen_ctx,
        "n_threads": 4,
        "n_gpu_layers": gpu_layers,
        "verbose": False,
    }
    if vision_handler:
        llama_kwargs["chat_handler"] = vision_handler
    else:
        llama_kwargs["chat_format"] = detect_chat_format(model_path)
        
    active_lora = find_active_lora_path(version=lora_version)
    if active_lora:
        llama_kwargs["lora_path"] = active_lora
        print(f"🎯 LoRA Adapter Terdeteksi & Dimuat: {os.path.basename(active_lora)}")

    try:
        llm = Llama(**llama_kwargs)
    except Exception as err:
        if "lora_path" in llama_kwargs:
            print(f"⚠️ Gagal memuat LoRA ({err}), mencoba tanpa LoRA...")
            llama_kwargs.pop("lora_path", None)
            try:
                llm = Llama(**llama_kwargs)
                err = None
            except Exception as e_retry:
                err = e_retry
        if err:
            if vision_handler:
                print(f"⚠️ Gagal memuat Vision Handler ({err}), fallback ke teks...")
                llama_kwargs.pop("chat_handler", None)
                llama_kwargs["chat_format"] = detect_chat_format(model_path)
                llm = Llama(**llama_kwargs)
                vision_handler = None
            else:
                raise err

    return llm, vision_handler
