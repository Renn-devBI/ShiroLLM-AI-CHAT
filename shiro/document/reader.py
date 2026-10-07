"""
Document & Folder Reader Module for Shiro LLMA.
Supports:
- PDF (.pdf) via pypdf
- Word (.docx, .doc) via python-docx
- Plain text & code (.txt, .md, .json, .csv, .py, .log, .html, .xml)
- Folder batch reading
- Intent detection: Rangkum (Summarize) vs Perbaiki (Proofread/Fix) vs Tanya Jawab (Q&A)
"""

import os
import re
from typing import Dict, Any, Optional, List

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".json", ".csv",
    ".log", ".py", ".html", ".xml", ".yaml", ".yml",
    ".ini", ".cfg", ".sql", ".js", ".css", ".tsv"
}

def extract_text_from_file(file_path: str, filename: Optional[str] = None, max_chars: int = 15000) -> Dict[str, Any]:
    """
    Extract readable text from a supported document file.
    Truncates gracefully if content exceeds max_chars to preserve LLM context budget.
    """
    if not filename:
        filename = os.path.basename(file_path)

    ext = os.path.splitext(filename)[1].lower()
    
    if not os.path.exists(file_path):
        return {
            "success": False,
            "filename": filename,
            "error": "File tidak ditemukan.",
            "text": ""
        }

    extracted_text = ""
    page_count = None
    file_type = "text"

    try:
        # 1. PDF File Extraction
        if ext == ".pdf":
            file_type = "pdf"
            import pypdf
            reader = pypdf.PdfReader(file_path)
            page_count = len(reader.pages)
            pages_text = []
            for i, page in enumerate(reader.pages):
                txt = page.extract_text() or ""
                if txt.strip():
                    pages_text.append(f"--- [Halaman {i+1}] ---\n{txt.strip()}")
            extracted_text = "\n\n".join(pages_text)

        # 2. Word (.docx) Extraction
        elif ext in (".docx", ".doc"):
            file_type = "docx"
            try:
                import docx
                doc = docx.Document(file_path)
                paras = [p.text for p in doc.paragraphs if p.text.strip()]
                # Also extract table text
                for table in doc.tables:
                    for row in table.rows:
                        row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                        if row_text:
                            paras.append(f"[Tabel] {row_text}")
                extracted_text = "\n".join(paras)
            except Exception as e_docx:
                # Fallback to plain text search if corrupted or older .doc
                with open(file_path, "rb") as f_raw:
                    raw_data = f_raw.read()
                clean_chars = [chr(c) for c in raw_data if 32 <= c <= 126 or c in (10, 13)]
                extracted_text = "".join(clean_chars)[:max_chars]

        # 3. Plain Text / Code / CSV / JSON
        else:
            file_type = ext.replace(".", "") or "text"
            encodings = ["utf-8", "cp1252", "latin-1", "utf-16"]
            for enc in encodings:
                try:
                    with open(file_path, "r", encoding=enc) as f_txt:
                        extracted_text = f_txt.read()
                    break
                except UnicodeDecodeError:
                    continue
                except Exception:
                    break

        extracted_text = extracted_text.strip()
        if not extracted_text:
            return {
                "success": False,
                "filename": filename,
                "file_type": file_type,
                "error": "File berhasil dibuka tetapi tidak ada teks yang dapat diekstrak (mungkin gambar hasil scan atau file kosong).",
                "text": ""
            }

        total_len = len(extracted_text)
        truncated = False
        if total_len > max_chars:
            extracted_text = extracted_text[:max_chars] + f"\n\n... [Teks dipotong karena melebihi {max_chars} karakter]"
            truncated = True

        return {
            "success": True,
            "filename": filename,
            "file_type": file_type,
            "page_count": page_count,
            "char_count": total_len,
            "truncated": truncated,
            "text": extracted_text
        }

    except Exception as e:
        return {
            "success": False,
            "filename": filename,
            "file_type": file_type,
            "error": f"Gagal membaca file: {str(e)}",
            "text": ""
        }

