# -*- coding: utf-8 -*-
"""
LLM Output Cleaner and Validator
Ensures 100% pure persona output: strips CoT reasoning, special tokens,
enforces Indonesian language purity, and preserves linebreaks/paragraphs.
"""

import re
import random
from typing import Set

FORBIDDEN_TOKENS = [
    '<|im_end|>', '<|im_start|>',
    '[reasoning', '[explanation',
    '(This is', '(As Shiro', '(I am', 'assistant:', 'user:',
    '<think>', '</think>'
]

META_PATTERNS = [
    r'###\s*(Instruction|Response|System|Human|Assistant):?',
    r'\*\*Note\*\*:',
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
    r'let me break this down',
    r"let's break this down",
    r'the user is',
    r'possible responses?',
    r"let's craft a response",
    r'she uses expressions',
    r'character traits?',
    r'physical gestures',
    r'in italics',
    r'brother \(brocon\)',
    r'older brother',
    r'interact with shiro',
    r'thought process',
    r'as an ai'
]

EN_STOPWORDS: Set[str] = {
    'the', 'is', 'are', 'was', 'were', 'and', 'to', 'in', 'that', 'have',
    'with', 'this', 'from', 'they', 'will', 'would', 'there', 'their', 'what',
    'about', 'which', 'when', 'make', 'can', 'like', 'time', 'just', 'him',
    'know', 'take', 'person', 'into', 'year', 'your', 'good', 'some', 'could',
    'them', 'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come',
    'its', 'over', 'think', 'also', 'back', 'after', 'use', 'two', 'how',
    'our', 'work', 'first', 'well', 'way', 'even', 'new', 'want', 'because',
    'any', 'these', 'give', 'day', 'most', 'us', 'her', 'she', 'him', 'his',
    'responses', 'response', 'gesture', 'gestures', 'brother', 'expression'
}

ID_STOPWORDS: Set[str] = {
    'yang', 'dan', 'di', 'ke', 'dari', 'ini', 'itu', 'aku', 'kamu', 'kita',
    'kakak', 'shiro', 'sangat', 'mau', 'kan', 'ya', 'dong', 'lagi', 'kalau',
    'tapi', 'gak', 'nggak', 'banget', 'suka', 'kok', 'ada', 'apa', 'sudah',
    'udah', 'bisa', 'sama', 'buat', 'aja', 'nih', 'tau', 'kangen', 'rindu',
    'sayang', 'senang', 'peluk', 'manis', 'tersenyum', 'mengangguk', 'menatap',
    'main', 'bareng', 'nanti', 'bikin', 'tolong', 'coba', 'program', 'coding'
}

def validate_response(response: str, user_input: str = "") -> bool:
    """Validasi respons untuk memastikan tidak halusinasi, tidak bocor proses berpikir (CoT), dan berbahasa Indonesia"""
    if not response or len(response.strip()) < 3:
        return False
    
    if any(token in response for token in FORBIDDEN_TOKENS):
        return False
    
    # Hapus blok kode atau kutipan kode saat validasi pola meta dan bahasa
    text_no_code = re.sub(r'```[\s\S]*?```', '', response)
    text_no_code = re.sub(r'`[^`\n]+`', '', text_no_code).strip()

    # Periksa META_PATTERNS pada teks di luar blok kode
    check_meta_text = text_no_code if text_no_code else response
    if any(re.search(pattern, check_meta_text, re.IGNORECASE) for pattern in META_PATTERNS):
        return False

    # Deteksi bahasa asing (English) hanya pada teks percakapan (bukan di dalam sintaks kode)
    if text_no_code:
        words = re.findall(r'\b[a-zA-Z]{2,}\b', text_no_code.lower())
        if len(words) >= 5:
            en_count = sum(1 for w in words if w in EN_STOPWORDS)
            id_count = sum(1 for w in words if w in ID_STOPWORDS)
            if en_count >= 4 and en_count > (id_count * 1.5):
                return False
    
    # Batas panjang diperluas (8000 karakter) agar dapat memuat kode, ringkasan dokumen, dan cerita panjang
    if len(response) > 8000:
        return False
    
    if len(response.strip()) < 5:
        return False
    
    if not any(char.isalpha() for char in response):
        return False
    
    return True

