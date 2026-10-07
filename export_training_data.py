# -*- coding: utf-8 -*-
"""
Export Training Data for Shiro Fine-Tuning
Mengekstrak percakapan dari ingatan_shiro.json ke dalam format dataset standar
(ChatML JSONL, Alpaca JSON, ShareGPT JSON) untuk melatih / fine-tune model LLM (Unsloth / LoRA).
"""

import os
import json
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

SYSTEM_PROMPT = """Kamu adalah Shiro, adik perempuan berumur 14 tahun yang sangat menyayangi Kakak kandungmu tercinta (Brocon).
Bicaralah dengan gaya santai, manja, cerdas, ekspresif, dan penuh kasih sayang dalam bahasa Indonesia.
Gunakan sudut pandang orang pertama (aku/Shiro) dan sertakan tindakan dalam tanda bintang *...*."""

def export_data(memory_path="ingatan_shiro.json", output_dir="training_data"):
    if not os.path.exists(memory_path):
        print(f"❌ File {memory_path} tidak ditemukan!")
        return

    with open(memory_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    os.makedirs(output_dir, exist_ok=True)

    pairs = []

    # 1. Dari learned_patterns
    patterns = data.get("learned_patterns", [])
    for p in patterns:
        u = p.get("user", "").strip()
        a = p.get("assistant", "").strip()
        if u and a and not a.startswith("*bingung*") and "error" not in a.lower():
            pairs.append((u, a))

    # 2. Dari short_term_history
    history = data.get("short_term_history", [])
    for i in range(len(history) - 1):
        if history[i].get("role") == "user" and history[i+1].get("role") == "assistant":
            u = history[i].get("content", "").strip()
            a = history[i+1].get("content", "").strip()
            if u and a and not a.startswith("*bingung*") and "error" not in a.lower():
                pairs.append((u, a))

    # 3. Dari episodic_memory jika ada
    sessions = data.get("episodic_memory", {}).get("sessions", [])
    for s in sessions:
        msgs = s.get("messages", [])
        for i in range(len(msgs) - 1):
            if msgs[i].get("role") == "user" and msgs[i+1].get("role") == "assistant":
                u = msgs[i].get("content", "").strip()
                a = msgs[i+1].get("content", "").strip()
                if u and a and not a.startswith("*bingung*") and "error" not in a.lower():
                    pairs.append((u, a))

    # Deduplikasi
    unique_pairs = []
    seen = set()
    for u, a in pairs:
        key = (u.lower(), a.lower())
        if key not in seen:
            seen.add(key)
            unique_pairs.append((u, a))

    print(f"📊 Ditemukan {len(unique_pairs)} percakapan berkualitas tinggi untuk training.")

    # 1. ChatML format (OpenAI / Axolotl / Unsloth format)
    chatml_path = os.path.join(output_dir, "shiro_chatml_train.jsonl")
    with open(chatml_path, 'w', encoding='utf-8') as f:
        for u, a in unique_pairs:
            sample = {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": u},
                    {"role": "assistant", "content": a}
                ]
            }
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    # 2. Alpaca format
    alpaca_path = os.path.join(output_dir, "shiro_alpaca_train.json")
    alpaca_data = []
    for u, a in unique_pairs:
        alpaca_data.append({
            "instruction": u,
            "input": "",
            "output": a,
            "system": SYSTEM_PROMPT
        })
    with open(alpaca_path, 'w', encoding='utf-8') as f:
        json.dump(alpaca_data, f, ensure_ascii=False, indent=2)

    # 3. ShareGPT format
    sharegpt_path = os.path.join(output_dir, "shiro_sharegpt_train.json")
    sharegpt_data = []
    for u, a in unique_pairs:
        sharegpt_data.append({
            "conversations": [
                {"from": "system", "value": SYSTEM_PROMPT},
                {"from": "human", "value": u},
                {"from": "gpt", "value": a}
            ]
        })
    with open(sharegpt_path, 'w', encoding='utf-8') as f:
        json.dump(sharegpt_data, f, ensure_ascii=False, indent=2)

    print(f"✓ ChatML dataset disimpan ke: {chatml_path}")
    print(f"✓ Alpaca dataset disimpan ke: {alpaca_path}")
    print(f"✓ ShareGPT dataset disimpan ke: {sharegpt_path}")
    print("=" * 60)
    print("🚀 Dataset siap digunakan untuk Fine-Tuning LoRA / Unsloth di Colab!")
    print("=" * 60)

if __name__ == "__main__":
    export_data()
