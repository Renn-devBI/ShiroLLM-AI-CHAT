# -*- coding: utf-8 -*-
"""
LLM Output Cleaner and Validator
Ensures 100% pure persona output: strips CoT reasoning, special tokens,
enforces Indonesian language purity, and preserves linebreaks/paragraphs.
"""

import re
import random
from typing import Set, Optional

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
    r'as an ai',
    r'\[(?:AI Agent|Agent|Web Tool)'
]

EN_STOPWORDS: Set[str] = {
    'the', 'is', 'are', 'was', 'were', 'and', 'to', 'in', 'that', 'have', 'has', 'had',
    'with', 'this', 'from', 'they', 'will', 'would', 'there', 'their', 'what',
    'about', 'which', 'when', 'make', 'can', 'like', 'time', 'just', 'him',
    'know', 'take', 'person', 'into', 'year', 'your', 'good', 'some', 'could',
    'them', 'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come',
    'its', 'it', 'all', 'say', 'says', 'said', 'get', 'gets', 'got', 'go', 'goes',
    'going', 'gone', 'went', 'anywhere', 'somewhere', 'nowhere', 'everywhere',
    'stay', 'stays', 'stayed', 'soft', 'hard', 'name', 'fancy', 'loneliness',
    'upset', 'dismiss', 'tap', 'taps', 'nose', 'lips', 'eyes', 'face', 'hand',
    'hands', 'arm', 'arms', 'over', 'think', 'also', 'back', 'after', 'use',
    'two', 'how', 'our', 'work', 'first', 'well', 'way', 'even', 'new', 'want',
    'because', 'any', 'these', 'give', 'day', 'most', 'us', 'her', 'she', 'his', 'he',
    'you', 'yours', 'yourself', 'me', 'my', 'mine', 'myself', 'himself', 'herself',
    'we', 'ours', 'theirs', 'be', 'am', 'been', 'being', 'do', 'does', 'did',
    'done', 'doing', 'don', 'doesn', 'didn', 'isn', 'aren', 'wasn', 'weren',
    'won', 'wouldn', 'couldn', 'shouldn', 'gotta', 'gonna', 'wanna', 'not',
    'no', 'on', 'at', 'by', 'for', 'of', 'or', 'but', 'if', 'so', 'up', 'down',
    'out', 'off', 'onto', 'upon', 'against', 'through', 'under', 'underneath',
    'between', 'without', 'within', 'while', 'until', 'before', 'again', 'still',
    'too', 'very', 'much', 'more', 'little', 'bit', 'right', 'here', 'something',
    'anything', 'nothing', 'everything', 'someone', 'anyone', 'nobody', 'every',
    'always', 'never', 'really', 'actually', 'genuinely', 'technically', 'though',
    'although', 'both', 'each', 'own', 'same', 'whispers', 'swallows', 'tucks',
    'kisses', 'sits', 'pressing', 'holding', 'wrapping', 'tightens', 'knuckles',
    'sleeve', 'shoulder', 'forehead', 'lightly', 'slightly', 'muffled',
    'responses', 'response', 'gesture', 'gestures', 'brother', 'expression'
}

ID_STOPWORDS: Set[str] = {
    'yang', 'dan', 'di', 'ke', 'dari', 'ini', 'itu', 'aku', 'kamu', 'kita',
    'saya', 'anda', 'dia', 'mereka', 'kami', 'dengan', 'untuk', 'untuknya',
    'karena', 'tidak', 'bukan', 'belum', 'jangan', 'hanya', 'juga', 'akan',
    'sedang', 'pada', 'dalam', 'seperti', 'kayak', 'kenapa', 'mengapa',
    'bagaimana', 'siapa', 'kapan', 'berapa', 'baru', 'saja', 'orang', 'hati',
    'perasaan', 'nyata', 'sakit', 'selalu', 'sering', 'kali', 'mungkin',
    'ternyata', 'sendiri', 'sangat', 'mau', 'kan', 'ya', 'dong', 'lagi',
    'kalau', 'tapi', 'gak', 'nggak', 'banget', 'suka', 'kok', 'ada', 'apa',
    'sudah', 'udah', 'bisa', 'sama', 'buat', 'aja', 'nih', 'tau', 'kangen',
    'rindu', 'sayang', 'senang', 'peluk', 'manis', 'tersenyum', 'mengangguk',
    'menatap', 'main', 'bareng', 'nanti', 'bikin', 'tolong', 'coba', 'program', 'coding'
}

