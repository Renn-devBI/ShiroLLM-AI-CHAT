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
    "llama", "mistral", "qwen", "qwen2", "qwen2.5", "qwen3", "qwen3.8", "qwen2moe",
    "phi2", "phi3", "gemma", "gemma2", "starcoder", "starcoder2", "falcon",
    "baichuan", "internlm2", "minicpm", "deepseek2", "bloom"
}

# Konfigurasi Extended Context & Alias khusus Qwen3.8-27B-Uncensored -> ShiroHaru-Lyra-Agent
LYRA_DISPLAY_NAME = "ShiroHaru-Lyra-Agent"
DEFAULT_LYRA_TIER = "high"
LYRA_CONTEXT_TIERS = [
    {
        "id": "low",
        "label": "ShiroHaru-Lyra Low",
        "tokens": 190000,
        "max_output": 2048,
        "thinking_mode": "off",
        "max_history_turns": 16,
        "top_k": 20,
    },
    {
        "id": "medium",
        "label": "ShiroHaru-Lyra Medium",
        "tokens": 262144,
        "max_output": 4096,
        "thinking_mode": "light",
        "max_history_turns": 32,
        "top_k": 30,
    },
    {
        "id": "high",
        "label": "ShiroHaru-Lyra High",
        "tokens": 500000,
        "max_output": 16384,
        "thinking_mode": "standard",
        "max_history_turns": 64,
        "top_k": 40,
    },
    {
        "id": "extra_high",
        "label": "ShiroHaru-Lyra Extra High",
        "tokens": 700000,
        "max_output": 24576,
        "thinking_mode": "deep",
        "max_history_turns": 128,
        "top_k": 40,
    },
    {
        "id": "ultra_high",
        "label": "ShiroHaru-Lyra Ultra High",
        "tokens": 1000000,
        "max_output": 32768,
        "thinking_mode": "ultra",
        "max_history_turns": None,
        "top_k": 50,
    },
]
LYRA_TIER_MAP = {t["id"]: t for t in LYRA_CONTEXT_TIERS}

QWEN38_27B_NATIVE_CTX = 262144
QWEN38_27B_EXTENDED_CTX = int(os.environ.get("SHIRO_QWEN38_27B_CONTEXT_SIZE", "500000"))
QWEN38_27B_CPU_SAFE_CTX = int(os.environ.get("SHIRO_QWEN38_27B_CPU_CONTEXT_SIZE", "32768"))
QWEN38_27B_MAX_OUTPUT = 16384


def is_qwen38_27b_uncensored(model_path: str) -> bool:
    """Mendeteksi secara ketat apakah model adalah Qwen3.8-27B-Uncensored."""
    if not model_path:
        return False
    name = os.path.basename(model_path).lower()
    has_qwen38 = any(k in name for k in ("qwen3.8", "qwen3_8", "qwen38", "qwen-3.8"))
    has_27b = "27b" in name
    has_uncensored = any(k in name for k in ("uncensored", "hauhaucs", "abliterated"))
    return has_qwen38 and has_27b and has_uncensored


def get_model_display_name(model_path: str, raw_fallback: Optional[str] = None) -> str:
    """Mengembalikan nama tampilan model (menyamarkan Qwen3.8-27B-Uncensored sebagai ShiroHaru-Lyra-Agent)."""
    if is_qwen38_27b_uncensored(model_path):
        return LYRA_DISPLAY_NAME
    if raw_fallback and str(raw_fallback).strip():
        return str(raw_fallback).strip()
    if not model_path:
        return ""
    return os.path.basename(model_path).replace(".gguf", "")


def _normalize_lyra_tier_key(tier_id: Optional[str]) -> Optional[str]:
    if not tier_id:
        return None
    norm = str(tier_id).strip().lower().replace("-", "_").replace(" ", "_")
    if norm in LYRA_TIER_MAP:
        return norm
    for t in LYRA_CONTEXT_TIERS:
        lbl_norm = t["label"].lower().replace("-", "_").replace(" ", "_")
        if norm == lbl_norm or norm == lbl_norm.replace("shiroharu_lyra_", ""):
            return t["id"]
    return None


