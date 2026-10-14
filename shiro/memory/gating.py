# -*- coding: utf-8 -*-
"""
Shiro Semantic Memory Gating
Menyaring fakta memori jangka panjang agar hanya fakta yang relevan dengan pesan saat ini
yang masuk ke prompt. Saat gambar baru dilampirkan, fakta bertema web/URL dikarantina
supaya model tidak mengaitkan gambar baru dengan situs dari percakapan lama.
"""

import re
from typing import Any, Dict, Iterable, List, Set

WEB_MARKERS = (
    "http", "www.", ".com", ".net", ".org", ".id", ".io", ".tv", ".xyz",
    "situs", "url", "link", "website", "web", "halaman", "domain", "browser",
)

# Kata umum bahasa Indonesia/Inggris yang tidak bermakna untuk pencocokan relevansi
STOPWORDS: Set[str] = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "ada", "aku", "kamu", "kak", "kakak",
    "shiro", "saya", "dia", "apa", "coba", "lihat", "tolong", "ya", "dong", "sih", "nih",
    "deh", "juga", "untuk", "dengan", "pada", "atau", "tidak", "gak", "nggak", "bisa",
    "mau", "the", "a", "an", "is", "are", "to", "of", "and", "in", "on", "for", "it",
    "gambar", "foto", "image", "suka", "punya", "adalah", "sudah", "akan", "lagi",
}

DOMAIN_RE = re.compile(r"\b[a-z0-9][a-z0-9-]{1,62}\.(?:com|net|org|id|io|tv|xyz|co|me|info|site|app)\b", re.IGNORECASE)


def tokenize(text: str) -> Set[str]:
    """Pecah teks menjadi token kata bermakna (huruf kecil, tanpa stopword)."""
    words = re.findall(r"[a-zA-Z0-9]{3,}", (text or "").lower())
    return {w for w in words if w not in STOPWORDS}


def fact_text(fact: Dict[str, Any]) -> str:
    return f"{fact.get('subject', '')} {fact.get('predicate', '')} {fact.get('object', '')}"


def is_web_fact(fact: Dict[str, Any]) -> bool:
    """Deteksi fakta yang berkaitan dengan situs web/URL/aktivitas browsing."""
    blob = fact_text(fact).lower()
    category = str(fact.get("category", "") or fact.get("type", "")).lower()
    if category in {"web_browsing", "url_history", "web"}:
        return True
    return any(m in blob for m in WEB_MARKERS) or bool(DOMAIN_RE.search(blob))


def gate_facts(
    facts: Iterable[Dict[str, Any]],
    query: str,
    has_image: bool = False,
    min_confidence: float = 0.7,
    max_facts: int = 5,
) -> List[Dict[str, Any]]:
    """
    Pilih fakta paling relevan untuk pesan saat ini.

    Aturan:
    1. Fakta dengan confidence di bawah ambang dibuang.
    2. Jika ada gambar baru (has_image), fakta web/URL dikarantina.
    3. Fakta diberi skor berdasarkan irisan kata dengan query. Fakta identitas inti
       (nama/panggilan Kakak) selalu diizinkan dengan skor kecil agar persona tetap konsisten.
    4. Saat ada gambar, hanya fakta yang benar-benar relevan (skor > 0) yang masuk,
       supaya memori lama tidak mengaburkan observasi visual.
    """
    query_tokens = tokenize(query)
    scored = []
    for fact in facts or []:
        if fact.get("confidence", 0) < min_confidence:
            continue
        if has_image and is_web_fact(fact):
            continue

        f_tokens = tokenize(fact_text(fact))
        overlap = len(query_tokens & f_tokens)
        score = float(overlap)

        predicate = str(fact.get("predicate", "")).lower()
        if any(k in predicate for k in ("nama", "name", "dipanggil", "panggilan")):
            score += 0.5

        if has_image and score <= 0:
            continue
        scored.append((score, fact.get("confidence", 0), fact))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [f for _, _, f in scored[:max_facts]]


def find_ungrounded_domains(reply: str, allowed_sources: Iterable[str]) -> List[str]:
    """
    Temukan nama domain di balasan model yang tidak berasal dari sumber yang sah
    (pesan pengguna, bukti visual, hasil tool web). Digunakan oleh grounding verifier.
    """
    allowed_blob = " ".join(s for s in allowed_sources if s).lower()
    found = []
    for m in DOMAIN_RE.finditer(reply or ""):
        dom = m.group(0).lower()
        if dom not in allowed_blob and dom not in found:
            found.append(dom)
    return found