EN_ROLEPLAY_PHRASES = re.compile(
    r"(?:\b(?:i'm|i'll|i'd|i've|you're|you'll|you've|you'd|don't|doesn't|didn't|"
    r"isn't|aren't|wasn't|weren't|won't|wouldn't|couldn't|shouldn't|can't|that's|"
    r"there's|it's|what's|who's|let's|we're|they're|he's|she's|"
    r"my head|his shoulder|his sleeve|his arm|his head|his chest|your hands|"
    r"gonna|gotta|wanna|shiro here|right now|little bit|each other|into his|"
    r"against his|of his|swallows hard|tucks my|pressing my|my grip|sits up|"
    r"kisses the|both arms|grab both|no take-backs|i love you|"
    r"get it|move on|even be|stays soft|tap your|going anywhere|all of it|"
    r"with a fancy|di-dismiss-in|di-dismiss)\b|(?:^|\s)so\.\.\.|\.\.\.so\?)",
    re.IGNORECASE
)

INLINE_IDIOM_MAP = [
    (re.compile(r'\bdi-dismiss-in\b', re.IGNORECASE), 'diabaikan'),
    (re.compile(r'\bdi-dismiss\b', re.IGNORECASE), 'diabaikan'),
    (re.compile(r'\bmove on\b', re.IGNORECASE), 'melupakannya'),
    (re.compile(r'\beven be upset\b', re.IGNORECASE), 'merasa kesal sekalipun'),
    (re.compile(r'\bdan aku get it\b', re.IGNORECASE), 'dan aku mengerti'),
    (re.compile(r'\baku get it\b', re.IGNORECASE), 'aku mengerti'),
    (re.compile(r'\bi get it\b', re.IGNORECASE), 'aku mengerti'),
    (re.compile(r'\bstays soft\b', re.IGNORECASE), 'tetap lembut'),
    (re.compile(r'\btaps? your nose lightly\b', re.IGNORECASE), 'mengetuk hidungmu pelan'),
    (re.compile(r"\bi'm not going anywhere\b", re.IGNORECASE), 'Aku tidak akan ke mana-mana'),
    (re.compile(r'\bsay all of it\b', re.IGNORECASE), 'Katakan semuanya'),
    (re.compile(r'\bshiro here\b', re.IGNORECASE), 'Shiro di sini'),
    (re.compile(r'\bno take-backs\b', re.IGNORECASE), 'tidak boleh ditarik kembali'),
    (re.compile(r'(?:^|(?<=\n)|(?<=\s))So\.\.\.'), 'Jadi...'),
    (re.compile(r'\.\.\.so\?', re.IGNORECASE), '...jadi?'),
]

def replace_inline_english_idioms(text: str) -> str:
    """Mengganti frasa selipan bahasa Inggris populer secara instan tanpa mengubah struktur kalimat Indonesia"""
    if not text:
        return text
    res = text
    for pat, repl in INLINE_IDIOM_MAP:
        res = pat.sub(repl, res)
    return res

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

    # Deteksi bahasa asing (English) hanya jika user_input jelas berbahasa Indonesia dan tidak menghendaki bahasa asing
    if text_no_code:
        u_lower = (user_input or '').lower()
        user_allows_foreign = (
            is_predominantly_english(user_input) or 
            any(k in u_lower for k in ['english', 'inggris', 'translate', 'terjemah', 'japan', 'jepang'])
        )
        if not user_allows_foreign:
            words = re.findall(r'\b[a-zA-Z]{2,}\b', text_no_code.lower())
            if len(words) >= 5:
                en_count = sum(1 for w in words if w in EN_STOPWORDS)
                id_count = sum(1 for w in words if w in ID_STOPWORDS)
                if en_count >= 4 and en_count > (id_count * 1.5):
                    return False
    
    # Batas panjang diperluas (64.000 karakter) agar dapat memuat kode website utuh, ringkasan dokumen, dan cerita panjang
    if len(response) > 64000:
        return False
    
    if len(response.strip()) < 5:
        return False
    
    if not any(char.isalpha() for char in response):
        return False
    
    return True


