import os
import sys
import glob
import ctypes

# Auto-configure and pre-load CUDA & cuBLAS runtime libraries on Linux / Google Colab
if sys.platform.startswith("linux"):
    cuda_dirs = [
        "/usr/local/cuda/lib64",
        "/usr/local/cuda-12/lib64",
        "/usr/local/cuda-12.2/lib64",
        "/usr/local/cuda-12.4/lib64",
        "/usr/lib/x86_64-linux-gnu",
        "/usr/lib64"
    ]
    # Search in nvidia pip packages (nvidia-cublas-cu12, nvidia-cuda-runtime-cu12, etc.)
    for p in glob.glob("/usr/local/lib/python*/dist-packages/nvidia/*/lib") + \
             glob.glob("/usr/lib/python*/dist-packages/nvidia/*/lib") + \
             glob.glob(os.path.expanduser("~/.local/lib/python*/dist-packages/nvidia/*/lib")):
        if os.path.isdir(p) and p not in cuda_dirs:
            cuda_dirs.append(p)
    
    # Update LD_LIBRARY_PATH
    valid_dirs = [d for d in cuda_dirs if os.path.isdir(d)]
    if valid_dirs:
        os.environ["LD_LIBRARY_PATH"] = ":".join(valid_dirs) + ":" + os.environ.get("LD_LIBRARY_PATH", "")
        # Pre-load libraries in exact dependency order into global symbol table
        for pat in ["libcudart.so*", "libcublasLt.so*", "libcublas.so*", "libcuda.so*"]:
            for d in valid_dirs:
                for f in sorted(glob.glob(os.path.join(d, pat)), reverse=True):
                    try:
                        ctypes.CDLL(f, mode=ctypes.RTLD_GLOBAL)
                    except Exception:
                        pass

from flask import Flask, render_template, request, jsonify, send_file, Response
try:
    from llama_cpp import Llama
except ImportError:
    Llama = None
from werkzeug.utils import secure_filename
from memory_manager_v2 import AdvancedMemoryManager
import json
import shutil
import random
import base64
import time
import queue
import threading
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import re
from memory_optimization import get_smart_memory_context, compress_old_messages
import web_reader
import typo_helper
from shiro.persona import build_system_prompt, build_vtuber_system_prompt, build_custom_system_prompt

# --- By CONFIG ---
MEMORY_FILE = "ingatan_shiro.json"
WORLD_FILE = "isekai_world.json"
CONTEXT_SIZE = int(os.environ.get("SHIRO_CONTEXT_SIZE", "8192"))
PROFILE_DIR = "profile"
MODEL_DIR = "model"
MODEL_CONFIG_FILE = "model_config.json"
API_KEY_FILE = "api_key.json"
SHIRO_SERIAL_QUESTIONS = 0

def get_active_model_ctx(model=None, fallback=CONTEXT_SIZE):
    """Mengambil kapasitas context window aktual dari model LLM yang sedang aktif"""
    if model is None:
        return fallback
    n = getattr(model, 'n_ctx', None)
    if callable(n):
        try:
            val = int(n())
            if val > 0:
                return val
        except Exception:
            pass
    elif isinstance(n, int) and n > 0:
        return n
    return fallback

# --- Real-Time Neural Execution Pipeline (n8n-style Workflow Visualizer) ---
latest_pipeline_trace = {
    "id": "trace-initial",
    "timestamp": datetime.now().isoformat(),
    "status": "idle",
    "total_duration_ms": 0,
    "user_input": "Halo Kakak!",
    "reply": "Halo Kakak. Ada yang bisa Shiro bantu hari ini?",
    "nodes": [
        {"id": "node_input", "name": "Input Ingestion", "type": "trigger", "icon": "ph-chat-circle-dots", "color": "#3b82f6", "status": "idle", "duration_ms": 0, "summary": "Siap menerima input pesan/gambar", "data_in": {}, "data_out": {}},
        {"id": "node_emotion", "name": "Emotion & Tone Classifier", "type": "analyzer", "icon": "ph-heartbeat", "color": "#ec4899", "status": "idle", "duration_ms": 0, "summary": "Deteksi sentimen & tone afektif", "data_in": {}, "data_out": {}},
        {"id": "node_memory", "name": "Cognitive Memory & RDF Retrieval", "type": "database", "icon": "ph-brain", "color": "#8b5cf6", "status": "idle", "duration_ms": 0, "summary": "Pencarian fakta RDF & exemplars", "data_in": {}, "data_out": {}},
        {"id": "node_prompt", "name": "Dynamic Prompt Synthesizer", "type": "transform", "icon": "ph-brackets-curly", "color": "#06b6d4", "status": "idle", "duration_ms": 0, "summary": "Perakitan sistem prompt & persona", "data_in": {}, "data_out": {}},
        {"id": "node_llm", "name": "Neural Inference Engine", "type": "ai_model", "icon": "ph-cpu", "color": "#f59e0b", "status": "idle", "duration_ms": 0, "summary": "Eksekusi LLM GGUF Qwen", "data_in": {}, "data_out": {}},
        {"id": "node_filter", "name": "Anti-Hallucination & CoT Filter", "type": "filter", "icon": "ph-shield-check", "color": "#10b981", "status": "idle", "duration_ms": 0, "summary": "Pembersihan CoT & validasi", "data_in": {}, "data_out": {}},
        {"id": "node_state", "name": "State & Persistence Sync", "type": "persistence", "icon": "ph-database", "color": "#6366f1", "status": "idle", "duration_ms": 0, "summary": "Update mood & persistensi memori", "data_in": {}, "data_out": {}},
        {"id": "node_output", "name": "Response Delivery Stream", "type": "output", "icon": "ph-paper-plane-right", "color": "#3b82f6", "status": "idle", "duration_ms": 0, "summary": "Penyampaian hasil respon akhir", "data_in": {}, "data_out": {}}
    ]
}
pipeline_subscribers = []
pipeline_subscribers_lock = threading.Lock()

def broadcast_pipeline_trace(trace):
    global latest_pipeline_trace
    latest_pipeline_trace = trace
    with pipeline_subscribers_lock:
        dead_queues = []
        for q in pipeline_subscribers:
            try:
                q.put_nowait(trace)
            except Exception:
                dead_queues.append(q)
        for dq in dead_queues:
            if dq in pipeline_subscribers:
                pipeline_subscribers.remove(dq)

def get_active_api_key():
    """Mengambil API Key aktif saat ini"""
    env_key = os.environ.get("SHIRO_API_KEY", "").strip()
    if env_key:
        return env_key
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                k = data.get("api_key", "").strip()
                if k:
                    return k
        except Exception:
            pass
    return get_or_create_api_key(force_new=True)

def get_all_valid_api_keys():
    """Mengambil himpunan semua API Key yang diizinkan (kunci aktif + riwayat kunci valid)"""
    keys = set()
    env_key = os.environ.get("SHIRO_API_KEY", "").strip()
    if env_key:
        keys.add(env_key)
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    k = data.get("api_key", "").strip()
                    if k:
                        keys.add(k)
                    for item in data.get("valid_keys", []):
                        if item and isinstance(item, str):
                            keys.add(item.strip())
        except Exception:
            pass
    if not keys:
        keys.add(get_or_create_api_key(force_new=True))
    return keys

def get_or_create_api_key(force_new=False):
    """
    Load atau hasilkan API Key baru.
    Jika force_new=True, selalu menghasilkan string API Key baru yang berbeda (random token_hex(16)),
    dan menyimpan key lama ke riwayat valid_keys agar bot/klien sebelumnya tidak langsung error.
    """
    env_key = os.environ.get("SHIRO_API_KEY", "").strip()
    if env_key and not force_new:
        return env_key
    
    drive_dir = os.environ.get("SHIRO_DRIVE_DIR")
    if not drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
        drive_dir = "/content/drive/MyDrive/Shiro_Memory"

    existing_keys = []
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    old_k = data.get("api_key", "").strip()
                    if old_k:
                        existing_keys.append(old_k)
                    for vk in data.get("valid_keys", []):
                        if vk and vk not in existing_keys:
                            existing_keys.append(vk)
        except Exception:
            pass

    if not force_new and existing_keys and not env_key:
        return existing_keys[0]

    import secrets
    new_key = "shiro-sk-" + secrets.token_hex(16)
    
    # Gabungkan riwayat key (simpan maksimal 25 key unik)
    all_valid = [new_key] + [k for k in existing_keys if k != new_key]
    all_valid = all_valid[:25]
    
    try:
        with open(API_KEY_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "api_key": new_key,
                "valid_keys": all_valid,
                "created_at": datetime.now().isoformat()
            }, f, indent=2)
        if drive_dir and os.path.exists(drive_dir):
            try:
                shutil.copy2(API_KEY_FILE, os.path.join(drive_dir, API_KEY_FILE))
            except Exception:
                pass
    except Exception as e:
        print(f"Warning: Could not save API key file: {e}")
    return new_key

def verify_api_key(allow_web_ui=True):
    """
    Verifikasi API Key dari request:
    - Header: Authorization: Bearer <key>
    - Header: X-API-Key: <key>
    - Query Param: ?api_key=<key>
    Mendukung pengecekan terhadap semua kunci aktif & riwayat kunci yang valid.
    """
    valid_keys = get_all_valid_api_keys()
    
    # 1. Header Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token in valid_keys:
            return True
            
    # 2. Header X-API-Key
    x_key = request.headers.get("X-API-Key", "").strip()
    if x_key and x_key in valid_keys:
        return True
        
    # 3. Query Param
    q_key = request.args.get("api_key", "").strip()
    if q_key and q_key in valid_keys:
        return True
        
    # 4. Internal Browser Web UI
    if allow_web_ui:
        sec_fetch = request.headers.get("Sec-Fetch-Site", "")
        referer = request.headers.get("Referer", "")
        host = request.headers.get("Host", "")
        if sec_fetch in ["same-origin", "same-site"]:
            return True
        if referer and host and host in referer:
            return True
        remote_addr = request.remote_addr or ""
        if remote_addr in ["127.0.0.1", "localhost", "::1"] and not auth_header and not x_key:
            return True
            
    return False

# Profile & Model directories
if not os.path.exists(PROFILE_DIR):
    os.makedirs(PROFILE_DIR)
if not os.path.exists(MODEL_DIR):
    os.makedirs(MODEL_DIR)

