# -*- coding: utf-8 -*-
"""
Shiro Vision Inspection & Local Ingestion
Provides local image inspection (resolution, brightness, aspect ratio) and OCR (easyocr / pytesseract)
when running models in text-only mode or as fallback when vision projector is offline.
"""

from typing import List, Optional

_CACHED_READER = None
_READER_TRIED = False

def get_ocr_reader():
    """Mengambil instance EasyOCR reader ter-cache agar proses OCR cepat tanpa delay inisialisasi"""
    global _CACHED_READER, _READER_TRIED
    if _CACHED_READER is not None:
        return _CACHED_READER
    if _READER_TRIED:
        return None
    _READER_TRIED = True
    try:
        import easyocr
        import torch
        use_gpu = torch.cuda.is_available()
        _CACHED_READER = easyocr.Reader(['id', 'en'], gpu=use_gpu, verbose=False)
        print(f"[Vision OCR] EasyOCR engine aktif (GPU: {use_gpu})")
        return _CACHED_READER
    except Exception as e:
        print(f"[Vision OCR Notice] EasyOCR tidak aktif: {e}")
        return None

def extract_local_image_text_and_info(images: List[str]) -> Optional[str]:
    """
    Ekstraksi teks lokal (OCR via easyocr / pytesseract) dan analisis metadata visual (resolusi,
    warna/luminance, rasio) untuk menyuplai fakta visual secara lokal tanpa dependensi eksternal.
    """
    if not images:
        return None
    try:
        from PIL import Image, ImageStat
        import io
        import base64

        info_lines = []
        reader = get_ocr_reader()

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
            # 1. Coba EasyOCR terlebih dahulu (akurat dan cepat dengan GPU)
            if reader:
                try:
                    import numpy as np
                    results = reader.readtext(np.array(pil_img))
                    extracted_words = [res[1].strip() for res in results if res[1].strip()]
                    ocr_text = " ".join(extracted_words).strip()
                except Exception as e_ocr:
                    print(f"[Vision OCR Exec]: {e_ocr}")

            # 2. Fallback ke PyTesseract jika EasyOCR belum ada
            if not ocr_text:
                try:
                    import pytesseract
                    ocr_text = pytesseract.image_to_string(pil_img).strip()
                except Exception:
                    pass

            frame_label = f"Gambar #{i+1}" if len(images) > 1 else "Gambar"
            line = f"- {frame_label} ({fmt}, {w}x{h} px, rasio {aspect}:1, {theme_desc})"
            if ocr_text:
                line += f":\n  [Teks terbaca pada gambar]: \"{ocr_text[:3000]}\""
            else:
                line += f":\n  [Gambar/tangkapan layar terlampir tanpa teks terdeteksi]"
            info_lines.append(line)

        if info_lines:
            return "\n".join(info_lines)
    except Exception as e:
        print(f"[Vision Local Info]: {e}")
    return None

def analyze_visual_bridge(images: List[str], query_text: str = "") -> Optional[str]:
    """
    Fungsi kompatibilitas: Mengembalikan informasi visual lokal tanpa dependensi eksternal.
    """
    if not images:
        return None
    local_info = extract_local_image_text_and_info(images)
    if local_info:
        return f"[Hasil Analisis Visual Lokal & Ekstraksi]:\n{local_info}"
    return f"- Gambar visual terlampir ({len(images)} berkas gambar/screenshot)."
