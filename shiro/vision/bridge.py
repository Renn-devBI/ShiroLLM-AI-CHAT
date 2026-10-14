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
    """
    Mengambil API Key Gemini dari berbagai sumber:
    1. Header HTTP permintaan aktif (X-Gemini-Key / X-Google-Key)
    2. Body JSON permintaan aktif
    3. Google Colab Secrets (userdata)
    4. Environment variables (GEMINI_API_KEY, GOOGLE_API_KEY, GEMINI_KEY)
    5. Konfigurasi model_config.json & api_key.json
    6. File Google Drive / Drive Shiro Memory
    7. File .env lokal
    """
    # 1. Periksa Flask request context jika sedang dalam siklus request
    try:
        from flask import has_request_context, request
        if has_request_context():
            for hdr in ["X-Gemini-Key", "X-Google-Key", "X-Gemini-Api-Key"]:
                val = request.headers.get(hdr)
                if val and str(val).strip():
                    return str(val).strip()
            if request.is_json and request.json:
                for k in ["gemini_api_key", "google_api_key", "gemini_key"]:
                    val = request.json.get(k)
                    if val and str(val).strip():
                        return str(val).strip()
    except Exception:
        pass

    # 2. Periksa Google Colab Secrets (userdata)
    try:
        from google.colab import userdata
        for k in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY"]:
            val = userdata.get(k)
            if val and str(val).strip():
                return str(val).strip()
    except Exception:
        pass

    # 3. Periksa environment variables
    for env_var in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY"]:
        val = os.environ.get(env_var, "").strip()
        if val:
            return val

    # 4. Periksa file json konfigurasi
    for json_file in ["model_config.json", "api_key.json"]:
        if os.path.exists(json_file):
            try:
                with open(json_file, "r", encoding="utf-8") as f_json:
                    jdata = json.load(f_json)
                    for k in ["gemini_api_key", "google_api_key", "gemini_key"]:
                        if jdata.get(k):
                            return str(jdata[k]).strip()
            except Exception:
                pass

    # 5. Periksa file Google Drive di Colab
    colab_drive_files = [
        "/content/drive/MyDrive/gemini_key.txt",
        "/content/drive/MyDrive/.env",
        "/content/drive/MyDrive/api_key.json",
        "/content/drive/MyDrive/Shiro_Memory/api_key.json"
    ]
    for p in colab_drive_files:
        if os.path.exists(p):
            try:
                if p.endswith(".json"):
                    with open(p, "r", encoding="utf-8") as fj:
                        jd = json.load(fj)
                        for k in ["gemini_api_key", "google_api_key", "gemini_key"]:
                            if jd.get(k):
                                return str(jd[k]).strip()
                elif p.endswith(".env"):
                    with open(p, "r", encoding="utf-8") as fe:
                        for line in fe:
                            if "=" in line:
                                k, v = line.strip().split("=", 1)
                                if k.strip() in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY"] and v.strip():
                                    return v.strip().strip("'\"")
                else:
                    with open(p, "r", encoding="utf-8") as ft:
                        val = ft.read().strip()
                        if val:
                            return val
            except Exception:
                pass

    # 6. Periksa file .env lokal
    possible_env_paths = [
        ".env",
        os.path.join("..", ".env"),
        os.path.join("data", ".env"),
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

def extract_local_image_text_and_info(images: List[str]) -> Optional[str]:
    """
    Ekstraksi teks lokal (OCR via easyocr / pytesseract) dan analisis metadata visual (resolusi,
    warna/luminance, rasio) untuk menyuplai fakta visual saat model berjalan dalam mode teks murni.
    """
    if not images:
        return None
    try:
        from PIL import Image, ImageStat
        import io
        import base64
        
        info_lines = []
        for i, img in enumerate(images[:4]):
            clean_b64 = img.split(",", 1)[1] if "," in img else img
            raw_bytes = base64.b64decode(clean_b64)
            pil_img = Image.open(io.BytesIO(raw_bytes))
            w, h = pil_img.size
            fmt = pil_img.format or "JPEG"
            aspect = round(w / max(1, h), 2)
            
            # Deteksi brightness rata-rata (gelap/terang -> deteksi IDE / dark mode / foto luar)
            theme_desc = "tampilan normal"
            try:
                gray_img = pil_img.convert('L')
                stat = ImageStat.Stat(gray_img)
                avg_luma = stat.mean[0]
                if avg_luma < 75:
                    theme_desc = "tampilan gelap/dark mode (kemungkinan IDE/editor/layar konsol)"
                elif avg_luma > 200:
                    theme_desc = "tampilan sangat terang/dokumen kertas"
            except Exception:
                pass
            
            ocr_text = ""
            # Coba EasyOCR terlebih dahulu (populer dan akurat di Colab / GPU)
            try:
                import easyocr
                import numpy as np
                reader = easyocr.Reader(['id', 'en'], gpu=False, verbose=False)
                results = reader.readtext(np.array(pil_img))
                ocr_text = " ".join([res[1] for res in results]).strip()
            except Exception:
                pass

            # Fallback ke PyTesseract
            if not ocr_text:
                try:
                    import pytesseract
                    ocr_text = pytesseract.image_to_string(pil_img).strip()
                except Exception:
                    pass
            
            frame_label = f"Gambar #{i+1}" if len(images) > 1 else "Gambar"
            line = f"- {frame_label} ({fmt}, {w}x{h} px, rasio {aspect}:1, {theme_desc})"
            if ocr_text:
                line += f":\n  [Teks terbaca pada gambar/layar]:\n  {ocr_text[:2000]}"
            else:
                line += f":\n  [Objek visual terdeteksi: Gambar/screenshot beresolusi {w}x{h}]"
            info_lines.append(line)
                
        if info_lines:
            return "\n".join(info_lines)
    except Exception as e:
        print(f"[Visual Bridge Local Info]: {e}")
    return None

def analyze_visual_bridge(images: List[str], query_text: str = "") -> Optional[str]:
    """
    Menganalisis visual (screenshot desktop, foto, atau sequential video frames)
    secara objektif menggunakan Gemini Vision API sebagai visual bridge,
    dengan fallback otomatis ke local OCR & inspection jika Gemini tidak aktif.
    """
    if not images:
        return None

    gemini_key = get_gemini_api_key()
    if gemini_key:
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
                    "Analisis gambar/screenshot/foto ini secara objektif dan akurat. "
                    "Jelaskan: (1) Siapa atau apa objek/karakter/tokoh/pemandangan/aplikasi di gambar; "
                    "(2) Semua teks, tulisan, judul, atau kode jika ada; (3) Suasana/aktivitas.\n"
                )
                if clean_user_q:
                    prompt += f"Pertanyaan spesifik pengguna: \"{clean_user_q}\""
                    
            parts.append({"text": prompt})
            for img in images[:8]:  # Maksimal 8 frame untuk efisiensi
                clean_b64 = img.split(",", 1)[1] if "," in img else img
                mime = "image/png" if img.startswith("data:image/png") else "image/jpeg"
                parts.append({"inline_data": {"mime_type": mime, "data": clean_b64}})

            req_data = {"contents": [{"parts": parts}]}
            for model_id in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
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
            print(f"[Visual Bridge] Warning calling Gemini: {e_vis}")

    # Fallback lokal: OCR & info gambar
    local_info = extract_local_image_text_and_info(images)
    if local_info:
        return f"[Hasil Analisis Visual Lokal & Ekstraksi]:\n{local_info}"
    return f"- Gambar visual terlampir ({len(images)} berkas gambar/screenshot)."