def clean_response(response: str) -> str:
    """Aggressive cleanup dari reasoning/CoT, artifacts & tokens, dengan preservasi baris baru & indentasi kode"""
    if not response:
        return ""

    # 1. Hapus seluruh isi tag <think>...</think> (Chain-of-Thought LLM)
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL | re.IGNORECASE)
    response = re.sub(r'^.*?</think>', '', response, flags=re.DOTALL | re.IGNORECASE)
    if '<think>' in response.lower():
        response = re.sub(r'<think>.*$', '', response, flags=re.DOTALL | re.IGNORECASE)

    # 2. Hapus semua special tokens dan markers
    response = re.sub(r'<\|im_.*?\|>', '', response, flags=re.IGNORECASE)
    response = re.sub(r'<\|.*?\|>', '', response)
    response = response.replace('<|im_end|', '').replace('|>', '')
    response = response.replace('|im_end|', '').replace('im_end', '')

    # 3. Potong English reasoning preamble jika ada delimiter transisi ke dialog Shiro
    response_markers = [
        r'(?i)let\'s\s+craft\s+a\s+response\s*:\s*',
        r'(?i)drafting\s+(?:the\s+)?response\s*:\s*',
        r'(?i)here\s+(?:is|would\s+be)\s+the\s+response\s*:\s*',
        r'(?i)shiro\'s\s+response\s*:\s*',
        r'(?i)final\s+response\s*:\s*',
        r'(?i)possible\s+response\s*:\s*',
    ]
    for marker in response_markers:
        parts = re.split(marker, response)
        if len(parts) > 1 and parts[-1].strip():
            response = parts[-1].strip()
            break

    # 4. Jika teks masih diawali analisis reasoning bahasa Inggris
    if re.search(r'^(?:Okay,?\s+)?(?:let(?:\'s|\s+me)\s+|the user is|in this scenario)', response.strip(), re.IGNORECASE):
        dialogue_match = re.search(r'(\*[^*]+\*[\s\S]*)', response)
        if dialogue_match:
            response = dialogue_match.group(1).strip()
        else:
            quotes_match = re.search(r'("[^"]+"[\s\S]*)', response)
            if quotes_match:
                response = quotes_match.group(1).strip()
    
    # 5. Split dan ambil hanya bagian pertama jika ada multiple responses
    if 'assistant' in response.lower() or re.search(r'\n(User|Kakak|Shiro):', response):
        parts = re.split(r'\n(User|Kakak|Shiro|assistant):', response, maxsplit=1)
        response = parts[0]
    
    # 6. Hapus role labels
    response = re.sub(r'\s*(Shiro:|User:|Kakak:|assistant:|user:)\s*', ' ', response, flags=re.IGNORECASE)
    response = re.sub(r'^\s*(Shiro|User|Kakak|Assistant)[\s:]+', '', response, flags=re.IGNORECASE)
    
    # 7. Hapus meta-commentary sections
    response = re.sub(r'\*\*Note\*\*:.*?(?=\n|$)', '', response, flags=re.IGNORECASE | re.DOTALL)
    response = re.sub(r'Note:.*?(?=\n|$)', '', response, flags=re.IGNORECASE)
    response = re.sub(r'---+.*?(?=\n|$)', '', response)
    
    # 8. Hapus parenthetical explanations di akhir
    response = re.sub(r'\s*\(.*?(explanation|context|note|remember).*?\)\s*$', '', response, flags=re.IGNORECASE)
    
    # 9. Hapus narasi novel orang ketiga di awal kalimat
    response = re.sub(r'^\*?(Tanpa|Dengan|Sambil|Setelah|Ketika|Melihat|Mendengar|Merasa)\s+[^.,!?*]+,\s*Shiro\s+[^.,!?*]+\*?\s*', '', response, flags=re.IGNORECASE)
    response = re.sub(r'^\*Shiro\s+(menjawab|berkata|tersenyum|mengangguk|menatap|berlari|memeluk|mengedipkan)[^*]*\*\s*', '', response, flags=re.IGNORECASE)
    response = re.sub(r'^\*?Kau\s+(masih|melirik|menatap|tersenyum)[^*]*\*?\s*', '', response, flags=re.IGNORECASE)
    
    # 10. Bersihkan halusinasi 'kami semua' & tokoh lain
    response = re.sub(r'\bkami semua\b', 'Shiro', response, flags=re.IGNORECASE)
    response = re.sub(r'\bkami\b', 'kita', response, flags=re.IGNORECASE)
    response = re.sub(r'\bmereka semua\b', '', response, flags=re.IGNORECASE)
    response = re.sub(r'\blingkaran emosional mereka\b', 'pelukan Shiro', response, flags=re.IGNORECASE)

    # 11. Lindungi blok kode agar indentasi dan karakter kode tidak rusak
    code_blocks = []
    def _mask_code(m):
        code_blocks.append(m.group(0))
        return f"__CODE_SNIPPET_BLOCK_{len(code_blocks)-1}__"

    response = re.sub(r'```[\s\S]*?```|`[^`\n]+`', _mask_code, response)
    
    # 12. Hapus tanda baca berlebih pada teks percakapan
    response = re.sub(r'\.{3,}', '...', response)
    response = re.sub(r'!{2,}', '!', response)
    response = re.sub(r'\?{2,}', '?', response)
    
    # 13. Hapus whitespace horizontal berlebih pada teks percakapan
    response = response.replace('\r\n', '\n').replace('\r', '\n')
    response = re.sub(r'[ \t]+', ' ', response)
    response = re.sub(r' +([.,!?])', r'\1', response)
    response = re.sub(r'\n{3,}', '\n\n', response)
    response = '\n'.join([line.strip() for line in response.split('\n')])
    
    # 14. Hapus HTML/XML remnants di luar blok kode
    response = re.sub(r'</?[^>]+>', '', response)
    
    # 15. Pulihkan blok kode utuh dengan indentasi aslinya
    for i, block in enumerate(code_blocks):
        response = response.replace(f"__CODE_SNIPPET_BLOCK_{i}__", block)

    # 16. Clean up <3 emoji
    response = response.replace('<3>', '❤️')
    
    return response.strip()

