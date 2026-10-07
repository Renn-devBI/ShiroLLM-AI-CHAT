# -*- coding: utf-8 -*-
"""
Typo and Slang Intelligence Helper for Shiro LLMA
Membantu Shiro memahami pesan Kakak dengan toleransi tinggi terhadap:
1. Salah ketik (Typo)
2. Huruf tertukar atau hilang
3. Singkatan chat Indonesia (bca, klo, bsa, tlg, skrg, gmn, dll)
4. Bahasa gaul / santai
"""

import re
from typing import Dict, List, Tuple, Any

# Kamus singkatan chat dan typo bahasa Indonesia yang umum
INDONESIAN_CHAT_TYPOS: Dict[str, str] = {
    # Tokoh & Persona
    "shrio": "shiro",
    "shirou": "shiro",
    "siro": "shiro",
    "shiroo": "shiro",
    "kk": "kakak",
    "kak": "kakak",
    
    # Kata Tanya
    "apkh": "apakah",
    "apkah": "apakah",
    "apk": "apakah",
    "knp": "kenapa",
    "knpa": "kenapa",
    "knpah": "kenapa",
    "gmn": "gimana",
    "gmna": "gimana",
    "gemana": "gimana",
    "gmana": "gimana",
    "bgmn": "bagaimana",
    "bgmna": "bagaimana",
    "syp": "siapa",
    "spe": "siapa",
    "brp": "berapa",
    "brapa": "berapa",
    "dmna": "dimana",
    "dmn": "dimana",
    "kmn": "kemana",
    "kmna": "kemana",
    
    # Kata Kerja (Verbs)
    "bca": "baca",
    "bcaa": "baca",
    "bc": "baca",
    "liat": "lihat",
    "liatt": "lihat",
    "lyt": "lihat",
    "lht": "lihat",
    "cba": "coba",
    "tlg": "tolong",
    "tlong": "tolong",
    "ingt": "ingat",
    "inget": "ingat",
    "bljr": "belajar",
    "bljar": "belajar",
    "maen": "main",
    "msk": "masuk",
    "ngerti": "mengerti",
    "ngrt": "mengerti",
    "faham": "paham",
    "cr": "cari",
    "cri": "cari",
    "bka": "buka",
    "bkin": "bikin",
    "bkn": "bukan",
    
    # Modalitas & Kata Bantu
    "bsa": "bisa",
    "bisaa": "bisa",
    "klo": "kalau",
    "kalo": "kalau",
    "klu": "kalau",
    "klw": "kalau",
    "kl": "kalau",
    "udh": "sudah",
    "uda": "sudah",
    "sdh": "sudah",
    "blm": "belum",
    "blom": "belum",
    "blum": "belum",
    "lg": "lagi",
    "lgi": "lagi",
    "mauu": "mau",
    "mw": "mau",
    
    # Kata Hubung & Preposisi
    "dgn": "dengan",
    "dg": "dengan",
    "yg": "yang",
    "yng": "yang",
    "sm": "sama",
    "sma": "sama",
    "dri": "dari",
    "krn": "karena",
    "karna": "karena",
    "jd": "jadi",
    "jdi": "jadi",
    "ttg": "tentang",
    "utk": "untuk",
    "buat": "untuk",
    
    # Adverbia & Sifat
    "bgt": "banget",
    "bngt": "banget",
    "bnget": "banget",
    "skrg": "sekarang",
    "skrng": "sekarang",
    "skr": "sekarang",
    "bnr": "benar",
    "bener": "benar",
    "beneran": "benar",
    "cm": "cuma",
    "cma": "cuma",
    "sdkt": "sedikit",
    "bnyk": "banyak",
    "kbr": "kabar",
    "kbrnya": "kabarnya",
    "webny": "webnya",
    "linkny": "linknya",
    "pake": "pakai",
    "pkai": "pakai",
    
    # Emosi & Kasih Sayang
    "mksh": "terima kasih",
    "mksih": "terima kasih",
    "makasi": "terima kasih",
    "makasih": "terima kasih",
    "thx": "terima kasih",
    "syg": "sayang",
    "syng": "sayang",
    "rndu": "rindu",
    "kangen": "rindu",
    
    # Negasi
    "ga": "tidak",
    "gak": "tidak",
    "gk": "tidak",
    "ngga": "tidak",
    "nggak": "tidak",
    "tdk": "tidak",
    "gpp": "tidak apa-apa",
    "gapapa": "tidak apa-apa"
}

def normalize_typos(text: str) -> Tuple[str, List[Dict[str, str]]]:
    """
    Menormalisasi typo dan singkatan chat umum bahasa Indonesia.
    Mengembalikan (normalized_text, list_koreksi).
    URL di dalam teks dijamin aman dan tidak disentuh.
    """
    if not text:
        return "", []

    # Simpan URL agar tidak terganggu proses normalisasi
    url_pattern = r'https?://[^\s<>"\')]+'
    saved_urls: List[str] = []
    
    def save_url_match(match):
        idx = len(saved_urls)
        saved_urls.append(match.group(0))
        return f"__URL_PLACEHOLDER_{idx}__"

    protected_text = re.sub(url_pattern, save_url_match, text)

    corrections = []
    words = re.split(r'(\s+|[.,;!?()]+)', protected_text)
    
    for i, word in enumerate(words):
        word_clean = word.strip()
        word_lower = word_clean.lower()
        if word_lower in INDONESIAN_CHAT_TYPOS:
            normalized_replacement = INDONESIAN_CHAT_TYPOS[word_lower]
            # Pertahankan kapitalisasi jika huruf pertama kapital
            if word_clean and word_clean[0].isupper():
                normalized_replacement = normalized_replacement.capitalize()
            words[i] = normalized_replacement
            corrections.append({
                "original": word_clean,
                "corrected": normalized_replacement
            })

    normalized_text = "".join(words)

    # Kembalikan URL yang disimpan
    for idx, u in enumerate(saved_urls):
        normalized_text = normalized_text.replace(f"__URL_PLACEHOLDER_{idx}__", u)

    return normalized_text, corrections

def get_typo_understanding_prompt(corrections: List[Dict[str, str]]) -> str:
    """
    Jika ada typo signifikan pada pesan Kakak, buat prompt pengarah tersembunyi
    agar model LLM memahami maksud sebenarnya dengan tepat tanpa mengoreksi balik Kakak.
    """
    if not corrections:
        return ""
    
    summary_corrections = ", ".join([f"'{c['original']}' -> {c['corrected']}" for c in corrections[:5]])
    return (
        f"\n[Catatan Pemahaman Bahasa: Pesan Kakak mengandung singkatan/salah ketik: ({summary_corrections}). "
        f"Tangkap maksud sebenarnya dan langsung jawab dengan gaya cerdas dan manja khas Shiro tanpa mengkritik typo Kakak.]\n"
    )
