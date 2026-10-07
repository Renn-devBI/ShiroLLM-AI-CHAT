import os
import sys
from huggingface_hub import hf_hub_download

os.makedirs("model", exist_ok=True)

# Pilihan 3 Model Khusus Google Colab:
# 1. '32b' / '1' -> Qwen3-32B (Model Utama ⭐: Penalaran Tertinggi & Paling Pintar, ~19.8 GB)
# 2. 'vl'  / '2' -> Qwen2.5-VL-7B-Instruct (Model ke-2 👁️: Vision Multimodal untuk Kamera & Gambar VTuber, ~5.6 GB)
# 3. '7b'  / '3' -> Qwen2.5-7B-Instruct (Model ke-3 ⚡: Super Cepat & Ringan di T4 GPU, ~5.4 GB)
model_choice = os.environ.get("MODEL_CHOICE", "32b").lower().strip()

extra_file = None

if model_choice in ["vl", "vision", "qwen2.5-vl", "2"]:
    REPO_ID = "unsloth/Qwen2.5-VL-7B-Instruct-GGUF"
    FILENAME = "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
    extra_file = "mmproj-F16.gguf"
    DESC = "Qwen2.5-VL 7B Instruct (Model ke-2 👁️: Vision Multimodal Kamera & Gambar VTuber, ~5.6 GB)"
elif model_choice in ["7b", "7", "3", "qwen2.5-7b"]:
    REPO_ID = "bartowski/Qwen2.5-7B-Instruct-GGUF"
    FILENAME = "Qwen2.5-7B-Instruct-Q5_K_M.gguf"
    DESC = "Qwen2.5 7B Instruct (Model ke-3 ⚡: Super Cepat & Ringan di T4 GPU, ~5.4 GB)"
else:
    # Model 1 (Default Colab Pro): Qwen3-32B
    REPO_ID = "Qwen/Qwen3-32B-GGUF"
    FILENAME = "Qwen3-32B-Q4_K_M.gguf"
    DESC = "Qwen3-32B (Model Utama ⭐: Cerdas, penalaran tertinggi, anti-halusinasi, ~19.8 GB)"

target_file = os.path.join("model", FILENAME)

# 1. Download Model Utama
if os.path.exists(target_file):
    print(f"✓ Model {FILENAME} sudah tersedia di folder model/.")
else:
    print("=" * 60)
    print(f"📥 MENDOWNLOAD MODEL:")
    print(f"👉 {DESC}")
    print(f"👉 Repository: {REPO_ID}")
    print("=" * 60)
    try:
        hf_hub_download(
            repo_id=REPO_ID,
            filename=FILENAME,
            local_dir="model",
            local_dir_use_symlinks=False
        )
        print(f"\n✓ SUKSES! Model {FILENAME} berhasil diunduh ke folder model/.")
    except Exception as e:
        print(f"\n❌ Gagal download {FILENAME}: {e}")
        sys.exit(1)

# 2. Download File Pendukung Vision (mmproj) jika memilih Model Vision
if extra_file:
    target_extra = os.path.join("model", extra_file)
    if os.path.exists(target_extra):
        print(f"✓ Vision Projector {extra_file} sudah tersedia di folder model/.")
    else:
        print(f"\n📥 Mendownload Vision Projector ({extra_file})...")
        try:
            hf_hub_download(
                repo_id=REPO_ID,
                filename=extra_file,
                local_dir="model",
                local_dir_use_symlinks=False
            )
            print(f"✓ SUKSES! {extra_file} berhasil diunduh ke folder model/.")
        except Exception as e:
            print(f"⚠️ Gagal download {extra_file}: {e}")