import os
import sys
from huggingface_hub import hf_hub_download

os.makedirs("model", exist_ok=True)

# Pilihan model: '7b' (default, sangat pintar, cepat) atau '14b' (genius level untuk Colab Pro)
model_choice = os.environ.get("MODEL_CHOICE", "7b").lower().strip()

if model_choice in ["14b", "14"]:
    REPO_ID = "bartowski/Qwen2.5-14B-Instruct-GGUF"
    FILENAME = "Qwen2.5-14B-Instruct-Q4_K_M.gguf"
    DESC = "Qwen2.5 14B Instruct (Genius level, penalaran sangat tinggi, ~9.0 GB)"
elif model_choice in ["lumimaid", "lumi"]:
    REPO_ID = "Lewdiculous/Lumimaid-v0.2-8B-GGUF-IQ-Imatrix"
    FILENAME = "Lumimaid-v0.2-8B-Q5_K_M-imat.gguf"
    DESC = "Lumimaid v0.2 8B (~5.4 GB)"
else:
    REPO_ID = "bartowski/Qwen2.5-7B-Instruct-GGUF"
    FILENAME = "Qwen2.5-7B-Instruct-Q5_K_M.gguf"
    DESC = "Qwen2.5 7B Instruct (Bahasa Indonesia sangat fasih, anti-halusinasi, cerdas, ~5.4 GB)"

target_file = os.path.join("model", FILENAME)

if os.path.exists(target_file):
    print(f"✓ Model {FILENAME} sudah tersedia di folder model/.")
    sys.exit(0)

print("=" * 60)
print(f"📥 MENDOWNLOAD MODEL TERBAIK & TERCANGGIH:")
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