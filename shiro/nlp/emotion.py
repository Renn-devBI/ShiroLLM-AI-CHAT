# -*- coding: utf-8 -*-
"""
Emotion and Sentiment Analysis Module for Shiro LLMA
Classifies user intent and emotion to tune Shiro's persona response
"""

def detect_emotion_category(text: str) -> str:
    """Deteksi kategori emosi dari teks input pengguna"""
    if not text:
        return "neutral"
    
    u_lower = text.lower()
    
    # Romantic / Love / Longing
    if any(x in u_lower for x in ["sayang", "cinta", "love", "peluk", "kangen", "rindu", "syg"]):
        return "romantic"
    
    # Jealous
    if any(x in u_lower for x in ["cewek", "perempuan", "pacar", "cantik", "gadis"]) and \
       "kamu" not in u_lower and "shiro" not in u_lower:
        return "jealous"
    
    # Happy
    if any(x in u_lower for x in ["bagus", "keren", "hebat", "senang", "ayo", "main", "seru"]):
        return "happy"
    
    # Sad / Apologetic / Angry
    if any(x in u_lower for x in ["maaf", "sedih", "nangis", "jahat", "benci"]):
        return "sad"
    
    return "neutral"
