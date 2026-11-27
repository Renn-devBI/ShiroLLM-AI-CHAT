# -*- coding: utf-8 -*-
"""
Shiro Agentic File & Multi-Format Archive Packager
Mengekstrak berkas kode/dokumen bernama persis (mis. login.app, app.py, index.html)
dan mengompresnya secara otomatis ke format arsip nyata (.zip, .tar.gz, .tar.bz2, .tar.xz, .tar, .gz, .7z).
"""

import os
import re
import uuid
import gzip
import shutil
import zipfile
import tarfile
import subprocess
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple

GENERATED_ARTIFACTS_DIR = os.path.join("data", "generated_files")

SUPPORTED_ARCHIVE_FORMATS = (
    "zip",
    "tar.gz",
    "tgz",
    "tar.bz2",
    "tbz2",
    "tar.xz",
    "txz",
    "tar",
    "gz",
    "7z",
)

LANG_DEFAULT_FILENAMES = {
    "html": "index.html",
    "htm": "index.html",
    "css": "style.css",
    "scss": "style.scss",
    "sass": "style.sass",
    "js": "script.js",
    "javascript": "script.js",
    "ts": "main.ts",
    "typescript": "main.ts",
    "jsx": "App.jsx",
    "tsx": "App.tsx",
    "vue": "App.vue",
    "py": "app.py",
    "python": "app.py",
    "json": "data.json",
    "xml": "config.xml",
    "yaml": "config.yaml",
    "yml": "config.yml",
    "toml": "config.toml",
    "sql": "schema.sql",
    "sh": "run.sh",
    "bash": "run.sh",
    "ps1": "run.ps1",
    "powershell": "run.ps1",
    "bat": "run.bat",
    "cmd": "run.cmd",
    "c": "main.c",
    "cpp": "main.cpp",
    "cs": "Program.cs",
    "java": "Main.java",
    "go": "main.go",
    "rs": "main.rs",
    "php": "index.php",
    "rb": "main.rb",
    "md": "README.md",
    "markdown": "README.md",
    "dockerfile": "Dockerfile",
}

_ARCHIVE_ACTION_WORDS = (
    "jadikan",
    "dijadikan",
    "jadiin",
    "zipin",
    "buatkan",
    "buat",
    "bikin",
    "kompres",
    "dikompres",
    "kompresi",
    "compress",
    "zipkan",
    "archive",
    "arsip",
    "arsipkan",
    "diarsipkan",
    "bungkus",
    "dibungkus",
    "bundel",
    "bundle",
    "pack",
    "package",
    "kirim",
    "kirimkan",
    "unduh",
    "download",
    "export",
    "ekspor",
    "simpan",
    "satukan",
    "gabung",
    "gabungkan",
    "convert",
    "konversi",
    "ubah",
    "bentuk",
    "format",
    "file",
    "berkas",
    "semua",
    "seluruh",
    "all",
    "into",
)

_ARCHIVE_FORMAT_WORDS = (
    r"\.tar\.gz",
    r"\btar\.gz\b",
    r"\.tgz\b",
    r"\btgz\b",
    r"\.tar\.bz2",
    r"\btar\.bz2\b",
    r"\.tbz2\b",
    r"\btbz2\b",
    r"\.tar\.xz",
    r"\btar\.xz\b",
    r"\.txz\b",
    r"\btxz\b",
    r"\.tar\b",
    r"\btar\b",
    r"\.gz\b",
    r"\bgzip\b",
    r"\.7z\b",
    r"\b7z\b",
    r"\b7zip\b",
    r"\b7-zip\b",
    r"\.zip\b",
    r"\bzip\b",
    r"\bzipkan\b",
    r"\.rar\b",
    r"\brar\b",
)

_FILENAME_TOKEN_RE = re.compile(
    r'([A-Za-z0-9_.\-/\\]+?\.[A-Za-z0-9]{1,12}|Dockerfile|Makefile|\.env(?:\.[A-Za-z0-9_]+)?)'
)


def format_size(num_bytes: int) -> str:
    """Memformat ukuran byte ke B / KB / MB yang mudah dibaca."""
    n = max(0, int(num_bytes))
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024.0:.1f} KB"
    return f"{n / (1024.0 * 1024.0):.2f} MB"


