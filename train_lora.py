# -*- coding: utf-8 -*-
"""
Shiro Fine-Tuning CLI (LoRA / QLoRA with Unsloth)
Melatih model AI menggunakan dataset percakapan yang diekspor dari ingatan Shiro.
Hasil pelatihan otomatis terbentuk sebagai Model AI baru dengan penomoran versi bertingkat:
ShiroAI-LLM-V1, ShiroAI-LLM-V2, ShiroAI-LLM-V3, dst.
"""

import os
import sys
import json
import shutil
import argparse
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from shiro.training.exporter import export_data
from shiro.training.versioning import get_next_model_name, get_next_training_version

def run_training(
    base_model="unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
    dataset_path="training_data/chat/shiro_chatml_train.jsonl",
    model_name=None,
    output_dir="lora",
    max_steps=60,
    learning_rate=2e-4,
    batch_size=2,
    gradient_accumulation_steps=4
):
    # 1. Tentukan Versi dan Nama Model Otomatis (ShiroAI-LLM-V1, V2, dst.)
    if not model_name:
        model_name = get_next_model_name()
    
    version_num = get_next_training_version()

    print("=" * 65)
    print("🎓 SHIRO CONTINUOUS LEARNING: PELATIHAN MODEL AI (LoRA)")
    print(f"🏷️  NAMA MODEL HASIL TRAINING: {model_name}")
    print("=" * 65)

    # 2. Pastikan dataset tersedia, jika belum ada, otomatis ekspor
    if not os.path.exists(dataset_path):
        print(f"ℹ️ Dataset {dataset_path} belum ditemukan. Menjalankan ekspor otomatis...")
        export_data()

    if not os.path.exists(dataset_path):
        alt_path = "training_data/shiro_chatml_train.jsonl"
        if os.path.exists(alt_path):
            dataset_path = alt_path
        else:
            print(f"❌ File dataset {dataset_path} tidak ditemukan!")
            return False

    with open(dataset_path, "r", encoding="utf-8") as f:
        samples = [line for line in f if line.strip()]
    sample_count = len(samples)
    print(f"📊 Dataset terdeteksi   : {sample_count} sampel percakapan.")
    if sample_count == 0:
        print("⚠️ Dataset kosong! Belum ada percakapan untuk dilatih.")
        return False

    print(f"🤖 Base Foundation Model: {base_model}")
    print(f"🎯 Target Model AI Baru : {model_name} (Versi {version_num})")
    print(f"⚡ Max Training Steps   : {max_steps}")
    print(f"📈 Learning Rate        : {learning_rate}")
    print("-" * 65)

    # 3. Coba import Unsloth
    try:
        import torch
        from unsloth import FastLanguageModel
        from datasets import load_dataset
        from trl import SFTTrainer
        from transformers import TrainingArguments
    except ImportError:
        print("⚠️ Paket 'unsloth' atau dependensinya belum terinstall.")
        print("👉 Di Google Colab, jalankan perintah berikut:")
        print("   !pip install --no-deps \"xformers<0.0.29\" \"trl<0.9.0\" peft accelerate bitsandbytes")
        print("   !pip install \"unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git\"")
        return False

    if not torch.cuda.is_available():
        print("❌ GPU CUDA tidak terdeteksi! Fine-tuning membutuhkan GPU (T4 / A100).")
        return False

    # 4. Muat Base Model dengan Unsloth 4-bit
    print("⏳ 1/4 Memuat Base Model ke GPU...")
    max_seq_length = 2048
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_seq_length,
        dtype=None,
        load_in_4bit=True,
    )

    # 5. Pasang LoRA Adapters
    print(f"🎯 2/4 Mempersiapkan LoRA Adapter untuk {model_name}...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    # 6. Format Dataset ChatML
    print("📚 3/4 Memformat dataset percakapan...")
    dataset = load_dataset("json", data_files={"train": dataset_path}, split="train")

    def format_chatml(examples):
        convos = examples["messages"]
        texts = [tokenizer.apply_chat_template(convo, tokenize=False, add_generation_prompt=False) for convo in convos]
        return {"text": texts}

    dataset = dataset.map(format_chatml, batched=True)

    # 7. Training SFTTrainer
    print(f"🚀 4/4 Memulai Pelatihan Model {model_name}...")
    os.makedirs("outputs", exist_ok=True)
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        dataset_num_proc=2,
        packing=False,
        args=TrainingArguments(
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            warmup_steps=min(5, max(1, max_steps // 10)),
            max_steps=max_steps,
            learning_rate=learning_rate,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=3407,
            output_dir="outputs",
            report_to="none"
        ),
    )

    trainer.train()

    # 8. Simpan LoRA Weights & Metadata
    model_lora_dir = os.path.join(output_dir, model_name)
    os.makedirs(model_lora_dir, exist_ok=True)
    print(f"\n💾 Menyimpan bobot LoRA adapter ke: '{model_lora_dir}'...")
    model.save_pretrained(model_lora_dir)
    tokenizer.save_pretrained(model_lora_dir)

    # 9. Bentuk File Model AI GGUF Standalone (model/ShiroAI-LLM-V{ver}.gguf)
    os.makedirs("model", exist_ok=True)
    target_gguf_file = os.path.join("model", f"{model_name}.gguf")
    export_folder = os.path.join("model", model_name)

    print(f"📦 Mengonversi hasil pelatihan ke Model AI GGUF: '{target_gguf_file}'...")
    gguf_created = False
    try:
        model.save_pretrained_gguf(export_folder, tokenizer, quantization_method="q4_k_m")
        # Cari file .gguf di dalam export folder lalu standarisasi namanya
        if os.path.exists(export_folder):
            for root, _, files in os.walk(export_folder):
                for f in files:
                    if f.endswith(".gguf"):
                        found_path = os.path.join(root, f)
                        if found_path != target_gguf_file:
                            shutil.copy2(found_path, target_gguf_file)
                        gguf_created = True
                        break
                if gguf_created:
                    break
    except Exception as e_gguf:
        print(f"ℹ️ Catatan export GGUF 4-bit: {e_gguf}")
        # Coba export LoRA GGUF adapter sebagai alternatif
        try:
            model.save_pretrained_gguf(model_lora_dir, tokenizer, quantization_method="f16")
            for f in os.listdir(model_lora_dir):
                if f.endswith(".gguf"):
                    shutil.copy2(os.path.join(model_lora_dir, f), target_gguf_file)
                    gguf_created = True
                    break
        except Exception:
            pass

    # Simpan Metadata Model
    info_path = os.path.join("model", f"{model_name}_info.json")
    meta_info = {
        "model_name": model_name,
        "version": version_num,
        "base_model": base_model,
        "trained_at": datetime.now().isoformat(),
        "total_samples": sample_count,
        "max_steps": max_steps,
        "learning_rate": learning_rate,
        "gguf_model": target_gguf_file if os.path.exists(target_gguf_file) else None,
        "lora_dir": model_lora_dir
    }
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(meta_info, f, indent=2, ensure_ascii=False)

    # 10. Otomatis sinkronkan ke Google Drive
    drive_dir = os.environ.get("SHIRO_DRIVE_DIR")
    if not drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
        drive_dir = "/content/drive/MyDrive/Shiro_Memory"
    if drive_dir and os.path.exists(drive_dir):
        try:
            # Sync model GGUF ke Drive
            drive_model_dir = os.path.join(drive_dir, "model")
            os.makedirs(drive_model_dir, exist_ok=True)
            if os.path.exists(target_gguf_file):
                shutil.copy2(target_gguf_file, os.path.join(drive_model_dir, f"{model_name}.gguf"))
                print(f"✓ Model AI {model_name}.gguf otomatis dicadangkan ke Google Drive: {drive_model_dir}")
            if os.path.exists(info_path):
                shutil.copy2(info_path, os.path.join(drive_model_dir, f"{model_name}_info.json"))

            # Sync LoRA adapter ke Drive
            drive_lora_dir = os.path.join(drive_dir, "lora", model_name)
            os.makedirs(drive_lora_dir, exist_ok=True)
            shutil.copytree(model_lora_dir, drive_lora_dir, dirs_exist_ok=True)
            print(f"✓ LoRA adapter {model_name} otomatis dicadangkan ke Google Drive: {drive_lora_dir}")
        except Exception as e_drv:
            print(f"Warning: Gagal sync model ke Drive: {e_drv}")

    print("\n" + "=" * 65)
    print(f"🎉 SUKSES! MODEL AI BARU TELAH DILATIH: {model_name}")
    print("=" * 65)
    if os.path.exists(target_gguf_file):
        print(f"📦 Berkas Model AI : {target_gguf_file}")
    print(f"🎯 Berkas LoRA     : {model_lora_dir}")
    print(f"📋 Info Metadata   : {info_path}")
    print("-" * 65)
    print("👉 CARA MENGGUNAKAN:")
    print(f"   Model '{model_name}' akan OTOMATIS muncul di menu:")
    print("   Pengaturan (⚙️) -> Model AI di Web UI!")
    print("   Tinggal pilih model tersebut dan Shiro langsung aktif dengan hasil training terbaru.")
    print("=" * 65 + "\n")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shiro LoRA Training Script with Auto-Versioning")
    parser.add_argument("--name", type=str, default=None, help="Nama model (contoh: ShiroAI-LLM-V1). Jika kosong, otomatis bertingkat V1, V2, dst.")
    parser.add_argument("--model", type=str, default="unsloth/Qwen2.5-7B-Instruct-bnb-4bit", help="Base model HuggingFace")
    parser.add_argument("--dataset", type=str, default="training_data/chat/shiro_chatml_train.jsonl", help="Dataset path")
    parser.add_argument("--output", type=str, default="lora", help="Output directory LoRA")
    parser.add_argument("--steps", type=int, default=60, help="Max training steps")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    args = parser.parse_args()

    run_training(
        base_model=args.model,
        dataset_path=args.dataset,
        model_name=args.name,
        output_dir=args.output,
        max_steps=args.steps,
        learning_rate=args.lr
    )
