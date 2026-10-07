import os
import sys
from huggingface_hub import hf_hub_download

os.makedirs("model", exist_ok=True)

# Pilihan model:
# - '32b' / '1' / default -> Qwen3-32B (Model Utama ⭐, ~19.8 GB)
# - '7b' / '2'           -> Qwen2.5-7B (Model ke-2 ⚡, ~5.4 GB)
# - '14b'                -> Qwen2.5-14B (~9.0 GB)
# - 'lumimaid'           -> Lumimaid 8B (~5.4 GB)
model_choice = os.environ.get("MODEL_CHOICE", "32b").lower().strip()

if model_choice in ["7b", "7", "2", "qwen2.5-7b"]:
    REPO_ID = "bartowski/Qwen2.5-7B-Instruct-GGUF"
    FILENAME = "Qwen2.5-7B-Instruct-Q5_K_M.gguf"
    DESC = "Qwen2.5 7B Instruct (Model ke-2: Super cepat & cerdas, efisien di GPU T4, ~5.4 GB)"
    MIRROR_REPO = "Qwen/Qwen2.5-7B-Instruct-GGUF"
    MIRROR_FILENAME = "qwen2.5-7b-instruct-q5_k_m.gguf"
elif model_choice in ["14b", "14"]:
    REPO_ID = "bartowski/Qwen2.5-14B-Instruct-GGUF"
    FILENAME = "Qwen2.5-14B-Instruct-Q4_K_M.gguf"
    DESC = "Qwen2.5 14B Instruct (Genius level, penalaran sangat tinggi, ~9.0 GB)"
    MIRROR_REPO = None
    MIRROR_FILENAME = None
elif model_choice in ["lumimaid", "lumi"]:
    REPO_ID = "Lewdiculous/Lumimaid-v0.2-8B-GGUF-IQ-Imatrix"
    FILENAME = "Lumimaid-v0.2-8B-Q5_K_M-imat.gguf"
    DESC = "Lumimaid v0.2 8B (~5.4 GB)"
    MIRROR_REPO = None
    MIRROR_FILENAME = None
else:
    # Model Utama: Qwen3-32B
    REPO_ID = "Qwen/Qwen3-32B-GGUF"
    FILENAME = "Qwen3-32B-Q4_K_M.gguf"
    DESC = "Qwen3-32B (Model Utama: Cerdas, penalaran tertinggi, anti-halusinasi ⭐, ~19.8 GB)"
    MIRROR_REPO = "bartowski/Qwen_Qwen3-32B-GGUF"
    MIRROR_FILENAME = "Qwen_Qwen3-32B-Q4_K_M.gguf"

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
    print(f"\n⚠️ Gagal download dari {REPO_ID}: {e}")
    if MIRROR_REPO:
        print(f"🔄 Mencoba mirror: {MIRROR_REPO} ({MIRROR_FILENAME})...")
        try:
            hf_hub_download(
                repo_id=MIRROR_REPO,
                filename=MIRROR_FILENAME,
                local_dir="model",
                local_dir_use_symlinks=False
            )
            print(f"\n✓ SUKSES! Model berhasil diunduh dari mirror.")
        except Exception as e2:
            print(f"\n❌ Gagal download dari mirror: {e2}")
            sys.exit(1)
    else:
        sys.exit(1)