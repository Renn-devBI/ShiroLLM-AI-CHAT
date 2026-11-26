# -*- coding: utf-8 -*-
"""
Shiro Colab & Local Server Auto-Healing Supervisor Watchdog
Menjaga server web.py dan tunnel Cloudflare/Ngrok tetap hidup:
- Deteksi GPU CUDA aktual (mencegah mismatch env N_GPU_LAYERS vs CPU runtime)
- Auto-restart server jika terjadi crash native (SIGABRT/OOM) tanpa mematikan cell Colab
- Step-down otomatis context window jika crash berulang akibat OOM/GGML
- Auto-restart Cloudflare Tunnel jika koneksi tunnel terputus
- Sinkronisasi berkala ingatan ke Google Drive
"""

import os
import re
import sys
import time
import shutil
import subprocess
import urllib.request
from datetime import datetime
from typing import Optional, Tuple, List


CONTEXT_STEPDOWN_LADDER: List[int] = [262144, 131072, 65536, 32768]


def detect_colab_gpu() -> Tuple[bool, str]:
    """Memeriksa keberadaan GPU NVIDIA nyata melalui nvidia-smi."""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            gpu_info = res.stdout.strip().splitlines()[0].strip()
            return True, gpu_info
    except Exception:
        pass
    return False, ""


def configure_runtime_env() -> Tuple[bool, str]:
    """
    Menyiapkan variabel lingkungan GPU/CPU & buffering log secara akurat
    sebelum menyalakan web.py.
    """
    os.environ["PYTHONUNBUFFERED"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"

    has_gpu, gpu_info = detect_colab_gpu()
    if has_gpu:
        os.environ["SHIRO_GPU_LAYERS"] = "-1"
        os.environ["N_GPU_LAYERS"] = "-1"
    else:
        os.environ["SHIRO_GPU_LAYERS"] = "0"
        os.environ["N_GPU_LAYERS"] = "0"
    return has_gpu, gpu_info


def backup_memory_to_drive(drive_dir: Optional[str] = None) -> bool:
    """Mencadangkan ingatan, profil, dan data training ke Google Drive jika tersedia."""
    target_dir = drive_dir or os.environ.get("SHIRO_DRIVE_DIR", "/content/drive/MyDrive/Shiro_Memory")
    if not target_dir or not os.path.exists(target_dir):
        return False
    try:
        for fname in ["ingatan_shiro.json", "isekai_world.json", "api_key.json"]:
            if os.path.exists(fname):
                shutil.copy2(fname, os.path.join(target_dir, fname))
        for dname in ["profile", "training_data"]:
            if os.path.exists(dname):
                shutil.copytree(dname, os.path.join(target_dir, dname), dirs_exist_ok=True)
        return True
    except Exception as e:
        print(f"[Watchdog] Peringatan sinkronisasi Drive: {e}", flush=True)
        return False


def wait_for_server_ready(
    server_proc: subprocess.Popen,
    timeout_sec: int = 180,
    port: int = 7474,
) -> bool:
    """Menunggu hingga Flask server merespons 200 di /api/health atau /api/key."""
    urls = [f"http://127.0.0.1:{port}/api/health", f"http://127.0.0.1:{port}/api/key"]
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if server_proc.poll() is not None:
            return False
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=1.5) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
        time.sleep(1.0)
    return False