def sanitize_filename(name: str, allow_subdirs: bool = False) -> str:
    """
    Membersihkan nama file sambil mempertahankan nama persis dan ekstensi kustom
    (mis. login.app, app.py, pondok-kayu.zip, project.tar.gz).
    """
    if not name:
        return ""
    clean = str(name).strip().strip("`\"'()[]{}<>.,;:")
    clean = clean.replace("\x00", "")
    clean = re.sub(r'[<>:"|?*]', "", clean)
    clean = clean.replace("\\", "/")

    parts = [p.strip() for p in clean.split("/") if p.strip() and p.strip() not in (".", "..")]
    if not parts:
        return ""

    if not allow_subdirs:
        return parts[-1]
    return "/".join(parts)


def _normalize_format_name(fmt: str) -> Tuple[str, Optional[str]]:
    """Menormalisasi nama format arsip dan catatan bila perlu fallback (mis. rar -> zip)."""
    f = (fmt or "zip").strip().lower().lstrip(".")
    alias_map = {
        "7zip": "7z",
        "7-zip": "7z",
        "gzip": "gz",
        "zipkan": "zip",
    }
    f = alias_map.get(f, f)
    if f == "rar":
        return "zip", "Format RAR bersifat proprietary; otomatis dikemas sebagai .zip standar universal yang kompatibel di semua sistem."
    if f not in SUPPORTED_ARCHIVE_FORMATS:
        return "zip", None
    return f, None


def detect_archive_request(text: str) -> Optional[Dict[str, Any]]:
    """
    Mendeteksi permintaan pengguna untuk mengompres/mengarsipkan berkas ke format apa pun
    (.zip, .tar.gz, .tgz, .tar.bz2, .tar.xz, .tar, .gz, .7z).
    Mengembalikan dict permintaan atau None jika hanya pertanyaan informatif biasa.
    """
    if not text or not text.strip():
        return None

    low = text.lower().strip()
    has_format_kw = any(re.search(pat, low) for pat in _ARCHIVE_FORMAT_WORDS)
    has_compress_verb = bool(
        re.search(r"\b(kompres|kompresi|compress|zipkan|arsipkan|bungkus|bundel|bundle|pack|package)\b", low)
    )
    if not (has_format_kw or has_compress_verb):
        return None

    # Guard pertanyaan teoritis tanpa niat membuat file/arsip
    is_info_question = bool(
        re.match(r"^(?:apa\s+itu|apa\s+perbedaan|jelaskan|mengapa|kenapa|bagaimana\s+cara\s+kerja|what\s+is|explain)\b", low)
    )
    has_action = has_compress_verb or any(re.search(rf"\b{re.escape(w)}\b", low) for w in _ARCHIVE_ACTION_WORDS)
    explicit_arch_file_m = re.search(
        r'\b([A-Za-z0-9_\-.]+\.(?:tar\.gz|tar\.bz2|tar\.xz|tgz|tbz2|txz|zip|tar|gz|7z))\b',
        text,
        re.IGNORECASE,
    )
    if is_info_question and not has_action and not explicit_arch_file_m:
        return None
    if not has_action and not explicit_arch_file_m:
        return None

    # Deteksi format (urutkan compound extension terlebih dahulu!)
    detected_fmt = "zip"
    for pat, fmt_val in [
        (r"(?:\.|\b)(?:tar\.gz)\b", "tar.gz"),
        (r"(?:\.|\b)(?:tgz)\b", "tgz"),
        (r"(?:\.|\b)(?:tar\.bz2)\b", "tar.bz2"),
        (r"(?:\.|\b)(?:tbz2)\b", "tbz2"),
        (r"(?:\.|\b)(?:tar\.xz)\b", "tar.xz"),
        (r"(?:\.|\b)(?:txz)\b", "txz"),
        (r"(?:\.|\b)(?:7z|7zip|7-zip)\b", "7z"),
        (r"(?:\.|\b)(?:tar)\b", "tar"),
        (r"(?:\.|\b)(?:gz|gzip)\b", "gz"),
        (r"(?:\.|\b)(?:rar)\b", "rar"),
        (r"(?:\.|\b)(?:zip|zipkan)\b", "zip"),
    ]:
        if re.search(pat, low):
            detected_fmt = fmt_val
            break

    norm_fmt, note = _normalize_format_name(detected_fmt)
    archive_name = None
    if explicit_arch_file_m:
        cand_name = sanitize_filename(explicit_arch_file_m.group(1), allow_subdirs=False)
        if cand_name and cand_name.lower() not in ("tar.gz", "tar.bz2", "tar.xz"):
            archive_name = cand_name
    if archive_name and norm_fmt == "zip" and detected_fmt == "rar":
        archive_name = re.sub(r"\.rar$", ".zip", archive_name, flags=re.IGNORECASE)

    return {
        "format": norm_fmt,
        "requested_format": detected_fmt,
        "archive_name": archive_name,
        "note": note,
    }


