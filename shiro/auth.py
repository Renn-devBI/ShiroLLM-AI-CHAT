# -*- coding: utf-8 -*-
"""
Shiro Authentication & API Key Management
Handles dynamic generation, verification, and rotation of API keys.
"""

import os
import json
import shutil
import secrets
from datetime import datetime
from flask import request
import shiro.config as config
API_KEY_FILE = getattr(config, "API_KEY_FILE", "api_key.json")

def _get_api_key_file() -> str:
    import sys
    if "web" in sys.modules and hasattr(sys.modules["web"], "API_KEY_FILE"):
        return sys.modules["web"].API_KEY_FILE
    import shiro.auth
    if hasattr(shiro.auth, "API_KEY_FILE") and shiro.auth.API_KEY_FILE != getattr(config, "API_KEY_FILE", "api_key.json"):
        return shiro.auth.API_KEY_FILE
    return getattr(config, "API_KEY_FILE", "api_key.json")

def get_active_api_key() -> str:
    """Mengambil API Key aktif saat ini"""
    env_key = os.environ.get("SHIRO_API_KEY", "").strip()
    if env_key:
        return env_key
    key_file = _get_api_key_file()
    if os.path.exists(key_file):
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                k = data.get("api_key", "").strip()
                if k:
                    return k
        except Exception:
            pass
    return get_or_create_api_key(force_new=True)

def get_all_valid_api_keys() -> set:
    """Mengambil himpunan semua API Key yang diizinkan (kunci aktif + riwayat kunci valid)"""
    keys = set()
    env_key = os.environ.get("SHIRO_API_KEY", "").strip()
    if env_key:
        keys.add(env_key)
    key_file = _get_api_key_file()
    if os.path.exists(key_file):
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    k = data.get("api_key", "").strip()
                    if k:
                        keys.add(k)
                    for item in data.get("valid_keys", []):
                        if item and isinstance(item, str):
                            keys.add(item.strip())
        except Exception:
            pass
    if not keys:
        keys.add(get_or_create_api_key(force_new=True))
    return keys

def get_or_create_api_key(force_new: bool = False) -> str:
    """
    Load atau hasilkan API Key baru.
    Jika force_new=True, selalu menghasilkan string API Key baru yang berbeda (random token_hex(16)),
    dan menyimpan key lama ke riwayat valid_keys agar klien/bot sebelumnya tidak terputus.
    """
    env_key = os.environ.get("SHIRO_API_KEY", "").strip()
    if env_key and not force_new:
        return env_key
    
    drive_dir = os.environ.get("SHIRO_DRIVE_DIR")
    if not drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
        drive_dir = "/content/drive/MyDrive/Shiro_Memory"

    existing_keys = []
    key_file = _get_api_key_file()
    if os.path.exists(key_file):
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    old_k = data.get("api_key", "").strip()
                    if old_k:
                        existing_keys.append(old_k)
                    for vk in data.get("valid_keys", []):
                        if vk and vk not in existing_keys:
                            existing_keys.append(vk)
        except Exception:
            pass

    if not force_new and existing_keys and not env_key:
        return existing_keys[0]

    new_key = "shiro-sk-" + secrets.token_hex(16)
    
    # Simpan riwayat key (maksimal 25 key unik)
    all_valid = [new_key] + [k for k in existing_keys if k != new_key]
    all_valid = all_valid[:25]
    
    try:
        with open(key_file, "w", encoding="utf-8") as f:
            json.dump({
                "api_key": new_key,
                "valid_keys": all_valid,
                "created_at": datetime.now().isoformat()
            }, f, indent=2)
        if drive_dir and os.path.exists(drive_dir):
            try:
                shutil.copy2(key_file, os.path.join(drive_dir, os.path.basename(key_file)))
            except Exception:
                pass
    except Exception as e:
        print(f"[Auth] Warning: Could not save API key file: {e}")
    return new_key

def verify_api_key(allow_web_ui: bool = True) -> bool:
    """
    Verifikasi API Key dari request:
    - Header: Authorization: Bearer <key>
    - Header: X-API-Key: <key>
    - Query Param: ?api_key=<key>
    Mendukung pengecekan terhadap semua kunci aktif & riwayat kunci yang valid.
    """
    valid_keys = get_all_valid_api_keys()
    
    # 1. Header Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token in valid_keys:
            return True
            
    # 2. Header X-API-Key
    x_key = request.headers.get("X-API-Key", "").strip()
    if x_key and x_key in valid_keys:
        return True
        
    # 3. Query Param
    q_key = request.args.get("api_key", "").strip()
    if q_key and q_key in valid_keys:
        return True
        
    # 4. Internal Browser Web UI
    if allow_web_ui:
        sec_fetch = request.headers.get("Sec-Fetch-Site", "")
        referer = request.headers.get("Referer", "")
        host = request.headers.get("Host", "")
        if sec_fetch in ["same-origin", "same-site"]:
            return True
        if referer and host and host in referer:
            return True
        remote_addr = request.remote_addr or ""
        if remote_addr in ["127.0.0.1", "localhost", "::1"] and not auth_header and not x_key:
            return True
            
    return False