def start_cloudflared_tunnel(
    tunnel_log: str = "/content/tunnel.log",
    binary: str = "/content/cloudflared",
    port: int = 7474,
    wait_sec: int = 60,
) -> Tuple[subprocess.Popen, Optional[str]]:
    """Menyalakan cloudflared tunnel dan mengekstrak URL trycloudflare.com."""
    try:
        if os.path.exists(tunnel_log):
            os.remove(tunnel_log)
    except OSError:
        pass

    log_handle = open(tunnel_log, "w", encoding="utf-8")
    try:
        tunnel_proc = subprocess.Popen(
            [binary, "tunnel", "--url", f"http://127.0.0.1:{port}"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
    finally:
        log_handle.close()

    cf_url = None
    for _ in range(wait_sec):
        if tunnel_proc.poll() is not None:
            break
        time.sleep(1.0)
        if os.path.exists(tunnel_log):
            try:
                with open(tunnel_log, "r", encoding="utf-8", errors="ignore") as f:
                    match = re.search(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)", f.read())
                    if match:
                        cf_url = match.group(1)
                        break
            except Exception:
                pass
    return tunnel_proc, cf_url


def spawn_web_server(log_path: str, append: bool = False) -> subprocess.Popen:
    """Menjalankan web.py dengan stdout/stderr diarahkan ke log_path (unbuffered)."""
    mode = "a" if append else "w"
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    with open(log_path, mode, encoding="utf-8") as log_f:
        if append:
            log_f.write(f"\n\n=== [WATCHDOG AUTO-RESTART {datetime.now().isoformat()}] ===\n")
            log_f.flush()
        proc = subprocess.Popen(
            [sys.executable, "-u", "web.py"],
            stdout=log_f,
            stderr=log_f,
            env=env,
        )
    return proc


def _next_stepdown_ctx(current_ctx: Optional[int]) -> int:
    """Memilih context window lebih aman berikutnya saat terjadi crash OOM/SIGABRT berulang."""
    if current_ctx is None:
        return CONTEXT_STEPDOWN_LADDER[0]
    for candidate in CONTEXT_STEPDOWN_LADDER:
        if candidate < current_ctx:
            return candidate
    return CONTEXT_STEPDOWN_LADDER[-1]


def _read_log_tail(log_path: str, max_chars: int = 1600) -> str:
    if not log_path or not os.path.exists(log_path):
        return ""
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
            return data[-max_chars:]
    except Exception:
        return ""


def run_shiro_supervisor(
    server_proc: subprocess.Popen,
    log_path: str,
    public_url: Optional[str],
    tunnel_proc: Optional[subprocess.Popen] = None,
    tunnel_mode: str = "cloudflare",
    drive_dir: Optional[str] = None,
    max_rapid_restarts: int = 8,
    rapid_window_sec: float = 300.0,
    poll_interval: float = 5.0,
    sync_interval: float = 600.0,
    port: int = 7474,
) -> None:
    """
    Loop penjaga (watchdog) anti-mati-mendadak untuk Google Colab.
    Jika server web.py atau tunnel berhenti tiba-tiba, otomatis backup memori,
    turunkan context bila perlu, dan restart kembali agar AI tetap online.
    """
    restart_timestamps: List[float] = []
    last_sync_time = time.monotonic()
    active_url = public_url

    try:
        while True:
            time.sleep(poll_interval)
            now = time.monotonic()

            # 1. Cek apakah tunnel Cloudflare terputus -> restart otomatis
            if tunnel_mode == "cloudflare" and tunnel_proc is not None and tunnel_proc.poll() is not None:
                print(
                    f"\n[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Tunnel Cloudflare berhenti "
                    f"(exit={tunnel_proc.returncode}). Menyalakan ulang tunnel...",
                    flush=True,
                )
                try:
                    tunnel_proc, new_url = start_cloudflared_tunnel(port=port)
                    if new_url:
                        active_url = new_url
                        print(f"✅ Tunnel Cloudflare baru aktif: {active_url}", flush=True)
                except Exception as e_tun:
                    print(f"[Watchdog] Gagal memulai ulang tunnel: {e_tun}", flush=True)

            # 2. Cek apakah proses web.py berhenti tiba-tiba -> auto-heal & restart
            exit_code = server_proc.poll()
            if exit_code is not None:
                ts_str = datetime.now().strftime("%H:%M:%S")
                print(
                    f"\n[{ts_str}] ⚠️ Server Shiro berhenti tak terduga (exit code: {exit_code}).",
                    flush=True,
                )
                tail = _read_log_tail(log_path, max_chars=1200)
                if tail.strip():
                    print("--- Ringkasan log terakhir sebelum crash ---", flush=True)
                    print(tail.strip(), flush=True)
                    print("--------------------------------------------", flush=True)

                # Amankan memori ke Drive sebelum restart
                if backup_memory_to_drive(drive_dir):
                    print(f"[{ts_str}] 💾 Ingatan & sesi berhasil diamankan ke Google Drive.", flush=True)

                # Evaluasi rate crash (circuit breaker)
                restart_timestamps = [t for t in restart_timestamps if (now - t) <= rapid_window_sec]
                restart_timestamps.append(now)

                if len(restart_timestamps) > max_rapid_restarts:
                    print(
                        f"\n❌ Server mengalami crash berulang ({len(restart_timestamps)}x dalam "
                        f"{int(rapid_window_sec)}s). Watchdog berhenti untuk mencegah loop tak terbatas. "
                        f"Periksa {log_path} dan pastikan Runtime Colab memakai GPU (A100/L4/T4).",
                        flush=True,
                    )
                    break

                # Jika crash native (SIGABRT -6/134 atau OOM SIGKILL -9/137), turunkan context bertahap agar stabil
                if exit_code in (-9, 137, -6, 134) and len(restart_timestamps) >= 2:
                    cur_env = os.environ.get("SHIRO_QWEN38_27B_CONTEXT_SIZE")
                    cur_ctx = int(cur_env) if (cur_env and cur_env.isdigit()) else None
                    next_ctx = _next_stepdown_ctx(cur_ctx)
                    os.environ["SHIRO_QWEN38_27B_CONTEXT_SIZE"] = str(next_ctx)
                    print(
                        f"[{ts_str}] 🛡️ Auto-recovery: menurunkan batas context ke {next_ctx:,} tokens "
                        f"untuk mencegah crash OOM/GGML berulang.",
                        flush=True,
                    )

                backoff = min(3 * len(restart_timestamps), 15)
                print(
                    f"[{ts_str}] 🔄 Memulai ulang Server Shiro secara otomatis dalam {backoff} detik "
                    f"(percobaan #{len(restart_timestamps)})...",
                    flush=True,
                )
                time.sleep(backoff)

                server_proc = spawn_web_server(log_path, append=True)
                if wait_for_server_ready(server_proc, timeout_sec=180, port=port):
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Server Shiro berhasil pulih otomatis! "
                        f"Web UI tetap aktif di: {active_url or f'http://127.0.0.1:{port}'}",
                        flush=True,
                    )
                else:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Restart belum siap, watchdog akan mencoba lagi...",
                        flush=True,
                    )

            # 3. Sinkronisasi berkala ke Google Drive agar ingatan selalu aman
            if (now - last_sync_time) >= sync_interval:
                backup_memory_to_drive(drive_dir)
                last_sync_time = now

    except KeyboardInterrupt:
        print("\nMenghentikan Server Shiro atas permintaan pengguna...", flush=True)
        for proc in (server_proc, tunnel_proc):
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        if backup_memory_to_drive(drive_dir):
            print("✓ Data dan ingatan tersinkron ke Google Drive.", flush=True)
        print("Server Shiro dihentikan dengan aman.", flush=True)
