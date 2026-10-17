# -*- coding: utf-8 -*-
"""
Shiro Model Versioning & Registry
Mengelola penomoran versi model hasil training LoRA (ShiroAI-LLM-V1, ShiroAI-LLM-V2, dst.)
secara otomatis berdasarkan model yang sudah ada di lokal maupun di Google Drive.
"""

import os
import re
import glob

DEFAULT_MODEL_PREFIX = "ShiroHaru-"
DEFAULT_MODEL_SUFFIX = "-Agent"

def get_search_directories():
    """Daftar direktori untuk mencari model yang sudah ada"""
    dirs = ["model", "lora", os.path.join("model", "lora")]
    drive_dir = os.environ.get("SHIRO_DRIVE_DIR")
    if not drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
        drive_dir = "/content/drive/MyDrive/Shiro_Memory"
    if drive_dir and os.path.exists(drive_dir):
        dirs.append(os.path.join(drive_dir, "model"))
        dirs.append(os.path.join(drive_dir, "lora"))
    return [d for d in dirs if os.path.exists(d)]

def get_existing_trained_versions(search_dirs=None, prefix=DEFAULT_MODEL_PREFIX, suffix=DEFAULT_MODEL_SUFFIX):
    """
    Memindai seluruh folder model & lora untuk mencari versi model yang sudah dilatih.
    Mendukung format ShiroHaru-{version}-Agent dan kompatibilitas format legacy ShiroAI-LLM-V{version}.
    Mengembalikan daftar nomor versi terurut (float), misal [1.0, 2.0].
    """
    if search_dirs is None:
        search_dirs = get_search_directories()

    versions = set()
    # Cocokkan ShiroHaru-(\d+(\.\d+)?)-Agent atau ShiroHaru-(\d+(\.\d+)?)
    pattern_new = re.compile(rf"{re.escape(prefix)}(\d+(?:\.\d+)?)(?:{re.escape(suffix)})?", re.IGNORECASE)
    # Kompatibilitas model lama ShiroAI-LLM-V(\d+)
    pattern_legacy = re.compile(r"ShiroAI-LLM-V(\d+(?:\.\d+)?)", re.IGNORECASE)

    for d in search_dirs:
        try:
            for item in os.listdir(d):
                m = pattern_new.search(item)
                if not m:
                    m = pattern_legacy.search(item)
                if m:
                    try:
                        v = float(m.group(1))
                        versions.add(v)
                    except ValueError:
                        pass
        except Exception:
            pass

    return sorted(list(versions))

def get_next_training_version(search_dirs=None, prefix=DEFAULT_MODEL_PREFIX, suffix=DEFAULT_MODEL_SUFFIX):
    """
    Mengembalikan nomor versi string berikutnya (contoh: '1.0', '2.0', '3.0').
    Jika belum ada -> '1.0'
    Jika sudah ada 1.0 -> '2.0'
    Jika sudah ada 2.0 -> '3.0'
    """
    existing = get_existing_trained_versions(search_dirs=search_dirs, prefix=prefix, suffix=suffix)
    if not existing:
        return "1.0"
    max_ver = max(existing)
    next_ver = int(max_ver) + 1
    return f"{next_ver}.0"

def get_next_model_name(search_dirs=None, prefix=DEFAULT_MODEL_PREFIX, suffix=DEFAULT_MODEL_SUFFIX):
    """
    Mengembalikan string nama model berikutnya, contoh: 'ShiroHaru-1.0-Agent', 'ShiroHaru-2.0-Agent'
    """
    ver = get_next_training_version(search_dirs=search_dirs, prefix=prefix, suffix=suffix)
    return f"{prefix}{ver}{suffix}"
