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
    # Documents
    ".pdf", ".docx", ".doc", ".txt", ".md", ".markdown", ".rtf", ".log",
    # Web & Frontend
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte", ".astro",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    # Backend & Systems Programming
    ".py", ".pyw", ".pyi", ".ipynb", ".java", ".c", ".cpp", ".cc", ".cxx",
    ".h", ".hpp", ".hh", ".cs", ".go", ".rs", ".php", ".rb", ".swift",
    ".kt", ".kts", ".scala", ".dart", ".lua", ".pl", ".pm", ".r", ".jl",
    ".zig", ".nim", ".v", ".ex", ".exs", ".erl", ".hrl", ".hs", ".clj",
    # Shell, Scripting & DevOps
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1", ".psd1", ".bat", ".cmd",
    ".awk", ".sed", ".dockerfile", ".vagrantfile", ".makefile", ".cmake", ".app",
    # Data, Config & Database
    ".json", ".jsonl", ".json5", ".yaml", ".yml", ".toml", ".xml", ".csv",
    ".tsv", ".sql", ".prisma", ".graphql", ".gql", ".ini", ".cfg", ".conf",
    ".config", ".properties", ".env", ".gitignore", ".dockerignore", ".editorconfig",
    ".lock", ".gradle", ".plist", ".proto"
}

def is_probably_text_file(file_path: str, sample_size: int = 4096) -> bool:
    """
    Detect whether a file is a plain text / source code file by checking the first sample_size bytes
    for null bytes (0x00). Allows reading extensionless files (e.g., Makefile, Dockerfile) or uncommon code files.
    """
    try:
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return False
        with open(file_path, "rb") as f:
            chunk = f.read(sample_size)
        if not chunk:
            return True
        if b"\x00" in chunk:
            return False
        return True
    except Exception:
        return False

def extract_text_from_file(file_path: str, filename: Optional[str] = None, max_chars: Optional[int] = None) -> Dict[str, Any]:
    """
    Extract readable text from a supported document file.
    Truncates gracefully if content exceeds max_chars to preserve LLM context budget.
    """
    if max_chars is None:
        max_chars = int(os.environ.get("SHIRO_MAX_DOC_CHARS", "12000"))

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
            full_p = os.path.join(root, f)
            if ext in SUPPORTED_EXTENSIONS or is_probably_text_file(full_p):
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


