# -*- coding: utf-8 -*-
"""
Shiro Model Management & Configuration
Handles model scanning, GGUF detection, vision handler initialization,
LoRA adapter discovery, and model loading.
"""

import os
import sys
import re
import json
import glob
import struct
from typing import Optional, List, Dict, Any, Tuple
from shiro.config import MODEL_DIR, MODEL_CONFIG_FILE, CONTEXT_SIZE, DEFAULT_MAX_TOKENS

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode('ascii', errors='replace').decode('ascii'))
        except Exception:
            pass

# Arsitektur model yang didukung oleh runtime llama-cpp
KNOWN_SUPPORTED_ARCHITECTURES = {
    "llama", "mistral", "qwen2", "qwen2moe", "phi2", "phi3", "gemma", "gemma2",
    "starcoder", "starcoder2", "falcon", "baichuan", "internlm2", "minicpm",
    "deepseek2", "bloom"
}



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

def read_gguf_metadata(path: str) -> Dict[str, Any]:
    """
    Membaca metadata header dari berkas GGUF secara langsung dan instan tanpa
    memuat bobot tensor ke RAM. Mengekstrak arsitektur, nama model, size label, dll.
    """
    info = {}
    if not path or not os.path.exists(path) or os.path.isdir(path):
        return info
    try:
        with open(path, 'rb') as f:
            magic = f.read(4)
            if magic != b'GGUF':
                return info
            version = struct.unpack('<I', f.read(4))[0]
            if version not in (2, 3):
                return info
            tensor_count = struct.unpack('<Q', f.read(8))[0]
            kv_count = struct.unpack('<Q', f.read(8))[0]
            for _ in range(min(kv_count, 60)):
                k_len_bytes = f.read(8)
                if len(k_len_bytes) < 8:
                    break
                k_len = struct.unpack('<Q', k_len_bytes)[0]
                if k_len > 1024 or k_len == 0:
                    break
                key = f.read(k_len).decode('utf-8', errors='ignore')
                vt_bytes = f.read(4)
                if len(vt_bytes) < 4:
                    break
                val_type = struct.unpack('<I', vt_bytes)[0]
                if val_type == 8:  # string
                    vl_bytes = f.read(8)
                    if len(vl_bytes) < 8:
                        break
                    vl = struct.unpack('<Q', vl_bytes)[0]
                    val = f.read(vl).decode('utf-8', errors='ignore')
                    info[key] = val
                elif val_type in (0, 1, 7):  # uint8, int8, bool
                    v_bytes = f.read(1)
                    if val_type == 7:
                        info[key] = (v_bytes != b'\x00')
                elif val_type in (2, 3):  # uint16, int16
                    f.seek(2, 1)
                elif val_type in (4, 5, 6):  # uint32, int32, float32
                    v_bytes = f.read(4)
                    if val_type == 4:
                        info[key] = struct.unpack('<I', v_bytes)[0]
                elif val_type in (10, 11, 12):  # uint64, int64, float64
                    v_bytes = f.read(8)
                    if val_type == 10:
                        info[key] = struct.unpack('<Q', v_bytes)[0]
                elif val_type == 9:  # array
                    et_bytes = f.read(4)
                    al_bytes = f.read(8)
                    if len(et_bytes) < 4 or len(al_bytes) < 8:
                        break
                    elem_type = struct.unpack('<I', et_bytes)[0]
                    arr_len = struct.unpack('<Q', al_bytes)[0]
                    if elem_type == 8:
                        for _ in range(arr_len):
                            sl_bytes = f.read(8)
                            if len(sl_bytes) < 8:
                                break
                            sl = struct.unpack('<Q', sl_bytes)[0]
                            f.seek(sl, 1)
                    elif elem_type in (0, 1, 7):
                        f.seek(arr_len * 1, 1)
                    elif elem_type in (2, 3):
                        f.seek(arr_len * 2, 1)
                    elif elem_type in (4, 5, 6):
                        f.seek(arr_len * 4, 1)
                    elif elem_type in (10, 11, 12):
                        f.seek(arr_len * 8, 1)
                    else:
                        break
                else:
                    break
    except Exception:
        pass
    return info