def _looks_like_explicit_filename(candidate: str) -> bool:
    if not candidate:
        return False
    c = sanitize_filename(candidate, allow_subdirs=True)
    if not c or c.startswith("http"):
        return False
    base = c.split("/")[-1]
    if base in ("Dockerfile", "Makefile") or base.startswith(".env"):
        return True
    if "." not in base:
        return False
    ext = base.rsplit(".", 1)[-1].lower()
    # Hindari domain website seperti example.com atau versi seperti v3.8
    if ext in ("com", "org", "net", "io", "id", "ai", "dev") and "/" not in c and not base.startswith("."):
        return False
    if ext.isdigit():
        return False
    return 1 <= len(ext) <= 12 and len(base) <= 120


def _infer_filename_for_block(
    fence_info: str,
    preceding_lines: List[str],
    code_text: str,
    index: int,
) -> Tuple[str, str]:
    """Menentukan (relative_filename, language) yang akurat untuk satu blok kode Markdown."""
    info = (fence_info or "").strip()
    lang = ""
    explicit_name = ""

    # 1. Fence info: misal ```python:login.app, ```login.app, ```html filename="index.html"
    attr_m = re.search(r'(?:filename|file|title|name)\s*=\s*["\']?([^\s"\']+)["\']?', info, re.IGNORECASE)
    if attr_m and _looks_like_explicit_filename(attr_m.group(1)):
        explicit_name = sanitize_filename(attr_m.group(1), allow_subdirs=True)
        lang_tok = info.split()[0].split(":")[0].strip().lower()
        lang = lang_tok if "." not in lang_tok else ""
    elif ":" in info:
        left, right = info.split(":", 1)
        if _looks_like_explicit_filename(right):
            explicit_name = sanitize_filename(right, allow_subdirs=True)
            lang = left.strip().lower()
    elif info:
        first_tok = info.split()[0].strip()
        if _looks_like_explicit_filename(first_tok):
            explicit_name = sanitize_filename(first_tok, allow_subdirs=True)
            lang = first_tok.rsplit(".", 1)[-1].lower()
        else:
            lang = first_tok.lower()
            rest = info[len(first_tok):].strip()
            if rest and _looks_like_explicit_filename(rest):
                explicit_name = sanitize_filename(rest, allow_subdirs=True)

    # 2. Baris tepat di atas code fence (scan dari bawah ke atas agar yang terdekat menang)
    if not explicit_name and preceding_lines:
        for line in reversed(preceding_lines[-4:]):
            clean_l = line.strip()
            if not clean_l:
                continue
            # Prioritaskan pola dengan label File / Simpan / heading / backtick
            for pat in [
                r'(?:SHIRO_FILE|filename|file|berkas|simpan\s+sebagai|save\s+as|nama\s+file)\s*[:=]\s*`?([A-Za-z0-9_.\-/\\]+)`?',
                r'`([A-Za-z0-9_.\-/\\]+?\.[A-Za-z0-9]{1,12}|Dockerfile|Makefile|\.env(?:\.[A-Za-z0-9_]+)?)`',
                r'^(?:#{1,6}\s*|(?:\d+[\.\)]\s*)?(?:\*\*|__)?(?:File\s*\d*\s*[:\-]?\s*)?)([A-Za-z0-9_.\-/\\]+?\.[A-Za-z0-9]{1,12})(?:\*\*|__)?\s*:?\s*$',
            ]:
                m = re.search(pat, clean_l, re.IGNORECASE)
                if m and _looks_like_explicit_filename(m.group(1)):
                    explicit_name = sanitize_filename(m.group(1), allow_subdirs=True)
                    break
            if explicit_name:
                break

    # 3. Komentar di 5 baris pertama isi kode
    if not explicit_name and code_text:
        head_lines = code_text.splitlines()[:5]
        for hline in head_lines:
            hl = hline.strip()
            m_c = (
                re.search(r'(?:SHIRO_FILE|filename|file|nama\s+berkas|name)\s*[:=]\s*([A-Za-z0-9_.\-/\\]+)', hl, re.IGNORECASE)
                or re.match(r'^(?://|#|<!--|/\*|--)\s*([A-Za-z0-9_.\-/\\]+?\.[A-Za-z0-9]{1,12})(?:\s*(?:-->|\*/))?\s*$', hl)
            )
            if m_c and _looks_like_explicit_filename(m_c.group(1)):
                explicit_name = sanitize_filename(m_c.group(1), allow_subdirs=True)
                break

    # 4. Fallback nama default berdasarkan bahasa
    if not explicit_name:
        if lang in LANG_DEFAULT_FILENAMES:
            explicit_name = LANG_DEFAULT_FILENAMES[lang]
        elif lang and re.match(r'^[a-z0-9]{1,10}$', lang):
            explicit_name = f"file_{index}.{lang}"
        else:
            explicit_name = f"file_{index}.txt"

    return explicit_name, lang


