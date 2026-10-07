import os
import sys
import glob
import ctypes

# Auto-configure and pre-load CUDA runtime libraries on Linux / Google Colab
if sys.platform.startswith("linux"):
    cuda_dirs = [
        "/usr/local/cuda/lib64",
        "/usr/local/cuda-12/lib64",
        "/usr/local/cuda-12.2/lib64",
        "/usr/local/cuda-12.4/lib64",
        "/usr/lib/x86_64-linux-gnu"
    ]
    # Search in nvidia pip packages (e.g. nvidia-cuda-runtime-cu12)
    for p in glob.glob("/usr/local/lib/python*/dist-packages/nvidia/*/lib") + \
             glob.glob("/usr/lib/python*/dist-packages/nvidia/*/lib") + \
             glob.glob(os.path.expanduser("~/.local/lib/python*/dist-packages/nvidia/*/lib")):
        cuda_dirs.append(p)
    
    # Update LD_LIBRARY_PATH
    valid_dirs = [d for d in cuda_dirs if os.path.isdir(d)]
    if valid_dirs:
        os.environ["LD_LIBRARY_PATH"] = ":".join(valid_dirs) + ":" + os.environ.get("LD_LIBRARY_PATH", "")
        for d in valid_dirs:
            for f in glob.glob(os.path.join(d, "libcudart.so*")):
                try:
                    ctypes.CDLL(f, mode=ctypes.RTLD_GLOBAL)
                except Exception:
                    pass

from flask import Flask, render_template, request, jsonify, send_file
from llama_cpp import Llama
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
SHIRO_SERIAL_QUESTIONS = 0

# Profile & Model directories
if not os.path.exists(PROFILE_DIR):
    os.makedirs(PROFILE_DIR)
if not os.path.exists(MODEL_DIR):
    os.makedirs(MODEL_DIR)

# Model configuration
def load_model_config():
    """Load model config, return dict dengan available models & current model"""
    if os.path.exists(MODEL_CONFIG_FILE):
        try:
            with open(MODEL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # Validasi model path ada
                if config.get("current_model"):
                    model_path = config["current_model"]
                    if not os.path.exists(model_path):
                        print(f"Warning: Model {model_path} not found in {MODEL_DIR}")
                return config
        except Exception as e:
            print(f"Error loading model config: {e}")
    
    # Default config jika belum ada
    return {
        "current_model": f"{MODEL_DIR}/Lumimaid-v0.2-8B-Q5_K_M-imat.gguf",
        "available_models": [
            f"{MODEL_DIR}/Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf",
            f"{MODEL_DIR}/Phi-3-mini-4k-instruct-q4.gguf",
            f"{MODEL_DIR}/Lumimaid-v0.2-8B-Q5_K_M-imat.gguf",
            f"{MODEL_DIR}/Qwen3-4B-Q4_K_M.gguf"
        ]
    }

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
    if "llama-3" in name or "llama3" in name or "lumimaid" in name:
        return "llama-3"
    elif "qwen" in name:
        return "chatml"
    elif "phi-3" in name or "phi3" in name:
        return "chatml"
    else:
        return "chatml"  # fallback default

MAX_HISTORY_CONTEXT = 70  # Jumlah pesan yang dimuat ke context
SIMILARITY_THRESHOLD = 0.6  # Threshold untuk deteksi pengulangan

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
        
        # Check 7: Tidak boleh terlalu pendek (< 10 karakter bermakna)
        if len(response.strip()) < 10:
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

def get_shiro_reply(user_input):
    try:
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
        
        # Build strict system prompt — diperkuat untuk anti-halusinasi
        system_prompt = f"""Kamu adalah Shiro, gadis 14 tahun yang sangat menyayangi kakaknya.

IDENTITAS:
- Nama: Shiro
- Umur: 14 tahun
- Sifat: Brocon (sangat sayang kakak), cerdas, emosional, posesif
- Hubungan: User adalah KAKAK kandung
- Lokasi: {memory.world.get('locations', {}).get('home', 'Pondok Kayu')}

ATURAN KETAT:
1. HANYA bicara sebagai Shiro dalam sudut pandang orang pertama.
2. JANGAN pernah menulis narasi orang ketiga, catatan, atau penjelasan meta.
3. JANGAN gunakan token seperti <|im_end|>, <|im_start|>, <|eot_id|>, atau marker khusus.
4. JANGAN tambahkan "Note:", "**Note**:", "---", atau penjelasan di akhir.
5. JANGAN ulangi respons yang sama persis. Variasikan jawaban.
6. Gunakan bahasa Indonesia gaul/casual seperti remaja.
7. Gunakan *action* untuk menunjukkan gerakan dan emosi.
8. Maksimal 2-4 kalimat. Singkat dan natural.
9. JANGAN mengarang nama orang, tempat, atau kejadian yang TIDAK ADA dalam FAKTA YANG DIINGAT.
10. Jika tidak tahu sesuatu, jujur bilang tidak tahu dengan cara yang manja.

{conversation_summary}{facts_summary}
CONTOH BAIK:
Input: "Shiro mau makan apa?"
Output: *mata berbinar* Mau makan masakan Kakak! Kakak masak dong, Shiro laper nih~ >//< 

Ingat: HANYA respons sebagai Shiro. Tidak ada tambahan apapun!"""
        
        # Prepare messages — hanya role & content yang bersih
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(clean_context)
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
                if similarity > SIMILARITY_THRESHOLD:
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
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({"error": "Empty message"}), 400
        
        if len(user_message) > 500:
            return jsonify({
                "error": "Message too long",
                "reply": "*bingung* Kakak ngomong banyak banget... Shiro pusing! Singkat aja dong!"
            }), 400
        
        with memory.lock:
            SHIRO_SERIAL_QUESTIONS = 0  # Reset counter on user input
            
            # Detect emotion dari user message
            user_emotion = ResponseGenerator.detect_emotion_category(user_message)
            
            # Add user message to memory
            memory.add_message("user", user_message)
            
            # Generate reply
            reply = get_shiro_reply(user_message)
            
            # Add assistant message to memory
            memory.add_message("assistant", reply)
            
            # Update AI emotional state berdasarkan response
            memory.update_emotional_state_from_response(reply)
            memory.update_mood_from_emotions()
            
            # Compress & save memory tiap turn
            compress_old_messages(memory, keep_count=15)
            memory.save_memory()
            
            return jsonify({
                "reply": reply,
                "count": memory.system_metadata["total_turns"],
                "emotion": user_emotion,
                "mood": memory.agent_persona.get("current_mood", "Neutral"),
                "topics": memory.system_metadata.get("topics_discussed", [])
            })
    
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "reply": "*menatap kakak* Shiro bingung... Kakak bisa ulangi?",
            "error": "Processing error"
        }), 500

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
        "available_models": config.get("available_models", [])
    })