# Vision Chat Handler, LLM & Memory instances
vision_chat_handler = None
llm = None
memory = AdvancedMemoryManager(MEMORY_FILE, WORLD_FILE)

def is_running_in_colab():
    """Deteksi apakah server berjalan di Google Colab atau komputer lokal"""
    return os.path.exists('/content') or 'COLAB_GPU' in os.environ or 'COLAB_RELEASE_TAG' in os.environ

def get_available_gguf_models():
    """Scan folder model/ & Google Drive secara dinamis untuk file .gguf (termasuk yang dimasukkan secara manual)"""
    models = []
    search_dirs = [MODEL_DIR]
    
    drive_dir = os.environ.get("SHIRO_DRIVE_DIR")
    if not drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
        drive_dir = "/content/drive/MyDrive/Shiro_Memory"
    if drive_dir and os.path.exists(drive_dir):
        drive_model = os.path.join(drive_dir, "model")
        if os.path.exists(drive_model):
            search_dirs.append(drive_model)

    for d in search_dirs:
        if os.path.exists(d):
            for f in sorted(os.listdir(d)):
                if f.endswith('.gguf') and not f.startswith('.'):
                    p = os.path.join(d, f).replace("\\", "/")
                    if p not in models:
                        models.append(p)
    return models

def init_vision_handler(model_path):
    """
    Inisialisasi vision chat handler jika model adalah model vision (seperti Qwen2.5-VL atau Llava)
    dan file mmproj tersedia di folder model/.
    """
    global vision_chat_handler
    vision_chat_handler = None
    
    name = os.path.basename(model_path).lower()
    is_vision = "vl" in name or "vision" in name or "llava" in name
    if not is_vision:
        return None
        
    mmproj_candidates = [
        os.path.join(MODEL_DIR, "mmproj-F16.gguf"),
        os.path.join(MODEL_DIR, "mmproj-BF16.gguf"),
        os.path.join(MODEL_DIR, "mmproj-model-f16.gguf"),
    ]
    if os.path.exists(MODEL_DIR):
        for f in os.listdir(MODEL_DIR):
            if "mmproj" in f.lower() and f.endswith(".gguf"):
                cand = os.path.join(MODEL_DIR, f)
                if cand not in mmproj_candidates:
                    mmproj_candidates.append(cand)
                    
    mmproj_file = None
    for cand in mmproj_candidates:
        if os.path.exists(cand):
            mmproj_file = cand
            break
            
    if not mmproj_file:
        print(f"⚠️ Warning: Model {name} adalah vision model, tapi file mmproj-*.gguf belum ditemukan di {MODEL_DIR}")
        return None
        
    # 1. Khusus Qwen2.5-VL: Gunakan Qwen25VLChatHandler
    if "qwen" in name or "vl" in name:
        try:
            from llama_cpp.llama_chat_format import Qwen25VLChatHandler
            vision_chat_handler = Qwen25VLChatHandler(clip_model_path=mmproj_file)
            print(f"👁️ Vision Chat Handler (Qwen25VL) aktif dengan projector: {mmproj_file}")
            return vision_chat_handler
        except Exception as e1:
            print(f"⚠️ Qwen25VLChatHandler tidak dapat diinisialisasi: {e1}")

    # 2. Khusus Llava: Gunakan Llava15ChatHandler
    if "llava" in name:
        try:
            from llama_cpp.llama_chat_format import Llava15ChatHandler
            vision_chat_handler = Llava15ChatHandler(clip_model_path=mmproj_file)
            print(f"👁️ Vision Chat Handler (Llava15) aktif dengan projector: {mmproj_file}")
            return vision_chat_handler
        except Exception as e2:
            print(f"⚠️ Llava15ChatHandler tidak dapat diinisialisasi: {e2}")

    return None