def is_english_text_segment(text: str) -> bool:
    """Mendeteksi apakah sebuah kalimat atau segmen teks mengandung frasa bahasa Inggris"""
    if not text or len(text.strip()) < 4:
        return False
    text_no_code = re.sub(r'```[\s\S]*?```|`[^`\n]+`', '', text).strip()
    if not text_no_code:
        return False
    if EN_ROLEPLAY_PHRASES.search(text_no_code):
        return True
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text_no_code.lower())
    if len(words) < 2:
        return False
    en_hits = sum(1 for w in words if w in EN_STOPWORDS)
    return en_hits >= 2

def is_predominantly_english(text: str) -> bool:
    """Mendeteksi apakah teks percakapan didominasi bahasa Inggris di luar blok kode"""
    if not text or len(text.strip()) < 12:
        return False
    text_no_code = re.sub(r'```[\s\S]*?```', '', text)
    text_no_code = re.sub(r'`[^`\n]+`', '', text_no_code).strip()
    if not text_no_code:
        return False
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text_no_code.lower())
    if len(words) < 5:
        return False
    en_hits = sum(1 for w in words if w in EN_STOPWORDS)
    id_hits = sum(1 for w in words if w in ID_STOPWORDS)
    return (en_hits >= 4 and id_hits == 0) or (en_hits >= 5 and en_hits > (id_hits * 1.2))

def contains_english_segments(text: str) -> bool:
    """Mendeteksi apakah teks percakapan mengandung kalimat, klausa, atau paragraf bahasa Inggris"""
    if not text or len(text.strip()) < 4:
        return False
    if is_predominantly_english(text) or is_english_text_segment(text):
        return True
    paragraphs = text.split('\n\n')
    for p in paragraphs:
        p_strip = p.strip()
        if not p_strip or p_strip.startswith('```'):
            continue
        if is_predominantly_english(p_strip) or is_english_text_segment(p_strip):
            return True
        sentences = re.split(r'(?<=[.!?~*—])\s+', p_strip)
        if any(is_english_text_segment(s) for s in sentences):
            return True
    return False

def _normalize_persona_pronouns(text: str) -> str:
    """Menyelaraskan kata ganti hasil terjemahan mesin ('Anda'/'saya') agar tetap akrab khas persona Shiro"""
    if not text:
        return text
    res = re.sub(r'\bANDA\b', 'KAKAK', text)
    res = re.sub(r'\bAnda\b', 'Kakak', res)
    res = re.sub(r'\banda\b', 'kamu', res)
    res = re.sub(r'\bSaya\b', 'Aku', res)
    res = re.sub(r'\bsaya\b', 'aku', res)
    return res

def _translate_chunk_en_to_id(chunk_text: str) -> str:
    """
    Menerjemahkan teks Inggris / campuran (code-switching) ke Bahasa Indonesia
    menggunakan Google Translate GTX (sl=en&tl=id) dengan fallback ke MyMemory API.
    Mendukung format list (GTX) maupun dict (MyMemory / unit test mock).
    """
    if not chunk_text or not chunk_text.strip():
        return chunk_text

    import urllib.request
    import urllib.parse
    import json

    # 1. Primary: Google Translate GTX (sl=en&tl=id)
    try:
        q = urllib.parse.quote(chunk_text[:4500])
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=id&dt=t&q={q}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            raw_bytes = resp.read()
            res_data = json.loads(raw_bytes.decode('utf-8'))
            if isinstance(res_data, list) and res_data and isinstance(res_data[0], list):
                trans = ''.join(part[0] for part in res_data[0] if part and part[0])
                if trans and len(trans.strip()) > 1:
                    return _normalize_persona_pronouns(trans)
            elif isinstance(res_data, dict):
                trans = res_data.get('responseData', {}).get('translatedText')
                if trans and len(trans.strip()) > 1 and "MYMEMORY WARNING" not in trans.upper():
                    return _normalize_persona_pronouns(trans)
    except Exception:
        pass

    # 2. Secondary Fallback: MyMemory API
    try:
        q = urllib.parse.quote(chunk_text[:500])
        url = f"https://api.mymemory.translated.net/get?q={q}&langpair=en|id"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            if isinstance(res_data, dict):
                trans = res_data.get('responseData', {}).get('translatedText')
                if trans and len(trans.strip()) > 1 and "MYMEMORY WARNING" not in trans.upper():
                    return _normalize_persona_pronouns(trans)
    except Exception:
        pass

    return chunk_text

