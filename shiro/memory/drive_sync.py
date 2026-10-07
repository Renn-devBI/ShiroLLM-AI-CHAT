# -*- coding: utf-8 -*-
"""
Google Drive Synchronization & Atomic File Operations for Shiro LLMA
Handles automatic backup and restoration of memories and training data in Google Colab.
"""

import os
import shutil
import tempfile
import json
from typing import Optional, Dict, Any

def get_drive_directory() -> Optional[str]:
    """Mengembalikan path direktori Google Drive jika terhubung di Colab/Linux"""
    drive_dir = os.environ.get("SHIRO_DRIVE_DIR")
    if not drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
        drive_dir = "/content/drive/MyDrive/Shiro_Memory"
    return drive_dir if drive_dir and os.path.exists(drive_dir) else None

def atomic_save_json(filepath: str, data: Any, indent: int = 2) -> bool:
    """
    Menyimpan data JSON secara atomic dengan menulis ke temporary file terlebih dahulu
    lalu me-replace file target. Mencegah file korup jika proses terputus tiba-tiba di Colab.
    """
    dir_name = os.path.dirname(filepath) or "."
    os.makedirs(dir_name, exist_ok=True)
    
    try:
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, ensure_ascii=False, indent=indent)
            temp_name = tf.name
        
        # Atomic replace
        if os.name == 'nt' and os.path.exists(filepath):
            os.replace(temp_name, filepath)
        else:
            shutil.move(temp_name, filepath)
        return True
    except Exception as e:
        print(f"Error atomic_save_json for {filepath}: {e}")
        try:
            if 'temp_name' in locals() and os.path.exists(temp_name):
                os.remove(temp_name)
        except Exception:
            pass
        return False

def sync_file_to_drive(local_path: str, filename: Optional[str] = None) -> bool:
    """Mencadangkan berkas lokal ke Google Drive secara aman"""
    drive_dir = get_drive_directory()
    if not drive_dir or not os.path.exists(local_path):
        return False
    
    target_filename = filename or os.path.basename(local_path)
    target_path = os.path.join(drive_dir, target_filename)
    try:
        shutil.copy2(local_path, target_path)
        return True
    except Exception as e:
        print(f"Warning syncing {local_path} to Drive: {e}")
        return False

def sync_dir_to_drive(local_dir: str, target_dir_name: str) -> bool:
    """Mencadangkan folder lokal (misal training_data) ke Google Drive"""
    drive_dir = get_drive_directory()
    if not drive_dir or not os.path.exists(local_dir):
        return False
    
    target_path = os.path.join(drive_dir, target_dir_name)
    try:
        shutil.copytree(local_dir, target_path, dirs_exist_ok=True)
        return True
    except Exception as e:
        print(f"Warning syncing folder {local_dir} to Drive: {e}")
        return False
