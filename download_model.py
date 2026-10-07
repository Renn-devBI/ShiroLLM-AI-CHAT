import os
import sys
from huggingface_hub import hf_hub_download

os.makedirs("model", exist_ok=True)

DEFAULT_MODEL = "Lumimaid-v0.2-8B-Q5_K_M-imat.gguf"
target_file = os.path.join("model", DEFAULT_MODEL)

if os.path.exists(target_file):
    print(f"✓ Model {DEFAULT_MODEL} sudah ada di folder model.")
    sys.exit(0)

print(f"📥 Mendownload model tercanggih: {DEFAULT_MODEL} (~5.4 GB)...")
print("Model Lumimaid-v0.2-8B (Llama-3 fine-tune) memiliki pemahaman persona dan percakapan terbaik.")

try:
    hf_hub_download(
        repo_id="Lewdiculous/Lumimaid-v0.2-8B-GGUF-IQ-Imatrix",
        filename=DEFAULT_MODEL,
        local_dir="model",
        local_dir_use_symlinks=False
    )
    print(f"\n✓ SUKSES! Model {DEFAULT_MODEL} berhasil diunduh ke folder model/.")
except Exception as e:
    print(f"\n⚠️ Gagal download dari Lewdiculous, mencoba mirror alternatif...")
    try:
        hf_hub_download(
            repo_id="mradermacher/Lumimaid-v0.2-8B-GGUF",
            filename="Lumimaid-v0.2-8B.Q5_K_M.gguf",
            local_dir="model",
            local_dir_use_symlinks=False
        )
        print("\n✓ SUKSES! Model Lumimaid berhasil diunduh dari mirror.")
    except Exception as e2:
        print(f"\n❌ Error download model: {e2}")
        sys.exit(1)