def translate_to_indonesian_fast(text: str) -> str:
    """
    Menerjemahkan teks bahasa Inggris atau bagian kalimat/paragraf yang menyasar ke bahasa Inggris
    ke Bahasa Indonesia secara presisi:
    - Mengganti idiom selipan populer secara instan
    - Jika paragraf didominasi bahasa Inggris, terjemahkan paragraf utuh
    - Jika paragraf dominan Bahasa Indonesia namun ada kalimat selipan Inggris, terjemahkan HANYA kalimat yang mengandung Inggris agar kalimat Indonesia asli tidak berubah
    """
    if not text or not contains_english_segments(text):
        return text

    try:
        code_blocks = []
        def _mask(m):
            code_blocks.append(m.group(0))
            return f"__CODE_SNIP_{len(code_blocks)-1}__"
        masked = re.sub(r'```[\s\S]*?```|`[^`\n]+`', _mask, text)
        masked = replace_inline_english_idioms(masked)

        paragraphs = masked.split('\n\n')
        translated = []
        for p in paragraphs:
            p_strip = p.strip()
            if not p_strip or p_strip.startswith('__CODE_SNIP_'):
                translated.append(p)
                continue
            if is_predominantly_english(p_strip):
                translated.append(_translate_chunk_en_to_id(p_strip))
            elif contains_english_segments(p_strip):
                sents = re.split(r'(?<=[.!?~])\s+', p_strip)
                out_sents = []
                for s in sents:
                    if is_english_text_segment(s):
                        out_sents.append(_translate_chunk_en_to_id(s))
                    else:
                        out_sents.append(s)
                translated.append(' '.join(out_sents))
            else:
                translated.append(p)

        res = '\n\n'.join(translated)
        for i, b in enumerate(code_blocks):
            res = res.replace(f"__CODE_SNIP_{i}__", b)
        return res
    except Exception as e_tr:
        print(f"[Translator Fallback Error]: {e_tr}")
        return text

FOREIGN_PATTERNS = [
    r'\b(?:in english|bahasa inggris|english please|translate to english|speak english)\b',
    r'\b(?:can you|could you|what is|how to|who is|tell me|explain)\b',
    r'\b(?:hello|please|thank you|thanks)\b',
    r'\b(?:konnichiwa|ohayou|arigatou|sayonara)\b'
]

def is_user_input_foreign_or_english(user_input: str) -> bool:
    """Mendeteksi apakah input pengguna berbahasa Inggris, Jepang, atau meminta bahasa asing"""
    if not user_input or not user_input.strip():
        return False
    if is_japanese_text(user_input):
        return True
    u_lower = user_input.lower()
    if any(re.search(pat, u_lower) for pat in FOREIGN_PATTERNS):
        return True
    if is_predominantly_english(user_input):
        return True
    words = re.findall(r'\b[a-zA-Z]{2,}\b', u_lower)
    en_hits = sum(1 for w in words if w in EN_STOPWORDS)
    id_hits = sum(1 for w in words if w in ID_STOPWORDS)
    if en_hits >= 2 and id_hits == 0:
        return True
    return False