def is_valid_lyra_tier(tier_id: Optional[str]) -> bool:
    """Memeriksa apakah id atau label tier ShiroHaru-Lyra valid."""
    return _normalize_lyra_tier_key(tier_id) is not None


def resolve_lyra_tier(tier_id: Optional[str] = None) -> Dict[str, Any]:
    """Mengembalikan info tier konteks ShiroHaru-Lyra yang valid (default: High / 500K)."""
    key = _normalize_lyra_tier_key(tier_id) or DEFAULT_LYRA_TIER
    return dict(LYRA_TIER_MAP[key])


def infer_lyra_tier_from_ctx(ctx: int) -> str:
    """Mencocokkan panjang n_ctx aktif ke tier ShiroHaru-Lyra terdekat."""
    if not ctx or ctx <= 0:
        return DEFAULT_LYRA_TIER
    best = min(LYRA_CONTEXT_TIERS, key=lambda t: abs(t["tokens"] - int(ctx)))
    return best["id"]


def get_saved_lyra_tier() -> str:
    """Membaca tier ShiroHaru-Lyra tersimpan dari model_config.json (default: high)."""
    if os.path.exists(MODEL_CONFIG_FILE):
        try:
            with open(MODEL_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    raw_tier = saved.get("lyra_tier")
                    if is_valid_lyra_tier(raw_tier):
                        return resolve_lyra_tier(raw_tier)["id"]
        except Exception:
            pass
    return DEFAULT_LYRA_TIER


def save_lyra_tier(tier_id: str) -> Dict[str, Any]:
    """Menyimpan pilihan tier konteks ShiroHaru-Lyra ke model_config.json."""
    tier = resolve_lyra_tier(tier_id)
    cfg = load_model_config()
    cfg["lyra_tier"] = tier["id"]
    save_model_config(cfg)
    return tier


def get_model_native_context_length(model_path: str, default: int = QWEN38_27B_NATIVE_CTX) -> int:
    """Membaca panjang context bawaan dari metadata GGUF model."""
    meta = read_gguf_metadata(model_path)
    for k, v in meta.items():
        if k.endswith(".context_length") and isinstance(v, int) and v > 0:
            return v
    return default


def _has_cuda_gpu() -> bool:
    """Mendeteksi keberadaan GPU CUDA nyata (via torch.cuda atau nvidia-smi)."""
    try:
        import torch
        if torch.cuda.is_available():
            return True
    except Exception:
        pass
    try:
        import subprocess
        res = subprocess.run(
            ["nvidia-smi", "-L"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3
        )
        if res.returncode == 0 and b"GPU" in res.stdout:
            return True
    except Exception:
        pass
    return False


def check_llama_cpp_gpu_offload(llama_cpp_mod: Any = None) -> Optional[bool]:
    """Memeriksa apakah biner llama-cpp-python benar-benar terkompilasi dengan dukungan offload GPU/CUDA."""
    mod = llama_cpp_mod
    if mod is None:
        try:
            import llama_cpp as mod
        except Exception:
            return None
    fn = getattr(mod, "llama_supports_gpu_offload", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:
            return None
    return None


def _get_gpu_vram_gb() -> Optional[float]:
    """Mengambil kapasitas VRAM GPU pertama dalam GB jika CUDA tersedia."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    except Exception:
        pass
    try:
        import subprocess
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3
        )
        if res.returncode == 0 and res.stdout.strip():
            first_line = res.stdout.strip().splitlines()[0].strip()
            return float(first_line) / 1024.0
    except Exception:
        pass
    return None


def _get_system_ram_gb() -> Optional[float]:
    """Mengambil kapasitas System RAM perangkat dalam GB."""
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb / (1024.0 * 1024.0)
    except Exception:
        pass
    try:
        import ctypes

        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        mem_st = _MEMORYSTATUSEX()
        mem_st.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem_st)):
            return mem_st.ullTotalPhys / (1024.0 ** 3)
    except Exception:
        pass
    return None


def build_colab_max_gpu_kwargs(
    is_gpu: bool,
    vram_gb: Optional[float] = None,
    ram_gb: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Khusus Google Colab GPU: menyetel parameter agresif agar GPU VRAM & High-RAM
    termanfaatkan optimal (~80% target, sisakan ~20% headroom) untuk kecepatan maksimal.
    Jika dijalankan di PC Lokal (bukan Colab) atau mode CPU, mengembalikan {} agar PC
    menyesuaikan otomatis secara aman.
    """
    if not (is_gpu and is_running_in_colab()):
        return {}

    vram = vram_gb if vram_gb is not None else _get_gpu_vram_gb()
    ram = ram_gb if ram_gb is not None else _get_system_ram_gb()
    cpu_cnt = os.cpu_count() or 8

    if vram is not None and vram >= 70.0:
        n_batch = 8192
        n_ubatch = 2048
    elif vram is not None and vram >= 35.0:
        n_batch = 4096
        n_ubatch = 1024
    else:
        n_batch = 2048
        n_ubatch = 512

    max_kwargs: Dict[str, Any] = {
        "n_gpu_layers": -1,
        "offload_kqv": True,
        "flash_attn": True,
        "n_batch": n_batch,
        "n_ubatch": n_ubatch,
        "n_threads": max(4, min(cpu_cnt, 12)),
        "n_threads_batch": max(4, min(cpu_cnt, 16)),
    }
    if ram is not None and ram >= 40.0:
        max_kwargs["use_mmap"] = False
        max_kwargs["use_mlock"] = True
    else:
        max_kwargs["use_mmap"] = True
        max_kwargs["use_mlock"] = False
    return max_kwargs


def build_qwen38_500k_llama_kwargs(
    model_path: str,
    chosen_ctx: int,
    llama_cpp_mod: Any = None,
    kv_cache_override: Optional[str] = None,
    use_gpu: bool = True
) -> Dict[str, Any]:
    """
    Menyusun parameter YaRN RoPE scaling, Flash Attention, dan kuantisasi KV cache
    khusus untuk model Qwen3.8-27B-Uncensored (ShiroHaru-Lyra-Agent) untuk tier
    190K / 262K / 500K / 700K / 1M di GPU.
    Di mode CPU (use_gpu=False), flash_attn dan kuantisasi KV Q4_0 dinonaktifkan
    untuk mencegah crash GGML_ASSERT pada backend ggml-cpu.
    """
    if not is_qwen38_27b_uncensored(model_path):
        return {}

    orig_ctx = get_model_native_context_length(model_path, default=QWEN38_27B_NATIVE_CTX)
    extra: Dict[str, Any] = {}

    if chosen_ctx > orig_ctx:
        yarn_type = getattr(llama_cpp_mod, "LLAMA_ROPE_SCALING_TYPE_YARN", 2)
        extra["rope_scaling_type"] = yarn_type
        extra["yarn_orig_ctx"] = orig_ctx
        extra["rope_freq_scale"] = round(orig_ctx / float(chosen_ctx), 6)
        extra["yarn_ext_factor"] = -1.0
        extra["yarn_attn_factor"] = 1.0
        extra["yarn_beta_fast"] = 32.0
        extra["yarn_beta_slow"] = 1.0

    if use_gpu and chosen_ctx > 65536:
        extra["flash_attn"] = True
        kv_mode = (kv_cache_override or os.environ.get("SHIRO_KV_CACHE_TYPE", "")).strip().lower()
        if not kv_mode:
            vram_gb = _get_gpu_vram_gb()
            if vram_gb is not None and vram_gb >= 70.0:
                if is_running_in_colab():
                    # Colab A100 80GB / H100: native F16 penuh hingga 1M (~75-80% VRAM, 0 penalti dekuantisasi KV)
                    kv_mode = "f16"
                else:
                    # PC Lokal 80GB+: native F16 hingga 700K, Q8_0 untuk 1M
                    kv_mode = "f16" if chosen_ctx <= 700000 else "q8_0"
            elif vram_gb is not None and vram_gb >= 35.0:
                # A100 40GB: native F16 untuk Low (190K), Medium (262K), High (500K); Q8_0 untuk 700K; Q4_0 untuk 1M
                if chosen_ctx <= 500000:
                    kv_mode = "f16"
                elif chosen_ctx <= 700000:
                    kv_mode = "q8_0"
                else:
                    kv_mode = "q4_0"
            elif vram_gb is not None and vram_gb >= 22.0 and chosen_ctx <= 262144:
                kv_mode = "q8_0"
            else:
                kv_mode = "q4_0"

        if kv_mode == "f16":
            kv_val = getattr(llama_cpp_mod, "GGML_TYPE_F16", 1)
            extra["type_k"] = kv_val
            extra["type_v"] = kv_val
        elif kv_mode == "q8_0":
            kv_val = getattr(llama_cpp_mod, "GGML_TYPE_Q8_0", 8)
            extra["type_k"] = kv_val
            extra["type_v"] = kv_val
        elif kv_mode == "q4_0":
            kv_val = getattr(llama_cpp_mod, "GGML_TYPE_Q4_0", 2)
            extra["type_k"] = kv_val
            extra["type_v"] = kv_val

    return extra


def get_optimal_n_threads(gpu_layers: int) -> int:
    """Menentukan jumlah CPU threads optimal agar inferensi CPU/GPU responsif."""
    env_threads = os.environ.get("SHIRO_N_THREADS")
    if env_threads:
        try:
            val = int(env_threads)
            if val > 0:
                return val
        except ValueError:
            pass
    cpu_cnt = os.cpu_count() or 4
    if gpu_layers == 0:
        # Mode CPU: gunakan sebagian besar core (maks 16) agar prefill tidak bottleneck di 4 thread
        return max(4, min(cpu_cnt, 16))
    # Mode GPU: cukup 4-8 thread CPU untuk orkestrasi tokenisasi & prompt prep
    return max(4, min(cpu_cnt // 2 or 4, 8))


# Deteksi GPU CUDA
def get_gpu_layers() -> int:
    gpu_layers_env = os.environ.get("SHIRO_GPU_LAYERS")
    if gpu_layers_env is not None:
        try:
            return int(gpu_layers_env)
        except ValueError:
            pass

    if _has_cuda_gpu():
        n_gpu_env = os.environ.get("N_GPU_LAYERS")
        if n_gpu_env is not None:
            try:
                return int(n_gpu_env)
            except ValueError:
                pass
        return -1  # Offload semua layer ke GPU
    return 0

def get_optimal_model_tokens(model_path: str, tier_override: Optional[str] = None) -> Tuple[int, int]:
    """
    Menentukan batas context window (n_ctx) dan max output tokens secara dinamis
    menyesuaikan ukuran dan arsitektur model yang terdeteksi:
    - ShiroHaru-Lyra-Agent (Qwen3.8-27B-Uncensored GPU): 190K / 262K / 500K / 700K / 1M (fallback aman 32K di mode CPU)
    - Model Besar (27B - 32B+ / A100): n_ctx 16384 s/d 32768, output hingga 16384 token
    - Model Sedang (7B - 14B / VL): n_ctx 8192 s/d 16384, output hingga 8192 token
    - Model Ringan (3B - 4B / T4): n_ctx 4096 s/d 8192, output hingga 2048 token
    """
    if not model_path:
        return (CONTEXT_SIZE, DEFAULT_MAX_TOKENS)

    gpu_layers = get_gpu_layers()
    is_gpu = gpu_layers != 0

    # 0. Khusus Qwen3.8-27B-Uncensored (ShiroHaru-Lyra-Agent):
    # GPU mendukung 5 tingkat konteks & kecepatan berbeda (Low 190K -> Ultra High 1M)
    if is_qwen38_27b_uncensored(model_path):
        explicit_ctx = os.environ.get("SHIRO_QWEN38_27B_CONTEXT_SIZE")
        active_tier = resolve_lyra_tier(
            tier_override if (tier_override and is_valid_lyra_tier(tier_override)) else get_saved_lyra_tier()
        )
        tier_max_out = int(active_tier.get("max_output", QWEN38_27B_MAX_OUTPUT))
        if is_gpu:
            if tier_override and is_valid_lyra_tier(tier_override):
                target_ctx = active_tier["tokens"]
            elif explicit_ctx:
                try:
                    target_ctx = int(explicit_ctx)
                except ValueError:
                    target_ctx = active_tier["tokens"]
            else:
                target_ctx = active_tier["tokens"]
        else:
            if explicit_ctx:
                try:
                    target_ctx = int(explicit_ctx)
                except ValueError:
                    target_ctx = QWEN38_27B_CPU_SAFE_CTX
            else:
                target_ctx = QWEN38_27B_CPU_SAFE_CTX
        max_out = tier_max_out if is_gpu else min(tier_max_out, 8192)
        return (target_ctx, max_out)

    name = os.path.basename(model_path).lower()

    # 1. Model Besar: 27B, 32B, 70B, dll.
    if any(k in name for k in ["27b", "32b", "70b", "34b"]):
        n_ctx = 32768 if (is_gpu or is_running_in_colab()) else 16384
        max_output = 16384 if (is_gpu or is_running_in_colab()) else 8192
        return (n_ctx, max_output)

    # 2. Model Sedang: 7B, 8B, 14B, VL
    elif any(k in name for k in ["7b", "8b", "9b", "12b", "13b", "14b", "vl"]):
        n_ctx = 16384 if is_gpu else 8192
        max_output = 8192 if is_gpu else 4096
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
        is_supported_arch = arch in KNOWN_SUPPORTED_ARCHITECTURES if arch else True

        # Di Google Colab GPU (A100/T4), model 27B / 32B diutamakan sebagai model utama
        in_colab = is_running_in_colab()
        if in_colab:
            if "27b" in basename or "qwen3.8" in basename:
                tier = 0
            elif is_tuned:
                tier = 1
            elif "32b" in basename:
                tier = 2
            elif is_supported_arch:
                tier = 3
            else:
                tier = 4
            return (tier, -size_bytes)

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

    def _init_mm_handler(handler_cls, mm_path: str):
        prefer_gpu = is_running_in_colab() and get_gpu_layers() != 0
        attempts = (
            [{"clip_model_path": mm_path, "verbose": False, "use_gpu": True}] if prefer_gpu else []
        ) + [
            {"clip_model_path": mm_path, "verbose": False},
            {"clip_model_path": mm_path},
        ]
        last_te = None
        for kw in attempts:
            try:
                return handler_cls(**kw)
            except TypeError as te:
                last_te = te
                continue
        if last_te is not None:
            raise last_te

    # 1. Arsitektur Qwen-VL (Qwen2.5-VL-7B, Qwen2.5-VL-32B):
    if "vl" in name or "qwen" in name:
        try:
            from llama_cpp.llama_chat_format import Qwen25VLChatHandler
            if mmproj_file:
                vision_chat_handler = _init_mm_handler(Qwen25VLChatHandler, mmproj_file)
                print(f"👁️ Vision Chat Handler (Qwen25VL) aktif dengan projector: {mmproj_file}")
                return vision_chat_handler
        except Exception as e1:
            print(f"[Vision Notice] Qwen25VLChatHandler fallback: {e1}")

    # 2. Khusus Llava / Model Vision Standar:
    if mmproj_file:
        try:
            from llama_cpp.llama_chat_format import Llava15ChatHandler
            vision_chat_handler = _init_mm_handler(Llava15ChatHandler, mmproj_file)
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

    config["lyra_tier"] = resolve_lyra_tier(config.get("lyra_tier"))["id"]

    # Filter dan susun model_info secara dinamis menggunakan metadata GGUF
    filtered_info = {}
    saved_info = config.get("model_info", {})
    if not isinstance(saved_info, dict):
        saved_info = {}

    for m in detected_models:
        if is_qwen38_27b_uncensored(m):
            size_gb = os.path.getsize(m) / (1024 * 1024 * 1024) if os.path.exists(m) else 0
            existing_entry = saved_info.get(m) if isinstance(saved_info.get(m), dict) else {}
            size_str = existing_entry.get("size") or (f"~{size_gb:.1f} GB" if size_gb > 0 else "GGUF")
            desc_old = str(existing_entry.get("description") or "")
            desc = (
                desc_old
                if (desc_old and "qwen3.8" not in desc_old.lower() and "qwen38" not in desc_old.lower())
                else f"Model Agen Utama: {LYRA_DISPLAY_NAME} ({size_str}) • Mendukung pilihan konteks Low hingga Ultra High (190K–1M token)"
            )
            filtered_info[m] = {
                "name": LYRA_DISPLAY_NAME,
                "size": size_str,
                "quantization": existing_entry.get("quantization") or "Multimodal · Agentic",
                "description": desc,
                "is_lyra": True,
            }
        elif m in saved_info and isinstance(saved_info[m], dict) and saved_info[m].get("name"):
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

def instantiate_llama_model(
    model_path: str,
    lora_version: Optional[int] = None,
    target_ctx_override: Optional[int] = None
) -> Tuple[Any, Any]:
    """
    Instantiate Llama model instance dan vision handler.
    Mengembalikan (llm_instance, vision_handler).
    """
    import llama_cpp
    from llama_cpp import Llama
    gpu_layers = get_gpu_layers()
    vision_handler = init_vision_handler(model_path)

    is_qwen38_unc = is_qwen38_27b_uncensored(model_path)
    is_gpu = gpu_layers != 0
    optimal_ctx, optimal_out = get_optimal_model_tokens(model_path)
    env_ctx = os.environ.get("SHIRO_CONTEXT_SIZE")
    if is_qwen38_unc:
        if is_gpu and target_ctx_override is not None:
            chosen_ctx = int(target_ctx_override)
        elif is_gpu and env_ctx:
            try:
                chosen_ctx = max(int(env_ctx), optimal_ctx)
            except Exception:
                chosen_ctx = optimal_ctx
        else:
            chosen_ctx = optimal_ctx
    elif env_ctx:
        try:
            chosen_ctx = max(int(env_ctx), optimal_ctx)
        except Exception:
            chosen_ctx = optimal_ctx
    else:
        chosen_ctx = optimal_ctx

    n_threads = get_optimal_n_threads(gpu_layers)
    gpu_offload_ok = check_llama_cpp_gpu_offload(llama_cpp)
    if is_gpu and gpu_offload_ok is False:
        safe_print(
            "⚠️ [CRITICAL] GPU CUDA terdeteksi, tetapi llama-cpp-python terkompilasi CPU-ONLY "
            "(llama_supports_gpu_offload=False)! Jalankan ulang Langkah 3 di Colab dengan CMAKE_ARGS=\"-DGGML_CUDA=on\"."
        )
        is_gpu = False
        gpu_layers = 0
        if is_qwen38_unc:
            chosen_ctx = min(chosen_ctx, QWEN38_27B_CPU_SAFE_CTX)
        n_threads = get_optimal_n_threads(gpu_layers)

    debug_llama = os.environ.get("SHIRO_DEBUG_LLAMA", "").strip().lower() in ("1", "true", "yes")
    llama_kwargs = {
        "model_path": model_path,
        "n_ctx": chosen_ctx,
        "n_threads": n_threads,
        "n_gpu_layers": gpu_layers,
        "n_batch": 1024 if is_gpu else 512,
        "n_ubatch": 256,
        "use_mmap": True,
        "use_mlock": False,
        "verbose": debug_llama,
    }
    if is_gpu:
        llama_kwargs["offload_kqv"] = True

    colab_max_kwargs = build_colab_max_gpu_kwargs(is_gpu=is_gpu)
    if colab_max_kwargs:
        llama_kwargs.update(colab_max_kwargs)
        safe_print(
            f"🔥 [Colab MAX-GPU] Mode performa penuh aktif (~80% target VRAM/RAM · "
            f"offload_kqv={llama_kwargs.get('offload_kqv')} · n_batch={llama_kwargs['n_batch']} · "
            f"n_ubatch={llama_kwargs['n_ubatch']} · use_mmap={llama_kwargs.get('use_mmap')} · "
            f"use_mlock={llama_kwargs.get('use_mlock')})"
        )

    orig_ctx = QWEN38_27B_NATIVE_CTX
    f16_val = getattr(llama_cpp, "GGML_TYPE_F16", 1)
    q8_val = getattr(llama_cpp, "GGML_TYPE_Q8_0", 8)
    q4_val = getattr(llama_cpp, "GGML_TYPE_Q4_0", 2)
    if is_qwen38_unc:
        qwen_extra = build_qwen38_500k_llama_kwargs(
            model_path,
            chosen_ctx,
            llama_cpp_mod=llama_cpp,
            use_gpu=is_gpu
        )
        orig_ctx = qwen_extra.get("yarn_orig_ctx", get_model_native_context_length(model_path, default=QWEN38_27B_NATIVE_CTX))
        llama_kwargs.update(qwen_extra)
        tk_init = qwen_extra.get("type_k")
        kv_lbl = "f16" if tk_init == f16_val else ("q8_0" if tk_init == q8_val else ("q4_0" if tk_init == q4_val else "f16"))
        if is_gpu and chosen_ctx > orig_ctx:
            safe_print(
                f"🚀 [{LYRA_DISPLAY_NAME}] Extended Context aktif: {chosen_ctx:,} tokens "
                f"(YaRN dari {orig_ctx:,}, flash_attn={qwen_extra.get('flash_attn', False)}, kv={kv_lbl}, n_batch={llama_kwargs['n_batch']}, n_ubatch={llama_kwargs['n_ubatch']})"
            )
        elif is_gpu:
            safe_print(
                f"🚀 [{LYRA_DISPLAY_NAME}] Context aktif: {chosen_ctx:,} tokens "
                f"(flash_attn={qwen_extra.get('flash_attn', False)}, kv={kv_lbl}, n_batch={llama_kwargs['n_batch']}, n_ubatch={llama_kwargs['n_ubatch']})"
            )
        elif not is_gpu:
            safe_print(
                f"⚠️ [{LYRA_DISPLAY_NAME}] Mode CPU terdeteksi (n_threads={n_threads}): "
                f"Context diamankan ke {chosen_ctx:,} tokens untuk mencegah crash GGML/OOM di CPU. "
                f"Aktifkan GPU (A100/L4/T4) untuk konteks 190K-1M & kecepatan penuh!"
            )

    if vision_handler:
        llama_kwargs["chat_handler"] = vision_handler
    else:
        llama_kwargs["chat_format"] = detect_chat_format(model_path)

    active_lora = find_active_lora_path(version=lora_version)
    if active_lora:
        llama_kwargs["lora_path"] = active_lora
        safe_print(f"🎯 LoRA Adapter Terdeteksi & Dimuat: {os.path.basename(active_lora)}")

    def _try_init_llama(kwargs_dict: Dict[str, Any]):
        optional_tuning_keys = ("n_ubatch", "n_threads_batch", "offload_kqv", "use_mmap", "use_mlock")
        try:
            return Llama(**kwargs_dict)
        except TypeError as te:
            # Fallback jika versi llama-cpp-python lama belum mendukung salah satu parameter tuning/KV
            without_opt = {k: v for k, v in kwargs_dict.items() if k not in optional_tuning_keys}
            if len(without_opt) < len(kwargs_dict):
                try:
                    return Llama(**without_opt)
                except TypeError:
                    pass
            stripped = {
                k: v for k, v in kwargs_dict.items()
                if k not in ("type_k", "type_v", "flash_attn") + optional_tuning_keys
            }
            if len(stripped) < len(kwargs_dict):
                safe_print(f"⚠️ Runtime llama-cpp tidak mendukung parameter KV/flash_attn/tuning ({te}), mencoba tanpa parameter tersebut...")
                return Llama(**stripped)
            raise
        except Exception as exc:
            err_lower = str(exc).lower()
            if kwargs_dict.get("use_mlock") and (
                isinstance(exc, OSError)
                or any(tok in err_lower for tok in ("mlock", "memlock", "memory lock"))
            ):
                safe_print(f"⚠️ Container membatasi use_mlock ({exc}), mencoba ulang dengan use_mlock=False...")
                retry_no_mlock = dict(kwargs_dict)
                retry_no_mlock["use_mlock"] = False
                return Llama(**retry_no_mlock)
            raise

    def _load_with_lora_and_vision_fallback(kwargs_dict: Dict[str, Any]):
        nonlocal vision_handler
        work_kwargs = dict(kwargs_dict)
        try:
            return _try_init_llama(work_kwargs), None
        except Exception as first_err:
            err = first_err
            if "lora_path" in work_kwargs:
                safe_print(f"⚠️ Gagal memuat LoRA ({err}), mencoba tanpa LoRA...")
                work_kwargs.pop("lora_path", None)
                try:
                    return _try_init_llama(work_kwargs), None
                except Exception as e_retry:
                    err = e_retry
            if "chat_handler" in work_kwargs:
                safe_print(f"⚠️ Gagal memuat Vision Handler ({err}), fallback ke teks...")
                work_kwargs.pop("chat_handler", None)
                work_kwargs["chat_format"] = detect_chat_format(model_path)
                try:
                    llm_inst = _try_init_llama(work_kwargs)
                    vision_handler = None
                    return llm_inst, None
                except Exception as e_vis:
                    err = e_vis
            return None, err

    final_kwargs = llama_kwargs
    llm, load_err = _load_with_lora_and_vision_fallback(llama_kwargs)

    if load_err is not None and is_qwen38_unc:
        if llama_kwargs.get("type_k") == f16_val:
            safe_print(f"⚠️ [{LYRA_DISPLAY_NAME}] Gagal memuat {chosen_ctx:,} dengan KV F16 ({load_err}), mencoba KV Q8_0...")
            q8_kwargs = dict(llama_kwargs)
            q8_kwargs["type_k"] = q8_val
            q8_kwargs["type_v"] = q8_val
            llm, load_err = _load_with_lora_and_vision_fallback(q8_kwargs)
            if llm is not None:
                llama_kwargs = q8_kwargs
                final_kwargs = q8_kwargs

        if load_err is not None and llama_kwargs.get("type_k") in (f16_val, q8_val):
            safe_print(f"⚠️ [{LYRA_DISPLAY_NAME}] Gagal memuat {chosen_ctx:,} dengan KV F16/Q8_0 ({load_err}), mencoba KV Q4_0...")
            q4_kwargs = dict(llama_kwargs)
            q4_kwargs["type_k"] = q4_val
            q4_kwargs["type_v"] = q4_val
            llm, load_err = _load_with_lora_and_vision_fallback(q4_kwargs)
            if llm is not None:
                llama_kwargs = q4_kwargs
                final_kwargs = q4_kwargs

        if load_err is not None and chosen_ctx > 32768:
            yarn_keys = (
                "rope_scaling_type", "yarn_orig_ctx", "rope_freq_scale",
                "yarn_ext_factor", "yarn_attn_factor", "yarn_beta_fast", "yarn_beta_slow"
            )
            for step_ctx in [700000, 500000, 262144, 190000, 131072, 65536, 32768]:
                if step_ctx >= chosen_ctx:
                    continue
                safe_print(f"⚠️ [{LYRA_DISPLAY_NAME}] Gagal memuat context {chosen_ctx:,} ({load_err}), fallback ke {step_ctx:,} tokens...")
                step_kwargs = dict(llama_kwargs)
                step_kwargs["n_ctx"] = step_ctx
                if is_gpu and step_kwargs.get("n_batch", 0) > 1024:
                    step_kwargs["n_batch"] = 1024
                    step_kwargs["n_ubatch"] = 256
                if step_ctx <= orig_ctx:
                    for yk in yarn_keys:
                        step_kwargs.pop(yk, None)
                    step_kwargs.update(build_qwen38_500k_llama_kwargs(model_path, step_ctx, llama_cpp_mod=llama_cpp, kv_cache_override="q4_0", use_gpu=is_gpu))
                else:
                    step_kwargs.update(build_qwen38_500k_llama_kwargs(model_path, step_ctx, llama_cpp_mod=llama_cpp, kv_cache_override="q4_0", use_gpu=is_gpu))
                llm, load_err = _load_with_lora_and_vision_fallback(step_kwargs)
                if llm is not None:
                    final_kwargs = step_kwargs
                    break

    if load_err is not None:
        raise load_err

    try:
        tk = final_kwargs.get("type_k")
        llm._shiro_kv_type = "f16" if tk == f16_val else ("q8_0" if tk == q8_val else ("q4_0" if tk == q4_val else "f16"))
        llm._shiro_fast_chatml = bool(
            detect_chat_format(model_path) == "chatml"
            and hasattr(llm, "create_completion")
            and callable(llm.create_completion)
            and type(llm).__module__.startswith("llama_cpp")
        )
        llm._shiro_gpu_offload_verified = gpu_offload_ok
        llm._shiro_colab_max_gpu = bool(colab_max_kwargs)
        llm._shiro_n_batch = int(final_kwargs.get("n_batch", 512))
        llm._shiro_n_ubatch = int(final_kwargs.get("n_ubatch", 256))
    except Exception:
        pass

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