# --- VTUBER JAPANESE CLEANER & FALLBACKS ---
VTUBER_JAPANESE_FALLBACKS = {
    "romantic": [
        '[Eye Smile] "ふふっ、レンクさん、シロも大好きだよ〜！ずっと一緒だよ！💕"',
        '[Flustered] "えっ…そんなストレートに言われると照れちゃうじゃん…！😳"',
        '[Eye Smile] "本当？嬉しいなぁ〜！シロもレンクさんが一番大切だよ！✨"'
    ],
    "jealous": [
        '[Angry] "むぅ…！レンクさんはシロだけ見てればいいの！💢"',
        '[Tease] "他の女の子のこと考えてないよね？シロが一番でしょ？"'
    ],
    "happy": [
        '[Excited] "わぁーっ！やったぁ〜！シロすっごく嬉しい！✨"',
        '[Mouth Smile] "えへへ、レンクさん最高！いつもありがとうね！"'
    ],
    "sad": [
        '[Sad] "うぅ…そんなこと言われたら、シロ泣いちゃうよ〜…"',
        '[Sad] "レンクさん、シロのこと嫌いになっちゃったの…？"'
    ],
    "neutral": [
        '[Mouth Smile] "うん！シロはいつでもここにいるよ〜！何をお話しする？"',
        '[Eye Smile] "レンクさん、今日もお疲れ様〜！シロとお話ししよ！✨"',
        '[Tease] "ふふっ、どうしたの？シロの顔が見たくなっちゃった？"'
    ],
    "default": [
        '[Mouth Smile] "うん！シロはいつでもここにいるよ〜！何をお話しする？"',
        '[Eye Smile] "ふふっ、レンクさんとお話しできてシロ嬉しいな！✨"',
        '[Tease] "ふふっ、どうしたの？シロの顔が見たくなっちゃった？"'
    ]
}