def get_available_gguf_models() -> List[str]:
    """Scan folder model/ dan subfoldernya untuk mencari semua file .gguf yang valid"""
    models = []
    if not os.path.exists(MODEL_DIR):
        return models
    for root, _, files in os.walk(MODEL_DIR):
        for f in files:
            # Kecualikan mmproj projector dan berkas non-gguf dari daftar model LLM
            if f.endswith(".gguf") and not f.startswith("mmproj-"):
                full_path = os.path.join(root, f)
                try:
                    # Filter file 0-byte atau file korup yang berukuran < 1 MB
                    if os.path.getsize(full_path) < 1024 * 1024:
                        continue
                except OSError:
                    continue
                rel_path = os.path.relpath(full_path, ".").replace("\\", "/")
                models.append(rel_path)
    return models

def sort_models_by_priority(models: List[str]) -> List[str]:
    """
    Mengurutkan model-model terdeteksi secara cerdas untuk Autodetect:
    1. Model hasil fine-tuning Shiro (shiroharu, shiroai)
    2. Model dengan arsitektur yang terbukti didukung oleh runtime llama.cpp (llama, qwen2, mistral, dll.)
    3. Diurutkan berdasarkan ukuran file (model lebih ringan diutamakan untuk responsivitas CPU/GPU lokal)
    4. Model dengan arsitektur eksperimental / tidak dikenal ditaruh paling belakang sebagai fallback
    """
    def _priority_score(path: str):
        basename = os.path.basename(path).lower()
        size_bytes = os.path.getsize(path) if os.path.exists(path) else 999999999999
        meta = read_gguf_metadata(path)
        arch = (meta.get("general.architecture") or "").lower()

        is_tuned = "shiroharu-" in basename or "shiroai-" in basename

        is_supported_arch = False
        if arch:
            is_supported_arch = arch in KNOWN_SUPPORTED_ARCHITECTURES
        else:
            is_supported_arch = not any(k in basename for k in ["qwen3"])

        if is_tuned and is_supported_arch:
            tier = 0
        elif is_supported_arch:
            tier = 1
        elif is_tuned:
            tier = 2
        else:
            tier = 3

        return (tier, size_bytes)

    return sorted(models, key=_priority_score)

def is_vision_model(model_path: str) -> bool:
    """Mendeteksi apakah model merupakan model multimodal vision sejati (Qwen-VL, Qwen3.8-27B + mmproj, Llava, dsb.)"""
    if not model_path:
        return False
    name = os.path.basename(model_path).lower()
    if any(k in name for k in ["-vl", "_vl", "vl-", "vl_", "vision", "llava", "internvl", "minicpm"]):
        return True
    
    # Dukungan native multimodal Qwen3.8-27B dengan proyektor mmproj
    if "qwen3.8" in name or ("27b" in name and "qwen" in name):
        model_dir = os.path.dirname(model_path) if model_path else MODEL_DIR
        search_dirs = [model_dir, MODEL_DIR, "model", "/content/model", "/content", "."]
        for d in search_dirs:
            if d and os.path.exists(d):
                try:
                    for f in os.listdir(d):
                        fl = f.lower()
                        if "mmproj" in fl and fl.endswith(".gguf") and ("27b" in fl or "qwen3.8" in fl or "bf16" in fl or "f16" in fl):
                            return True
                except Exception:
                    pass
        if "qwen3.8" in name:
            return True
    return False