def extract_documents_from_archive(
    archive_path: str,
    max_files: int = 100,
    max_total_chars: int = 1_500_000,
) -> List[Dict[str, Any]]:
    """
    Mengekstrak isi seluruh berkas teks/kode di dalam arsip unggahan (.zip, .tar.gz, .tgz, .tar)
    untuk dibaca penuh oleh AI Agent tanpa batas 1 file.
    """
    import zipfile
    import tarfile
    import tempfile
    import shutil

    if not archive_path or not os.path.exists(archive_path):
        return []

    lower = archive_path.lower()
    tmp_dir = tempfile.mkdtemp(prefix="shiro_arch_in_")
    extracted_docs: List[Dict[str, Any]] = []
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    used_chars = 0

    try:
        safe_members: List[Tuple[str, bytes]] = []
        if lower.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    rel = info.filename.replace("\\", "/").lstrip("/")
                    parts = [p for p in rel.split("/") if p and p != "."]
                    if not parts or ".." in parts or any(p in skip_dirs for p in parts):
                        continue
                    if len(safe_members) >= max_files:
                        break
                    safe_members.append(("/".join(parts), zf.read(info.filename)))
        elif any(lower.endswith(s) for s in (".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar")):
            with tarfile.open(archive_path, "r:*") as tf:
                for mem in tf.getmembers():
                    if not mem.isfile():
                        continue
                    rel = mem.name.replace("\\", "/").lstrip("/")
                    parts = [p for p in rel.split("/") if p and p != "."]
                    if not parts or ".." in parts or any(p in skip_dirs for p in parts):
                        continue
                    f_obj = tf.extractfile(mem)
                    if f_obj is None:
                        continue
                    safe_members.append(("/".join(parts), f_obj.read()))
                    if len(safe_members) >= max_files:
                        break

        for rel_path, raw_bytes in safe_members:
            tmp_file = os.path.abspath(os.path.join(tmp_dir, rel_path.replace("/", os.sep)))
            if os.path.commonpath([tmp_dir, tmp_file]) != tmp_dir:
                continue
            os.makedirs(os.path.dirname(tmp_file), exist_ok=True)
            with open(tmp_file, "wb") as out_f:
                out_f.write(raw_bytes)
            ext = os.path.splitext(rel_path)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS and not is_probably_text_file(tmp_file):
                continue
            remaining = max(2000, max_total_chars - used_chars)
            res = extract_text_from_file(tmp_file, filename=rel_path, max_chars=remaining)
            if res.get("success") and res.get("text"):
                extracted_docs.append(res)
                used_chars += len(res["text"])
                if used_chars >= max_total_chars:
                    break
    except Exception as e_arch:
        print(f"[Archive Extract Warning]: {e_arch}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return extracted_docs


def build_multi_document_prompt(
    documents: List[Dict[str, Any]],
    user_query: str,
    max_total_chars: int = 1_500_000,
) -> str:
    """
    Menyusun blok prompt terstruktur untuk 1 atau banyak berkas sekaligus.
    Mewajibkan AI Agent membaca seluruh berkas, memetakan dependensi/masalah,
    dan merancang rencana perbaikan sebelum menuliskan solusi atau kode.
    """
    valid_docs = [d for d in (documents or []) if isinstance(d, dict) and (d.get("text") or "").strip()]
    if not valid_docs:
        return ""

    intent = detect_document_intent(user_query or "")
    total_raw_chars = sum(len(str(d.get("text", ""))) for d in valid_docs)
    n_docs = len(valid_docs)

    inventory_lines: List[str] = []
    file_blocks: List[str] = []

    if total_raw_chars <= max_total_chars:
        per_doc_caps = [len(str(d.get("text", ""))) for d in valid_docs]
    else:
        # Alokasikan anggaran karakter proporsional agar setiap berkas tetap terbaca adil
        min_floor = min(4000, max_total_chars // max(1, n_docs))
        per_doc_caps = []
        for d in valid_docs:
            raw_len = len(str(d.get("text", "")))
            share = int((raw_len / float(max(1, total_raw_chars))) * max_total_chars)
            per_doc_caps.append(max(min_floor, min(raw_len, share)))

    for idx, (doc, cap) in enumerate(zip(valid_docs, per_doc_caps), 1):
        fname = doc.get("filename") or f"file_{idx}"
        raw_txt = str(doc.get("text") or "")
        line_cnt = raw_txt.count("\n") + 1
        inventory_lines.append(f"{idx}. `{fname}` ({line_cnt:,} baris · {len(raw_txt):,} karakter)")
        if len(raw_txt) > cap:
            shown = raw_txt[:cap] + f"\n... [Dipangkas {len(raw_txt) - cap:,} karakter untuk menjaga batas konteks]"
        else:
            shown = raw_txt
        file_blocks.append(
            f"=== [BERKAS {idx}/{n_docs}: {fname}] ===\n"
            f"{shown}\n"
            f"=== [AKHIR BERKAS {idx}/{n_docs}: {fname}] ==="
        )

    protocol_block = (
        "### 🧠 PROTOKOL WAJIB AI AGENT (READ ALL -> DIAGNOSE -> PLAN -> FIX):\n"
        f"1. **READ ALL FIRST**: Kamu baru saja menerima {n_docs} berkas secara bersamaan. "
        "WAJIB baca dan silang-periksa (cross-reference) SELURUH isi ke-" + f"{n_docs} berkas di atas sebelum mengambil kesimpulan.\n"
        "2. **ANALYZE & PLAN INSIDE `<think>`**: Di dalam blok `<think>...</think>` (dalam Bahasa Inggris yang terstruktur), "
        "petakan hubungan antar berkas, identifikasi di berkas & baris/fungsi mana tepatnya sumber masalahnya, dan susun rencana perbaikan langkah demi langkah.\n"
        "3. **PRESENT PLAN BEFORE FIXES**: Jika pengguna meminta debugging, audit, atau perbaikan masalah, jelaskan terlebih dahulu ringkasan diagnosa lokasi masalah serta **Rencana Perbaikan** yang jelas, lalu berikan solusi/kode perbaikan lengkap dengan nama berkas persis masing-masing.\n"
    )
    if intent == "summarize":
        protocol_block += "4. **FOCUS (SUMMARIZE)**: Rangkum keterkaitan dan inti penting dari semua berkas di atas secara terstruktur.\n"
    elif intent == "proofread":
        protocol_block += "4. **FOCUS (FIX & IMPROVE)**: Perbaiki setiap bug/kesalahan di berkas terkait dengan mempertahankan nama berkas persisnya.\n"

    return (
        f"\n\n### 📂 INVENTARIS {n_docs} BERKAS YANG DIUNGGAH BERSAMAAN:\n"
        + "\n".join(inventory_lines)
        + "\n\n"
        + "\n\n".join(file_blocks)
        + "\n\n"
        + protocol_block
    )
