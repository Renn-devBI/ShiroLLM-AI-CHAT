import os
import sys
import json
from huggingface_hub import hf_hub_download

os.makedirs("model", exist_ok=True)

# Definisi Model Tersedia:
COLAB_MODELS = {
    "32b": {
        "repo": "Qwen/Qwen3-32B-GGUF",
        "file": "Qwen3-32B-Q4_K_M.gguf",
        "extra_file": None,
        "desc": "Qwen3-32B (Model #1: Penalaran Tinggi / A100 GPU, ~19.8 GB)"
    },
    "27b": {
        "repo": "JonathanColetti/Qwen3.8-27B-Uncensored-GGUF",
        "file": "Qwen3.8-27B-Uncensored-Q4_K_M.gguf",
        "extra_file": None,
        "desc": "Qwen3.8-27B-Uncensored (Model #2: Uncensored / A100 GPU, ~16.8 GB)"
    },
    "vl": {
        "repo": "unsloth/Qwen2.5-VL-7B-Instruct-GGUF",
        "file": "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
        "extra_file": "mmproj-F16.gguf",
        "desc": "Qwen2.5-VL-7B (Model #3: Vision Multimodal Kamera & Gambar VTuber, ~5.6 GB)"
    },
    "7b": {
        "repo": "bartowski/Qwen2.5-7B-Instruct-GGUF",
        "file": "Qwen2.5-7B-Instruct-Q5_K_M.gguf",
        "extra_file": None,
        "desc": "Qwen2.5-7B (Model #4: Hemat VRAM / GPU T4, ~5.4 GB)"
    },
    "3.2b": {
        "repo": "bartowski/Llama-3.2-3B-Instruct-uncensored-GGUF",
        "file": "Llama-3.2-3B-Instruct-uncensored-Q6_K.gguf",
        "extra_file": None,
        "desc": "Llama-3.2-3B-Uncensored (Model #5: Super Ringan Fallback GPU T4, ~2.9 GB)"
    },
    "4b": {
        "repo": "Qwen/Qwen3-4B-GGUF",
        "file": "Qwen3-4B-Q4_K_M.gguf",
        "extra_file": None,
        "desc": "Qwen3-4B (Model #6: Ringan untuk CPU/T4, ~2.5 GB)"
    }
}

def set_active_model_in_config(model_filename):
    config_file = "model_config.json"
    if not os.path.exists(config_file):
        return
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        model_path = f"model/{model_filename}"
        cfg["current_model"] = model_path
        if model_path not in cfg.get("available_models", []):
            cfg.setdefault("available_models", []).insert(0, model_path)
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        print(f"[CONFIG] Model aktif diatur ke: {model_filename}")
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

    if os.path.exists(target_path):
        size_gb = os.path.getsize(target_path) / (1024 * 1024 * 1024)
        print(f"[OK] Model {fname} sudah ada di folder model/ ({size_gb:.1f} GB). Skip download.")
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
        except Exception as e:
            print(f"[ERROR] Gagal mengunduh {fname}: {e}")
            return False

    if extra:
        extra_path = os.path.join("model", extra)
        if os.path.exists(extra_path):
            print(f"[OK] Vision Projector {extra} sudah ada di folder model/. Skip download.")
        else:
            print(f"[DOWNLOAD] Mengunduh Vision Projector ({extra})...")
            try:
                hf_hub_download(
                    repo_id=repo,
                    filename=extra,
                    local_dir="model",
                    local_dir_use_symlinks=False
                )
                print(f"[OK] Projector {extra} berhasil diunduh.")
            except Exception as e:
                print(f"[WARN] Gagal download {extra}: {e}")
    
    return True

def main():
    arg_choice = None
    if len(sys.argv) > 1:
        arg_choice = sys.argv[1].replace("--", "").lower().strip()

    choice = (arg_choice or os.environ.get("MODEL_CHOICE", "27b")).lower().strip()

    print("\n" + "=" * 65)
    print("SHIRO AI - MODEL DOWNLOADER")
    print(f"Mode Pilihan: '{choice}'")
    print("=" * 65)

    if choice in ["2", "27b", "uncensored", "qwen27b", "qwen3.8"]:
        if download_single_model("27b", COLAB_MODELS["27b"]):
            set_active_model_in_config(COLAB_MODELS["27b"]["file"])
    elif choice in ["1", "32b", "main", "qwen3-32b"]:
        if download_single_model("32b", COLAB_MODELS["32b"]):
            set_active_model_in_config(COLAB_MODELS["32b"]["file"])
    elif choice in ["3", "vl", "vision", "qwen2.5-vl"]:
        if download_single_model("vl", COLAB_MODELS["vl"]):
            set_active_model_in_config(COLAB_MODELS["vl"]["file"])
    elif choice in ["4", "7b", "fast", "qwen2.5-7b"]:
        if download_single_model("7b", COLAB_MODELS["7b"]):
            set_active_model_in_config(COLAB_MODELS["7b"]["file"])
    elif choice in ["5", "3.2b", "llama", "llama3.2"]:
        if download_single_model("3.2b", COLAB_MODELS["3.2b"]):
            set_active_model_in_config(COLAB_MODELS["3.2b"]["file"])
    elif choice in ["6", "4b", "qwen4b", "cpu"]:
        if download_single_model("4b", COLAB_MODELS["4b"]):
            set_active_model_in_config(COLAB_MODELS["4b"]["file"])
    elif choice in ["a100"]:
        print("Mengunduh model untuk A100 GPU (32B, 27B-Uncensored, VL)...")
        for key in ["32b", "27b", "vl"]:
            download_single_model(key, COLAB_MODELS[key])
        set_active_model_in_config(COLAB_MODELS["27b"]["file"])
    elif choice in ["t4", "hemat"]:
        print("Mengunduh model untuk T4 GPU (VL, 7B, 3.2B)...")
        for key in ["vl", "7b", "3.2b"]:
            download_single_model(key, COLAB_MODELS[key])
        set_active_model_in_config(COLAB_MODELS["7b"]["file"])
    elif choice in ["all", "semua", "full"]:
        print("Mengunduh semua model...")
        for key in ["32b", "27b", "vl", "7b", "3.2b", "4b"]:
            download_single_model(key, COLAB_MODELS[key])
    else:
        print(f"[WARN] Pilihan '{choice}' tidak dikenali. Mengunduh model default (27b)...")
        if download_single_model("27b", COLAB_MODELS["27b"]):
            set_active_model_in_config(COLAB_MODELS["27b"]["file"])

    print("\n" + "=" * 65)
    print("STATUS MODEL DI FOLDER model/:")
    if os.path.exists("model"):
        for f in sorted(os.listdir("model")):
            if f.endswith(".gguf"):
                sz = os.path.getsize(os.path.join("model", f)) / (1024 * 1024 * 1024)
                print(f"  * {f} ({sz:.2f} GB)")
    print("Selesai. Model siap digunakan.")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()