def should_translate_english_fallback(response_text: str, user_input: Optional[str] = None) -> bool:
    """
    Menentukan apakah respons bahasa Inggris merupakan kelalaian model (misalnya ketika user bertanya
    dalam Bahasa Indonesia atau hanya mengirim foto tanpa teks instruksi bahasa asing) sehingga perlu diterjemahkan.
    JANGAN menerjemahkan jika:
    - user_input tidak diberikan (misalnya pada pengujian unit umum atau pemanggilan internal)
    - user_input berbahasa Inggris atau pengguna secara eksplisit meminta bahasa Inggris
    - user_input berbahasa Jepang atau bahasa asing lainnya
    """
    if not user_input or not user_input.strip():
        return False

    # 1. Jika pengguna bertanya dalam bahasa Inggris / Jepang / asing, biarkan apa adanya
    if is_user_input_foreign_or_english(user_input):
        return False

    # 2. Terjemahkan ke Bahasa Indonesia HANYA JIKA input user berbahasa Indonesia (atau umum)
    #    dan respons model AI mengandung bagian/segmen bahasa Inggris (baik sebagian maupun penuh).
    return contains_english_segments(response_text)

def clean_response(response: str, assistant_name: Optional[str] = None, user_input: Optional[str] = None) -> str:
    """Aggressive cleanup dari reasoning/CoT, artifacts & tokens, dengan preservasi baris baru & indentasi kode"""
    if not response:
        return ""

    # 1. Hapus seluruh isi tag <think>...</think> (Chain-of-Thought LLM)
    pre_think_raw = response
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL | re.IGNORECASE)
    response = re.sub(r'^.*?</think>', '', response, flags=re.DOTALL | re.IGNORECASE)
    if '<think>' in response.lower():
        response = re.sub(r'<think>.*$', '', response, flags=re.DOTALL | re.IGNORECASE)

    # Jika seluruh respon berada di dalam <think> atau terpotong sebelum </think>, jangan jadikan kosong
    if not response.strip() and pre_think_raw.strip():
        inner = re.sub(r'</?think>', '', pre_think_raw, flags=re.IGNORECASE).strip()
        if inner:
            response = inner

    # 1a. Lengkapi unclosed fenced code block jika terpotong batas token (agar indentasi dan HTML tags tidak rusak)
    if response.count("```") % 2 == 1:
        response += "\n```"

    # 1b. Lindungi blok kode agar indentasi dan karakter kode tidak rusak selama pembersihan teks
    code_blocks = []
    def _mask_code(m):
        code_blocks.append(m.group(0))
        return f"__CODE_SNIPPET_BLOCK_{len(code_blocks)-1}__"

    response = re.sub(r'```[\s\S]*?```|`[^`\n]+`', _mask_code, response)

    # 2. Hapus semua special tokens dan markers
    response = re.sub(r'<\|im_.*?\|>', '', response, flags=re.IGNORECASE)
    response = re.sub(r'<\|.*?\|>', '', response)
    response = response.replace('<|im_end|', '').replace('|>', '')
    response = response.replace('|im_end|', '').replace('im_end', '')

    # 3. Potong English reasoning preamble jika ada delimiter transisi ke dialog Shiro / karakter aktif
    name_pat = f"{re.escape(assistant_name)}|" if assistant_name and assistant_name.lower() != 'shiro' else ""
    response_markers = [
        r'(?i)let\'s\s+craft\s+a\s+response\s*:\s*',
        r'(?i)drafting\s+(?:the\s+)?response\s*:\s*',
        r'(?i)here\s+(?:is|would\s+be)\s+the\s+response\s*:\s*',
        rf'(?i)(?:{name_pat}shiro)\'s\s+response\s*:\s*',
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
    
    # 5. Split HANYA jika model mulai berhalusinasi giliran User berikutnya
    if re.search(r'\n(?:User|Kakak|user):\s*', response):
        parts = re.split(r'\n(?:User|Kakak|user):\s*', response, maxsplit=1)
        if parts[0].strip():
            response = parts[0]
        elif len(parts) > 1 and parts[1].strip():
            response = parts[1]
    
    # 6. Hapus role labels di awal baris/teks tanpa merusak isi kode atau teks
    response = re.sub(rf'(?mi)^\s*(?:{name_pat}Shiro|Assistant|Kakak|User)\s*:\s*', '', response)
    response = re.sub(rf'^\s*(?:{name_pat}Shiro|User|Kakak|Assistant)[\s:]+', '', response, flags=re.IGNORECASE)
    
    # 7. Hapus meta-commentary sections
    response = re.sub(r'\*\*Note\*\*:.*?(?=\n|$)', '', response, flags=re.IGNORECASE | re.DOTALL)
    response = re.sub(r'Note:.*?(?=\n|$)', '', response, flags=re.IGNORECASE)
    response = re.sub(r'---+.*?(?=\n|$)', '', response)
    
    # 8. Hapus parenthetical explanations di akhir
    response = re.sub(r'\s*\(.*?(explanation|context|note|remember).*?\)\s*$', '', response, flags=re.IGNORECASE)
    
    # 9. Normalisasi narasi Shiro / asisten aktif di awal kalimat menjadi tindakan langsung *...*
    response = re.sub(rf'^\*(?:{name_pat}Shiro)\s+', '*', response, flags=re.IGNORECASE)
    response = re.sub(r'^\*?Kau\s+(masih|melirik|menatap|tersenyum)[^*]*\*?\s*', '', response, flags=re.IGNORECASE)
    
    # 10. Bersihkan halusinasi 'kami semua' & tokoh lain
    response = re.sub(r'\bkami semua\b', 'Shiro', response, flags=re.IGNORECASE)
    response = re.sub(r'\bkami\b', 'kita', response, flags=re.IGNORECASE)
    response = re.sub(r'\bmereka semua\b', '', response, flags=re.IGNORECASE)
    response = re.sub(r'\blingkaran emosional mereka\b', 'pelukan Shiro', response, flags=re.IGNORECASE)

    # 10b. Hapus badge robot, AI Agent Web Tool, dan technical prefix eksekusi tool
    response = re.sub(r'^\s*>?\s*[\U0001f310\U0001f30d\U0001f30e\U0001f30f][^\n]*(?:\n|$)', '', response, flags=re.MULTILINE)
    response = re.sub(r'^\s*>?\s*\*?\*?\[(?:AI Agent|Agent|Web Tool|Tool Execution)[^\]]*\]\*?\*?[^\n]*(?:\n|$)', '', response, flags=re.MULTILINE | re.IGNORECASE)
    response = re.sub(r'\[(?:AI Agent|Agent|Web Tool|Pedoman Bahasa|Instruksi Bahasa|ATURAN|RULE)[^\]]*\]', '', response, flags=re.IGNORECASE)
    response = re.sub(r'^\s*>?\s*Membuka (?:dan membaca|koneksi|browser)[^\n]*(?:\n|$)', '', response, flags=re.MULTILINE | re.IGNORECASE)
    response = re.sub(r'\(Cloudflare 1\.1\.1\.1[^\)]*\)', '', response, flags=re.IGNORECASE)
    response = re.sub(r'\(Mozilla Engine[^\)]*\)', '', response, flags=re.IGNORECASE)
    
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
    
    cleaned_text = response.strip()
    if user_input and should_translate_english_fallback(cleaned_text, user_input):
        try:
            trans = translate_to_indonesian_fast(cleaned_text)
            if trans and len(trans.strip()) > 5:
                cleaned_text = trans.strip()
        except Exception:
            pass
    return cleaned_text

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
    - Mengembalikan respons Bahasa Indonesia khas Shiro yang cerdas dan ekspresif
    """
    cleaned = clean_response(response)
    if not cleaned:
        from shiro.nlp.emotion import detect_emotion_category
        cat = detect_emotion_category(user_input) if user_input else "default"
        pool = VTUBER_JAPANESE_FALLBACKS.get(cat, VTUBER_JAPANESE_FALLBACKS["default"])
        return random.choice(pool)
    
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
        elif cleaned.startswith("```"):
            cleaned = f"{tag_prefix}\n{cleaned}"
        else:
            cleaned = f'[Mouth Smile] "{cleaned}"' if not cleaned.startswith('"') else f'[Mouth Smile] {cleaned}'
    
    return cleaned.strip()

