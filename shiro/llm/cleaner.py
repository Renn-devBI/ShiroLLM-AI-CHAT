# -*- coding: utf-8 -*-
"""
LLM Output Cleaner and Validator
Ensures 100% pure persona output: strips CoT reasoning, special tokens,
enforces Indonesian language purity, and preserves linebreaks/paragraphs.
"""

import re
from typing import Set

FORBIDDEN_TOKENS = [
    '<|im_end|>', '<|im_start|>', '###', '```',
    'Note:', '**Note**:', '---', '[reasoning', '[explanation',
    '(This is', '(As Shiro', '(I am', 'assistant:', 'user:',
    '<think>', '</think>'
]

META_PATTERNS = [
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
    'main', 'bareng', 'nanti'
}

def validate_response(response: str, user_input: str = "") -> bool:
    """Validasi respons untuk memastikan tidak halusinasi, tidak bocor proses berpikir (CoT), dan berbahasa Indonesia"""
    if not response or len(response.strip()) < 3:
        return False
    
    if any(token in response for token in FORBIDDEN_TOKENS):
        return False
    
    if any(re.search(pattern, response, re.IGNORECASE) for pattern in META_PATTERNS):
        return False

    words = re.findall(r'\b[a-zA-Z]{2,}\b', response.lower())
    if len(words) >= 5:
        en_count = sum(1 for w in words if w in EN_STOPWORDS)
        id_count = sum(1 for w in words if w in ID_STOPWORDS)
        if en_count >= 3 and en_count > id_count:
            return False
    
    if len(response) > 800:
        return False
    
    if len(response.strip()) < 5:
        return False
    
    if not any(char.isalpha() for char in response):
        return False
    
    return True

def clean_response(response: str) -> str:
    """Aggressive cleanup dari reasoning/CoT, artifacts & tokens, dengan preservasi baris baru"""
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
    
    # 11. Hapus tanda baca berlebih
    response = re.sub(r'\.{3,}', '...', response)
    response = re.sub(r'!{2,}', '!', response)
    response = re.sub(r'\?{2,}', '?', response)
    
    # 12. Hapus whitespace horizontal berlebih namun pertahankan pemisahan baris / paragraf (Shift+Enter)
    response = response.replace('\r\n', '\n').replace('\r', '\n')
    response = re.sub(r'[ \t]+', ' ', response)
    response = re.sub(r' +([.,!?])', r'\1', response)
    response = re.sub(r'\n{3,}', '\n\n', response)
    response = '\n'.join([line.strip() for line in response.split('\n')])
    
    # 13. Hapus HTML/XML remnants
    response = re.sub(r'</?[^>]+>', '', response)
    
    # 14. Clean up <3 emoji
    response = response.replace('<3>', '❤️')
    
    return response.strip()