def init_vision_handler(model_path: str):
    """
    Inisialisasi Vision Chat Handler (multimodal projector) untuk model vision sejati (Qwen2.5-VL, Llava).
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

    mmproj_candidates = []
    is_32b = "32b" in name
    is_27b = "27b" in name or "qwen3.8" in name

    if is_27b:
        mmproj_candidates.extend([
            os.path.join(MODEL_DIR, "mmproj-Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-BF16.gguf"),
            os.path.join(MODEL_DIR, "mmproj-Qwen3.8-27B-BF16.gguf"),
            os.path.join(MODEL_DIR, "mmproj-BF16.gguf"),
            os.path.join(MODEL_DIR, "mmproj-Qwen3.8-27B-Uncensored-BF16.gguf"),
            os.path.join(MODEL_DIR, "mmproj-F16.gguf"),
        ])
    elif is_32b:
        mmproj_candidates.extend([
            os.path.join(MODEL_DIR, "mmproj-Qwen_Qwen2.5-VL-32B-Instruct-f16.gguf"),
            os.path.join(MODEL_DIR, "mmproj-Qwen2.5-VL-32B-Instruct-f16.gguf"),
            os.path.join(MODEL_DIR, "mmproj-32b-f16.gguf")
        ])
    elif "7b" in name:
        mmproj_candidates.extend([
            os.path.join(MODEL_DIR, "mmproj-F16.gguf"),
            os.path.join(MODEL_DIR, "mmproj-model-f16.gguf")
        ])

    mmproj_candidates.extend([
        os.path.join(MODEL_DIR, "mmproj-BF16.gguf"),
        os.path.join(MODEL_DIR, "mmproj-F16.gguf"),
        os.path.join(MODEL_DIR, "mmproj-model-f16.gguf"),
    ])
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
    def _size_ok(path: str) -> bool:
        p = os.path.basename(path).lower()
        if is_27b:
            return "27b" in p or "qwen3.8" in p or "bf16" in p
        if is_32b:
            return "32b" in p
        return "32b" not in p and "27b" not in p
    for cand in [c for c in mmproj_candidates if _size_ok(c)] + mmproj_candidates:
        if os.path.exists(cand):
            mmproj_file = cand
            break

    # 1. Arsitektur Qwen-VL (Qwen2.5-VL-7B, Qwen2.5-VL-32B):
    if "vl" in name or "qwen" in name:
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
    """
    Load model config dengan prinsip AUTODETECT cerdas.
    Memindai berkas model di folder model/, mengurutkan berdasarkan kompatibilitas & ukuran,
    dan memilih model yang benar-benar ada dan didukung tanpa bergantung pada default model yang kaku.
    """
    scanned_models = get_available_gguf_models()
    prioritized_scanned = sort_models_by_priority(scanned_models)

    config = {
        "current_model": "",
        "auto_detect": True,
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

    # AUTO-DETECT: Urutkan dan masukkan model yang benar-benar ada di disk
    detected_models = []

    # 1. Masukkan hasil scan disk sesuai urutan prioritas kompatibilitas
    for m in prioritized_scanned:
        if m not in detected_models:
            detected_models.append(m)

    # 2. Pertahankan model yang ada di config jika berkasnya ada di disk tapi belum masuk
    for m in config.get("available_models", []):
        if os.path.exists(m) and m not in detected_models:
            detected_models.append(m)

    config["available_models"] = detected_models

    # Filter dan susun model_info secara dinamis menggunakan metadata GGUF
    filtered_info = {}
    saved_info = config.get("model_info", {})
    if not isinstance(saved_info, dict):
        saved_info = {}

    for m in detected_models:
        if m in saved_info and isinstance(saved_info[m], dict) and saved_info[m].get("name"):
            filtered_info[m] = saved_info[m]
        else:
            meta = read_gguf_metadata(m)
            raw_name = meta.get("general.name")
            basename = os.path.basename(m).replace(".gguf", "")
            display_name = raw_name if raw_name else basename
            size_gb = os.path.getsize(m) / (1024 * 1024 * 1024) if os.path.exists(m) else 0
            size_str = meta.get("general.size_label") or (f"~{size_gb:.1f} GB" if size_gb > 0 else "GGUF")
            arch = meta.get("general.architecture") or "GGUF"
            is_trained = "shiroharu-" in basename.lower() or "shiroai-llm-v" in basename.lower()
            quant = "Fine-Tuned (LoRA)" if is_trained else "Auto-Detected"
            desc = f"Model Pelatihan Mandiri: {display_name} ({size_str})" if is_trained else f"Model AI ({arch}): {display_name} ({size_str})"
            filtered_info[m] = {
                "name": display_name,
                "size": size_str,
                "quantization": quant,
                "description": desc
            }
    config["model_info"] = filtered_info

    current_model = config.get("current_model", "")

    # PRINSIP AUTODETECT: Jangan mengikuti model default yang kaku!
    # Jika current_model kosong, bernilai 'auto', berkas tidak ada di disk,
    # atau memiliki arsitektur yang tidak didukung sementara ada model yang didukung:
    should_autodetect = (
        not current_model
        or current_model.lower() == "auto"
        or not os.path.exists(current_model)
        or (current_model not in detected_models)
    )

    if not should_autodetect and os.path.exists(current_model):
        cur_meta = read_gguf_metadata(current_model)
        cur_arch = (cur_meta.get("general.architecture") or "").lower()
        if cur_arch and cur_arch not in KNOWN_SUPPORTED_ARCHITECTURES and detected_models:
            # Model pertama di detected_models sudah diprioritaskan yang didukung
            if detected_models[0] != current_model:
                should_autodetect = True

    if should_autodetect:
        if detected_models:
            config["current_model"] = detected_models[0]
        else:
            config["current_model"] = ""

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
    meta = read_gguf_metadata(model_path)
    arch = (meta.get("general.architecture") or "").lower()

    if arch == "llama" or "llama-3" in name or "llama3" in name or "lumimaid" in name:
        return "llama-3"
    elif "qwen2.5" in name or "qwen-2.5" in name or arch in ("qwen2", "qwen"):
        return "chatml"
    elif "phi-3" in name or "phi3" in name or arch == "phi3":
        return "chatml"
    elif "gemma" in name or arch in ("gemma", "gemma2"):
        return "gemma"
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

def instantiate_llama_model_with_autodetect(
    preferred_model_path: Optional[str] = None,
    lora_version: Optional[int] = None
) -> Tuple[Any, Any, str]:
    """
    Memuat model LLM dengan fitur Autodetect cerdas dan auto-fallback dinamis.
    Tidak bergantung pada default model yang kaku.
    Jika preferred_model_path tidak diset ('', None, 'auto') atau gagal dimuat,
    sistem otomatis mencoba model-model .gguf lain yang tersedia di folder MODEL_DIR sampai berhasil.
    Mengembalikan (llm_instance, vision_handler, active_model_path).
    """
    scanned = get_available_gguf_models()
    prioritized = sort_models_by_priority(scanned)

    if not prioritized and not (preferred_model_path and os.path.exists(preferred_model_path)):
        raise FileNotFoundError(
            f"Tidak ada berkas model .gguf yang ditemukan di folder '{MODEL_DIR}'. "
            f"Silakan letakkan model GGUF di folder '{MODEL_DIR}' terlebih dahulu."
        )

    candidates: List[str] = []
    if preferred_model_path and preferred_model_path.lower() != "auto" and os.path.exists(preferred_model_path):
        norm_pref = preferred_model_path.replace("\\", "/")
        candidates.append(norm_pref)
        for m in prioritized:
            if m != norm_pref:
                candidates.append(m)
    else:
        candidates = list(prioritized)

    safe_print(f"🔍 [Autodetect] Memeriksa {len(candidates)} kandidat model di folder '{MODEL_DIR}'...")

    errors = []
    for idx, cand_path in enumerate(candidates, 1):
        cand_name = os.path.basename(cand_path)
        try:
            if idx > 1:
                safe_print(f"🔄 [Autodetect Fallback] Mencoba model alternatif ({idx}/{len(candidates)}): {cand_name}...")
            else:
                safe_print(f"⏳ Memuat model: {cand_name}...")
            llm, vision = instantiate_llama_model(cand_path, lora_version=lora_version)

            # Simpan model aktif yang berhasil dimuat ke config
            try:
                cfg = load_model_config()
                cfg["current_model"] = cand_path
                cfg["auto_detect"] = True
                save_model_config(cfg)
            except Exception:
                pass

            return llm, vision, cand_path
        except Exception as err:
            safe_print(f"⚠️ [Autodetect] Gagal memuat '{cand_name}': {err}")
            errors.append((cand_name, str(err)))
            continue

    summary_errors = "\n".join([f"  • {c}: {e}" for c, e in errors])
    raise RuntimeError(
        f"Gagal memuat semua model yang terdeteksi di folder '{MODEL_DIR}':\n{summary_errors}"
    )