def find_active_lora_path(version=None):
    """
    Mendeteksi file bobot LoRA adapter (.gguf atau .bin) hasil fine-tuning jika tersedia:
    - Di environment variable SHIRO_LORA_PATH
    - Di folder lora/
    - Di folder model/lora/
    - Di Google Drive /content/drive/MyDrive/Shiro_Memory/lora/
    Jika version disertakan (contoh: 1, 2), mencari spesifik versi tersebut.
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

    # Urutkan berdasarkan nomor versi tertinggi (misal V2 lebih prioritas dibanding V1)
    found_loras = sorted(list(set(found_loras)), key=_get_ver_key, reverse=True)
    return found_loras[0] if found_loras else None

# Model configuration
def load_model_config():
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

    # Gabungkan file .gguf yang baru dimasukkan secara manual ke folder model/
    current_list = list(config.get("available_models", []))
    for m in scanned_models:
        if m not in current_list:
            current_list.append(m)
    config["available_models"] = current_list
    
    # Auto-generate metadata untuk model manual baru & model hasil training (ShiroAI-LLM-V1, V2, dll.)
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
            desc = f"Model Hasil Pelatihan Mandiri: {basename} ({size_str})" if is_trained else f"Model Lokal (Manual): {basename} ({size_str})"
            config["model_info"][m] = {
                "name": basename,
                "size": size_str,
                "quantization": quant,
                "description": desc
            }

    # Penentuan model aktif otomatis:
    in_colab = is_running_in_colab()
    current_model = config.get("current_model", "")
    
    if not in_colab:
        # NON-COLAB (Local PC / Komputer Biasa):
        # Auto-default ke model rendah agar tidak membebani PC
        local_default = config.get("local_default_model", "model/Qwen3-4B-Q4_K_M.gguf")
        
        # Jika model belum dipilih atau model saat ini (misal 32B Colab) tidak tersedia di disk
        if not current_model or not os.path.exists(current_model) or ("32b" in current_model.lower() and not os.path.exists(current_model)):
            if os.path.exists(local_default):
                config["current_model"] = local_default
            elif scanned_models:
                # Cari model dengan ukuran terkecil di folder model/
                sorted_by_size = sorted(scanned_models, key=lambda p: os.path.getsize(p) if os.path.exists(p) else 999999999999)
                config["current_model"] = sorted_by_size[0]
            else:
                config["current_model"] = local_default
    else:
        # GOOGLE COLAB:
        colab_default = "model/Qwen3-32B-Q4_K_M.gguf"
        if not current_model or not os.path.exists(current_model):
            if os.path.exists(colab_default):
                config["current_model"] = colab_default
            elif scanned_models:
                config["current_model"] = scanned_models[0]
            else:
                config["current_model"] = colab_default
                
    return config

def save_model_config(config):
    """Save model config"""
    try:
        with open(MODEL_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving model config: {e}")

GPU_LAYERS = int(os.environ.get("N_GPU_LAYERS", "0"))

def detect_chat_format(model_path):
    """Deteksi chat_format yang tepat berdasarkan nama file model"""
    name = os.path.basename(model_path).lower()
    if "vl" in name or "vision" in name:
        return "chatml"
    elif "llama-3" in name or "llama3" in name or "lumimaid" in name:
        return "llama-3"
    elif "qwen" in name:
        return "chatml"
    elif "phi-3" in name or "phi3" in name:
        return "chatml"
    else:
        return "chatml"  # fallback default

MAX_HISTORY_CONTEXT = 70  # Jumlah pesan yang dimuat ke context
SIMILARITY_THRESHOLD = 0.88  # Threshold untuk deteksi pengulangan (hanya jika sangat mirip)

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

app = Flask(__name__, 
    template_folder='templates',
    static_folder='static',
    static_url_path='/static'
)

# --- UTILITY FUNCTIONS ---
class ConversationAnalyzer:
    """Analisis pola percakapan untuk mencegah halusinasi"""
    
    @staticmethod
    def extract_keywords(text, min_length=3):
        """Ekstrak keyword penting dari teks"""
        # Hapus stopwords bahasa Indonesia umum
        stopwords = {
            'yang', 'ini', 'itu', 'dan', 'di', 'ke', 'dari', 'untuk', 'pada',
            'adalah', 'dengan', 'tidak', 'juga', 'saya', 'kamu', 'nya', 'ya',
            'atau', 'akan', 'sudah', 'bisa', 'ada', 'apa', 'siapa', 'kenapa'
        }
        words = re.findall(r'\b\w+\b', text.lower())
        return [w for w in words if len(w) >= min_length and w not in stopwords]
    
    @staticmethod
    def calculate_similarity(text1, text2):
        """Hitung similaritas antara dua teks"""
        words1 = set(ConversationAnalyzer.extract_keywords(text1))
        words2 = set(ConversationAnalyzer.extract_keywords(text2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    @staticmethod
    def detect_topic_shift(current_msg, previous_msgs, threshold=0.3):
        """Deteksi pergantian topik percakapan"""
        if not previous_msgs:
            return True
        
        recent_msg = previous_msgs[-1]['content']
        similarity = ConversationAnalyzer.calculate_similarity(current_msg, recent_msg)
        
        return similarity < threshold
    
    @staticmethod
    def extract_facts(conversation_history):
        """Ekstrak fakta penting dari riwayat percakapan"""
        facts = {
            'names': set(),
            'locations': set(),
            'events': [],
            'preferences': defaultdict(list)
        }
        
        for msg in conversation_history:
            content = msg['content']
            
            # Ekstrak nama (kapitalisasi)
            names = re.findall(r'\b[A-Z][a-z]+\b', content)
            facts['names'].update(names)
            
            # Ekstrak preferensi (suka/tidak suka)
            if any(word in content.lower() for word in ['suka', 'senang', 'favorit']):
                facts['preferences']['likes'].append(content)
            if any(word in content.lower() for word in ['benci', 'tidak suka', 'gak suka']):
                facts['preferences']['dislikes'].append(content)
        
        return facts

# --- EnhancedMemoryManager dihapus (dead code) ---
# Menggunakan AdvancedMemoryManager dari memory_manager_v2.py


class ResponseGenerator:
    """Generator respons dengan validasi anti-halusinasi"""
    
    # Template respons untuk fallback
    ROMANTIC_RESPONSES = [
        "*mata berkaca-kaca* Benarkah, Kak?! Shiro juga sayang banget sama Kakak! >//<",
        "*memeluk erat* Kakak... Shiro gak mau pisah dari Kakak! Selamanya ya?",
        "*wajah memerah* Kakak bilang apa sih... Tapi Shiro senang denger itu! (//∇//)",
        "*menyembunyikan wajah* Kakak tau gak? Shiro paling senang kalau sama Kakak...",
        "*menggenggam tangan kakak* Janji ya Kak? Jangan pernah tinggalin Shiro!"
    ]
    
    JEALOUS_RESPONSES = [
        "*cemberut* Gak boleh! Kakak cuma boleh perhatiin Shiro aja! (ò_ó)",
        "*menarik lengan kakak* Kakak! Itu siapa?! Shiro kan lebih penting!",
        "*mengembungkan pipi* Hmph! Kakak jahat! Shiro marah nih!",
        "*mata berkaca* Kakak... Jangan lupain Shiro ya... Shiro takut...",
        "*memeluk dari belakang* Gak boleh lirik yang lain! Kakak punya Shiro!"
    ]
    
    HAPPY_RESPONSES = [
        "*loncat-loncat* Yey! Kakak yang terbaik! Shiro sayang Kakak! ♡",
        "*tersenyum lebar* Hehe~ Shiro senang banget! Makasih ya Kak!",
        "*mata berbinar* Wah! Kakak emang paling ngerti Shiro! >//<",
        "*memeluk* Kakak baik deh! Shiro lucky punya Kakak!",
        "*berputar-putar* Senangnya~ Shiro paling suka kalau Kakak begini!"
    ]
    
    SAD_RESPONSES = [
        "*menunduk* Shiro... Shiro sedih... Kakak jahat...",
        "*mata berkaca* Kenapa sih Kakak... Shiro kan cuma mau perhatian...",
        "*mengusap mata* Hiks... Kakak gak sayang Shiro ya?",
        "*memeluk boneka* Shiro kesepian... Kakak kemana aja...",
        "*suara pelan* Kakak... Jangan marah dong... Shiro minta maaf..."
    ]
    
    DEFAULT_RESPONSES = [
        "*memiringkan kepala sambil tersenyum manis* Hehe, Shiro dengerin Kakak kok~ Mau Shiro bantu apa lagi nih, Kak?",
        "*tersenyum hangat* Shiro selalu ada di sini buat Kakak! Mau kita bahas apa lagi sekarang?",
        "*menatap lembut* Iya Kakak sayang? Shiro siap nemenin dan bantuin Kakak!",
        "*mengangguk ceria* Shiro ngerti kok, Kakak! Coba ceritain lebih lanjut ke Shiro ya~",
        "*tersenyum manis dan memeluk lengan Kakak* Shiro senang banget ngobrol sama Kakak! Ada hal seru apa lagi hari ini?"
    ]
    
    @staticmethod
    def detect_emotion_category(text):
        """Deteksi kategori emosi dari input"""
        from shiro.nlp.emotion import detect_emotion_category as _dec
        return _dec(text)
    
    @staticmethod
    def validate_response(response, user_input=""):
        """Validasi respons untuk memastikan tidak halusinasi, tidak bocor proses berpikir (CoT), dan berbahasa Indonesia"""
        from shiro.llm.cleaner import validate_response as _vr
        return _vr(response, user_input)
    
    @staticmethod
    def clean_response(response):
        """Aggressive cleanup dari reasoning/CoT, artifacts & tokens, dengan preservasi baris baru"""
        from shiro.llm.cleaner import clean_response as _cr
        return _cr(response)

    @staticmethod
    def clean_vtuber_response(response, user_input=""):
        """Pembersihan khusus VTuber: wajib tag ekspresi & output bahasa Jepang"""
        from shiro.llm.cleaner import clean_vtuber_response as _cvr
        return _cvr(response, user_input)

def get_shiro_reply(user_input, image_base64=None, document_info=None, return_trace=False, api_version="v1", custom_system_prompt=None, incoming_messages=None):
    t_start_total = time.perf_counter()
    nodes = []
    try:
        active_model_name = os.path.basename(getattr(llm, 'model_path', '')).lower() if hasattr(llm, 'model_path') else ""
        # Pastikan engine multimodal vision benar-benar aktif pada instance model
        has_vision = bool(getattr(llm, 'chat_handler', None) is not None or vision_chat_handler is not None)
        
        # -------------------------------------------------------------
        # NODE 1: Input Ingestion
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        has_image = bool(image_base64)
        raw_chars = len(user_input) if user_input else 0
        img_len = len(image_base64) if image_base64 else 0
        
        # Penanganan Dokumen Lampiran (PDF, Word, Text, CSV, dll.)
        doc_prompt_addon = ""
        has_doc = bool(document_info and document_info.get("text"))
        doc_name = document_info.get("filename", "Dokumen") if has_doc else None
        if has_doc:
            from shiro.document import build_document_prompt
            doc_prompt_addon = build_document_prompt(document_info, user_input)
            print(f"📄 [Document Reader] Melampirkan isi dokumen: {doc_name} ({len(document_info.get('text', ''))} karakter)")

        # Analisis Typo & Singkatan Bahasa Indonesia (Typo-Tolerant Intelligence)
        normalized_input, typo_corrections = typo_helper.normalize_typos(user_input)
        typo_prompt_addon = typo_helper.get_typo_understanding_prompt(typo_corrections) if typo_corrections else ""
        
        # Penanganan khusus jika Kakak mengirim gambar:
        if image_base64:
            if not has_vision:
                # Cek apakah ada GEMINI_API_KEY di environment untuk visual bridge
                gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
                if gemini_key:
                    try:
                        import urllib.request
                        clean_b64 = image_base64.split(",", 1)[1] if "," in image_base64 else image_base64
                        req_data = {
                            "contents": [{
                                "parts": [
                                    {"text": "Deskripsikan secara detail dan padat apa saja yang terlihat di gambar ini dalam 1-2 kalimat bahasa Indonesia untuk konteks visual Shiro."},
                                    {"inline_data": {"mime_type": "image/jpeg", "data": clean_b64}}
                                ]
                            }]
                        }
                        req_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
                        req = urllib.request.Request(req_url, data=json.dumps(req_data).encode('utf-8'), headers={"Content-Type": "application/json"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            resp_json = json.loads(resp.read().decode('utf-8'))
                            vis_desc = resp_json['candidates'][0]['content']['parts'][0]['text'].strip()
                            user_input = f"[Shiro melihat gambar yang diperlihatkan Kakak: {vis_desc}]\n{user_input if user_input.strip() else 'Bagaimana menurutmu, Shiro?'}"
                    except Exception as gemini_err:
                        print(f"Gemini visual bridge: {gemini_err}")
                else:
                    fallback_vision = "*melihat foto yang Kakak perlihatkan* Wah, Kakak memperlihatkan gambar baru ya? Tapi mata visual Shiro (Vision Projector mmproj) belum aktif atau sedang memakai model teks biasa. Pastikan file 'mmproj-F16.gguf' sudah ada di folder model/ dan pilih model Vision **Qwen2.5-VL-7B** di Pengaturan Model ya, Kak! (//∇//)"
                    if return_trace:
                        return fallback_vision, latest_pipeline_trace
                    return fallback_vision

        # -------------------------------------------------------------
        # ONLINE WEB READING & REAL-TIME BROWSING
        # -------------------------------------------------------------
        web_data = None
        web_prompt_addon = ""
        try:
            web_intent = web_reader.detect_web_intent(user_input)
            if web_intent["type"] == "url" and web_intent["urls"]:
                target_url = web_intent["urls"][0]
                print(f"🌐 [Web Reader] Membaca URL: {target_url}")
                fetch_res = web_reader.fetch_url(target_url)
                if fetch_res.get("success"):
                    web_data = {
                        "source": target_url,
                        "title": fetch_res.get("title", "Halaman Web"),
                        "content": fetch_res.get("content", "")
                    }
                    web_prompt_addon = (
                        f"\n\n### INFORMASI HASIL PEMBACAAN DARI HALAMAN WEB NYATA ({target_url}):\n"
                        f"Judul Halaman: {web_data['title']}\n"
                        f"Isi Konten Utama:\n{web_data['content']}\n"
                        "Gunakan informasi di atas untuk menjawab dan menjelaskan kepada Kakak dengan gaya manja, cerdas, dan penuh kasih sayang khas Shiro!\n"
                    )
                elif fetch_res.get("is_cloudflare"):
                    web_prompt_addon = (
                        f"\n\n[Catatan Sistem: Halaman {target_url} terhalang proteksi Cloudflare Turnstile/Bot Challenge. Sampaikan kepada Kakak secara sopan dan manja bahwa situs tersebut diproteksi bot security.]\n"
                    )
            elif web_intent["type"] == "search" and web_intent["query"]:
                search_q = web_intent["query"]
                print(f"🔍 [Web Search] Mencari info online: {search_q}")
                s_res = web_reader.search_wikipedia_online(search_q)
                if s_res.get("success") and s_res.get("results"):
                    snippets = "\n".join([f"- {r['title']}: {r['snippet']} ({r['url']})" for r in s_res["results"]])
                    web_data = {
                        "source": f"Pencarian: {search_q}",
                        "title": f"Hasil Pencarian: {search_q}",
                        "content": snippets
                    }
                    web_prompt_addon = (
                        f"\n\n### INFORMASI HASIL PENCARIAN ONLINE REAL-TIME:\n"
                        f"Topik: {search_q}\n"
                        f"Ringkasan:\n{snippets}\n"
                        "Gunakan fakta di atas untuk menjawab pertanyaan Kakak dengan gaya Shiro!\n"
                    )
        except Exception as e_web:
            print(f"Warning in online web reader: {e_web}")

        t_input_dur = (time.perf_counter() - t0) * 1000
        summary_node1 = f"{raw_chars} Karakter" + (" + Visual Kamera/Foto" if has_image else "")
        if has_doc:
            summary_node1 += f" • Dokumen ({doc_name[:20]})"
        if typo_corrections:
            summary_node1 += f" • Koreksi Typo ({len(typo_corrections)})"
        if web_data:
            summary_node1 += f" • Web ({web_data['title'][:25]})"

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
                "message": user_input,
                "has_image": has_image,
                "image_bytes_approx": img_len,
                "document": doc_name if has_doc else None,
                "web_intent": web_intent if 'web_intent' in locals() else None,
                "typo_corrections": typo_corrections
            },
            "data_out": {
                "processed_text": user_input,
                "normalized_text": normalized_input,
                "source": "web_or_api",
                "api_version": api_version,
                "web_ingested": bool(web_data),
                "doc_ingested": has_doc,
                "timestamp": datetime.now().isoformat()
            }
        })

        # -------------------------------------------------------------
        # NODE 2: Emotion & Tone Classifier
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        user_emotion = ResponseGenerator.detect_emotion_category(normalized_input)
        u_lower = normalized_input.lower()
        matched_words = [w for w in ["sayang", "kangen", "cinta", "rindu", "peluk", "manis", "cium", "cantik", "bagus", "keren", "hebat", "senang", "ayo", "main", "maaf", "sedih", "nangis", "jahat", "benci", "siapa", "cewek", "perempuan", "selingkuh"] if w in u_lower]
        t_emotion_dur = (time.perf_counter() - t0) * 1000
        target_persona_label = "VTuber Waifu (Japanese)" if api_version == "v2" else ("Custom Base Prompt" if api_version == "v3" else "Brocon (Adik Manja)")
        nodes.append({
            "id": "node_emotion",
            "name": "Emotion & Tone Classifier",
            "type": "analyzer",
            "icon": "ph-heartbeat",
            "color": "#ec4899",
            "status": "success",
            "duration_ms": round(t_emotion_dur, 2),
            "summary": f"Kategori: {user_emotion.capitalize()} ({api_version.upper()})",
            "data_in": {
                "text": user_input
            },
            "data_out": {
                "category": user_emotion,
                "matched_keywords": matched_words,
                "target_persona": target_persona_label
            }
        })

        # -------------------------------------------------------------
        # NODE 3: Cognitive Memory & RDF Retrieval
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        if api_version in ["v2", "v3"] and incoming_messages:
            clean_context = []
            for msg in incoming_messages:
                r = msg.get("role")
                c = msg.get("content", "")
                if r in ["user", "assistant"] and msg != incoming_messages[-1]:
                    txt_c = c if isinstance(c, str) else str(c)
                    clean_context.append({"role": r, "content": txt_c})
            clean_context = clean_context[-6:]
            exemplars = []
            relevant_facts = []
            traits = []
            cross_session_addon = ""
            has_cross_session = False
            summary_node3 = f"{api_version.upper()} Context ({len(clean_context)} Turn)"
        else:
            recent_context = get_smart_memory_context(memory, limit=8)
            clean_context = []
            for msg in recent_context:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "assistant":
                    content = ResponseGenerator.clean_response(content)
                    if not ResponseGenerator.validate_response(content, ""):
                        continue
                clean_context.append({
                    "role": role,
                    "content": content
                })

            # Sanitasi konteks visual jika Kakak mengirim gambar baru:
            if has_image:
                sanitized_context = []
                for msg in clean_context:
                    m_copy = dict(msg)
                    if m_copy.get("role") == "user" and ("[gambar" in m_copy.get("content", "").lower() or "[visual" in m_copy.get("content", "").lower()):
                        m_copy["content"] = "[Kakak memperlihatkan gambar visual pada obrolan sebelumnya]"
                    elif m_copy.get("role") == "assistant":
                        txt = m_copy.get("content", "")
                        if any(w in txt.lower() for w in ["memandang gambar", "poster tersebut", "gambar visual ini", "poster"]):
                            m_copy["content"] = "*tersenyum manis* Shiro sudah melihat gambar Kakak yang sebelumnya. Nah, sekarang gambar baru apa yang Kakak bawa ini?"
                    sanitized_context.append(m_copy)
                clean_context = sanitized_context

            facts = memory.knowledge_base.get("facts", [])
            relevant_facts = [f for f in facts if f.get("confidence", 0) >= 0.8][:5]
            traits = memory.user_profile.get("personality_traits", [])

            if has_image:
                exemplars = [ex for ex in memory.get_relevant_exemplars(user_input, max_count=2) 
                             if not ex.get("image") and not any(k in ex.get("user", "").lower() for k in ["[gambar", "kamera", "visual", "foto"])]
            else:
                exemplars = memory.get_relevant_exemplars(user_input, max_count=2)
            
            cross_session_addon = memory.get_cross_session_context(normalized_input)
            has_cross_session = bool(cross_session_addon)
            summary_node3 = f"{len(relevant_facts)} Fakta RDF • {len(exemplars)} Exemplars"
            if has_cross_session:
                summary_node3 += " • Cross-Session Memory"
            summary_node3 += " • Cross-Session Memory"

        t_mem_dur = (time.perf_counter() - t0) * 1000
        nodes.append({
            "id": "node_memory",
            "name": "Cognitive Memory & RDF Retrieval",
            "type": "database",
            "icon": "ph-brain",
            "color": "#8b5cf6",
            "status": "success",
            "duration_ms": round(t_mem_dur, 2),
            "summary": summary_node3,
            "data_in": {
                "query": user_input,
                "context_limit": 8
            },
            "data_out": {
                "relevant_facts": relevant_facts,
                "user_traits": traits,
                "exemplars": exemplars,
                "cross_session_recalled": has_cross_session,
                "active_history_turns": len(clean_context)
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

        facts_summary = ""
        if traits:
            facts_summary = f"\nKARAKTERISTIK KAKAK: {', '.join(traits)}\n"

        exemplar_prompt = ""
        if exemplars:
            exemplar_prompt = "\nCONTOH DIALOG SEBELUMNYA (PELAJARI & TIRU GAYA BICARA INI):\n"
            for ex in exemplars:
                exemplar_prompt += f"Kakak: \"{ex.get('user')}\"\nShiro: \"{ex.get('assistant')}\"\n"

        if api_version == "v2":
            # VTuber Persona Mode (100% Japanese with [Tag])
            client_sys = custom_system_prompt or ""
            if not client_sys and incoming_messages:
                for m in incoming_messages:
                    if m.get("role") == "system":
                        client_sys = m.get("content", "")
                        break
            system_prompt = build_vtuber_system_prompt(
                owner_name="Renku",
                custom_instruction=client_sys
            )
            msgs = [{"role": "system", "content": system_prompt}]
            msgs.extend(clean_context)
            vtuber_user_prompt = f"{user_input}\n(Awali dengan [Tag] emosi yang tepat dan jawab dalam Bahasa Indonesia khas Shiro)"
            if image_base64 and has_vision:
                img_url = image_base64 if image_base64.startswith("data:") else f"data:image/jpeg;base64,{image_base64}"
                msgs.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"[VTuber Vision Screen / Camera]: {vtuber_user_prompt}"},
                        {"type": "image_url", "image_url": {"url": img_url}}
                    ]
                })
            else:
                msgs.append({"role": "user", "content": vtuber_user_prompt})

        elif api_version == "v3":
            # Custom Base Prompt Mode
            sys_text = custom_system_prompt or ""
            if not sys_text and incoming_messages:
                for m in incoming_messages:
                    if m.get("role") == "system":
                        sys_text = m.get("content", "")
                        break
            system_prompt = build_custom_system_prompt(sys_text)
            msgs = [{"role": "system", "content": system_prompt}]
            msgs.extend(clean_context)
            if image_base64 and has_vision:
                img_url = image_base64 if image_base64.startswith("data:") else f"data:image/jpeg;base64,{image_base64}"
                msgs.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_input},
                        {"type": "image_url", "image_url": {"url": img_url}}
                    ]
                })
            else:
                msgs.append({"role": "user", "content": user_input})

        else:
            # v1 Default (Indonesian Shiro Persona)
            system_prompt = build_system_prompt(
                home_location=memory.world.get('locations', {}).get('home', 'Pondok Kayu'),
                conversation_summary=conversation_summary,
                facts_summary=facts_summary,
                exemplar_prompt=exemplar_prompt,
                web_prompt_addon=web_prompt_addon,
                typo_prompt_addon=typo_prompt_addon,
                document_prompt_addon=doc_prompt_addon,
                cross_session_addon=cross_session_addon
            )
            msgs = [{"role": "system", "content": system_prompt}]
            msgs.extend(clean_context)

            if image_base64 and has_vision:
                img_url = image_base64 if image_base64.startswith("data:") else f"data:image/jpeg;base64,{image_base64}"
                custom_q = user_input.strip() if user_input.strip() and not user_input.startswith("Kakak memperlihatkan gambar") else ""
                if custom_q:
                    prompt_text = (
                        f"[ANALISIS VISUAL GAMBAR BARU]: Kakak memperlihatkan gambar baru ini sambil bertanya: \"{custom_q}\".\n"
                        f"TUGAS SHIRO: Amati dengan cermat apa saja objek nyata, warna, tulisan, dan detail visual di dalam GAMBAR TERBARU INI secara langsung. "
                        f"Jawab pertanyaan Kakak secara spesifik sesuai apa yang benar-benar ada di gambar baru ini (jangan pernah mengulang atau mengaitkan dengan gambar dari obrolan sebelumnya)!"
                    )
                else:
                    prompt_text = (
                        "[ANALISIS VISUAL GAMBAR BARU]: Kakak memperlihatkan gambar baru ini kepadamu, Shiro!\n"
                        "TUGAS SHIRO: Amati dengan cermat apa saja objek nyata, warna, tulisan, orang/benda, dan suasana yang terlihat di dalam GAMBAR BARU INI secara langsung. "
                        "Jelaskan apa yang kamu lihat sekarang secara segar, unik, dan mendetail dengan gaya bicaramu yang manja, cerdas, dan hangat khas Shiro (jangan pernah mengulang deskripsi gambar sebelumnya)!"
                    )
                msgs.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": img_url}}
                    ]
                })
            else:
                msgs.append({"role": "user", "content": user_input})

        # -------------------------------------------------------------
        # SMART TOKEN BUDGET GUARD & ADAPTIVE TRUNCATOR
        # Menjamin prompt + output tokens selalu muat dalam context window model
        # -------------------------------------------------------------
        from shiro.memory.optimization import calculate_messages_tokens, trim_text_to_token_budget
        
        active_ctx = get_active_model_ctx(llm, CONTEXT_SIZE)
        max_output_tokens = 180 if api_version == "v2" else 450
        safety_headroom = 150
        max_allowed_prompt = max(1000, active_ctx - max_output_tokens - safety_headroom)
        
        user_turn_msg = msgs[-1]
        current_prompt_tokens = calculate_messages_tokens(msgs, llm)
        if current_prompt_tokens > max_allowed_prompt:
            print(f"⚠️ [Token Budget Guard] Total token ({current_prompt_tokens}) melebihi batas aman ({max_allowed_prompt}/{active_ctx}). Melakukan adaptasi cerdas...")
            
            # 1. Pangkas riwayat percakapan lama terlebih dahulu (prioritas utama adalah dokumen & input Kakak)
            while clean_context and calculate_messages_tokens([{"role": "system", "content": system_prompt}] + clean_context + [user_turn_msg], llm) > max_allowed_prompt:
                clean_context.pop(0)

            # 2. Jika masih melebihi batas dan terdapat lampiran dokumen
            if has_doc and document_info and calculate_messages_tokens([{"role": "system", "content": system_prompt}] + clean_context + [user_turn_msg], llm) > max_allowed_prompt:
                base_system = build_system_prompt(
                    home_location=memory.world.get('locations', {}).get('home', 'Pondok Kayu'),
                    conversation_summary=conversation_summary,
                    facts_summary=facts_summary,
                    exemplar_prompt=exemplar_prompt,
                    web_prompt_addon=web_prompt_addon,
                    typo_prompt_addon=typo_prompt_addon,
                    document_prompt_addon="",
                    cross_session_addon=cross_session_addon
                )
                used_tokens = calculate_messages_tokens([{"role": "system", "content": base_system}] + clean_context + [user_turn_msg], llm)
                remaining_doc_tokens = max(300, max_allowed_prompt - used_tokens - 100)
                
                doc_full_text = document_info.get("text", "")
                trimmed_text = trim_text_to_token_budget(
                    doc_full_text,
                    remaining_doc_tokens,
                    suffix="\n\n... [Sisa teks dokumen dipotong otomatis agar pas dengan kapasitas memori AI] ..."
                )
                if len(trimmed_text) < len(doc_full_text):
                    print(f"✂️ [Adaptive Truncator] Memangkas teks dokumen dari {len(doc_full_text)} -> {len(trimmed_text)} karakter (~{remaining_doc_tokens} tokens).")
                    trimmed_doc_info = dict(document_info)
                    trimmed_doc_info["text"] = trimmed_text
                    doc_prompt_addon = build_document_prompt(trimmed_doc_info, user_input)
                    system_prompt = build_system_prompt(
                        home_location=memory.world.get('locations', {}).get('home', 'Pondok Kayu'),
                        conversation_summary=conversation_summary,
                        facts_summary=facts_summary,
                        exemplar_prompt=exemplar_prompt,
                        web_prompt_addon=web_prompt_addon,
                        typo_prompt_addon=typo_prompt_addon,
                        document_prompt_addon=doc_prompt_addon,
                        cross_session_addon=cross_session_addon
                    )

            # Susun ulang daftar pesan akhir
            msgs = [{"role": "system", "content": system_prompt}]
            msgs.extend(clean_context)
            msgs.append(user_turn_msg)
            final_tokens = calculate_messages_tokens(msgs, llm)
            print(f"✓ [Token Budget Guard] Prompt siap: {final_tokens} tokens (Batas Aman: {max_allowed_prompt}/{active_ctx})")

        t_prompt_dur = (time.perf_counter() - t0) * 1000
        constraints_list = ["100% Native Japanese with [Tag]", "VoiceVox Speech Opt"] if api_version == "v2" else (["Custom System Prompt"] if api_version == "v3" else ["100% Bahasa Indonesia", "Anti-CoT", "Anti-Hallucination"])
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
                "persona": target_persona_label,
                "api_version": api_version,
                "rdf_facts_injected": len(relevant_facts),
                "exemplars_injected": len(exemplars)
            },
            "data_out": {
                "system_prompt_chars": len(system_prompt),
                "total_messages": len(msgs),
                "constraints": constraints_list
            }
        })

        # -------------------------------------------------------------
        # NODE 5: Neural Inference Engine (LLM)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        gen_params = {
            "temperature": 0.72 if has_image else (0.70 if api_version == "v2" else 0.65),
            "repeat_penalty": 1.25 if has_image else 1.2,
            "frequency_penalty": 0.5 if has_image else 0.3,
            "presence_penalty": 0.3 if has_image else 0.0,
            "top_p": 0.92,
            "top_k": 40,
            "max_tokens": 180 if api_version == "v2" else 450,
            "stop": ["User:", "Kakak:", "Shiro:", "assistant:", "\n\n\n", "###", 
                     "Note:", "<|im_end|>", "<|im_start|>", "<|eot_id|>", 
                     "<|end|>", "<|end_of_text|>", "Okay, let me", "The user is"]
        }

        try:
            res = llm.create_chat_completion(
                messages=msgs,
                **gen_params
            )
        except Exception as inf_err:
            err_str = str(inf_err).lower()
            if "exceed" in err_str and ("context" in err_str or "token" in err_str or "window" in err_str):
                print(f"⚠️ [Context Guard] Exception exceed context window tertangkap: {inf_err}. Menjalankan pemangkasan darurat...")
                emergency_msgs = [{"role": "system", "content": system_prompt[:1200] + "\n[Catatan: Ringkas jawaban secara padat.]"}]
                if has_doc and document_info:
                    doc_snip = document_info.get("text", "")[:2500]
                    emergency_msgs.append({"role": "user", "content": f"[Dokumen {doc_name}]:\n{doc_snip}\n\n{user_input}"})
                else:
                    emergency_msgs.append(user_turn_msg)
                res = llm.create_chat_completion(
                    messages=emergency_msgs,
                    **gen_params
                )
            else:
                raise inf_err

        raw_reply = res['choices'][0]['message']['content'].strip()
        t_llm_dur = (time.perf_counter() - t0) * 1000
        nodes.append({
            "id": "node_llm",
            "name": "Neural Inference Engine",
            "type": "ai_model",
            "icon": "ph-cpu",
            "color": "#f59e0b",
            "status": "success",
            "duration_ms": round(t_llm_dur, 2),
            "summary": f"{round(t_llm_dur)}ms • {active_model_name or 'Qwen'}",
            "data_in": {
                "model": active_model_name or getattr(llm, 'model_path', 'LLM'),
                "parameters": gen_params
            },
            "data_out": {
                "raw_response": raw_reply,
                "finish_reason": res['choices'][0].get('finish_reason', 'stop'),
                "usage": res.get("usage", {})
            }
        })

        # -------------------------------------------------------------
        # NODE 6: Anti-Hallucination & Neural Filter
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        had_think = ("<think>" in raw_reply.lower() or "</think>" in raw_reply.lower())
        had_cot = any(x in raw_reply.lower() for x in ["okay, let me", "let me break this down", "possible responses", "let's craft"])

        if api_version == "v2":
            cleaned_reply = ResponseGenerator.clean_vtuber_response(raw_reply, user_input)
            is_valid = True
            is_fallback = False
        elif api_version == "v3":
            cleaned_reply = ResponseGenerator.clean_response(raw_reply)
            is_valid = True
            is_fallback = False
        else:
            cleaned_reply = ResponseGenerator.clean_response(raw_reply)
            is_valid = ResponseGenerator.validate_response(cleaned_reply, user_input)
            is_fallback = False

            if not is_valid:
                is_fallback = True
                if user_emotion == "romantic":
                    cleaned_reply = random.choice(ResponseGenerator.ROMANTIC_RESPONSES)
                elif user_emotion == "jealous":
                    cleaned_reply = random.choice(ResponseGenerator.JEALOUS_RESPONSES)
                elif user_emotion == "happy":
                    cleaned_reply = random.choice(ResponseGenerator.HAPPY_RESPONSES)
                elif user_emotion == "sad":
                    cleaned_reply = random.choice(ResponseGenerator.SAD_RESPONSES)
                else:
                    cleaned_reply = random.choice(ResponseGenerator.DEFAULT_RESPONSES)

        # Check untuk duplicate responses (mencegah repetisi)
        if memory.short_term_history:
            last_responses = [m['content'] for m in memory.short_term_history[-3:] if m['role'] == 'assistant']
            for last_resp in last_responses:
                similarity = ConversationAnalyzer.calculate_similarity(cleaned_reply, last_resp)
                is_repetitive = (similarity >= SIMILARITY_THRESHOLD or cleaned_reply.strip().lower() == last_resp.strip().lower())
                if has_image and "poster tersebut" in cleaned_reply.lower() and "poster tersebut" in last_resp.lower():
                    is_repetitive = True

                if is_repetitive:
                    print(f"⚠️ [Anti-Repetition] Respons terdeteksi duplikat/mirip ({similarity:.2f}) dengan giliran sebelumnya! Mengganti dengan respon segar...")
                    if api_version == "v2":
                        from shiro.llm.cleaner import VTUBER_JAPANESE_FALLBACKS
                        pool = VTUBER_JAPANESE_FALLBACKS.get(user_emotion, VTUBER_JAPANESE_FALLBACKS["default"])
                        cleaned_reply = random.choice(pool)
                    elif has_image:
                        visual_fallbacks = [
                            "*memperhatikan gambar baru dengan seksama* Wah, gambar yang ini beda dari sebelumnya ya Kak! Shiro melihat visual baru ini... coba Kakak kasih tahu Shiro, bagian mana dari gambar ini yang paling Kakak suka?",
                            "*tersenyum manis sambil mengamati gambar* Hehe, Kakak bawa gambar baru lagi! Menarik banget gambarnya, Kak! Mau Shiro jelaskan detail apa dari gambar ini?",
                            "*menatap antusias* Wah, ini gambar yang baru ya Kak? Tampilannya unik dan beda dari yang tadi! Shiro siap nemenin Kakak bahas gambar ini~"
                        ]
                        cleaned_reply = random.choice(visual_fallbacks)
                    else:
                        emotion = ResponseGenerator.detect_emotion_category(user_input)
                        if emotion == "romantic":
                            cleaned_reply = random.choice(ResponseGenerator.ROMANTIC_RESPONSES)
                        elif emotion == "jealous":
                            cleaned_reply = random.choice(ResponseGenerator.JEALOUS_RESPONSES)
                        elif emotion == "happy":
                            cleaned_reply = random.choice(ResponseGenerator.HAPPY_RESPONSES)
                        elif emotion == "sad":
                            cleaned_reply = random.choice(ResponseGenerator.SAD_RESPONSES)
                        else:
                            cleaned_reply = random.choice(ResponseGenerator.DEFAULT_RESPONSES)
                    break

        t_filter_dur = (time.perf_counter() - t0) * 1000
        nodes.append({
            "id": "node_filter",
            "name": "Anti-Hallucination & CoT Filter",
            "type": "filter",
            "icon": "ph-shield-check",
            "color": "#10b981",
            "status": "success",
            "duration_ms": round(t_filter_dur, 2),
            "summary": "100% ID Clean" if not is_fallback else "Fallback Safe",
            "data_in": {
                "raw_text": raw_reply
            },
            "data_out": {
                "think_tags_detected": had_think,
                "cot_reasoning_stripped": had_cot,
                "validation_passed": is_valid,
                "fallback_triggered": is_fallback,
                "cleaned_output": cleaned_reply
            }
        })

        # -------------------------------------------------------------
        # NODE 7: State & Persistence Sync (Termasuk Pembelajaran Web)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        current_mood = memory.agent_persona.get("current_mood", "Neutral")
        emo_state = memory.agent_persona.get("emotional_state", {})

        # Integrasikan pengetahuan web ke memori RDF & training_data permanen
        if web_data:
            try:
                web_reader.integrate_web_knowledge(
                    memory_manager=memory,
                    user_input=user_input,
                    assistant_reply=cleaned_reply,
                    web_title=web_data["title"],
                    url_or_query=web_data["source"],
                    web_content=web_data["content"]
                )
                print(f"🧠 [Online Learning] Pengetahuan web berhasil diintegrasikan ke memori & training_data: {web_data['title']}")
            except Exception as e_web_save:
                print(f"Warning integrating web knowledge: {e_web_save}")

        t_state_dur = (time.perf_counter() - t0) * 1000
        state_summary = f"Mood: {current_mood}"
        if web_data:
            state_summary += " • Web Data Learned"

        nodes.append({
            "id": "node_state",
            "name": "State & Persistence Sync",
            "type": "persistence",
            "icon": "ph-database",
            "color": "#6366f1",
            "status": "success",
            "duration_ms": round(t_state_dur, 2),
            "summary": state_summary,
            "data_in": {
                "reply": cleaned_reply,
                "web_learned": bool(web_data)
            },
            "data_out": {
                "current_mood": current_mood,
                "emotional_state": emo_state,
                "total_turns": memory.system_metadata.get("total_turns", 0),
                "web_data_integrated": bool(web_data)
            }
        })

        # -------------------------------------------------------------
        # NODE 8: Response Delivery Stream
        # -------------------------------------------------------------
        t_total_dur = (time.perf_counter() - t_start_total) * 1000
        nodes.append({
            "id": "node_output",
            "name": "Response Delivery Stream",
            "type": "output",
            "icon": "ph-paper-plane-right",
            "color": "#3b82f6",
            "status": "success",
            "duration_ms": 0.5,
            "summary": f"{round(t_total_dur)}ms Latency",
            "data_in": {
                "chars_count": len(cleaned_reply)
            },
            "data_out": {
                "final_reply": cleaned_reply,
                "total_duration_ms": round(t_total_dur, 2)
            }
        })

        trace = {
            "id": f"trace-{int(time.time()*1000)}",
            "timestamp": datetime.now().isoformat(),
            "status": "completed",
            "total_duration_ms": round(t_total_dur, 2),
            "user_input": user_input,
            "reply": cleaned_reply,
            "nodes": nodes
        }
        broadcast_pipeline_trace(trace)

        if return_trace:
            return cleaned_reply, trace
        return cleaned_reply

    except Exception as e:
        print(f"Error generating response: {e}")
        if api_version == "v2":
            err_msg = '[Sad] "ごめんなさい、ちょっとエラーが出ちゃったみたい…！"'
        elif api_version == "v3":
            err_msg = f"Error processing request: {str(e)[:50]}"
        else:
            err_msg = f"*bingung* Kakak... Shiro tidak mengerti... (Error: {str(e)[:50]})"
        err_trace = {
            "id": f"trace-err-{int(time.time()*1000)}",
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "total_duration_ms": round((time.perf_counter() - t_start_total) * 1000, 2),
            "user_input": user_input,
            "reply": err_msg,
            "error": str(e),
            "nodes": nodes
        }
        broadcast_pipeline_trace(err_trace)
        if return_trace:
            return err_msg, err_trace
        return err_msg

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pipeline')
def pipeline_page():
    """Halaman visualisasi real-time alur kerja pemikiran AI (n8n-style workflow canvas)"""
    return render_template('pipeline.html')

@app.route('/api/pipeline/latest', methods=['GET'])
def get_latest_pipeline():
    """Mengambil trace eksekusi neural pipeline terkini"""
    return jsonify(latest_pipeline_trace)

@app.route('/api/pipeline/events')
def pipeline_events():
    """Server-Sent Events (SSE) stream untuk telemetry alur AI real-time"""
    def event_stream():
        q = queue.Queue(maxsize=20)
        with pipeline_subscribers_lock:
            pipeline_subscribers.append(q)
        # Snapshot awal
        yield f"data: {json.dumps(latest_pipeline_trace)}\n\n"
        try:
            while True:
                try:
                    tr = q.get(timeout=20)
                    yield f"data: {json.dumps(tr)}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        except GeneratorExit:
            with pipeline_subscribers_lock:
                if q in pipeline_subscribers:
                    pipeline_subscribers.remove(q)

    return Response(event_stream(), mimetype="text/event-stream")

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

@app.route('/api/history', methods=['GET'])
def get_history():
    return jsonify({
        "history": [_format_message_for_api(m) for m in memory.short_term_history],
        "count": len(memory.short_term_history),
        "metadata": memory.system_metadata,
        "user_profile": memory.user_profile,
        "agent_persona": memory.agent_persona,
        "topics": memory.system_metadata.get("topics_discussed", [])
    })

@app.route('/api/memory-count', methods=['GET'])
def get_memory_count():
    return jsonify({
        "count": memory.system_metadata["total_turns"],
        "facts_count": len(memory.knowledge_base.get("facts", [])),
        "topics_count": len(memory.system_metadata.get("topics_discussed", [])),
        "metadata": memory.system_metadata
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    user_msgs = len([m for m in memory.short_term_history if m['role'] == 'user'])
    assistant_msgs = len([m for m in memory.short_term_history if m['role'] == 'assistant'])
    
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

# System Trigger Pesan Jika diam lebih dari 3 pertanyaan berturut-turut, untuk menjaga interaksi tetap hidup
@app.route('/api/trigger', methods=['POST'])
def auto_trigger():
    global SHIRO_SERIAL_QUESTIONS
    try:
        with memory.lock:
            # Batasi hanya 1 inisiatif saja, tidak boleh spam beruntun sampai Kakak membalas
            if SHIRO_SERIAL_QUESTIONS >= 1:
                return jsonify({"status": "idle", "reason": "already_initiated"})

            trigger_prompt = (
                "Kakak sudah lama tidak bersuara. Sebagai Shiro (adik perempuan), berikan SATU sapaan santai atau perhatian kecil "
                "(misalnya: tanya Kakak lagi sibuk apa, celetukan manja, atau sapaan hangat). "
                "ATURAN: Maksimal 1-2 kalimat pendek, sudut pandang orang pertama 'Shiro/aku', "
                "JANGAN gunakan narasi novel orang ketiga, JANGAN mengulang kalimat sebelumnya."
            )
            
            reply = get_shiro_reply(trigger_prompt)
            
            memory.add_message("assistant", reply)
            compress_old_messages(memory, keep_count=15)
            memory.save_memory()
            SHIRO_SERIAL_QUESTIONS += 1
            
            return jsonify({
                "reply": reply,
                "count": memory.system_metadata["total_turns"],
                "mood": memory.agent_persona.get("current_mood", "Neutral")
            })
    except Exception as e:
        print(f"Trigger Error: {e}")
        return jsonify({"status": "error"}), 500
    

@app.route('/api/chat', methods=['POST'])
def chat():
    global SHIRO_SERIAL_QUESTIONS # Sytem Srial Questions
    # Verifikasi API Key (izinkan browser Web UI internal, wajibkan key untuk external request)
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized: Invalid or missing API Key. Use 'Authorization: Bearer <key>' or 'X-API-Key: <key>'"}), 401
        
    try:
        data = request.json or {}
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
            
        if not user_message and image_base64:
            user_message = "Kakak memperlihatkan gambar ini kepadamu, Shiro."
        elif not user_message and document_info:
            user_message = f"Shiro, tolong baca dokumen '{document_name}' ini dan jelaskan ya!"
        
        if len(user_message) > 6000:
            return jsonify({
                "error": "Message too long (Maksimal 6000 karakter)",
                "reply": "*bingung* Kakak ngomong panjang banget lebih dari 6000 karakter... Shiro pusing! Singkat sedikit ya, Kak!"
            }), 400
        
        saved_img_rel = None
        if image_base64:
            try:
                import uuid
                v_dir = os.path.join("training_data", "vision", "images")
                os.makedirs(v_dir, exist_ok=True)
                fn = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
                fp = os.path.join(v_dir, fn)
                raw = image_base64.split(",", 1)[1] if "," in image_base64 else image_base64
                with open(fp, "wb") as f_out:
                    f_out.write(base64.b64decode(raw))
                saved_img_rel = os.path.join("images", fn).replace("\\", "/")
            except Exception as e_img:
                print(f"Warning saving vision image: {e_img}")

        with memory.lock:
            SHIRO_SERIAL_QUESTIONS = 0  # Reset counter on user input
            
            # Detect emotion dari user message
            user_emotion = ResponseGenerator.detect_emotion_category(user_message)
            
            # Add user message to memory with document and image metadata
            log_msg = user_message
            if image_base64:
                log_msg = f"[Gambar/Kamera Dikirim] {user_message}"
            elif document_name:
                log_msg = f"[Dokumen: {document_name}] {user_message}"

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
            
            # Generate reply
            reply, trace = get_shiro_reply(
                user_message,
                image_base64=image_base64,
                document_info=document_info,
                return_trace=True
            )
            
            # Add assistant message to memory
            memory.add_message("assistant", reply)
            
            # Update AI emotional state berdasarkan response
            memory.update_emotional_state_from_response(reply)
            memory.update_mood_from_emotions()
            
            # Simpan interaksi berkualitas untuk in-context few-shot learning
            # (hindari menyimpan jika respon mengandung pengulangan poster lama)
            if not image_base64 or "poster tersebut" not in reply.lower():
                memory.record_learned_pattern(log_msg, reply, image_path=saved_img_rel)
            
            # Compress & save memory tiap turn
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
        import traceback
        traceback.print_exc()
        return jsonify({
            "reply": "*menatap kakak* Shiro bingung... Kakak bisa ulangi?",
            "error": "Processing error"
        }), 500

@app.route('/api/upload/document', methods=['POST'])
def upload_document():
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "Tidak ada file yang dipilih."}), 400
        
        f = request.files['file']
        if f.filename == '':
            return jsonify({"success": False, "error": "Nama file kosong."}), 400

        from shiro.document import extract_text_from_file, SUPPORTED_EXTENSIONS
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return jsonify({
                "success": False,
                "error": f"Format '{ext}' belum didukung. Format didukung: PDF, Word (docx), Text, Markdown, CSV, JSON, Python, dll."
            }), 400

        upload_dir = os.path.join("data", "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        save_path = os.path.join(upload_dir, f.filename)
        f.save(save_path)

        res = extract_text_from_file(save_path, filename=f.filename)
        if not res["success"]:
            return jsonify(res), 400

        preview = res["text"][:200] + ("..." if len(res["text"]) > 200 else "")
        res["preview"] = preview
        res["url"] = f"/api/files/{f.filename}"
        res["filename"] = f.filename
        return jsonify(res)
    except Exception as e:
        print(f"Error in upload_document: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/files/<path:filename>', methods=['GET'])
def get_uploaded_file(filename):
    """Serve uploaded document or file from data/uploads/"""
    upload_dir = os.path.abspath(os.path.join("data", "uploads"))
    target = os.path.abspath(os.path.join(upload_dir, filename))
    if not target.startswith(upload_dir) or not os.path.exists(target):
        return jsonify({"error": "File tidak ditemukan"}), 404
    
    as_attachment = request.args.get('download', '0') == '1'
    return send_file(target, as_attachment=as_attachment)

@app.route('/api/document/preview', methods=['GET'])
def preview_document():
    """Retrieve extracted text and metadata of an uploaded document"""
    filename = request.args.get('filename')
    if not filename:
        return jsonify({"success": False, "error": "Parameter filename wajib diisi"}), 400
    
    upload_dir = os.path.abspath(os.path.join("data", "uploads"))
    target = os.path.abspath(os.path.join(upload_dir, filename))
    if not target.startswith(upload_dir) or not os.path.exists(target):
        return jsonify({"success": False, "error": "File tidak ditemukan"}), 404

    from shiro.document import extract_text_from_file
    res = extract_text_from_file(target, filename=filename)
    res["url"] = f"/api/files/{filename}"
    return jsonify(res)

@app.route('/api/images/<path:filename>', methods=['GET'])
@app.route('/images/<path:filename>', methods=['GET'])
def get_uploaded_image(filename):
    """Serve image from training_data/vision/images/ or data/uploads/"""
    v_dir = os.path.abspath(os.path.join("training_data", "vision", "images"))
    target_v = os.path.abspath(os.path.join(v_dir, filename))
    if target_v.startswith(v_dir) and os.path.exists(target_v):
        return send_file(target_v)
    
    u_dir = os.path.abspath(os.path.join("data", "uploads"))
    target_u = os.path.abspath(os.path.join(u_dir, filename))
    if target_u.startswith(u_dir) and os.path.exists(target_u):
        return send_file(target_u)
        
    return jsonify({"error": "Gambar tidak ditemukan"}), 404

@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        with memory.lock:
            return jsonify({
                "sessions": memory.get_sessions_list(),
                "active_session_id": getattr(memory, "active_session_id", "default"),
                "messages": [_format_message_for_api(m) for m in memory.short_term_history]
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/new', methods=['POST'])
def create_session():
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json or {}
        title = data.get("title", None)
        with memory.lock:
            new_id = memory.create_new_session(title=title)
            return jsonify({
                "success": True,
                "session_id": new_id,
                "sessions": memory.get_sessions_list(),
                "active_session_id": new_id,
                "messages": []
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/switch', methods=['POST'])
def switch_session():
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json or {}
        session_id = data.get("session_id")
        if not session_id:
            return jsonify({"error": "session_id wajib diisi"}), 400
        with memory.lock:
            ok = memory.switch_session(session_id)
            if not ok:
                return jsonify({"error": "Sesi tidak ditemukan"}), 404
            return jsonify({
                "success": True,
                "active_session_id": session_id,
                "messages": [_format_message_for_api(m) for m in memory.short_term_history],
                "sessions": memory.get_sessions_list()
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        with memory.lock:
            ok = memory.delete_session(session_id)
            return jsonify({
                "success": ok,
                "active_session_id": memory.active_session_id,
                "messages": [_format_message_for_api(m) for m in memory.short_term_history],
                "sessions": memory.get_sessions_list()
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def handle_openai_chat_completions(api_version="v1"):
    """
    OpenAI-compatible Chat Completions API endpoint handler:
    - v1: Default Shiro (100% Bahasa Indonesia, Persona Adik Manja)
    - v2: VTuber Engine (100% Japanese with [Tag] Expression Selector untuk VoiceVox TTS)
    - v3: Custom Base Prompt (Bebas mengikuti system prompt dari payload client tanpa paksaan bahasa)
    Header: Authorization: Bearer <SHIRO_API_KEY> atau X-API-Key: <SHIRO_API_KEY>
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
        import time
        import secrets
        data = request.json or {}
        messages = data.get("messages", [])
        model_name = data.get("model", "Qwen3-32B")
        
        if not messages:
            return jsonify({
                "error": {
                    "message": "No messages provided in request",
                    "type": "invalid_request_error"
                }
            }), 400

        # Ekstrak custom system prompt dari payload
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

        # Ambil pesan user terakhir & ekstrak teks serta gambar multimodal (OpenAI format)
        user_message = ""
        image_base64 = None
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
                                    image_base64 = img_url_obj.get("url", "")
                                elif isinstance(img_url_obj, str):
                                    image_base64 = img_url_obj
                    user_message = " ".join(text_parts).strip()
                elif isinstance(content, str):
                    user_message = content.strip()
                break
                
        if not user_message and not image_base64:
            user_message = messages[-1].get("content", "").strip() if messages else "Halo Shiro!"
            
        saved_img_rel = None
        if image_base64:
            try:
                import uuid
                v_dir = os.path.join("training_data", "vision", "images")
                os.makedirs(v_dir, exist_ok=True)
                fn = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
                fp = os.path.join(v_dir, fn)
                raw = image_base64.split(",", 1)[1] if "," in image_base64 else image_base64
                with open(fp, "wb") as f_out:
                    f_out.write(base64.b64decode(raw))
                saved_img_rel = os.path.join("images", fn).replace("\\", "/")
            except Exception as e_img:
                print(f"Warning saving vision image in completions: {e_img}")

        with memory.lock:
            log_msg = user_message if not image_base64 else f"[Visual VTuber/Webcam] {user_message}"
            memory.add_message("user", log_msg, image_path=saved_img_rel)
            reply = get_shiro_reply(
                user_message,
                image_base64=image_base64,
                api_version=effective_version,
                custom_system_prompt=client_system_prompt,
                incoming_messages=messages
            )
            memory.add_message("assistant", reply)
            if effective_version == "v1" and (not image_base64 or "poster tersebut" not in reply.lower()):
                memory.record_learned_pattern(log_msg, reply, image_path=saved_img_rel)
            memory.update_emotional_state_from_response(reply)
            memory.update_mood_from_emotions()
            compress_old_messages(memory, keep_count=15)
            memory.save_memory()
            
        response_id = f"chatcmpl-shiro-{effective_version}-{secrets.token_hex(8)}"
        created_time = int(time.time())
        prompt_tokens = len(user_message.split())
        comp_tokens = len(reply.split())
        
        return jsonify({
            "id": response_id,
            "object": "chat.completion",
            "created": created_time,
            "model": model_name,
            "api_version": effective_version,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": reply
                    },
                    "finish_reason": "stop"
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

@app.route('/v1/chat/completions', methods=['POST'])
def openai_chat_completions_v1():
    return handle_openai_chat_completions(api_version="v1")

@app.route('/v2/chat/completions', methods=['POST'])
@app.route('/v2/v1/chat/completions', methods=['POST'])
def openai_chat_completions_v2():
    return handle_openai_chat_completions(api_version="v2")

@app.route('/v3/chat/completions', methods=['POST'])
@app.route('/v3/v1/chat/completions', methods=['POST'])
def openai_chat_completions_v3():
    return handle_openai_chat_completions(api_version="v3")

@app.route('/v1/models', methods=['GET'])
@app.route('/v2/models', methods=['GET'])
@app.route('/v2/v1/models', methods=['GET'])
@app.route('/v3/models', methods=['GET'])
@app.route('/v3/v1/models', methods=['GET'])
def openai_models():
    """List available models for OpenAI SDK client compatibility with dynamic auto-detection"""
    config = load_model_config()
    current = config.get("current_model", "")
    current_name = os.path.basename(current).replace(".gguf", "") if current else ""
    
    # 1. Models dari scanned files di model/ & Google Drive
    raw_models = config.get("available_models", [])
    
    # 2. Versi trained LoRA / model dari shiro.training.versioning
    try:
        from shiro.training.versioning import get_existing_trained_versions
        trained_versions = get_existing_trained_versions()
    except Exception:
        trained_versions = []

    model_ids = []
    # Prioritaskan model yang sedang aktif
    if current_name and current_name not in model_ids:
        model_ids.append(current_name)

    # Tambahkan file .gguf yang terdeteksi
    for m_path in raw_models:
        m_name = os.path.basename(m_path).replace(".gguf", "")
        if m_name and m_name not in model_ids:
            model_ids.append(m_name)

    # Tambahkan model trained (ShiroAI-LLM-V1, ShiroAI-LLM-V2, dst)
    for v in trained_versions:
        t_name = f"ShiroAI-LLM-V{v}"
        if t_name not in model_ids:
            model_ids.append(t_name)

    # Fallback minimal jika disk belum ada file .gguf
    if not model_ids:
        model_ids = ["Qwen2.5-VL-7B", "Qwen3-32B", "ShiroAI-LLM-V1"]

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

    active_model = current_name or (model_ids[0] if model_ids else "Qwen2.5-VL-7B")
    return jsonify({
        "object": "list",
        "data": data,
        "current_model": active_model
    })

@app.route('/api/key', methods=['GET'])
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
                "description": "Karakter VTuber Waifu Shiro dalam 100% Bahasa Jepang dengan tag emosi [Tag] untuk VoiceVox TTS"
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

@app.route('/api/key/regenerate', methods=['POST'])
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

@app.route('/api/reset', methods=['POST'])
def reset():
    try:
        with memory.lock:
            # Finalize current session before reset
            memory.finalize_session()
            
            # Reset memory completely
            memory.reset_memory()
            
            return jsonify({
                "success": True,
                "message": "Memory reset successfully"
            })
    except Exception as e:
        print(f"Error in reset: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/export', methods=['GET'])
def export_memory():
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

@app.route('/api/profile', methods=['GET'])
def get_profile():
    user_profile = None
    ai_profile = None
    user_file = os.path.join(PROFILE_DIR, 'user.json')
    ai_file = os.path.join(PROFILE_DIR, 'ai.json')
    
    if os.path.exists(user_file):
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                user_profile = json.load(f)
        except: pass
    
    if os.path.exists(ai_file):
        try:
            with open(ai_file, 'r', encoding='utf-8') as f:
                ai_profile = json.load(f)
        except: pass
    
    return jsonify({
        "user": user_profile,
        "ai": ai_profile
    })

@app.route('/api/profile/upload', methods=['POST'])
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
        
        profile_file = os.path.join(PROFILE_DIR, f'{profile_type}.json')
        with open(profile_file, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        
        # Real-time auto-sync profile ke Google Drive jika aktif
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
        print(f"Error upload profile: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/models', methods=['GET'])
def get_models():
    config = load_model_config()
    return jsonify({
        "current_model": config.get("current_model"),
        "available_models": config.get("available_models", []),
        "model_info": config.get("model_info", {}),
        "is_colab": is_running_in_colab()
    })

@app.route('/api/models/switch', methods=['POST'])
@app.route('/v1/models/switch', methods=['POST'])
@app.route('/v2/models/switch', methods=['POST'])
@app.route('/v3/models/switch', methods=['POST'])
def switch_model():
    try:
        global llm
        data = request.json or {}
        model_path = data.get('model')
        
        if not model_path:
            return jsonify({"error": "Parameter 'model' harus disertakan"}), 400

        config = load_model_config()
        available = config.get("available_models", [])

        target_path = None
        target_lora_ver = None

        if model_path:
            # 1. Cek langsung path
            if os.path.exists(model_path):
                target_path = model_path
            # 2. Cek di MODEL_DIR
            elif os.path.exists(os.path.join(MODEL_DIR, f"{model_path}.gguf")):
                target_path = os.path.join(MODEL_DIR, f"{model_path}.gguf").replace("\\", "/")
            elif os.path.exists(os.path.join(MODEL_DIR, model_path)):
                target_path = os.path.join(MODEL_DIR, model_path).replace("\\", "/")
            else:
                # 3. Match against available_models by basename
                for cand in available:
                    bname = os.path.basename(cand)
                    bname_no_ext = os.path.splitext(bname)[0]
                    if model_path.lower() in (bname.lower(), bname_no_ext.lower()):
                        target_path = cand
                        break

            # 4. Jika model adalah model trained LoRA ShiroAI-LLM-V*
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
        print(f"\n⚙️  Switching model ke: {model_name} ({file_size_gb:.2f} GB)")
        
        if file_size_gb < 0.1:
            return jsonify({"error": f"File model '{model_name}' rusak atau belum selesai diunduh ({file_size_gb:.2f} GB)"}), 400

        # Simpan backup referensi
        old_llm = llm
        
        try:
            # 1. Bebaskan VRAM GPU & RAM dari model sebelumnya agar tidak OOM
            if llm is not None:
                try:
                    if hasattr(llm, 'close'):
                        llm.close()
                except Exception as e_close:
                    print(f"Warning closing previous LLM: {e_close}")
                del llm
                llm = None
                import gc
                gc.collect()
                print("🧹 VRAM GPU & Memori model sebelumnya berhasil dibersihkan.")

            vision_handler = init_vision_handler(model_path)
            llama_kwargs = {
                "model_path": model_path,
                "n_ctx": CONTEXT_SIZE,
                "n_threads": 4,
                "n_gpu_layers": GPU_LAYERS,
                "verbose": False,
            }
            if vision_handler:
                llama_kwargs["chat_handler"] = vision_handler
            else:
                llama_kwargs["chat_format"] = detect_chat_format(model_path)
            
            active_lora = find_active_lora_path(version=target_lora_ver)
            if active_lora:
                llama_kwargs["lora_path"] = active_lora
                print(f"🎯 LoRA Adapter Training Terdeteksi & Dimuat: {os.path.basename(active_lora)}")
                
            try:
                new_llm = Llama(**llama_kwargs)
            except Exception as load_err:
                # Jika gagal saat memakai LoRA, coba fallback tanpa LoRA
                if "lora_path" in llama_kwargs:
                    print(f"⚠️ Gagal memuat LoRA adapter ({load_err}). Mencoba tanpa LoRA...")
                    llama_kwargs.pop("lora_path", None)
                    try:
                        new_llm = Llama(**llama_kwargs)
                    except Exception as retry_err:
                        load_err = retry_err
                if 'new_llm' not in locals():
                    if vision_handler:
                        print(f"⚠️ Gagal memuat dengan Vision Chat Handler: {load_err}")
                        print("🔄 Mencoba fallback memuat model dalam mode teks standar...")
                        llama_kwargs.pop("chat_handler", None)
                        llama_kwargs["chat_format"] = detect_chat_format(model_path)
                        new_llm = Llama(**llama_kwargs)
                        vision_handler = None
                    else:
                        raise load_err
            
            # Update global llm instance
            llm = new_llm
            vision_chat_handler = vision_handler
            
            # Update configuration
            config["current_model"] = model_path
            save_model_config(config)
            
            print(f"✓ Model switched to: {model_name}")
            
            return jsonify({
                "success": True,
                "message": f"Model switched to {model_name}",
                "current_model": model_path,
                "has_vision": bool(vision_handler is not None)
            })
        
        except Exception as load_error:
            print(f"❌ Error loading model: {load_error}")
            # Kembalikan old_llm jika new_llm gagal
            if llm is None and old_llm is not None:
                llm = old_llm
            return jsonify({"error": f"Gagal load model: {str(load_error)[:120]}"}), 500
    
    except Exception as e:
        print(f"Error in switch_model endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    import logging
    from werkzeug.serving import WSGIRequestHandler
    
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    # Load model configuration (auto scan & fallback for local PC)
    config = load_model_config()
    current_model_path = config.get("current_model")
    
    if not current_model_path or not os.path.exists(current_model_path):
        # Auto-fallback: jika model utama belum diunduh, gunakan model lain yang tersedia di folder model/
        existing_models = get_available_gguf_models()
        if existing_models:
            current_model_path = existing_models[0]
            print(f"⚠️ Model di config ({config.get('current_model')}) belum tersedia di disk, otomatis beralih ke: {current_model_path}")
        else:
            print(f"❌ Error: Model file '{current_model_path}' tidak ditemukan di folder {MODEL_DIR}!")
            sys.exit(1)
    
    try:
        vision_handler = init_vision_handler(current_model_path)
        llama_kwargs = {
            "model_path": current_model_path,
            "n_ctx": CONTEXT_SIZE,
            "n_threads": 4,
            "n_gpu_layers": GPU_LAYERS,
            "verbose": False,
        }
        if vision_handler:
            llama_kwargs["chat_handler"] = vision_handler
        else:
            llama_kwargs["chat_format"] = detect_chat_format(current_model_path)
            
        active_lora = find_active_lora_path()
        if active_lora:
            llama_kwargs["lora_path"] = active_lora
            print(f"🎯 LoRA Adapter Training Terdeteksi & Dimuat: {os.path.basename(active_lora)}")
            
        try:
            llm = Llama(**llama_kwargs)
        except Exception as startup_vis_err:
            if "lora_path" in llama_kwargs:
                print(f"⚠️ Gagal memuat LoRA adapter saat startup ({startup_vis_err}). Mencoba tanpa LoRA...")
                llama_kwargs.pop("lora_path", None)
                try:
                    llm = Llama(**llama_kwargs)
                    startup_vis_err = None
                except Exception as retry_err:
                    startup_vis_err = retry_err
            if startup_vis_err:
                if vision_handler:
                    print(f"⚠️ Gagal memuat Vision Handler saat startup ({startup_vis_err}). Fallback ke mode teks standar...")
                    llama_kwargs.pop("chat_handler", None)
                    llama_kwargs["chat_format"] = detect_chat_format(current_model_path)
                    llm = Llama(**llama_kwargs)
                    vision_handler = None
                    vision_chat_handler = None
                else:
                    raise startup_vis_err
        vision_chat_handler = vision_handler
        model_name = os.path.basename(current_model_path)
        print(f"✓ Model loaded: {model_name}")
        print(f"✓ Context Window: {CONTEXT_SIZE} tokens")
        if vision_handler:
            print("👁️ Multimodal Vision Mode: AKTIF (Mendukung Kamera Real-Time & Analisis Gambar)")
        if GPU_LAYERS != 0:
            print(f"🚀 Akselerasi GPU AKTIF (Layers: {GPU_LAYERS})")
        else:
            print("⚠️ Mode: CPU (Lambat! Di Colab pastikan Runtime -> Change runtime type -> T4/A100 GPU)")
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        sys.exit(1)
    
    memory = AdvancedMemoryManager(MEMORY_FILE, WORLD_FILE)
    
    try:
        active_api_key = get_or_create_api_key(force_new=True)
        print("\n" + "=" * 60)
        print("SERVER SHIRO LLMA AKTIF")
        print("Web UI: http://127.0.0.1:7474")
        print("=" * 60)
        print("API INTEGRATION (WhatsApp Bot / VTuber / Eksternal):")
        print(f"SHIRO API KEY: {active_api_key}")
        print("👉 v1 (Default Shiro - ID)  : http://127.0.0.1:7474/v1")
        print("👉 v2 (VTuber Engine - JP)  : http://127.0.0.1:7474/v2")
        print("👉 v3 (Custom Base Prompt)  : http://127.0.0.1:7474/v3")
        print("👉 Chat Endpoint (v1)       : http://127.0.0.1:7474/v1/chat/completions")
        print("👉 Chat Endpoint (v2 VTuber): http://127.0.0.1:7474/v2/chat/completions")
        print("👉 Chat Endpoint (v3 Custom): http://127.0.0.1:7474/v3/chat/completions")
        print("=" * 60)
        print("Press Ctrl+C to stop\n")
        
        app.run(
            host='127.0.0.1',
            port=7474,
            debug=False,
            use_reloader=False,
            threaded=True
        )
    except OSError as e:
        print(f"\n❌ Port 7474 already in use or error: {e}")
        print("💡 Try closing other applications using this port")
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped. Goodbye!")
