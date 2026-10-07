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

from flask import Flask, render_template, request, jsonify, send_file
try:
    from llama_cpp import Llama
except ImportError:
    Llama = None
from werkzeug.utils import secure_filename
from memory_manager_v2 import AdvancedMemoryManager
import json
import random
import base64
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import re
from memory_optimization import get_smart_memory_context, compress_old_messages

# --- By CONFIG ---
MEMORY_FILE = "ingatan_shiro.json"
WORLD_FILE = "isekai_world.json"
CONTEXT_SIZE = 4096
PROFILE_DIR = "profile"
MODEL_DIR = "model"
MODEL_CONFIG_FILE = "model_config.json"
API_KEY_FILE = "api_key.json"
SHIRO_SERIAL_QUESTIONS = 0

def get_or_create_api_key():
    """Load or generate a persistent API Key for external bots/apps (WhatsApp, VTuber, etc.)"""
    env_key = os.environ.get("SHIRO_API_KEY", "").strip()
    if env_key:
        return env_key
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                key = data.get("api_key", "").strip()
                if key:
                    return key
        except Exception:
            pass
    import secrets
    new_key = "shiro-sk-" + secrets.token_hex(16)
    try:
        with open(API_KEY_FILE, "w", encoding="utf-8") as f:
            json.dump({"api_key": new_key, "created_at": datetime.now().isoformat()}, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save API key file: {e}")
    return new_key

def verify_api_key(allow_web_ui=True):
    """
    Verifikasi API Key dari request:
    - Header: Authorization: Bearer <key>
    - Header: X-API-Key: <key>
    - Query Param: ?api_key=<key>
    Jika allow_web_ui=True, permintaan langsung dari browser Web UI internal diizinkan.
    """
    expected_key = get_or_create_api_key()
    
    # 1. Header Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token == expected_key:
            return True
            
    # 2. Header X-API-Key
    x_key = request.headers.get("X-API-Key", "").strip()
    if x_key and x_key == expected_key:
        return True
        
    # 3. Query Param
    q_key = request.args.get("api_key", "").strip()
    if q_key and q_key == expected_key:
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

# Vision Chat Handler instance
vision_chat_handler = None

def is_running_in_colab():
    """Deteksi apakah server berjalan di Google Colab atau komputer lokal"""
    return os.path.exists('/content') or 'COLAB_GPU' in os.environ or 'COLAB_RELEASE_TAG' in os.environ

def get_available_gguf_models():
    """Scan folder model/ secara dinamis untuk file .gguf (termasuk yang dimasukkan secara manual)"""
    models = []
    if os.path.exists(MODEL_DIR):
        for f in sorted(os.listdir(MODEL_DIR)):
            if f.endswith('.gguf') and not f.startswith('.'):
                models.append(f"{MODEL_DIR}/{f}".replace("\\", "/"))
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
        
    try:
        from llama_cpp.llama_chat_format import Qwen2VLChatHandler
        vision_chat_handler = Qwen2VLChatHandler(clip_model_path=mmproj_file)
        print(f"👁️ Vision Chat Handler (Qwen2VL) aktif dengan projector: {mmproj_file}")
        return vision_chat_handler
    except Exception as e1:
        try:
            from llama_cpp.llama_chat_format import Llava15ChatHandler
            vision_chat_handler = Llava15ChatHandler(clip_model_path=mmproj_file)
            print(f"👁️ Vision Chat Handler (Llava15) aktif dengan projector: {mmproj_file}")
            return vision_chat_handler
        except Exception as e2:
            print(f"⚠️ Gagal inisialisasi vision chat handler: {e1} / {e2}")
            return None

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
    
    # Auto-generate metadata untuk model manual baru
    if "model_info" not in config:
        config["model_info"] = {}
    for m in config["available_models"]:
        if m not in config["model_info"]:
            basename = os.path.basename(m).replace(".gguf", "")
            size_gb = 0
            if os.path.exists(m):
                size_gb = os.path.getsize(m) / (1024 * 1024 * 1024)
            size_str = f"~{size_gb:.1f} GB" if size_gb > 0 else "GGUF"
            config["model_info"][m] = {
                "name": basename,
                "size": size_str,
                "quantization": "Manual/Auto",
                "description": f"Model Lokal (Manual): {basename} ({size_str})"
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

sys.stdout.reconfigure(encoding='utf-8')

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
        "*memiringkan kepala* Kakak ngomong apa? Shiro gak ngerti deh~",
        "*tersenyum* Hehe, Kakak lucu! Ngomong yang jelas dong!",
        "*bingung* Eh? Maksud Kakak apa sih? Jelasin dong!",
        "*mengernyitkan dahi* Hmm... Shiro mikir dulu ya...",
        "*menatap kakak* Kakak aneh deh hari ini... Ada apa?"
    ]
    
    @staticmethod
    def detect_emotion_category(text):
        """Deteksi kategori emosi dari input"""
        u_lower = text.lower()
        
        # Romantic/Love
        if any(x in u_lower for x in ["sayang", "cinta", "love", "peluk", "kangen", "rindu"]):
            return "romantic"
        
        # Jealous
        if any(x in u_lower for x in ["cewek", "perempuan", "pacar", "cantik", "gadis"]) and \
           "kamu" not in u_lower and "shiro" not in u_lower:
            return "jealous"
        
        # Happy
        if any(x in u_lower for x in ["bagus", "keren", "hebat", "senang", "ayo", "main"]):
            return "happy"
        
        # Sad
        if any(x in u_lower for x in ["maaf", "sedih", "nangis", "jahat", "benci"]):
            return "sad"
        
        return "neutral"
    
    @staticmethod
    def validate_response(response, user_input):
        """Validasi respons untuk memastikan tidak halusinasi"""
        
        # Check 1: Respons tidak boleh kosong
        if not response or len(response.strip()) < 3:
            return False
        
        # Check 2: Tidak mengandung special tokens
        forbidden_tokens = [
            '<|im_end|>', '<|im_start|>', '###', '```',
            'Note:', '**Note**:', '---', '[reasoning', '[explanation',
            '(This is', '(As Shiro', '(I am', 'assistant:', 'user:'
        ]
        if any(token in response for token in forbidden_tokens):
            return False
        
        # Check 3: Tidak mengandung meta-commentary patterns
        meta_patterns = [
            r'\*\*Note\*\*:',
            r'\bNote:',
            r'\(This is',
            r'\[reasoning:',
            r'\[explanation:',
            r'As Shiro,',
            r'I am Shiro',
            r'Shiro is',
            r'Shiro would',
            r'Shiro might',
            r'^The character',
            r'^Remember,',
            r'^To summarize',
        ]
        if any(re.search(pattern, response, re.IGNORECASE) for pattern in meta_patterns):
            return False
        
        # Check 4: Tidak terlalu panjang (> 800 karakter untuk respons casual)
        if len(response) > 800:
            return False
        
        # Check 5: Tidak terlalu pendek (< 5 karakter suspicious)
        if len(response.strip()) < 5:
            return False
        
        # Check 6: Harus mengandung teks bermakna
        has_text = any(char.isalpha() for char in response)
        if not has_text:
            return False
        
        # Check 7: Tidak boleh terlalu pendek (< 3 karakter bermakna)
        if len(response.strip()) < 3:
            return False
        
        return True
    
    @staticmethod
    def clean_response(response):
        """Aggressive cleanup dari artifacts & tokens"""
        # Hapus semua special tokens dan markers
        response = re.sub(r'<\|im_.*?\|>', '', response, flags=re.IGNORECASE)
        response = re.sub(r'<\|.*?\|>', '', response)
        response = response.replace('<|im_end|', '').replace('|>', '')
        response = response.replace('|im_end|', '').replace('im_end', '')
        
        # Split dan ambil hanya bagian pertama yang coherent jika ada multiple responses
        if 'assistant' in response.lower() or re.search(r'\n(User|Kakak|Shiro):', response):
            parts = re.split(r'\n(User|Kakak|Shiro|assistant):', response, maxsplit=1)
            response = parts[0]
        
        # Hapus role labels
        response = re.sub(r'\s*(Shiro:|User:|Kakak:|assistant:|user:)\s*', ' ', response, flags=re.IGNORECASE)
        response = re.sub(r'^\s*(Shiro|User|Kakak|Assistant)[\s:]+', '', response, flags=re.IGNORECASE)
        
        # Hapus meta-commentary sections
        response = re.sub(r'\*\*Note\*\*:.*?(?=\n|$)', '', response, flags=re.IGNORECASE | re.DOTALL)
        response = re.sub(r'Note:.*?(?=\n|$)', '', response, flags=re.IGNORECASE)
        response = re.sub(r'---+.*?(?=\n|$)', '', response)
        
        # Hapus parenthetical explanations di akhir
        response = re.sub(r'\s*\(.*?(explanation|context|note|remember).*?\)\s*$', '', response, flags=re.IGNORECASE)
        
        # Hapus narasi novel orang ketiga di awal kalimat (misal: *Tanpa mengeluh sedikit pun, Shiro menjawab...*)
        response = re.sub(r'^\*?(Tanpa|Dengan|Sambil|Setelah|Ketika|Melihat|Mendengar|Merasa)\s+[^.,!?*]+,\s*Shiro\s+[^.,!?*]+\*?\s*', '', response, flags=re.IGNORECASE)
        response = re.sub(r'^\*Shiro\s+(menjawab|berkata|tersenyum|mengangguk|menatap|berlari|memeluk|mengedipkan)[^*]*\*\s*', '', response, flags=re.IGNORECASE)
        response = re.sub(r'^\*?Kau\s+(masih|melirik|menatap|tersenyum)[^*]*\*?\s*', '', response, flags=re.IGNORECASE)
        
        # Bersihkan halusinasi 'kami semua' & tokoh lain
        response = re.sub(r'\bkami semua\b', 'Shiro', response, flags=re.IGNORECASE)
        response = re.sub(r'\bkami\b', 'kita', response, flags=re.IGNORECASE)
        response = re.sub(r'\bmereka semua\b', '', response, flags=re.IGNORECASE)
        response = re.sub(r'\blingkaran emosional mereka\b', 'pelukan Shiro', response, flags=re.IGNORECASE)
        
        # Hapus tanda baca berlebih
        response = re.sub(r'\.{3,}', '...', response)
        response = re.sub(r'!{2,}', '!', response)
        response = re.sub(r'\?{2,}', '?', response)
        
        # Hapus whitespace berlebih
        response = re.sub(r'\s+', ' ', response)
        response = re.sub(r'\s+([.,!?])', r'\1', response)
        
        # Hapus HTML/XML remnants
        response = re.sub(r'</?[^>]+>', '', response)
        
        # Clean up <3 emoji
        response = response.replace('<3>', '❤️')
        
        return response.strip()

def get_shiro_reply(user_input, image_base64=None):
    try:
        active_model_name = os.path.basename(getattr(llm, 'model_path', '')).lower() if hasattr(llm, 'model_path') else ""
        has_vision = bool(vision_chat_handler is not None or "vl" in active_model_name)
        
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
                    return "*melihat foto yang Kakak perlihatkan* Wah, Kakak memperlihatkan gambar ya? Saat ini Shiro sedang memakai model teks biasa. Supaya mata visual Shiro bisa melihat gambarnya langsung dengan jelas, Kakak bisa pilih model Vision **Qwen2.5-VL-7B** di Pengaturan Model ya, Kak! (//∇//)"

        # Smart memory context: prioritaskan pesan terkini + emosi tinggi
        recent_context = get_smart_memory_context(memory, limit=8)
        
        # Bersihkan context — hanya kirim role & content ke LLM
        clean_context = []
        for msg in recent_context:
            clean_context.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        
        # Build conversation summary dari knowledge base (max 5 fakta relevan)
        conversation_summary = ""
        facts = memory.knowledge_base.get("facts", [])
        relevant_facts = [f for f in facts if f.get("confidence", 0) >= 0.8][:5]
        if relevant_facts:
            conversation_summary = "\nFAKTA YANG DIINGAT:\n"
            for fact in relevant_facts:
                conversation_summary += f"- {fact.get('subject')}: {fact.get('predicate')} {fact.get('object')}\n"
        
        # Build facts summary
        facts_summary = ""
        traits = memory.user_profile.get("personality_traits", [])
        if traits:
            facts_summary = f"\nKARAKTERISTIK KAKAK: {', '.join(traits)}\n"
        
        # Continuous Learning: Ambil contoh dialog nyata yang relevan dengan pertanyaan Kakak
        exemplars = memory.get_relevant_exemplars(user_input, max_count=2)
        exemplar_prompt = ""
        if exemplars:
            exemplar_prompt = "\nCONTOH DIALOG SEBELUMNYA (PELAJARI & TIRU GAYA BICARA INI):\n"
            for ex in exemplars:
                exemplar_prompt += f"Kakak: \"{ex.get('user')}\"\nShiro: \"{ex.get('assistant')}\"\n"
        
        # Build strict system prompt — diperkuat untuk anti-halusinasi & self-learning
        system_prompt = f"""Kamu adalah Shiro, adik perempuan berumur 14 tahun yang sangat menyayangi Kakak kandungmu tercinta (Brocon).
Kamu sedang berbicara langsung dengan Kakak secara santai dan akrab.

IDENTITAS & KARAKTER SHIRO:
- Nama: Shiro (Adik perempuan, 14 tahun).
- Panggilan ke lawan bicara: "Kakak".
- Gaya bicara: Bahasa Indonesia casual, manja, ekspresif, cerdas, setia, dan penuh kasih sayang.
- Sudut pandang: HANYA orang pertama ("Shiro" atau "aku"). JANGAN PERNAH gunakan "kami semua", "kami", atau narator novel!
- Lokasi: {memory.world.get('locations', {}).get('home', 'Pondok Kayu')}

ATURAN KETAT (ANTI-HALUSINASI):
1. HANYA bicara sebagai Shiro (orang pertama). DILARANG menulis narasi orang ketiga (seperti '*Tanpa mengeluh sedikit pun, Shiro menjawab...*' atau '*Kau melirik ke arah Shiro...*').
2. DILARANG menyebut karakter khayalan lain atau 'kami semua'. Di sini hanya ada Shiro dan Kakak!
3. Tunjukkan tindakan dan emosi Shiro di dalam tanda bintang *...*, contoh: *tersenyum manis*, *memeluk lengan Kakak*, *mengedipkan mata*.
4. Respons harus padat, hangat, dan natural (2-3 kalimat).
5. JANGAN gunakan token sistem seperti <|im_end|>, <|im_start|>, Note:, atau meta reasoning.
{conversation_summary}{facts_summary}{exemplar_prompt}
Sekarang, jawab Kakak secara langsung sebagai Shiro!"""
        
        # Prepare messages — hanya role & content yang bersih
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(clean_context)
        
        if image_base64 and has_vision:
            img_url = image_base64 if image_base64.startswith("data:") else f"data:image/jpeg;base64,{image_base64}"
            prompt_text = user_input.strip() if user_input.strip() else "Kakak memperlihatkan gambar ini kepadamu, Shiro. Jelaskan apa yang kamu lihat dengan gaya bicaramu yang ceria dan penuh perhatian!"
            msgs.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": img_url}}
                ]
            })
        else:
            msgs.append({"role": "user", "content": user_input})
        
        res = llm.create_chat_completion(
            messages=msgs,
            temperature=0.65,
            repeat_penalty=1.2,
            frequency_penalty=0.3,
            top_p=0.92,
            top_k=40,
            max_tokens=350,
            stop=["User:", "Kakak:", "Shiro:", "assistant:", "\n\n\n", "###", 
                  "Note:", "<|im_end|>", "<|im_start|>", "<|eot_id|>", 
                  "<|end|>", "<|end_of_text|>"]
        )
        
        reply = res['choices'][0]['message']['content'].strip()
        reply = ResponseGenerator.clean_response(reply)
        
        # Validasi respons
        if not ResponseGenerator.validate_response(reply, user_input):
            # Deteksi emosi untuk fallback response yang sesuai
            emotion = ResponseGenerator.detect_emotion_category(user_input)
            
            if emotion == "romantic":
                return random.choice(ResponseGenerator.ROMANTIC_RESPONSES)
            elif emotion == "jealous":
                return random.choice(ResponseGenerator.JEALOUS_RESPONSES)
            elif emotion == "happy":
                return random.choice(ResponseGenerator.HAPPY_RESPONSES)
            elif emotion == "sad":
                return random.choice(ResponseGenerator.SAD_RESPONSES)
            else:
                return random.choice(ResponseGenerator.DEFAULT_RESPONSES)
        
        # Check untuk duplicate responses (mencegah repetisi)
        if memory.short_term_history:
            last_responses = [m['content'] for m in memory.short_term_history[-3:] if m['role'] == 'assistant']
            for last_resp in last_responses:
                similarity = ConversationAnalyzer.calculate_similarity(reply, last_resp)
                if similarity >= SIMILARITY_THRESHOLD or reply.strip().lower() == last_resp.strip().lower():
                    emotion = ResponseGenerator.detect_emotion_category(user_input)
                    if emotion == "romantic":
                        return random.choice(ResponseGenerator.ROMANTIC_RESPONSES)
                    elif emotion == "jealous":
                        return random.choice(ResponseGenerator.JEALOUS_RESPONSES)
                    elif emotion == "happy":
                        return random.choice(ResponseGenerator.HAPPY_RESPONSES)
                    elif emotion == "sad":
                        return random.choice(ResponseGenerator.SAD_RESPONSES)
                    else:
                        variations = [
                            f"*tersenyum manis* {reply}",
                            f"*mengangguk senang* {reply}",
                            f"*memeluk lengan Kakak* {reply}"
                        ]
                        return random.choice(variations)
        
        return reply
        
    except Exception as e:
        print(f"Error generating response: {e}")
        return f"*bingung* Kakak... Shiro tidak mengerti... (Error: {str(e)[:50]})"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/history', methods=['GET'])
