# 🌸 ShiroLLM-AI-CHAT

Chatbot AI Karakter Interaktif dengan Sistem Memori Bertingkat (Self-Learning), Emosi Dinamis, dan Anti-Halusinasi.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Renn-devBI/ShiroLLM-AI-CHAT/blob/main/Shiro_LLMA_Colab.ipynb)

---

## ✨ Fitur Unggulan

- **🧠 Model Tercanggih & Beragam**:
  - `Lumimaid-v0.2-8B-Q5_K_M` *(Rekomendasi Utama)*: Fine-tuned khusus roleplay dan percakapan karakter ekspresif.
  - `Qwen3-4B-Q4_K_M`: Model penalaran cerdas & cepat.
  - `Llama-3.2-3B-Instruct`: Sangat cepat dan efisien.
  - `Phi-3-mini-4k-instruct`: Ringan dan hemat memori.
- **💡 Continuous Self-Learning**:
  - AI secara otomatis mengekstrak fakta, preferensi pengguna (suka/tidak suka), janji, dan peristiwa dari percakapan maupun responsnya sendiri.
  - Fakta disimpan secara terstruktur dan diingat lintas sesi percakapan.
- **🛡️ Anti-Halusinasi & Konteks Bersih**:
  - Konteks percakapan diseleksi secara cerdas (`get_smart_memory_context`) tanpa token sampah.
  - Sistem kompresi memori otomatis (`compress_old_messages`).
- **⚡ Google Colab Ready (Akselerasi GPU)**:
  - Buka notebook `Shiro_LLMA_Colab.ipynb` untuk menjalankan AI di cloud dengan GPU T4/A100 gratis tanpa membebani komputer lokal Anda!
- **🌐 Antarmuka Web Modern**:
  - UI responsif, avatar kustom, panel statistik emosi real-time, dan fitur switch model langsung dari browser.

---

## 🚀 Cara Menjalankan

### Opsi 1: Menjalankan di Google Colab (Gratis GPU, Rekomendasi!)
1. Buka file [`Shiro_LLMA_Colab.ipynb`](Shiro_LLMA_Colab.ipynb) di Google Colab dengan mengklik badge di atas.
2. Pastikan Runtime diset ke **T4 GPU** (*Runtime* -> *Change runtime type* -> *T4 GPU*).
3. Jalankan semua cell secara berurutan.
4. Klik link publik yang dihasilkan oleh Cloudflare Tunnel untuk membuka Web UI di browser Anda.

---

### Opsi 2: Menjalankan di Komputer Lokal

1. **Clone Repository**:
   ```bash
   git clone https://github.com/Renn-devBI/ShiroLLM-AI-CHAT.git
   cd ShiroLLM-AI-CHAT
   ```

2. **Buat Virtual Environment & Install Dependencies**:
   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # Linux / Mac
   source venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Unduh Model**:
   ```bash
   python download_model.py
   ```

4. **Jalankan Server**:
   ```bash
   python web.py
   ```
   Akses melalui browser di: `http://127.0.0.1:7474`

---

## 📁 Struktur Direktori

```
Shiro-LLMA/
├── Shiro_LLMA_Colab.ipynb   # Notebook Google Colab 1-Klik
├── web.py                   # Server Flask & logika inferensi LLM
├── memory_manager_v2.py     # Sistem memori cerdas & emosi
├── memory_optimization.py   # Modul optimasi & pencegahan halusinasi
├── download_model.py        # Skrip unduh model otomatis
├── model_config.json        # Konfigurasi model aktif & daftar model
├── isekai_world.json        # Pengaturan latar dunia cerita
├── ingatan_shiro.json       # Database memori & fakta yang dipelajari
├── templates/               # Tampilan HTML web UI
├── static/                  # CSS & JavaScript antarmuka
└── model/                   # Folder file GGUF model (.gitignore)
```

---

## 📜 Lisensi
Open Source - Dibuat untuk tujuan eksplorasi AI interaktif dan percakapan karakter.
