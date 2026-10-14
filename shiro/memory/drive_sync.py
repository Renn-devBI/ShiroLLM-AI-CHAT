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

def get_pristine_memory_data(user_name: str = "Kakak", keep_profile: bool = False, existing_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Menghasilkan struktur data ingatan awal Shiro yang bersih (0 fakta, 0 turn)"""
    from datetime import datetime
    now_iso = datetime.now().isoformat()
    user_profile = {
        "name": user_name,
        "aliases": [user_name],
        "personality_traits": ["Affectionate"],
        "preferences": {
            "topics_of_interest": [],
            "disliked_topics": [],
            "interaction_style": "Warm & Affectionate"
        },
        "relationship_info": {
            "role": "User",
            "importance": "High"
        }
    }
    if keep_profile and existing_data and isinstance(existing_data.get("user_profile"), dict):
        user_profile.update(existing_data["user_profile"])
        user_name = user_profile.get("name", user_name)

    return {
        "system_metadata": {
            "version": "2.0",
            "created_date": now_iso,
            "last_interaction": None,
            "total_turns": 0,
            "token_usage_approx": 0,
            "session_count": 0,
            "user_name": user_name,
            "topics_discussed": []
        },
        "user_profile": user_profile,
        "agent_persona": {
            "name": "Shiro",
            "current_mood": "Neutral & Menunggu",
            "emotional_state": {
                "happiness": 50,
                "anxiety": 0,
                "arousal": 0,
                "confidence": 50,
                "longing": 0
            },
            "relationship_status": {
                "label": "Unknown",
                "intimacy_level": 0,
                "commitment": ""
            },
            "internal_thought": "",
            "recent_actions": []
        },
        "knowledge_base": {
            "facts": [],
            "concepts": {},
            "relationships": {}
        },
        "episodic_memory": {
            "sessions": []
        },
        "learned_patterns": [],
        "short_term_history": [],
        "archived_training_history": [],
        "sessions_store": {
            "default": {
                "id": "default",
                "title": "Obrolan Utama",
                "created_at": now_iso,
                "last_active": now_iso,
                "messages": []
            }
        },
        "active_session_id": "default"
    }

def get_pristine_world_data() -> Dict[str, Any]:
    """Menghasilkan konfigurasi awal dunia Arcadia yang bersih"""
    return {
        "world_name": "Arcadia",
        "locations": {
            "home": "Pondok Kayu",
            "visited": []
        },
        "shiro_role": "Adik (Brocon)",
        "relationship_level": 1,
        "shared_memories": []
    }

def clean_training_directory(dir_path: str) -> int:
    """
    Mengosongkan seluruh dataset training (json, jsonl) dan file gambar di dalam direktori
    namun menjaga struktur direktori dan file .gitkeep tetap ada.
    Mengembalikan jumlah berkas yang berhasil dikosongkan.
    """
    if not os.path.exists(dir_path):
        return 0
    cleaned_count = 0
    for root, dirs, files in os.walk(dir_path):
        for f in files:
            if f == ".gitkeep":
                continue
            p = os.path.join(root, f)
            if f.endswith(".json"):
                try:
                    with open(p, "w", encoding="utf-8") as jf:
                        jf.write("[]\n")
                    cleaned_count += 1
                except Exception:
                    pass
            elif f.endswith(".jsonl"):
                try:
                    with open(p, "w", encoding="utf-8") as jf:
                        jf.write("")
                    cleaned_count += 1
                except Exception:
                    pass
            elif f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                try:
                    os.remove(p)
                    cleaned_count += 1
                except Exception:
                    pass
    return cleaned_count

def count_training_samples(dir_path: str) -> int:
    """Menghitung perkiraan jumlah sampel dataset training di dalam direktori"""
    if not os.path.exists(dir_path):
        return 0
    total = 0
    candidates = [
        os.path.join(dir_path, "shiro_alpaca_train.json"),
        os.path.join(dir_path, "chat", "shiro_alpaca_train.json"),
        os.path.join(dir_path, "vision", "shiro_vision_alpaca.json"),
        os.path.join(dir_path, "shiro_sharegpt_train.json"),
        os.path.join(dir_path, "chat", "shiro_sharegpt_train.json"),
        os.path.join(dir_path, "vision", "shiro_vision_sharegpt.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if isinstance(d, list):
                        total = max(total, len(d))
            except Exception:
                pass
    return total

def create_memory_backup(drive_dir: Optional[str] = None, include_world: bool = True, include_training: bool = True) -> Dict[str, Any]:
    """
    Membuat salinan cadangan berkas ingatan, world, dan data training ke Google Drive
    dengan penamaan ber-timestamp agar data lama tidak hilang permanen.
    """
    from datetime import datetime
    target_drive = drive_dir or get_drive_directory()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_files = []

    # Sumber ingatan: Drive jika ada, atau lokal
    drive_mem = os.path.join(target_drive, "ingatan_shiro.json") if target_drive else None
    local_mem = "ingatan_shiro.json"

    # Backup di Google Drive jika terhubung
    if target_drive and os.path.exists(target_drive):
        if drive_mem and os.path.exists(drive_mem) and os.path.getsize(drive_mem) > 10:
            dest_backup = os.path.join(target_drive, f"ingatan_shiro_backup_{timestamp}.json")
            try:
                shutil.copy2(drive_mem, dest_backup)
                backup_files.append(dest_backup)
            except Exception as e:
                print(f"Warning saat backup ingatan di Drive: {e}")
        elif os.path.exists(local_mem) and os.path.getsize(local_mem) > 10:
            dest_backup = os.path.join(target_drive, f"ingatan_shiro_backup_{timestamp}.json")
            try:
                shutil.copy2(local_mem, dest_backup)
                backup_files.append(dest_backup)
            except Exception as e:
                print(f"Warning saat backup lokal ke Drive: {e}")

        if include_world:
            drive_world = os.path.join(target_drive, "isekai_world.json")
            if os.path.exists(drive_world) and os.path.getsize(drive_world) > 10:
                dest_w_backup = os.path.join(target_drive, f"isekai_world_backup_{timestamp}.json")
                try:
                    shutil.copy2(drive_world, dest_w_backup)
                    backup_files.append(dest_w_backup)
                except Exception as e:
                    print(f"Warning saat backup world di Drive: {e}")

        if include_training:
            drive_train = os.path.join(target_drive, "training_data")
            if os.path.exists(drive_train) and len(os.listdir(drive_train)) > 0:
                dest_t_backup = os.path.join(target_drive, f"training_data_backup_{timestamp}")
                try:
                    shutil.copytree(drive_train, dest_t_backup, dirs_exist_ok=True)
                    backup_files.append(dest_t_backup)
                except Exception as e:
                    print(f"Warning saat backup training_data di Drive: {e}")

    # Cadangan lokal jika file lokal ada isi
    if os.path.exists(local_mem) and os.path.getsize(local_mem) > 10:
        local_backup = f"ingatan_shiro_backup_{timestamp}.json"
        try:
            shutil.copy2(local_mem, local_backup)
            backup_files.append(local_backup)
        except Exception:
            pass

    return {
        "success": True,
        "timestamp": timestamp,
        "backup_files": backup_files
    }

def notify_local_server_reset(port: int = 7474, timeout: float = 2.0) -> bool:
    """Mengirim sinyal POST /api/reset ke server Shiro jika sedang aktif di localhost"""
    import urllib.request
    urls = [f"http://127.0.0.1:{port}/api/reset", f"http://localhost:{port}/api/reset"]
    for url in urls:
        try:
            req = urllib.request.Request(
                url,
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            continue
    return False

def reset_drive_memory(
    drive_dir: Optional[str] = None,
    backup: bool = True,
    reset_world: bool = False,
    keep_profile: bool = False,
    clean_training: bool = True,
    notify_server: bool = True
) -> Dict[str, Any]:
    """
    Mereset total ingatan Shiro di Google Drive dan direktori lokal.
    Secara default juga mengosongkan dataset training (clean_training=True)
    sehingga Shiro benar-benar memulai dari lembaran baru tanpa sisa data lama.
    """
    import glob
    target_drive = drive_dir or get_drive_directory()
    backup_info = {}
    if backup:
        backup_info = create_memory_backup(target_drive, include_world=reset_world, include_training=clean_training)

    facts_cleared = 0
    turns_cleared = 0
    training_samples_cleared = 0
    existing_data = None
    source_candidate = os.path.join(target_drive, "ingatan_shiro.json") if (target_drive and os.path.exists(os.path.join(target_drive, "ingatan_shiro.json"))) else "ingatan_shiro.json"
    if os.path.exists(source_candidate):
        try:
            with open(source_candidate, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                facts_cleared = len(existing_data.get("knowledge_base", {}).get("facts", []))
                turns_cleared = existing_data.get("system_metadata", {}).get("total_turns", 0) or len(existing_data.get("short_term_history", []))
        except Exception:
            pass

    # Hitung jumlah sampel training sebelum dikosongkan
    if clean_training:
        drive_train_dir = os.path.join(target_drive, "training_data") if target_drive else None
        if drive_train_dir and os.path.exists(drive_train_dir):
            training_samples_cleared = max(training_samples_cleared, count_training_samples(drive_train_dir))
        if os.path.exists("training_data"):
            training_samples_cleared = max(training_samples_cleared, count_training_samples("training_data"))

    pristine_memory = get_pristine_memory_data(keep_profile=keep_profile, existing_data=existing_data)
    pristine_world = get_pristine_world_data()

    drive_reset = False
    local_reset = False
    world_reset_done = False
    training_cleaned = False

    # 1. Tulis ke Google Drive jika terhubung
    if target_drive and os.path.exists(target_drive):
        drive_mem_file = os.path.join(target_drive, "ingatan_shiro.json")
        drive_reset = atomic_save_json(drive_mem_file, pristine_memory)
        if reset_world:
            drive_world_file = os.path.join(target_drive, "isekai_world.json")
            atomic_save_json(drive_world_file, pristine_world)
            world_reset_done = True
        if clean_training:
            drive_train_dir = os.path.join(target_drive, "training_data")
            if os.path.exists(drive_train_dir):
                clean_training_directory(drive_train_dir)
                training_cleaned = True

    # 2. Tulis ke direktori lokal
    local_reset = atomic_save_json("ingatan_shiro.json", pristine_memory)
    if reset_world:
        atomic_save_json("isekai_world.json", pristine_world)
        world_reset_done = True
    if clean_training:
        local_train_dir = "training_data"
        if os.path.exists(local_train_dir):
            clean_training_directory(local_train_dir)
            training_cleaned = True

    # 3. Beritahu server aktif jika sedang berjalan
    server_notified = False
    if notify_server:
        server_notified = notify_local_server_reset()

    return {
        "success": drive_reset or local_reset,
        "drive_connected": bool(target_drive and os.path.exists(target_drive)),
        "drive_dir": target_drive,
        "drive_reset": drive_reset,
        "local_reset": local_reset,
        "facts_cleared": facts_cleared,
        "turns_cleared": turns_cleared,
        "training_samples_cleared": training_samples_cleared,
        "world_reset": world_reset_done,
        "training_cleaned": training_cleaned,
        "backup_info": backup_info,
        "server_notified": server_notified
    }

def get_drive_memory_status(drive_dir: Optional[str] = None) -> Dict[str, Any]:
    """Mendapatkan status saat ini dari penyimpanan ingatan di Drive dan lokal"""
    import glob
    target_drive = drive_dir or get_drive_directory()
    drive_connected = bool(target_drive and os.path.exists(target_drive))
    
    drive_stats = {"exists": False, "size_bytes": 0, "facts": 0, "turns": 0, "user_name": "-", "training_samples": 0}
    if drive_connected:
        d_mem = os.path.join(target_drive, "ingatan_shiro.json")
        if os.path.exists(d_mem):
            drive_stats["exists"] = True
            drive_stats["size_bytes"] = os.path.getsize(d_mem)
            try:
                with open(d_mem, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    drive_stats["facts"] = len(d.get("knowledge_base", {}).get("facts", []))
                    drive_stats["turns"] = d.get("system_metadata", {}).get("total_turns", 0) or len(d.get("short_term_history", []))
                    drive_stats["user_name"] = d.get("system_metadata", {}).get("user_name", "Kakak")
            except Exception:
                pass
        d_train = os.path.join(target_drive, "training_data")
        if os.path.exists(d_train):
            drive_stats["training_samples"] = count_training_samples(d_train)

    local_stats = {"exists": False, "size_bytes": 0, "facts": 0, "turns": 0, "user_name": "-", "training_samples": 0}
    if os.path.exists("ingatan_shiro.json"):
        local_stats["exists"] = True
        local_stats["size_bytes"] = os.path.getsize("ingatan_shiro.json")
        try:
            with open("ingatan_shiro.json", "r", encoding="utf-8") as f:
                d = json.load(f)
                local_stats["facts"] = len(d.get("knowledge_base", {}).get("facts", []))
                local_stats["turns"] = d.get("system_metadata", {}).get("total_turns", 0) or len(d.get("short_term_history", []))
                local_stats["user_name"] = d.get("system_metadata", {}).get("user_name", "Kakak")
        except Exception:
            pass
    if os.path.exists("training_data"):
        local_stats["training_samples"] = count_training_samples("training_data")

    backups = []
    if drive_connected:
        for b in glob.glob(os.path.join(target_drive, "*backup*.*")):
            backups.append(os.path.basename(b))
        for b in glob.glob(os.path.join(target_drive, "*backup*")):
            if os.path.isdir(b) and os.path.basename(b) not in backups:
                backups.append(os.path.basename(b) + "/")

    return {
        "drive_connected": drive_connected,
        "drive_dir": target_drive,
        "drive_stats": drive_stats,
        "local_stats": local_stats,
        "backups": sorted(backups, reverse=True)
    }
