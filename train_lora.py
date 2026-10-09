# -*- coding: utf-8 -*-
"""
Shiro Fine-Tuning CLI (LoRA / QLoRA with Unsloth)
Melatih model AI (Qwen2.5) menggunakan dataset percakapan yang diekspor dari ingatan Shiro.
Hasil LoRA adapter (.gguf / safetensors) otomatis disimpan ke folder lora/ dan Google Drive.
"""

import os
import sys
import json
import shutil
import argparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from shiro.training.exporter import export_data

def run_training(
    base_model="unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
    dataset_path="training_data/chat/shiro_chatml_train.jsonl",
    output_dir="lora",
    max_steps=60,
    learning_rate=2e-4,
    batch_size=2,
    gradient_accumulation_steps=4
):
    print("=" * 65)
    print("🎓 SHIRO CONTINUOUS LEARNING: FINE-TUNING LoRA / QLoRA")
    print("=" * 65)

    # 1. Pastikan dataset tersedia, jika belum ada, otomatis ekspor
    if not os.path.exists(dataset_path):
        print(f"ℹ️ Dataset {dataset_path} belum ditemukan. Menjalankan ekspor otomatis...")
        export_data()

    if not os.path.exists(dataset_path):
        # Coba fallback ke shiro_chatml_train.jsonl di root training_data
        alt_path = "training_data/shiro_chatml_train.jsonl"
        if os.path.exists(alt_path):
            dataset_path = alt_path
        else:
            print(f"❌ File dataset {dataset_path} tidak ditemukan!")
            return False

    # Hitung jumlah sampel di dataset
    with open(dataset_path, "r", encoding="utf-8") as f:
        samples = [line for line in f if line.strip()]
    sample_count = len(samples)
    print(f"📊 Dataset terdeteksi: {sample_count} sampel percakapan.")
    if sample_count == 0:
        print("⚠️ Dataset kosong! Belum ada percakapan untuk dilatih.")
        return False

    print(f"🤖 Base Model      : {base_model}")
    print(f"📁 Output LoRA     : {output_dir}")
    print(f"⚡ Max Steps       : {max_steps}")
    print(f"📈 Learning Rate   : {learning_rate}")
    print("-" * 65)

    # 2. Coba import Unsloth (Solusi tercepat & paling hemat memori di GPU T4)
    try:
        import torch
        from unsloth import FastLanguageModel
        from datasets import load_dataset
        from trl import SFTTrainer
        from transformers import TrainingArguments
    except ImportError:
        print("⚠️ Paket 'unsloth' atau dependensinya belum terinstall.")
        print("👉 Di Google Colab, jalankan perintah berikut terlebih dahulu:")
        print("   !pip install --no-deps \"xformers<0.0.29\" \"trl<0.9.0\" peft accelerate bitsandbytes")
        print("   !pip install \"unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git\"")
        return False

    if not torch.cuda.is_available():
        print("❌ GPU CUDA tidak terdeteksi! Fine-tuning membutuhkan GPU (T4 / A100).")
        return False

    # 3. Muat Base Model dengan Unsloth 4-bit
    print("⏳ 1/4 Memuat Base Model ke GPU...")
    max_seq_length = 2048
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_seq_length,
        dtype=None,
        load_in_4bit=True,
    )

    # 4. Pasang LoRA Adapters
    print("🎯 2/4 Mempersiapkan LoRA Adapter...")
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

    # 5. Format Dataset ChatML
    print("📚 3/4 Memformat dataset percakapan...")
    dataset = load_dataset("json", data_files={"train": dataset_path}, split="train")

    def format_chatml(examples):
        convos = examples["messages"]
        texts = [tokenizer.apply_chat_template(convo, tokenize=False, add_generation_prompt=False) for convo in convos]
        return {"text": texts}

    dataset = dataset.map(format_chatml, batched=True)

    # 6. Training SFTTrainer
    print("🚀 4/4 Memulai Pelatihan Model...")
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

    # 7. Simpan Model LoRA Adapter
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n💾 Menyimpan LoRA adapter ke folder '{output_dir}'...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Coba ekspor ke format GGUF jika llama.cpp compiler tersedia di sistem
    try:
        print("📦 Mengonversi LoRA adapter ke format GGUF untuk llama.cpp...")
        model.save_pretrained_gguf(output_dir, tokenizer, quantization_method="f16")
    except Exception as e_gguf:
        print(f"ℹ️ GGUF conversion skipped / manual ({e_gguf}). Adapter safetensors tetap tersimpan rapi.")

    # 8. Otomatis sinkronkan ke Google Drive jika Drive aktif
    drive_dir = os.environ.get("SHIRO_DRIVE_DIR")
    if not drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
        drive_dir = "/content/drive/MyDrive/Shiro_Memory"
    if drive_dir and os.path.exists(drive_dir):
        try:
            drive_lora = os.path.join(drive_dir, "lora")
            shutil.copytree(output_dir, drive_lora, dirs_exist_ok=True)
            print(f"✓ LoRA adapter otomatis dicadangkan ke Google Drive: {drive_lora}")
        except Exception as e_drv:
            print(f"Warning: Gagal sync lora ke Drive: {e_drv}")

    print("=" * 65)
    print("🎉 PELATIHAN LoRA SHIRO SELESAI!")
    print("👉 Saat server Shiro dinyalakan ulang, LoRA adapter akan otomatis terdeteksi dan dimuat!")
    print("=" * 65)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shiro LoRA Training Script")
    parser.add_argument("--model", type=str, default="unsloth/Qwen2.5-7B-Instruct-bnb-4bit", help="Base model HuggingFace")
    parser.add_argument("--dataset", type=str, default="training_data/chat/shiro_chatml_train.jsonl", help="Dataset path")
    parser.add_argument("--output", type=str, default="lora", help="Output directory")
    parser.add_argument("--steps", type=int, default=60, help="Max training steps")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    args = parser.parse_args()

    run_training(
        base_model=args.model,
        dataset_path=args.dataset,
        output_dir=args.output,
        max_steps=args.steps,
        learning_rate=args.lr
    )
