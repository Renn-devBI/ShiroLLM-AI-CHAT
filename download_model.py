import os
import sys
import json
from huggingface_hub import hf_hub_download

os.makedirs("model", exist_ok=True)

# Definisi Model Tersedia:
COLAB_MODELS = {
    "27b": {
        "repo": "HauhauCS/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-GGUF",
        "file": "Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-Q4_K_P.gguf",
        "alt_files": ["Qwen3.8-27B-Uncensored-Q4_K_M.gguf"],
        "extra_file": "mmproj-Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-BF16.gguf",
        "extra_alias": "mmproj-BF16.gguf",
        "desc": "Qwen3.8-27B-Uncensored Multimodal (Model Utama: Roleplay, Gambar/Vision & Deep Reasoning / A100 GPU, ~16.8 GB + mmproj-BF16)"
    },
    "vl": {
        "repo": "unsloth/Qwen2.5-VL-7B-Instruct-GGUF",
        "file": "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
        "extra_file": "mmproj-F16.gguf",
        "desc": "Qwen2.5-VL-7B (Model Vision Multimodal: Kamera Webcam & Gambar VTuber, ~5.6 GB + mmproj)"
    },
    "4b": {
        "repo": "Qwen/Qwen3-4B-GGUF",
        "file": "Qwen3-4B-Q4_K_M.gguf",
        "extra_file": None,
        "desc": "Qwen3-4B (Model Ringan: Respon Kilat CPU/T4 GPU, ~2.5 GB)"
    },
    "32b": {
        "repo": "Qwen/Qwen3-32B-GGUF",
        "file": "Qwen3-32B-Q4_K_M.gguf",
        "extra_file": None,
        "desc": "Qwen3-32B (Model Penalaran Tinggi Teks / A100 GPU, ~19.8 GB)"
    },
    "vl-32b": {
        "repo": "bartowski/Qwen_Qwen2.5-VL-32B-Instruct-GGUF",
        "file": "Qwen_Qwen2.5-VL-32B-Instruct-Q4_K_M.gguf",
        "extra_file": "mmproj-Qwen_Qwen2.5-VL-32B-Instruct-f16.gguf",
        "desc": "Qwen2.5-VL-32B (Model Vision Multimodal #1: Penalaran Tinggi / A100 GPU, ~19.8 GB)"
    },
    "7b": {
        "repo": "bartowski/Qwen2.5-7B-Instruct-GGUF",
        "file": "Qwen2.5-7B-Instruct-Q5_K_M.gguf",
        "extra_file": None,
        "desc": "Qwen2.5-7B (Model Hemat VRAM / GPU T4, ~5.4 GB)"
    },
    "3.2b": {
        "repo": "bartowski/Llama-3.2-3B-Instruct-uncensored-GGUF",
        "file": "Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf",
        "extra_file": None,
        "desc": "Llama-3.2-3B-Uncensored (Model Super Ringan Fallback GPU T4, ~2.9 GB)"
    }
}

def set_active_models_in_config(downloaded_filenames, primary_filename=None):
    """
    Mendaftarkan seluruh model yang diunduh ke model_config.json
    dan menyetel primary_filename sebagai model aktif (current_model).
    """
    config_file = "model_config.json"
    if not os.path.exists(config_file):
        return
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        available = cfg.get("available_models", [])
        for fname in reversed(downloaded_filenames):
            m_path = f"model/{fname}"
            if m_path in available:
                available.remove(m_path)
            available.insert(0, m_path)
        cfg["available_models"] = available

        if primary_filename:
            cfg["current_model"] = f"model/{primary_filename}"
        elif downloaded_filenames:
            cfg["current_model"] = f"model/{downloaded_filenames[0]}"

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        print(f"[CONFIG] Model aktif diatur ke: {cfg.get('current_model')}")
        print(f"[CONFIG] Total model tersedia di menu UI: {len(available)} model terdaftar.")
    except Exception as e:
        print(f"[WARN] Gagal memperbarui model_config.json: {e}")

