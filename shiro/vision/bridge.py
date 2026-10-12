# -*- coding: utf-8 -*-
"""
Shiro Visual Bridge & Multimodal Ingestion
Translates screenshots, webcam images, documents, and sequential video frames into rich visual context
for models running in text-only mode or as fallback when vision projector is not locally active.
"""

import os
import json
import urllib.request
from typing import List, Optional

def get_gemini_api_key() -> Optional[str]:
    """Mengambil API Key Gemini dari environment atau file .env"""
    for env_var in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY"]:
        val = os.environ.get(env_var, "").strip()
        if val:
            return val
            
    possible_env_paths = [
        ".env",
        os.path.join("..", ".env"),
        r"D:\Downloads\vtuber\.env",
    ]
    for p in possible_env_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY"] and v:
                            return v
            except Exception:
                pass
    return None

def analyze_visual_bridge(images: List[str], query_text: str = "") -> Optional[str]:
    """
    Menganalisis visual (screenshot desktop, foto webcam, atau sequential video frames)
    secara objektif menggunakan Gemini Vision API sebagai visual bridge.
    Tidak menginjeksi prompt percakapan palsu.
    """
    gemini_key = get_gemini_api_key()
    if not gemini_key or not images:
        return None
    try:
        parts = []
        is_video_stream = len(images) > 1
        clean_user_q = query_text.strip() if query_text else ""
        
        if is_video_stream:
            prompt = (
                f"Analisis rangkaian {len(images)} frame visual secara objektif dan kronologis. "
                f"Jelaskan urutan kejadian, perubahan posisi/objek, peristiwa kunci, dan aktivitas visual.\n"
            )
            if clean_user_q:
                prompt += f"Pertanyaan spesifik pengguna: \"{clean_user_q}\""
        else:
            prompt = (
                "Analisis visual/screenshot/tampilan desktop/diagram ini secara objektif dan akurat. "
                "Sertakan: (1) Objek, elemen UI/desktop; (2) Teks, pesan error, kode (OCR); "
                "(3) Diagram/grafik/tabel jika ada.\n"
            )
            if clean_user_q:
                prompt += f"Pertanyaan spesifik pengguna: \"{clean_user_q}\""
                
        parts.append({"text": prompt})
        for img in images[:8]:  # Maksimal 8 frame untuk efisiensi
            clean_b64 = img.split(",", 1)[1] if "," in img else img
            mime = "image/png" if img.startswith("data:image/png") else "image/jpeg"
            parts.append({"inline_data": {"mime_type": mime, "data": clean_b64}})

        req_data = {"contents": [{"parts": parts}]}
        for model_id in ["gemini-2.5-flash", "gemini-1.5-flash"]:
            try:
                req_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={gemini_key}"
                req = urllib.request.Request(
                    req_url,
                    data=json.dumps(req_data).encode('utf-8'),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp_json = json.loads(resp.read().decode('utf-8'))
                    return resp_json['candidates'][0]['content']['parts'][0]['text'].strip()
            except Exception:
                continue
    except Exception as e_vis:
        print(f"[Visual Bridge] Warning: {e_vis}")
    return None
