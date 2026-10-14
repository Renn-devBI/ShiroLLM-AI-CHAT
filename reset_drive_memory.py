#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shiro LLMA - Reset Ingatan & Cache Google Drive
Skrip utilitas untuk membersihkan ingatan lama / halusinasi dari Google Drive dan direktori lokal Colab.
Otomatis membuat cadangan (backup) ber-timestamp sebelum reset.

Penggunaan:
    python reset_drive_memory.py                # Reset standar (auto-backup ke Drive & lokal)
    python reset_drive_memory.py --status       # Cek status & daftar backup tanpa mereset
    python reset_drive_memory.py --all          # Reset total: ingatan + world + cache training
    python reset_drive_memory.py --reset-world  # Ikut mereset isekai_world.json ke default
    python reset_drive_memory.py --keep-profile # Bersihkan fakta & chat tapi simpan profil nama user
    python reset_drive_memory.py --no-backup    # Lewati pembuatan file backup
"""

import os
import sys
import argparse

# Pastikan UTF-8 encoding di Windows dan Linux
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Pastikan direktori root masuk ke sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from shiro.memory.drive_sync import (
    get_drive_directory,
    reset_drive_memory,
    get_drive_memory_status
)

def format_size(bytes_val: int) -> str:
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    else:
        return f"{bytes_val / (1024 * 1024):.1f} MB"

def show_status(drive_dir=None):
    status = get_drive_memory_status(drive_dir)
    print("\n" + "=" * 68)
    print("  [STATUS] INGATAN SHIRO (Google Drive & Lokal)")
    print("=" * 68)
    
    # Drive
    if status["drive_connected"]:
        print(f"  Google Drive        : [TERHUBUNG]")
        print(f"  Direktori Drive     : {status['drive_dir']}")
        ds = status["drive_stats"]
        if ds["exists"]:
            print(f"  Berkas Drive        : ingatan_shiro.json ({format_size(ds['size_bytes'])})")
            print(f"  Fakta di Drive      : {ds['facts']} fakta tersimpan")
            print(f"  Pesan di Drive      : {ds['turns']} giliran chat")
            print(f"  Nama Pengguna       : {ds['user_name']}")
        else:
            print("  Berkas Drive        : Belum ada ingatan_shiro.json di Drive")
    else:
        print("  Google Drive        : [TIDAK TERHUBUNG / BUKAN DI COLAB]")
        if status["drive_dir"]:
            print(f"  Target Path         : {status['drive_dir']} (folder belum ada)")

    # Local
    print("-" * 68)
    ls = status["local_stats"]
    if ls["exists"]:
        print(f"  Penyimpanan Lokal   : ingatan_shiro.json ({format_size(ls['size_bytes'])})")
        print(f"  Fakta Lokal         : {ls['facts']} fakta tersimpan")
        print(f"  Pesan Lokal         : {ls['turns']} giliran chat")
        print(f"  Nama Pengguna       : {ls['user_name']}")
    else:
        print("  Penyimpanan Lokal   : Belum ada ingatan_shiro.json lokal")

    # Backups
    print("-" * 68)
    backups = status.get("backups", [])
    if backups:
        print(f"  Cadangan di Drive   : {len(backups)} berkas backup ditemukan:")
        for b in backups[:5]:
            print(f"    - {b}")
        if len(backups) > 5:
            print(f"    ... dan {len(backups) - 5} berkas backup lainnya.")
    else:
        print("  Cadangan di Drive   : Belum ada berkas backup.")

    print("=" * 68 + "\n")

def run_reset(args):
    print("\n" + "=" * 68)
    print("  [RESET] Shiro LLMA - Reset Ingatan & Cache Google Drive")
    print("=" * 68)

    drive_dir = args.drive_dir or os.environ.get("SHIRO_DRIVE_DIR")
    if not drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
        drive_dir = "/content/drive/MyDrive/Shiro_Memory"

    # [1] Periksa status Google Drive
    print("[1] Memeriksa Lokasi Penyimpanan...")
    if drive_dir and os.path.exists(drive_dir):
        print(f"    [OK] Google Drive terdeteksi: {drive_dir}")
    else:
        if drive_dir:
            print(f"    [INFO] Target Drive ditentukan ({drive_dir}) namun belum ada.")
        else:
            print("    [INFO] Google Drive tidak aktif. Reset dilakukan pada direktori lokal.")

    # [2] Eksekusi Reset
    print("[2] Melakukan Reset Ingatan...")
    result = reset_drive_memory(
        drive_dir=drive_dir,
        backup=not args.no_backup,
        reset_world=args.reset_world or args.all,
        keep_profile=args.keep_profile,
        clean_training=args.clean_training or args.all,
        notify_server=not args.no_server_sync
    )

    # [3] Laporkan Hasil Backup
    if not args.no_backup:
        b_files = result.get("backup_info", {}).get("backup_files", [])
        if b_files:
            print("[3] Cadangan (Backup) Berhasil Dibuat:")
            for bf in b_files:
                print(f"    [BACKUP] {bf}")
        else:
            print("[3] Cadangan (Backup): Tidak ada berkas lama yang perlu dicadangkan.")
    else:
        print("[3] Cadangan (Backup): Dilewati (--no-backup).")

    # [4] Laporkan Pembersihan
    print("[4] Status Pembersihan:")
    print(f"    [OK] {result['facts_cleared']} fakta lama berhasil dibersihkan.")
    print(f"    [OK] {result['turns_cleared']} riwayat percakapan lama dibersihkan.")
    if result.get("drive_reset"):
        print(f"    [OK] Google Drive ({drive_dir}/ingatan_shiro.json) diperbarui dengan template bersih.")
    if result.get("local_reset"):
        print("    [OK] Berkas lokal (ingatan_shiro.json) diperbarui dengan template bersih.")
    if result.get("world_reset"):
        print("    [OK] Pengaturan dunia isekai_world.json berhasil di-reset ke default.")
    if result.get("training_cleaned"):
        print("    [OK] Cache berkas training_data/ lama berhasil dibersihkan.")

    # [5] Notifikasi Server
    if result.get("server_notified"):
        print("[5] Sinkronisasi Server Aktif:")
        print("    [OK] Server Shiro aktif di localhost:7474 berhasil menyelaraskan memori baru secara langsung!")
    elif not args.no_server_sync:
        print("[5] Sinkronisasi Server Aktif:")
        print("    [INFO] Server Shiro tidak sedang berjalan di localhost:7474 (tidak perlu sinkronisasi live).")

    print("\n" + "=" * 68)
    print("  [SUKSES] Ingatan Shiro telah bersih dari riwayat dan halusinasi!")
    print("  Saat server Shiro dijalankan, ia akan mulai dari awal tanpa data lama.")
    print("=" * 68 + "\n")
    return 0

def main():
    parser = argparse.ArgumentParser(
        description="Shiro LLMA - Reset ingatan di Google Drive dan direktori lokal Colab"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Hanya tampilkan status ingatan di Drive & lokal serta daftar backup"
    )
    parser.add_argument(
        "--drive-dir",
        type=str,
        default=None,
        help="Path ke direktori Google Drive (default: $SHIRO_DRIVE_DIR atau /content/drive/MyDrive/Shiro_Memory)"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Jangan buat file cadangan (backup) sebelum reset"
    )
    parser.add_argument(
        "--reset-world",
        action="store_true",
        help="Ikut mereset berkas isekai_world.json ke pengaturan bawaan Arcadia"
    )
    parser.add_argument(
        "--clean-training",
        action="store_true",
        help="Bersihkan berkas riwayat dataset di folder training_data"
    )
    parser.add_argument(
        "--keep-profile",
        action="store_true",
        help="Pertahankan nama pengguna & profil interaksi (hanya reset fakta & riwayat chat)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Reset total: bersihkan ingatan, world settings, dan cache dataset training"
    )
    parser.add_argument(
        "--no-server-sync",
        action="store_true",
        help="Jangan mencoba mengirimkan sinyal reset ke localhost:7474 jika server sedang aktif"
    )

    args = parser.parse_args()

    if args.status:
        show_status(args.drive_dir)
        sys.exit(0)

    exit_code = run_reset(args)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
