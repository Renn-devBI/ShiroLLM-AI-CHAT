# -*- coding: utf-8 -*-
"""
Shiro Model Versioning & Registry
Mengelola penomoran versi model hasil training LoRA (ShiroAI-LLM-V1, ShiroAI-LLM-V2, dst.)
secara otomatis berdasarkan model yang sudah ada di lokal maupun di Google Drive.
"""

import os
import re
import glob

DEFAULT_MODEL_PREFIX = "ShiroAI-LLM-V"

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

def get_existing_trained_versions(search_dirs=None, prefix=DEFAULT_MODEL_PREFIX):
    """
    Memindai seluruh folder model & lora untuk mencari versi model yang sudah dilatih.
    Mengembalikan daftar nomor versi terurut, misal [1, 2].
    """
    if search_dirs is None:
        search_dirs = get_search_directories()

    versions = set()
    pattern = re.compile(rf"{re.escape(prefix)}(\d+)", re.IGNORECASE)

    for d in search_dirs:
        try:
            for item in os.listdir(d):
                m = pattern.search(item)
                if m:
                    try:
                        v = int(m.group(1))
                        versions.add(v)
                    except ValueError:
                        pass
        except Exception:
            pass

    return sorted(list(versions))

def get_next_training_version(search_dirs=None, prefix=DEFAULT_MODEL_PREFIX):
    """
    Mengembalikan nomor versi integer berikutnya.
    Jika belum ada -> 1
    Jika sudah ada V1 -> 2
    Jika sudah ada V1, V2 -> 3
    """
    existing = get_existing_trained_versions(search_dirs=search_dirs, prefix=prefix)
    if not existing:
        return 1
    return max(existing) + 1

def get_next_model_name(search_dirs=None, prefix=DEFAULT_MODEL_PREFIX):
    """
    Mengembalikan string nama model berikutnya, contoh: 'ShiroAI-LLM-V1', 'ShiroAI-LLM-V2'
    """
    ver = get_next_training_version(search_dirs=search_dirs, prefix=prefix)
    return f"{prefix}{ver}"