def download_single_model(m_key, info):
    repo = info["repo"]
    fname = info["file"]
    extra = info.get("extra_file")
    desc = info["desc"]
    target_path = os.path.join("model", fname)

    print("\n" + "=" * 65)
    print(f"[TARGET] {desc}")
    print(f"Repo : {repo}")
    print(f"File : {fname}")
    print("=" * 65)

    success = False
    alt_files = info.get("alt_files", [])
    found_alt = None
    for af in alt_files:
        af_path = os.path.join("model", af)
        if os.path.exists(af_path):
            found_alt = af_path
            break

    if os.path.exists(target_path):
        size_gb = os.path.getsize(target_path) / (1024 * 1024 * 1024)
        print(f"[OK] Model {fname} sudah ada di folder model/ ({size_gb:.1f} GB). Skip download.")
        success = True
    elif found_alt:
        size_gb = os.path.getsize(found_alt) / (1024 * 1024 * 1024)
        print(f"[OK] Model varian {os.path.basename(found_alt)} sudah ada di folder model/ ({size_gb:.1f} GB). Skip download.")
        fname = os.path.basename(found_alt)
        success = True
    else:
        print(f"[DOWNLOAD] Mengunduh model {fname}...")
        try:
            hf_hub_download(
                repo_id=repo,
                filename=fname,
                local_dir="model",
                local_dir_use_symlinks=False
            )
            print(f"[OK] Model {fname} berhasil diunduh ke folder model/.")
            success = True
        except Exception as e:
            print(f"[ERROR] Gagal mengunduh {fname}: {e}")
            success = False

    if extra:
        extra_path = os.path.join("model", extra)
        extra_alias = info.get("extra_alias")
        alias_path = os.path.join("model", extra_alias) if extra_alias else None

        if os.path.exists(extra_path) or (alias_path and os.path.exists(alias_path)):
            print(f"[OK] Vision Projector {extra} sudah ada di folder model/. Skip download.")
        else:
            print(f"[DOWNLOAD] Mengunduh Vision Projector ({extra})...")
            try:
                hf_hub_download(
                    repo_id=info.get("extra_repo", repo),
                    filename=extra,
                    local_dir="model",
                    local_dir_use_symlinks=False
                )
                print(f"[OK] Projector {extra} berhasil diunduh.")
                if alias_path and os.path.exists(extra_path) and not os.path.exists(alias_path):
                    import shutil
                    try:
                        shutil.copy2(extra_path, alias_path)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[WARN] Gagal download projector {extra}: {e}")
    
    return success