def extract_named_files_from_markdown(text: str) -> List[Dict[str, str]]:
    """
    Mengekstrak semua fenced code block beserta nama file persisnya dari respons Markdown.
    Mengembalikan daftar dict: {filename, basename, content, language, explicit}.
    """
    if not text:
        return []

    files_by_name: Dict[str, Dict[str, str]] = {}
    used_generic_counts: Dict[str, int] = {}

    fence_re = re.compile(r'```([^\n]*)\n([\s\S]*?)```')
    block_idx = 0
    for m in fence_re.finditer(text):
        fence_info = m.group(1) or ""
        code_body = (m.group(2) or "").rstrip()
        if not code_body.strip():
            continue
        lang_low = fence_info.strip().split()[0].lower() if fence_info.strip() else ""
        if lang_low in ("mermaid",):
            continue

        block_idx += 1
        prefix_text = text[:m.start()]
        prev_nonempty = [ln for ln in prefix_text.splitlines() if ln.strip()][-4:]
        rel_name, detected_lang = _infer_filename_for_block(
            fence_info=fence_info,
            preceding_lines=prev_nonempty,
            code_text=code_body,
            index=block_idx,
        )

        # Hindari tabrakan bila ada beberapa blok unnamed dengan bahasa yang sama
        if rel_name in files_by_name and rel_name.startswith("file_"):
            used_generic_counts[rel_name] = used_generic_counts.get(rel_name, 1) + 1
            stem, dot, ext = rel_name.partition(".")
            rel_name = f"{stem}_{used_generic_counts[rel_name]}.{ext}" if dot else f"{rel_name}_{used_generic_counts[rel_name]}"

        basename = rel_name.split("/")[-1]
        files_by_name[rel_name] = {
            "filename": rel_name,
            "basename": basename,
            "content": code_body + "\n",
            "language": detected_lang or "text",
        }

    return list(files_by_name.values())


