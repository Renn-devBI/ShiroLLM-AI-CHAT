import os
import sys
from huggingface_hub import hf_hub_download

os.makedirs("model", exist_ok=True)

# Definisi 3 Model Utama Colab:
COLAB_MODELS = {
    "32b": {
        "repo": "Qwen/Qwen3-32B-GGUF",
        "file": "Qwen3-32B-Q4_K_M.gguf",
        "extra_file": None,
        "desc": "Qwen3-32B (Model Utama ⭐: Penalaran Tertinggi & Paling Pintar, ~19.8 GB)"
    },
    "vl": {
        "repo": "unsloth/Qwen2.5-VL-7B-Instruct-GGUF",
        "file": "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
        "extra_file": "mmproj-F16.gguf",
        "desc": "Qwen2.5-VL-7B (Model ke-2 👁️: Multimodal Vision Kamera Webcam & Gambar VTuber, ~5.6 GB)"
    },
    "7b": {
        "repo": "bartowski/Qwen2.5-7B-Instruct-GGUF",
        "file": "Qwen2.5-7B-Instruct-Q5_K_M.gguf",
        "extra_file": None,
        "desc": "Qwen2.5-7B (Model ke-3 ⚡: Super Cepat & Ringan di GPU T4, ~5.4 GB)"
    }
}

def download_single_model(m_key, info):
    repo = info["repo"]
    fname = info["file"]
    extra = info.get("extra_file")
    desc = info["desc"]
    target_path = os.path.join("model", fname)

    print("\n" + "=" * 65)
    print(f"📦 TARGET: {desc}")
    print(f"👉 Repo Hugging Face: {repo}")
    print(f"👉 File GGUF: {fname}")
    print("=" * 65)

    if os.path.exists(target_path):
        size_gb = os.path.getsize(target_path) / (1024 * 1024 * 1024)
        print(f"✓ Model {fname} sudah ada di folder model/ ({size_gb:.1f} GB). Skip download.")
    else:
        print(f"📥 Mengunduh model {fname}...")
        try:
            hf_hub_download(
                repo_id=repo,
                filename=fname,
                local_dir="model",
                local_dir_use_symlinks=False
            )
            print(f"✓ SUKSES! Model {fname} berhasil diunduh ke folder model/.")
        except Exception as e:
            print(f"❌ Gagal mengunduh {fname}: {e}")
            return False

    if extra:
        extra_path = os.path.join("model", extra)
        if os.path.exists(extra_path):
            print(f"✓ Vision Projector {extra} sudah ada di folder model/. Skip download.")
        else:
            print(f"📥 Mengunduh Vision Projector ({extra})...")
            try:
                hf_hub_download(
                    repo_id=repo,
                    filename=extra,
                    local_dir="model",
                    local_dir_use_symlinks=False
                )
                print(f"✓ SUKSES! Projector {extra} berhasil diunduh.")
            except Exception as e:
                print(f"⚠️ Gagal download {extra}: {e}")
    
    return True

# Ambil pilihan dari argumen CLI (misal: python download_model.py --all) atau environment variable
arg_choice = None
if len(sys.argv) > 1:
    arg_choice = sys.argv[1].replace("--", "").lower().strip()

choice = (arg_choice or os.environ.get("MODEL_CHOICE", "all")).lower().strip()

print("\n" + "#" * 65)
print("🤖 SHIRO AI • MODEL DOWNLOADER (GOOGLE COLAB & LOCAL PC)")
print(f"👉 Mode Pilihan: '{choice}'")
print("#" * 65)

if choice in ["all", "semua", "3", "full"]:
    print("🚀 Mengunduh 3 Model Utama Colab sekaligus agar bisa Switch di Web UI:")
    print("   1. Qwen3-32B (Model Utama)")
    print("   2. Qwen2.5-VL-7B (Model Vision VTuber)")
    print("   3. Qwen2.5-7B (Model Fast)")
    for key in ["32b", "vl", "7b"]:
        download_single_model(key, COLAB_MODELS[key])
elif choice in ["vl", "vision", "qwen2.5-vl", "2"]:
    download_single_model("vl", COLAB_MODELS["vl"])
elif choice in ["7b", "fast", "qwen2.5-7b"]:
    download_single_model("7b", COLAB_MODELS["7b"])
elif choice in ["32b", "1", "qwen3-32b", "main"]:
    download_single_model("32b", COLAB_MODELS["32b"])
else:
    print(f"⚠️ Pilihan '{choice}' tidak dikenali. Mengunduh semua 3 model...")
    for key in ["32b", "vl", "7b"]:
        download_single_model(key, COLAB_MODELS[key])

print("\n" + "=" * 65)
print("🎉 STATUS MODEL DI FOLDER model/:")
for f in os.listdir("model"):
    if f.endswith(".gguf"):
        sz = os.path.getsize(os.path.join("model", f)) / (1024 * 1024 * 1024)
        print(f"  • {f} ({sz:.2f} GB)")
print("✓ Selesai! Model siap digunakan dan dapat di-switch di Pengaturan Web UI.")
print("=" * 65 + "\n")