def main():
    in_colab = os.path.exists("/content") or "COLAB_GPU" in os.environ
    force_local = "--force-local" in sys.argv or os.environ.get("SHIRO_FORCE_LOCAL_DOWNLOAD") == "1"
    dry_run = "--dry-run" in sys.argv
    
    if not in_colab and not force_local and not dry_run:
        print("\n" + "=" * 65)
        print("[PROTEKSI DISK LOKAL AKTIF]")
        print("Script download_model.py khusus dijalankan di Google Colab cloud GPU.")
        print("Untuk menjaga kapasitas SSD/HDD komputer Anda, download lokal dinonaktifkan.")
        print("=" * 65 + "\n")
        return

    # Kumpulan 3 Model Utama Shiro (27B Uncensored + VL-7B Vision + 4B Ringan)
    TRIO_KEYS = ["27b", "vl", "4b"]

    ALIAS_MAP = {
        "27b": TRIO_KEYS,          # Default Colab: mengunduh 3 model utama (27B, VL, 4B)
        "3models": TRIO_KEYS,
        "3model": TRIO_KEYS,
        "trio": TRIO_KEYS,
        "default": TRIO_KEYS,
        "recommended": TRIO_KEYS,
        "shiro": TRIO_KEYS,
        "27b-only": ["27b"],
        "single-27b": ["27b"],
        "27b_only": ["27b"],
        "qwen27b": ["27b"],
        "qwen3.8": ["27b"],
        "uncensored": ["27b"],
        "vl": ["vl"],
        "vision": ["vl"],
        "qwen-vl": ["vl"],
        "qwen2.5-vl": ["vl"],
        "vl-7b": ["vl"],
        "4b": ["4b"],
        "qwen4b": ["4b"],
        "cpu": ["4b"],
        "32b": ["32b"],
        "main": ["32b"],
        "qwen32b": ["32b"],
        "vl-32b": ["vl-32b"],
        "7b": ["7b"],
        "fast": ["7b"],
        "qwen7b": ["7b"],
        "3.2b": ["3.2b"],
        "llama": ["3.2b"],
        "llama3.2": ["3.2b"],
        "a100": ["32b", "27b", "vl", "4b"],
        "t4": ["vl", "4b", "7b", "3.2b"],
        "hemat": ["vl", "4b", "7b", "3.2b"],
        "all": ["27b", "vl", "4b", "32b", "7b", "3.2b"],
        "semua": ["27b", "vl", "4b", "32b", "7b", "3.2b"]
    }

    # Kumpulkan input dari CLI arguments atau environment variable
    raw_tokens = []
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            clean = arg.replace("--", "").strip().lower()
            if clean in ["force-local", "dry-run"]:
                continue
            if "," in clean:
                raw_tokens.extend([x.strip() for x in clean.split(",") if x.strip()])
            else:
                raw_tokens.append(clean)

    if not raw_tokens:
        env_choice = os.environ.get("MODEL_CHOICE", "27b").strip().lower()
        if "," in env_choice:
            raw_tokens.extend([x.strip() for x in env_choice.split(",") if x.strip()])
        elif " " in env_choice:
            raw_tokens.extend([x.strip() for x in env_choice.split() if x.strip()])
        else:
            raw_tokens.append(env_choice)

    # Resolusi keys model
    target_keys = []
    for token in raw_tokens:
        if token in ALIAS_MAP:
            target_keys.extend(ALIAS_MAP[token])
        elif token in COLAB_MODELS:
            target_keys.append(token)
        else:
            print(f"[WARN] Pilihan '{token}' tidak dikenali. Memasukkan trio model default.")
            target_keys.extend(TRIO_KEYS)

    # Hilangkan duplikat tapi jaga urutan
    unique_keys = list(dict.fromkeys(target_keys))

    print("\n" + "=" * 65)
    print("SHIRO AI - MODEL DOWNLOADER")
    print(f"Target Unduhan ({len(unique_keys)} model): {', '.join(unique_keys)}")
    print("=" * 65)

    if dry_run:
        print("[DRY RUN] Daftar model yang akan diunduh:")
        for k in unique_keys:
            info = COLAB_MODELS.get(k, {})
            print(f" - [{k}] {info.get('desc')} -> {info.get('file')} (Projector: {info.get('extra_file')})")
        return

    downloaded_filenames = []
    for k in unique_keys:
        if k in COLAB_MODELS:
            ok = download_single_model(k, COLAB_MODELS[k])
            if ok:
                downloaded_filenames.append(COLAB_MODELS[k]["file"])

    if downloaded_filenames:
        primary = COLAB_MODELS["27b"]["file"] if "27b" in unique_keys else downloaded_filenames[0]
        set_active_models_in_config(downloaded_filenames, primary_filename=primary)

    print("\n" + "=" * 65)
    print("STATUS MODEL DI FOLDER model/:")
    if os.path.exists("model"):
        for f in sorted(os.listdir("model")):
            if f.endswith(".gguf"):
                sz = os.path.getsize(os.path.join("model", f)) / (1024 * 1024 * 1024)
                print(f"  * {f} ({sz:.2f} GB)")
    print("Selesai. Seluruh model siap digunakan.")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()