def infer_project_name_from_text(text: str, files: Optional[List[Dict[str, str]]] = None) -> str:
    """Menebak nama folder/proyek yang rapi dari teks asisten atau struktur berkas."""
    if files:
        roots = {f["filename"].split("/")[0] for f in files if "/" in f.get("filename", "")}
        if len(roots) == 1:
            root = sanitize_filename(next(iter(roots)))
            if root and "." not in root:
                return root

    if text:
        patterns = [
            r'folder\s+baru\s*\(\s*misal(?:nya)?\s*`?([A-Za-z0-9_\-]{2,40})`?\s*\)',
            r'folder\s+`([A-Za-z0-9_\-]{2,40})`',
            r'proyek\s+`([A-Za-z0-9_\-]{2,40})`',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                cand = sanitize_filename(m.group(1))
                if cand:
                    return cand

    if files and len(files) == 1:
        b = files[0]["basename"]
        stem = b.rsplit(".", 1)[0] if "." in b else b
        if stem:
            return stem

    return "shiro-project"


_NON_PROJECT_SKIP_EXTS = {
    "zip", "tar", "gz", "tgz", "bz2", "tbz2", "xz", "txz", "7z", "rar",
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "ico", "svg",
    "mp4", "webm", "mov", "mkv", "avi", "mp3", "wav", "ogg",
}


def extract_requested_filenames(text: str) -> List[str]:
    """
    Mengekstrak nama berkas eksplisit yang diminta pengguna (mis. 'app.py', 'index.html', 'login.app'),
    mengabaikan ekstensi arsip seperti .zip/.tar.gz.
    """
    if not text:
        return []
    seen = set()
    requested: List[str] = []
    for m in _FILENAME_TOKEN_RE.finditer(text):
        cand = sanitize_filename(m.group(1), allow_subdirs=True)
        if not cand or not _looks_like_explicit_filename(cand):
            continue
        low = cand.lower()
        ext = low.rsplit(".", 1)[-1] if "." in low else ""
        if ext in _NON_PROJECT_SKIP_EXTS or low.endswith(".tar.gz") or low.endswith(".tar.bz2") or low.endswith(".tar.xz"):
            continue
        if low not in seen:
            seen.add(low)
            requested.append(cand)
    return requested


def _file_matches_requested(item: Dict[str, str], requested_filenames: List[str]) -> bool:
    """Memeriksa apakah item file cocok dengan salah satu nama yang diminta user."""
    if not requested_filenames:
        return True
    fname_low = str(item.get("filename") or "").strip().lower()
    base_low = str(item.get("basename") or "").strip().lower()
    for req in requested_filenames:
        req_low = str(req).strip().lower()
        req_base = req_low.split("/")[-1]
        if fname_low == req_low or base_low == req_base or fname_low.endswith("/" + req_low):
            return True
    return False


def merge_file_collections(
    *collections: List[Dict[str, str]],
    requested_filenames: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """
    Menggabungkan beberapa sumber daftar berkas dengan prioritas urutan argumen
    (koleksi lebih awal = versi lebih baru / prioritas lebih tinggi).
    Deduplikasi berdasarkan path maupun basename (bila basename identik, versi terprioritas dipertahankan).
    """
    merged: List[Dict[str, str]] = []
    seen_paths = set()
    seen_basenames = set()

    for col in collections:
        if not col:
            continue
        for item in col:
            if not isinstance(item, dict):
                continue
            rel = sanitize_filename(item.get("filename") or item.get("basename") or "", allow_subdirs=True)
            if not rel:
                continue
            base = rel.split("/")[-1]
            norm_path = rel.lower()
            norm_base = base.lower()
            if norm_path in seen_paths:
                continue
            # Jika sudah ada versi lebih baru dengan basename sama, jangan timpa dengan versi lama
            if "/" not in rel and norm_base in seen_basenames:
                continue
            if norm_base in seen_basenames and any(m.get("basename", "").lower() == norm_base and "/" not in m.get("filename", "") for m in merged):
                continue
            seen_paths.add(norm_path)
            seen_basenames.add(norm_base)
            merged.append({
                "filename": rel,
                "basename": base,
                "content": str(item.get("content") or ""),
                "language": str(item.get("language") or "text"),
            })

    if requested_filenames:
        matched = [m for m in merged if _file_matches_requested(m, requested_filenames)]
        if matched:
            return matched

    return merged


def detect_archive_claim_in_reply(reply_text: str) -> Optional[Dict[str, Any]]:
    """
    Mendeteksi bila AI dalam teks balasannya menyebut pembuatan arsip (.zip/.tar.gz/.7z/.tar)
    namun belum memanggil tag [[AGENT_TOOL:create_archive|...]] secara eksplisit.
    """
    if not reply_text:
        return None
    m = re.search(
        r'`?([A-Za-z0-9_\-.]+\.(?:tar\.gz|tar\.bz2|tar\.xz|tgz|tbz2|txz|zip|tar|gz|7z))`?',
        reply_text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    arch_name = sanitize_filename(m.group(1), allow_subdirs=False)
    low = reply_text.lower()
    if any(kw in low for kw in ("arsip", "archive", "berhasil dibuat", "dikemas", "dikompres", "compressed", "ekstrak zip", "pack", "packaged")):
        req_fmt = "zip"
        for ext_pat, f_name in [
            (".tar.gz", "tar.gz"), (".tgz", "tgz"), (".tar.bz2", "tar.bz2"),
            (".tar.xz", "tar.xz"), (".7z", "7z"), (".tar", "tar"), (".gz", "gz"), (".zip", "zip")
        ]:
            if arch_name.lower().endswith(ext_pat):
                req_fmt = f_name
                break
        return {"format": req_fmt, "archive_name": arch_name}
    return None


def _read_artifact_disk_content(download_url: str, fallback_name: str, is_archive_member: bool = False) -> Optional[str]:
    """Membaca isi berkas artifact tersimpan di GENERATED_ARTIFACTS_DIR secara aman."""
    if not download_url:
        return None
    root_abs = os.path.abspath(GENERATED_ARTIFACTS_DIR)
    cand_paths = []
    m_sub = re.match(r'^/api/artifacts/([A-Za-z0-9_\-]+)/files/(.+)$', download_url)
    m_top = re.match(r'^/api/artifacts/([A-Za-z0-9_\-]+)/([^/]+)$', download_url)
    if m_sub:
        bundle_id = sanitize_filename(m_sub.group(1))
        rel = urllib.parse.unquote(m_sub.group(2)).lstrip("/").replace("/", os.sep)
        cand_paths.append(os.path.abspath(os.path.join(root_abs, bundle_id, "files", rel)))
    elif m_top:
        bundle_id = sanitize_filename(m_top.group(1))
        fname = sanitize_filename(urllib.parse.unquote(m_top.group(2)))
        if is_archive_member:
            cand_paths.append(os.path.abspath(os.path.join(root_abs, bundle_id, "files", fname)))
        cand_paths.append(os.path.abspath(os.path.join(root_abs, bundle_id, fname)))

    for p in cand_paths:
        try:
            if os.path.commonpath([root_abs, p]) == root_abs and os.path.isfile(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f_in:
                    return f_in.read()
        except Exception:
            continue
    return None


def extract_files_from_conversation(
    history: Optional[List[Dict[str, Any]]],
    max_lookback: int = 60,
    requested_filenames: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """
    Mengumpulkan seluruh berkas program terbaru dari riwayat percakapan (kode markdown asisten,
    artifact file/archive sebelumnya di disk, serta berkas unggahan user) lintas giliran chat.
    """
    if not history:
        return [], None

    recent = list(history)[-max_lookback:]
    collected_by_norm: Dict[str, Dict[str, str]] = {}
    seen_basenames = set()
    project_name: Optional[str] = None
    uploads_root = os.path.abspath(os.path.join("data", "uploads"))

    def _register_file(rel_name: str, content: str, language: str = "text"):
        clean_rel = sanitize_filename(rel_name, allow_subdirs=True)
        if not clean_rel or not str(content or "").strip():
            return
        norm_path = clean_rel.lower()
        base = clean_rel.split("/")[-1]
        norm_base = base.lower()
        if norm_path in collected_by_norm or norm_base in seen_basenames:
            return
        collected_by_norm[norm_path] = {
            "filename": clean_rel,
            "basename": base,
            "content": str(content),
            "language": str(language or "text"),
        }
        seen_basenames.add(norm_base)

    for msg in reversed(recent):
        role = msg.get("role")
        if role == "assistant":
            content = str(msg.get("content") or "")
            extracted = extract_named_files_from_markdown(content)
            if extracted:
                if not project_name:
                    cand_proj = infer_project_name_from_text(content, extracted)
                    if cand_proj and cand_proj != "shiro-project":
                        project_name = cand_proj
                for item in extracted:
                    _register_file(item["filename"], item["content"], item.get("language", "text"))

            # Hidrasi dari artifacts pesan asisten sebelumnya (jika kode tidak diulang atau berada di archive/file artifact)
            arts = msg.get("artifacts")
            if isinstance(arts, list):
                for art in arts:
                    if not isinstance(art, dict):
                        continue
                    kind = art.get("kind")
                    if kind == "file":
                        a_name = art.get("filename") or ""
                        txt = _read_artifact_disk_content(art.get("download_url") or "", a_name, is_archive_member=False)
                        if txt:
                            _register_file(a_name, txt, art.get("format") or "text")
                    elif kind == "archive" and isinstance(art.get("individual_files"), list):
                        for sf in art["individual_files"]:
                            if not isinstance(sf, dict):
                                continue
                            sf_name = sf.get("rel_path") or sf.get("filename") or ""
                            txt = _read_artifact_disk_content(sf.get("download_url") or "", sf_name, is_archive_member=True)
                            if txt:
                                _register_file(sf_name, txt, "text")
        elif role == "user":
            # Sertakan berkas yang pernah diunggah user (metadata text maupun fallback disk/document_text)
            docs_meta = msg.get("documents")
            if isinstance(docs_meta, list):
                for d in docs_meta:
                    if not isinstance(d, dict):
                        continue
                    d_name = sanitize_filename(d.get("filename") or "", allow_subdirs=True)
                    d_text = d.get("text")
                    if (not d_text or not str(d_text).strip()) and d_name:
                        disk_up = os.path.abspath(os.path.join(uploads_root, d_name.split("/")[-1]))
                        try:
                            if os.path.commonpath([uploads_root, disk_up]) == uploads_root and os.path.isfile(disk_up):
                                with open(disk_up, "r", encoding="utf-8", errors="ignore") as f_up:
                                    d_text = f_up.read()
                        except Exception:
                            d_text = None
                    if d_name and d_text and str(d_text).strip():
                        _register_file(d_name, str(d_text), str(d.get("file_type") or "text"))
            single_dname = msg.get("document_name")
            single_dtext = msg.get("document_text")
            if single_dname and single_dtext and str(single_dtext).strip():
                _register_file(str(single_dname), str(single_dtext), str(msg.get("document_type") or "text"))

    all_files = list(collected_by_norm.values())
    if requested_filenames:
        matched = [f for f in all_files if _file_matches_requested(f, requested_filenames)]
        if matched:
            all_files = matched

    if not project_name and all_files:
        project_name = infer_project_name_from_text("", all_files)

    return all_files, project_name


def create_archive_artifact(
    files: List[Dict[str, str]],
    fmt: str = "zip",
    archive_name: Optional[str] = None,
    project_name: Optional[str] = None,
    base_dir: str = GENERATED_ARTIFACTS_DIR,
) -> Dict[str, Any]:
    """
    Membuat berkas arsip nyata di disk (.zip, .tar.gz, .tgz, .tar.bz2, .tar.xz, .tar, .gz, .7z)
    beserta salinan masing-masing file individual untuk diunduh langsung.
    """
    if not files:
        raise ValueError("Tidak ada berkas untuk dikompres.")

    norm_fmt, format_note = _normalize_format_name(fmt)
    bundle_id = uuid.uuid4().hex[:12]
    bundle_dir = os.path.abspath(os.path.join(base_dir, bundle_id))
    files_root = os.path.join(bundle_dir, "files")
    os.makedirs(files_root, exist_ok=True)

    written_files: List[Tuple[str, str, int]] = []
    for f_entry in files:
        rel_path = sanitize_filename(f_entry.get("filename") or f_entry.get("basename") or "file.txt", allow_subdirs=True)
        if not rel_path:
            rel_path = "file.txt"
        disk_path = os.path.abspath(os.path.join(files_root, rel_path.replace("/", os.sep)))
        if os.path.commonpath([files_root, disk_path]) != files_root:
            continue
        os.makedirs(os.path.dirname(disk_path), exist_ok=True)
        raw_bytes = (f_entry.get("content") or "").encode("utf-8")
        with open(disk_path, "wb") as out_f:
            out_f.write(raw_bytes)
        written_files.append((rel_path, disk_path, len(raw_bytes)))

    if not written_files:
        raise ValueError("Semua berkas gagal divalidasi untuk pengemasan.")

    base_stem = sanitize_filename(project_name or "") or infer_project_name_from_text("", files)
    actual_fmt = norm_fmt
    extra_notes: List[str] = [format_note] if format_note else []

    if archive_name:
        exact_archive_name = sanitize_filename(archive_name, allow_subdirs=False)
    else:
        exact_archive_name = f"{base_stem}.{actual_fmt}"

    # Tangani .gz untuk multi-file (gzip tunggal hanya untuk 1 berkas -> bungkus sebagai .tar.gz)
    if actual_fmt == "gz" and len(written_files) > 1:
        actual_fmt = "tar.gz"
        if archive_name:
            exact_archive_name = re.sub(r"\.gz$", ".tar.gz", exact_archive_name, flags=re.IGNORECASE)
            if not exact_archive_name.lower().endswith(".tar.gz"):
                exact_archive_name += ".tar.gz"
        else:
            exact_archive_name = f"{base_stem}.tar.gz"
        extra_notes.append("Karena terdiri dari beberapa berkas, dikemas sebagai .tar.gz standar agar struktur file utuh.")

    archive_path = os.path.join(bundle_dir, exact_archive_name)

    if actual_fmt == "zip":
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel_path, disk_path, _ in written_files:
                zf.write(disk_path, arcname=rel_path)
    elif actual_fmt in ("tar.gz", "tgz", "tar.bz2", "tbz2", "tar.xz", "txz", "tar"):
        mode_map = {
            "tar": "w",
            "tar.gz": "w:gz",
            "tgz": "w:gz",
            "tar.bz2": "w:bz2",
            "tbz2": "w:bz2",
            "tar.xz": "w:xz",
            "txz": "w:xz",
        }
        with tarfile.open(archive_path, mode_map[actual_fmt]) as tf:
            for rel_path, disk_path, _ in written_files:
                tf.add(disk_path, arcname=rel_path)
    elif actual_fmt == "gz":
        rel_path, disk_path, _ = written_files[0]
        if not archive_name:
            exact_archive_name = f"{rel_path.split('/')[-1]}.gz"
            archive_path = os.path.join(bundle_dir, exact_archive_name)
        with open(disk_path, "rb") as src_f, gzip.open(archive_path, "wb") as gz_f:
            shutil.copyfileobj(src_f, gz_f)
    elif actual_fmt == "7z":
        done_7z = False
        try:
            import py7zr  # type: ignore
            with py7zr.SevenZipFile(archive_path, "w") as szf:
                for rel_path, disk_path, _ in written_files:
                    szf.write(disk_path, arcname=rel_path)
            done_7z = True
        except Exception:
            pass

        if not done_7z:
            seven_bin = shutil.which("7z") or shutil.which("7za") or shutil.which("7zr")
            if seven_bin:
                try:
                    res = subprocess.run(
                        [seven_bin, "a", "-y", archive_path, "."],
                        cwd=files_root,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=30,
                    )
                    if res.returncode == 0 and os.path.exists(archive_path):
                        done_7z = True
                except Exception:
                    pass

        if not done_7z:
            actual_fmt = "tar.xz"
            exact_archive_name = re.sub(r"\.7z$", ".tar.xz", exact_archive_name, flags=re.IGNORECASE)
            if not exact_archive_name.lower().endswith(".tar.xz"):
                exact_archive_name = f"{base_stem}.tar.xz"
            archive_path = os.path.join(bundle_dir, exact_archive_name)
            with tarfile.open(archive_path, "w:xz") as tf:
                for rel_path, disk_path, _ in written_files:
                    tf.add(disk_path, arcname=rel_path)
            extra_notes.append("Library py7zr/7z tidak terpasang di server; otomatis dikemas menggunakan kompresi LZMA (.tar.xz) setara 7z.")

    archive_size = os.path.getsize(archive_path)
    individual_files = []
    for rel_path, _, byte_len in written_files:
        encoded_rel = "/".join(urllib.parse.quote(seg) for seg in rel_path.split("/"))
        individual_files.append({
            "filename": rel_path.split("/")[-1],
            "rel_path": rel_path,
            "size_bytes": byte_len,
            "size_label": format_size(byte_len),
            "download_url": f"/api/artifacts/{bundle_id}/files/{encoded_rel}",
        })

    return {
        "id": bundle_id,
        "kind": "archive",
        "filename": exact_archive_name,
        "format": actual_fmt,
        "size_bytes": archive_size,
        "size_label": format_size(archive_size),
        "download_url": f"/api/artifacts/{bundle_id}/{urllib.parse.quote(exact_archive_name)}",
        "files_included": [rel for rel, _, _ in written_files],
        "file_count": len(written_files),
        "individual_files": individual_files,
        "note": " ".join([n for n in extra_notes if n]).strip() or None,
    }


def create_file_artifacts(
    files: List[Dict[str, str]],
    base_dir: str = GENERATED_ARTIFACTS_DIR,
) -> List[Dict[str, Any]]:
    """
    Menyimpan berkas individual dengan nama persisnya (mis. login.app) agar bisa diunduh
    langsung dari server melalui /api/artifacts/<id>/<filename>.
    """
    if not files:
        return []

    bundle_id = uuid.uuid4().hex[:12]
    bundle_dir = os.path.abspath(os.path.join(base_dir, bundle_id))
    os.makedirs(bundle_dir, exist_ok=True)

    results: List[Dict[str, Any]] = []
    for f_entry in files:
        exact_name = sanitize_filename(f_entry.get("basename") or f_entry.get("filename") or "file.txt", allow_subdirs=False)
        if not exact_name:
            exact_name = "file.txt"
        disk_path = os.path.abspath(os.path.join(bundle_dir, exact_name))
        if os.path.commonpath([bundle_dir, disk_path]) != bundle_dir:
            continue
        raw_bytes = (f_entry.get("content") or "").encode("utf-8")
        with open(disk_path, "wb") as out_f:
            out_f.write(raw_bytes)
        ext = exact_name.rsplit(".", 1)[-1].lower() if "." in exact_name else (f_entry.get("language") or "file")
        results.append({
            "id": f"{bundle_id}_{len(results) + 1}",
            "kind": "file",
            "filename": exact_name,
            "format": ext,
            "size_bytes": len(raw_bytes),
            "size_label": format_size(len(raw_bytes)),
            "download_url": f"/api/artifacts/{bundle_id}/{urllib.parse.quote(exact_name)}",
            "files_included": [exact_name],
            "file_count": 1,
        })
    return results
