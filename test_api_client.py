# -*- coding: utf-8 -*-
"""
Contoh Script Client untuk Menghubungkan Bot WhatsApp / VTuber / Eksternal ke Shiro LLMA
Mendukung 2 format:
1. Format OpenAI Standard (/v1/chat/completions) - Kompatibel dengan semua AI Bot & Framework
2. Format Direct Shiro API (/api/chat)
"""

import requests
import json
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ganti URL ini dengan URL Ngrok / Cloudflare Tunnel dari Colab Anda,
# atau http://127.0.0.1:7474 jika berjalan di jaringan yang sama.
BASE_URL = os.environ.get("SHIRO_BASE_URL", "http://127.0.0.1:7474")

# Ambil API Key dari api_key.json atau environment
API_KEY = os.environ.get("SHIRO_API_KEY", "")
if not API_KEY and os.path.exists("api_key.json"):
    try:
        with open("api_key.json", "r", encoding="utf-8") as f:
            API_KEY = json.load(f).get("api_key", "")
    except Exception:
        pass

if not API_KEY:
    API_KEY = "shiro-sk-demo-key"


def chat_openai_format(user_prompt):
    """
    Format 1: OpenAI-Compatible Chat Completions
    Cocok untuk WhatsApp Bot (Baileys/Wppconnect/Python), VTuber, Telegram Bot, LangChain, dll.
    """
    url = f"{BASE_URL.rstrip('/')}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    payload = {
        "model": "Qwen3-32B",
        "messages": [
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7
    }

    print(f"\n[OpenAI Format] Mengirim pesan: '{user_prompt}'")
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=60)
        if res.status_code == 200:
            data = res.json()
            reply = data["choices"][0]["message"]["content"]
            print(f"[Shiro Reply]: {reply}")
            return reply
        else:
            print(f"Error {res.status_code}: {res.text}")
            return None
    except Exception as e:
        print(f"Gagal koneksi ke {url}: {e}")
        return None


def chat_direct_format(user_prompt):
    """
    Format 2: Direct Shiro API (/api/chat)
    Format sederhana untuk HTTP request cepat.
    """
    url = f"{BASE_URL.rstrip('/')}/api/chat"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    payload = {
        "message": user_prompt
    }

    print(f"\n[Direct Format] Mengirim pesan: '{user_prompt}'")
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=60)
        if res.status_code == 200:
            data = res.json()
            reply = data.get("reply", "")
            mood = data.get("mood", "")
            print(f"[Shiro Reply]: {reply} (Mood: {mood})")
            return reply
        else:
            print(f"Error {res.status_code}: {res.text}")
            return None
    except Exception as e:
        print(f"Gagal koneksi ke {url}: {e}")
        return None


if __name__ == "__main__":
    print("=" * 60)
    print("🌸 SHIRO LLMA API CLIENT EXAMPLE")
    print(f"📍 Target Base URL : {BASE_URL}")
    print(f"🔑 Target API Key  : {API_KEY[:12]}... (panjang: {len(API_KEY)})")
    print("=" * 60)
    
    # Contoh penggunaan:
    prompt = "Halo Shiro! Kakak baru pulang nih, kamu lagi apa?"
    print("\n1. Menguji format OpenAI Compatible...")
    chat_openai_format(prompt)
