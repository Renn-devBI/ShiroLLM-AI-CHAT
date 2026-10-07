# -*- coding: utf-8 -*-
"""
Export Training Data for Shiro Fine-Tuning
Mengekstrak percakapan dari ingatan_shiro.json ke dalam format dataset terpisah:
1. training_data/chat/   -> Dataset Teks Percakapan (untuk Text LLM: Qwen3-32B, Qwen2.5-7B, dll.)
2. training_data/vision/ -> Dataset Visual Multimodal (untuk Vision VLM: Qwen2.5-VL-7B, LLaVA, dll.)
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

def export_data(memory_path="ingatan_shiro.json", base_output_dir="training_data"):
    if not os.path.exists(memory_path):
        print(f"❌ File {memory_path} tidak ditemukan!")
        return

    with open(memory_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    chat_dir = os.path.join(base_output_dir, "chat")
    vision_dir = os.path.join(base_output_dir, "vision")
    os.makedirs(chat_dir, exist_ok=True)
    os.makedirs(vision_dir, exist_ok=True)
    os.makedirs(os.path.join(vision_dir, "images"), exist_ok=True)

    chat_pairs = []
    vision_pairs = []

    def is_valid_response(a):
        return a and not a.startswith("*bingung*") and "error" not in a.lower()

    # 1. Ekstrak dari learned_patterns
    patterns = data.get("learned_patterns", [])
    for p in patterns:
        u = p.get("user", "").strip()
        a = p.get("assistant", "").strip()
        img = p.get("image", None)
        if u and is_valid_response(a):
            if img:
                vision_pairs.append((u, a, img))
            else:
                chat_pairs.append((u, a))

    # 2. Ekstrak dari short_term_history
    history = data.get("short_term_history", [])
    for i in range(len(history) - 1):
        if history[i].get("role") == "user" and history[i+1].get("role") == "assistant":
            u = history[i].get("content", "").strip()
            a = history[i+1].get("content", "").strip()
            img = history[i].get("image", None)
            if u and is_valid_response(a):
                if img:
                    vision_pairs.append((u, a, img))
                elif "[gambar/kamera dikirim]" in u.lower() or "[visual vtuber/webcam]" in u.lower():
                    # Jika ada tag visual tapi image belum tercatat terpisah
                    cleaned_u = re.sub(r'\[(gambar/kamera dikirim|visual vtuber/webcam)\]', '', u, flags=re.IGNORECASE).strip()
                    if cleaned_u:
                        chat_pairs.append((cleaned_u, a))
                else:
                    chat_pairs.append((u, a))

    # 3. Ekstrak dari episodic_memory jika ada
    sessions = data.get("episodic_memory", {}).get("sessions", [])
    for s in sessions:
        msgs = s.get("messages", [])
        for i in range(len(msgs) - 1):
            if msgs[i].get("role") == "user" and msgs[i+1].get("role") == "assistant":
                u = msgs[i].get("content", "").strip()
                a = msgs[i+1].get("content", "").strip()
                img = msgs[i].get("image", None)
                if u and is_valid_response(a):
                    if img:
                        vision_pairs.append((u, a, img))
                    else:
                        chat_pairs.append((u, a))

    # Deduplikasi Chat Pairs
    unique_chat = []
    seen_chat = set()
    for u, a in chat_pairs:
        k = (u.lower(), a.lower())
        if k not in seen_chat:
            seen_chat.add(k)
            unique_chat.append((u, a))

    # Deduplikasi Vision Pairs
    unique_vision = []
    seen_vision = set()
    for u, a, img in vision_pairs:
        k = (u.lower(), a.lower(), str(img))
        if k not in seen_vision:
            seen_vision.add(k)
            unique_vision.append((u, a, img))

    print("=" * 60)
    print("📊 STATUS DATASET TRAINING SHIRO:")
    print(f"👉 1. Dataset Chat (Teks)   : {len(unique_chat)} percakapan")
    print(f"👉 2. Dataset Vision (Visual): {len(unique_vision)} percakapan multimodal")
    print("=" * 60)

    # ========================================================
    # A. EXPORT DATASET CHAT (TEKS SAJA) -> training_data/chat/
    # ========================================================
    # 1. ChatML format
    chatml_path = os.path.join(chat_dir, "shiro_chatml_train.jsonl")
    with open(chatml_path, 'w', encoding='utf-8') as f:
        for u, a in unique_chat:
            sample = {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": u},
                    {"role": "assistant", "content": a}
                ]
            }
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    # 2. Alpaca format
    alpaca_path = os.path.join(chat_dir, "shiro_alpaca_train.json")
    alpaca_data = []
    for u, a in unique_chat:
        alpaca_data.append({
            "instruction": u,
            "input": "",
            "output": a,
            "system": SYSTEM_PROMPT
        })
    with open(alpaca_path, 'w', encoding='utf-8') as f:
        json.dump(alpaca_data, f, ensure_ascii=False, indent=2)

    # 3. ShareGPT format
    sharegpt_path = os.path.join(chat_dir, "shiro_sharegpt_train.json")
    sharegpt_data = []
    for u, a in unique_chat:
        sharegpt_data.append({
            "conversations": [
                {"from": "system", "value": SYSTEM_PROMPT},
                {"from": "human", "value": u},
                {"from": "gpt", "value": a}
            ]
        })
    with open(sharegpt_path, 'w', encoding='utf-8') as f:
        json.dump(sharegpt_data, f, ensure_ascii=False, indent=2)

    print(f"✓ [CHAT] ChatML disimpan ke   : {chatml_path}")
    print(f"✓ [CHAT] Alpaca disimpan ke   : {alpaca_path}")
    print(f"✓ [CHAT] ShareGPT disimpan ke : {sharegpt_path}")

    # ========================================================
    # B. EXPORT DATASET VISION (GAMBAR) -> training_data/vision/
    # ========================================================
    # Jika belum ada sample vision dari user, siapkan starter exemplar
    if not unique_vision:
        # Tambahkan 1 starter template multimodal
        unique_vision.append((
            "Kakak memperlihatkan gambar ini kepadamu, Shiro. Apa yang kamu lihat?",
            "*melihat foto dengan mata berbinar* Wah, Kakak! Shiro bisa melihatnya dengan jelas! Lucu dan menarik banget, Shiro suka deh kalau Kakak berbagi momen seperti ini sama Shiro~ >//<",
            "images/starter_sample.jpg"
        ))

    # 1. Vision ChatML (Format Multimodal Qwen2-VL / LLaVA)
    vision_chatml_path = os.path.join(vision_dir, "shiro_vision_chatml.jsonl")
    with open(vision_chatml_path, 'w', encoding='utf-8') as f:
        for u, a, img in unique_vision:
            sample = {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": img},
                            {"type": "text", "text": u}
                        ]
                    },
                    {"role": "assistant", "content": a}
                ]
            }
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    # 2. Vision ShareGPT (Format LLaVA / Unsloth Multimodal)
    vision_sharegpt_path = os.path.join(vision_dir, "shiro_vision_sharegpt.json")
    vision_sharegpt_data = []
    for idx, (u, a, img) in enumerate(unique_vision, start=1):
        vision_sharegpt_data.append({
            "id": f"shiro_vision_{idx:04d}",
            "image": img,
            "conversations": [
                {"from": "human", "value": f"<image>\n{u}"},
                {"from": "gpt", "value": a}
            ]
        })
    with open(vision_sharegpt_path, 'w', encoding='utf-8') as f:
        json.dump(vision_sharegpt_data, f, ensure_ascii=False, indent=2)

    # 3. Vision Alpaca
    vision_alpaca_path = os.path.join(vision_dir, "shiro_vision_alpaca.json")
    vision_alpaca_data = []
    for u, a, img in unique_vision:
        vision_alpaca_data.append({
            "instruction": u,
            "input": "",
            "image": img,
            "output": a,
            "system": SYSTEM_PROMPT
        })
    with open(vision_alpaca_path, 'w', encoding='utf-8') as f:
        json.dump(vision_alpaca_data, f, ensure_ascii=False, indent=2)

    print(f"✓ [VISION] ChatML disimpan ke  : {vision_chatml_path}")
    print(f"✓ [VISION] ShareGPT disimpan ke: {vision_sharegpt_path}")
    print(f"✓ [VISION] Alpaca disimpan ke  : {vision_alpaca_path}")
    print("=" * 60)
    print("🚀 Dataset Chat & Vision BERHASIL DIPISAH dan siap digunakan untuk Fine-Tuning!")
    print("=" * 60)

if __name__ == "__main__":
    export_data()