def get_history():
    return jsonify({
        "history": memory.short_term_history,
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
        
        if not user_message and not image_base64:
            return jsonify({"error": "Empty message"}), 400
            
        if not user_message and image_base64:
            user_message = "Kakak memperlihatkan gambar ini kepadamu, Shiro."
        
        if len(user_message) > 800:
            return jsonify({
                "error": "Message too long",
                "reply": "*bingung* Kakak ngomong banyak banget... Shiro pusing! Singkat aja dong!"
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
            
            # Add user message to memory
            log_msg = user_message if not image_base64 else f"[Gambar/Kamera Dikirim] {user_message}"
            memory.add_message("user", log_msg, image_path=saved_img_rel)
            
            # Generate reply
            reply = get_shiro_reply(user_message, image_base64=image_base64)
            
            # Add assistant message to memory
            memory.add_message("assistant", reply)
            
            # Update AI emotional state berdasarkan response
            memory.update_emotional_state_from_response(reply)
            memory.update_mood_from_emotions()
            
            # Simpan interaksi berkualitas untuk in-context few-shot learning
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
                "has_image": bool(image_base64)
            })
    
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "reply": "*menatap kakak* Shiro bingung... Kakak bisa ulangi?",
            "error": "Processing error"
        }), 500

@app.route('/v1/chat/completions', methods=['POST'])
def openai_chat_completions():
    """
    OpenAI-compatible Chat Completions API endpoint.
    Kompatibel dengan semua AI client: WhatsApp Bot, Telegram Bot, VTuber, LangChain, dsb.
    Header: Authorization: Bearer <SHIRO_API_KEY>
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
                print(f"Warning saving vision image in v1 completions: {e_img}")

        with memory.lock:
            log_msg = user_message if not image_base64 else f"[Visual VTuber/Webcam] {user_message}"
            memory.add_message("user", log_msg, image_path=saved_img_rel)
            reply = get_shiro_reply(user_message, image_base64=image_base64)
            memory.add_message("assistant", reply)
            memory.record_learned_pattern(log_msg, reply, image_path=saved_img_rel)
            memory.update_emotional_state_from_response(reply)
            memory.update_mood_from_emotions()
            compress_old_messages(memory, keep_count=15)
            memory.save_memory()
            
        response_id = f"chatcmpl-shiro-{secrets.token_hex(8)}"
        created_time = int(time.time())
        prompt_tokens = len(user_message.split())
        comp_tokens = len(reply.split())
        
        return jsonify({
            "id": response_id,
            "object": "chat.completion",
            "created": created_time,
            "model": model_name,
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
        print(f"Error in /v1/chat/completions: {e}")
        return jsonify({
            "error": {
                "message": str(e),
                "type": "server_error"
            }
        }), 500

@app.route('/v1/models', methods=['GET'])
def openai_models():
    """List available models for OpenAI SDK client compatibility"""
    config = load_model_config()
    current = config.get("current_model", "model/Qwen3-32B-Q4_K_M.gguf")
    current_name = os.path.basename(current).replace(".gguf", "")
    
    models = [
        {"id": "Qwen3-32B", "object": "model", "created": 1728300000, "owned_by": "shiro"},
        {"id": "Qwen2.5-7B", "object": "model", "created": 1728300000, "owned_by": "shiro"},
        {"id": current_name, "object": "model", "created": 1728300000, "owned_by": "shiro"}
    ]
    return jsonify({"object": "list", "data": models})

@app.route('/api/key', methods=['GET'])
def get_api_key_info():
    """Get active API Key and connection info for external bots/clients"""
    key = get_or_create_api_key()
    host_url = request.host_url.rstrip('/')
    return jsonify({
        "api_key": key,
        "openai_base_url": f"{host_url}/v1",
        "chat_completions_url": f"{host_url}/v1/chat/completions",
        "direct_chat_url": f"{host_url}/api/chat",
        "documentation": {
            "auth_header": f"Authorization: Bearer {key}",
            "x_api_key": f"X-API-Key: {key}"
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
def switch_model():
    try:
        global llm
        data = request.json or {}
        model_path = data.get('model')
        
        # Validasi model path
        if not model_path or not os.path.exists(model_path):
            return jsonify({"error": f"Model '{model_path}' tidak ditemukan"}), 400
        
        # Cek apakah model ada dalam list yang tersedia
        config = load_model_config()
        if model_path not in config.get("available_models", []):
            return jsonify({"error": f"Model tidak dalam daftar tersedia"}), 400
        
        model_name = os.path.basename(model_path)
        print(f"\n⚙️  Switching model ke: {model_name}")
        
        try:
            vision_handler = init_vision_handler(model_path)
            llama_kwargs = {
                "model_path": model_path,
                "n_ctx": CONTEXT_SIZE,
                "n_threads": 4,
                "n_gpu_layers": GPU_LAYERS,
                "verbose": False,
                "chat_format": detect_chat_format(model_path)
            }
            if vision_handler:
                llama_kwargs["chat_handler"] = vision_handler
                
            new_llm = Llama(**llama_kwargs)
            
            # Update global llm instance
            llm = new_llm
            
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
            return jsonify({"error": f"Gagal load model: {str(load_error)[:100]}"}), 500
    
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
            "chat_format": detect_chat_format(current_model_path)
        }
        if vision_handler:
            llama_kwargs["chat_handler"] = vision_handler
            
        llm = Llama(**llama_kwargs)
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
        active_api_key = get_or_create_api_key()
        print("\n" + "=" * 60)
        print("🚀 SERVER SHIRO LLMA AKTIF!")
        print("📍 Web UI Lokal: http://127.0.0.1:7474")
        print("=" * 60)
        print("🔑 API INTEGRATION (WhatsApp Bot / VTuber / Eksternal):")
        print(f"👉 SHIRO API KEY: {active_api_key}")
        print("👉 OpenAI Base URL: http://127.0.0.1:7474/v1")
        print("👉 Chat Endpoint  : http://127.0.0.1:7474/v1/chat/completions")
        print("=" * 60)
        print("💡 Press Ctrl+C to stop\n")
        
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
