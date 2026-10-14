# -*- coding: utf-8 -*-
"""
Shiro Vision Inspection & Local Ingestion
Provides local image inspection (resolution, brightness, aspect ratio) and OCR (easyocr / pytesseract)
when needed for debugging or as a fallback when vision projector is offline.
"""

from typing import List, Optional

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