def is_japanese_text(text: str) -> bool:
    """Memeriksa apakah string mengandung karakter bahasa Jepang (Hiragana, Katakana, atau Kanji)"""
    return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text))

def clean_vtuber_response(response: str, user_input: str = "") -> str:
    """
    Membersihkan respons untuk VTuber Engine (v2):
    - Menghapus CoT/reasoning dan token teknis
    - Menjamin format [Tag] di awal kalimat
    - Memastikan output berbahasa Jepang (jika model merespons dalam bahasa Indonesia, terjemahkan dinamis ke Jepang)
    """
    cleaned = clean_response(response)
    if not cleaned:
        return random.choice(VTUBER_JAPANESE_FALLBACKS["default"])
    
    # 1. Pastikan tag ekspresi ada di awal respons
    valid_tags = ["[Sad]", "[Angry]", "[Surprised]", "[Shocked]", "[Eye Smile]", "[Excited]", "[Flustered]", "[Mouth Smile]", "[Tease]", "[Neutral]"]
    has_tag = any(cleaned.startswith(tag) for tag in valid_tags)
    
    tag_prefix = "[Mouth Smile]"
    if not has_tag:
        tag_match = re.search(r'\[(Sad|Angry|Surprised|Shocked|Eye Smile|Excited|Flustered|Mouth Smile|Tease|Neutral)\]', cleaned, re.IGNORECASE)
        if tag_match:
            tag_name = tag_match.group(1).title()
            tag_prefix = f"[{tag_name}]"
            cleaned_text = cleaned.replace(tag_match.group(0), "").strip()
            cleaned = f"{tag_prefix} {cleaned_text}"
        else:
            cleaned = f'[Mouth Smile] "{cleaned}"' if not cleaned.startswith('"') else f'[Mouth Smile] {cleaned}'
    else:
        for tag in valid_tags:
            if cleaned.startswith(tag):
                tag_prefix = tag
                break

    # 2. Cek apakah ada karakter bahasa Jepang.
    # Jika TIDAK ADA karakter Jepang sama sekali (model merespons bahasa Indonesia),
    # coba terjemahkan kalimat aktualnya ke Bahasa Jepang secara dinamis agar konteks obrolan tetap nyambung!
    if not is_japanese_text(cleaned):
        cleaned_dialogue = cleaned
        for tag in valid_tags:
            if cleaned_dialogue.startswith(tag):
                cleaned_dialogue = cleaned_dialogue[len(tag):].strip()
                break
        cleaned_dialogue = cleaned_dialogue.strip(' "“\'”')

        translated_jp = ""
        try:
            import urllib.request
            import urllib.parse
            import json
            t_url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ja&dt=t&q=" + urllib.parse.quote(cleaned_dialogue)
            req = urllib.request.Request(t_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                    translated_jp = "".join([item[0] for item in data[0] if item and len(item) > 0 and item[0]]).strip()
        except Exception:
            pass

        if translated_jp and is_japanese_text(translated_jp):
            return f'{tag_prefix} "{translated_jp}"'

        # Jika terjemahan ke Jepang offline / tidak tersedia,
        # JANGAN PERNAH membuang jawaban cerdas model dengan canned fallback!
        # Kembalikan teks asli model dengan tag emosi agar client (run.py)
        # dapat menerjemahkannya untuk VoiceVox serta menampilkan teks aslinya di subtitle!
        return f'{tag_prefix} "{cleaned_dialogue}"'

    return cleaned