def extract_text_from_folder(folder_path: str, max_files: int = 15, max_chars_per_file: int = 4000) -> Dict[str, Any]:
    """
    Scan a directory on disk and extract readable documents.
    """
    if not os.path.isdir(folder_path):
        return {
            "success": False,
            "error": f"Folder tidak ditemukan: {folder_path}",
            "files": [],
            "text": ""
        }

    combined_text = []
    read_files = []

    for root, _, files in os.walk(folder_path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, folder_path)
                res = extract_text_from_file(full_p, filename=rel_p, max_chars=max_chars_per_file)
                if res["success"]:
                    read_files.append(rel_p)
                    combined_text.append(f"=== [BERKAS: {rel_p}] ===\n{res['text']}\n")
                if len(read_files) >= max_files:
                    break
        if len(read_files) >= max_files:
            break

    if not read_files:
        return {
            "success": False,
            "error": "Tidak ditemukan berkas dokumen yang didukung di dalam folder tersebut.",
            "files": [],
            "text": ""
        }

    return {
        "success": True,
        "folder_path": folder_path,
        "files": read_files,
        "file_count": len(read_files),
        "text": "\n\n".join(combined_text)
    }

def detect_document_intent(query: str) -> str:
    """
    Detect whether the user wants to summarize (rangkum), proofread/fix (perbaiki), or Q&A.
    """
    q_lower = query.lower()
    
    # Check for proofreading / correction keywords
    fix_keywords = [
        "perbaiki", "koreksi", "benerin", "revisi", "fix", "edit",
        "tata bahasa", "grammar", "cek salah", "cek typo", "perbaiki kalimat",
        "apakah ada salah", "salah ketik"
    ]
    if any(k in q_lower for k in fix_keywords):
        return "proofread"

    # Check for summary keywords
    summary_keywords = [
        "rangkum", "ringkas", "summary", "intisari", "poin penting",
        "kesimpulan", "jelaskan intinya", "singkatkan", "garis besar"
    ]
    if any(k in q_lower for k in summary_keywords):
        return "summarize"

    return "qa"

def build_document_prompt(doc_info: Dict[str, Any], user_query: str) -> str:
    """
    Build structured prompt injection for Shiro when handling document content.
    """
    filename = doc_info.get("filename", "Dokumen")
    doc_text = doc_info.get("text", "")
    intent = detect_document_intent(user_query)

    guidance = ""
    if intent == "summarize":
        guidance = (
            "📌 PANDUAN MERANGKUM (SUMMARIZE):\n"
            "1. Buat ringkasan yang padat, rapi, dan berbobot dengan poin-poin terstruktur (bullet points / nomor).\n"
            "2. Soroti ide utama, temuan penting, atau alur kesimpulan dokumen.\n"
            "3. Sampaikan ringkasan dengan gaya khas Shiro yang manis, cerdas, dan menyenangkan untuk Kakak."
        )
    elif intent == "proofread":
        guidance = (
            "🛠️ PANDUAN MEMPERBAIKI (PROOFREAD & FIX):\n"
            "1. Analisis kesalahan dalam dokumen: perbaiki salah ketik (typo), tata bahasa, pemilihan kata rancu, serta struktur kalimat.\n"
            "2. Berikan VERSI PERBAIKAN yang sudah rapi dan mengalir enak dibaca.\n"
            "3. Jelaskan secara singkat poin-poin perubahan atau perbaikan penting apa saja yang Shiro lakukan agar Kakak tahu alasannya."
        )
    else:
        guidance = (
            "💡 PANDUAN MENJAWAB (Q&A):\n"
            "1. Jawab pertanyaan Kakak secara akurat dan setia pada fakta di dalam dokumen.\n"
            "2. Jika informasi tidak ada di dalam dokumen, katakan dengan jujur dan manja."
        )

    prompt = (
        f"\n\n### 📄 KONTEN DOKUMEN YANG DIUNGGAH KAKAK ({filename}):\n"
        f"{doc_text}\n\n"
        f"### TUGAS KHUSUS SHIRO UNTUK DOKUMEN INI:\n"
        f"{guidance}\n"
    )
    return prompt