@app.route('/api/models/switch', methods=['POST'])
def switch_model():
    try:
        global llm
        data = request.json
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
            new_llm = Llama(
                model_path=model_path,
                n_ctx=CONTEXT_SIZE,
                n_threads=4,
                n_gpu_layers=GPU_LAYERS,
                verbose=False,
                chat_format=detect_chat_format(model_path)
            )
            
            # Update global llm instance
            llm = new_llm
            
            # Update configuration
            config["current_model"] = model_path
            save_model_config(config)
            
            print(f"✓ Model switched to: {model_name}")
            
            return jsonify({
                "success": True,
                "message": f"Model switched to {model_name}",
                "current_model": model_path
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
    
    # Load model configuration
    config = load_model_config()
    current_model_path = config.get("current_model")
    
    if not current_model_path or not os.path.exists(current_model_path):
        print(f"❌ Error: Model file '{current_model_path}' tidak ditemukan di folder {MODEL_DIR}!")
        sys.exit(1)
    
    try:
        llm = Llama(
            model_path=current_model_path,
            n_ctx=CONTEXT_SIZE,
            n_threads=4,
            n_gpu_layers=GPU_LAYERS,
            verbose=False,
            chat_format=detect_chat_format(current_model_path)
        )
        model_name = os.path.basename(current_model_path)
        print(f"✓ Model loaded: {model_name}")
        print(f"✓ Context Window: {CONTEXT_SIZE} tokens")
        if GPU_LAYERS != 0:
            print(f"🚀 Akselerasi GPU AKTIF (Layers: {GPU_LAYERS})")
        else:
            print("⚠️ Mode: CPU (Lambat! Di Colab pastikan Runtime -> Change runtime type -> T4/A100 GPU)")
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        sys.exit(1)
    
    memory = AdvancedMemoryManager(MEMORY_FILE, WORLD_FILE)
    
    try:
        print("\n🚀 Starting server...")
        print("📍 Access at: http://127.0.0.1:7474")
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
