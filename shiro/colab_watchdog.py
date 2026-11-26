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
import glob
import json
import time
import shutil
import platform
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


def refresh_cuda_ldconfig() -> str:
    """Memastikan jalur library CUDA/cuBLAS aktif di LD_LIBRARY_PATH dan ldconfig (Linux)."""
    candidate_globs = [
        "/usr/local/lib/python*/dist-packages/nvidia/*/lib",
        "/usr/lib/python*/dist-packages/nvidia/*/lib",
        "/usr/local/cuda/lib64",
        "/usr/local/cuda-12*/lib64",
        "/usr/local/cuda-13*/lib64",
    ]
    valid_dirs: List[str] = []
    for pattern in candidate_globs:
        for p in glob.glob(pattern):
            if os.path.isdir(p) and p not in valid_dirs:
                valid_dirs.append(p)

    existing_ld = [x for x in os.environ.get("LD_LIBRARY_PATH", "").split(":") if x]
    merged_ld: List[str] = []
    for d in valid_dirs + existing_ld:
        if d and d not in merged_ld:
            merged_ld.append(d)
    if merged_ld:
        os.environ["LD_LIBRARY_PATH"] = ":".join(merged_ld)

    if platform.system() == "Linux" and os.path.isdir("/usr/lib/x86_64-linux-gnu"):
        try:
            for d in valid_dirs:
                for so_path in glob.glob(os.path.join(d, "*.so*")):
                    target_link = os.path.join("/usr/lib/x86_64-linux-gnu", os.path.basename(so_path))
                    if not os.path.exists(target_link):
                        try:
                            os.symlink(so_path, target_link)
                        except OSError:
                            pass
            subprocess.run(["ldconfig"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        except Exception:
            pass
    return os.environ.get("LD_LIBRARY_PATH", "")


def detect_cuda_tag() -> List[str]:
    """Mendeteksi versi CUDA driver/runtime terpasang lalu mengembalikan urutan tag wheel paling kompatibel."""
    ver: Optional[Tuple[int, int]] = None
    for cmd, pattern in [
        (["nvidia-smi"], r"CUDA Version:\s*(\d+)\.(\d+)"),
        (["nvcc", "--version"], r"release\s+(\d+)\.(\d+)"),
    ]:
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4)
            if res.returncode == 0 and res.stdout:
                m = re.search(pattern, res.stdout)
                if m:
                    ver = (int(m.group(1)), int(m.group(2)))
                    break
        except Exception:
            pass

    if ver is None:
        try:
            import torch
            tcuda = getattr(torch.version, "cuda", None)
            if tcuda:
                parts = str(tcuda).split(".")
                ver = (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except Exception:
            pass

    if ver is None:
        return ["cu124", "cu126", "cu128"]
    if ver >= (13, 2):
        return ["cu132", "cu131", "cu130", "cu128", "cu126", "cu124"]
    if ver >= (13, 1):
        return ["cu131", "cu130", "cu128", "cu126", "cu124"]
    if ver >= (13, 0):
        return ["cu130", "cu128", "cu126", "cu124"]
    if ver >= (12, 8):
        return ["cu128", "cu126", "cu124"]
    if ver >= (12, 6):
        return ["cu126", "cu124"]
    return ["cu124", "cu126", "cu128"]


def check_cuda_offload_subprocess() -> bool:
    """Memeriksa di subprocess baru apakah llama-cpp-python terpasang mendukung offload GPU CUDA."""
    try:
        res = subprocess.run(
            [
                sys.executable,
                "-c",
                "import llama_cpp; print('SHIRO_GPU_OFFLOAD=' + str(bool(llama_cpp.llama_supports_gpu_offload())))",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=dict(os.environ),
            timeout=20,
        )
        return res.returncode == 0 and "SHIRO_GPU_OFFLOAD=True" in (res.stdout or "")
    except Exception:
        return False


def find_prebuilt_cuda_wheel_url(
    py_tag: Optional[str] = None,
    preferred_cu_tags: Optional[List[str]] = None,
) -> List[str]:
    """Mencari URL wheel CUDA Linux pra-kompilasi (termasuk Python 3.12 & 3.13) dari JamePeng releases."""
    py_tag = py_tag or f"cp{sys.version_info.major}{sys.version_info.minor}"
    cu_tags = preferred_cu_tags or detect_cuda_tag()
    expected_suffix = f"-{py_tag}-{py_tag}-linux_x86_64.whl"

    candidates_by_cu: dict = {cu: [] for cu in cu_tags}
    other_matches: List[str] = []
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/JamePeng/llama-cpp-python/releases?per_page=25",
            headers={"User-Agent": "Shiro-LLMA"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            releases = json.loads(resp.read().decode("utf-8", errors="ignore"))
        if isinstance(releases, list):
            for rel in releases:
                assets = rel.get("assets") or []
                for asset in assets:
                    name = asset.get("name", "")
                    dl_url = asset.get("browser_download_url", "")
                    if not (name.endswith(expected_suffix) and "+cu" in name and dl_url):
                        continue
                    matched = False
                    for cu in cu_tags:
                        if f"+{cu}-" in name:
                            candidates_by_cu[cu].append(dl_url)
                            matched = True
                            break
                    if not matched:
                        other_matches.append(dl_url)
    except Exception:
        pass

    ordered: List[str] = []
    for cu in cu_tags:
        for u in candidates_by_cu.get(cu, []):
            if u not in ordered:
                ordered.append(u)
    for u in other_matches:
        if u not in ordered:
            ordered.append(u)

    # Static fallback URLs jika GitHub API terkena rate-limit
    for cu in cu_tags:
        static_url = (
            f"https://github.com/JamePeng/llama-cpp-python/releases/download/"
            f"v0.4.8-{cu}-linux-20261122/"
            f"llama_cpp_python-0.4.8+{cu}-{py_tag}-{py_tag}-linux_x86_64.whl"
        )
        if static_url not in ordered:
            ordered.append(static_url)
    return ordered


def ensure_cuda_llama_cpp(force: bool = False) -> bool:
    """
    Memastikan llama-cpp-python aktif dengan akselerasi CUDA di GPU Colab (termasuk Python 3.13).
    Jika saat ini terpasang versi CPU-only (menyebabkan GPU RAM 0.0 GB), otomatis mengunduh
    wheel CUDA pra-kompilasi (~15 detik) atau build CUDA sebagai fallback terakhir.
    """
    has_gpu, gpu_info = detect_colab_gpu()
    if not has_gpu:
        return False

    refresh_cuda_ldconfig()
    if not force and check_cuda_offload_subprocess():
        return True

    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    print("=" * 62, flush=True)
    print(f"🔧 [CUDA SETUP] GPU terdeteksi ({gpu_info}), Python {py_tag}.", flush=True)
    print("   Memastikan llama-cpp-python terpasang dengan akselerasi CUDA penuh...", flush=True)
    print("=" * 62, flush=True)

    wheel_urls = find_prebuilt_cuda_wheel_url(py_tag=py_tag)
    for whl_url in wheel_urls[:4]:
        print(f"📦 Mencoba wheel CUDA pra-kompilasi: {os.path.basename(whl_url)}", flush=True)
        try:
            res = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--force-reinstall",
                    "--no-deps",
                    "--no-cache-dir",
                    whl_url,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180,
            )
            if res.returncode == 0:
                refresh_cuda_ldconfig()
                if check_cuda_offload_subprocess():
                    print("✅ Akselerasi CUDA GPU (llama_supports_gpu_offload=True) BERHASIL DIAKTIFKAN!", flush=True)
                    return True
        except Exception as e_whl:
            print(f"⚠️ Gagal memasang wheel ({os.path.basename(whl_url)}): {e_whl}", flush=True)

    print("🛠️ Wheel pra-kompilasi tidak cocok, mengompilasi ulang llama-cpp-python dengan CUDA...", flush=True)
    build_env = dict(os.environ)
    build_env["CMAKE_ARGS"] = "-DGGML_CUDA=on -DGGML_CUDA_FA_ALL_QUANTS=on -DCMAKE_CUDA_ARCHITECTURES=native"
    build_env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(max(2, os.cpu_count() or 4))
    build_env["FORCE_CMAKE"] = "1"
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--force-reinstall",
                "llama-cpp-python",
            ],
            env=build_env,
            timeout=600,
        )
        refresh_cuda_ldconfig()
        if check_cuda_offload_subprocess():
            print("✅ Kompilasi CUDA GPU berhasil (llama_supports_gpu_offload=True)!", flush=True)
            return True
    except Exception as e_src:
        print(f"⚠️ Gagal kompilasi CUDA dari source: {e_src}", flush=True)

    return check_cuda_offload_subprocess()


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
