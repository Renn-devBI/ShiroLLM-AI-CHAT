# ShiroLLM-AI-CHAT

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Renn-devBI/ShiroLLM-AI-CHAT/blob/main/Shiro_LLMA_Colab.ipynb)

---

## Fitur Unggulan

- **3 Model Resmi Google Colab (GPU Accelerasi)**:
  - `Qwen3-32B` *(Model Utama ⭐)*: Penalaran tertinggi, sangat cerdas, anti-halusinasi untuk Colab Pro (~19.8 GB).
  - `Qwen2.5-VL-7B-Instruct` *(Model ke-2 👁️)*: Vision Multimodal untuk pemahaman kamera webcam real-time & kirim gambar (mendukung Web UI & Project VTuber, ~5.6 GB).
  - `Qwen2.5-7B-Instruct` *(Model ke-3 ⚡)*: Super cepat & efisien di GPU T4 standar Colab gratis (~5.4 GB).
- **Auto Computer & Manual Model Drop (Versi Non-Colab)**:
  - Komputer lokal otomatis memilih model berukuran rendah (`Qwen3-4B-Q4_K_M`, `Phi-3-mini`, dsb.) agar CPU tidak berat.
  - **Manual Model Insertion**: Cukup letakkan file `.gguf` apa saja ke dalam folder `model/`, sistem akan otomatis memindai dan menampilkannya di menu ganti model web UI!
- **Fitur Visual Kamera & Upload Gambar**:
  - Ambil foto langsung melalui webcam / kamera real-time atau unggah file gambar di antarmuka web.
  - Kompatibel dengan endpoint OpenAI Vision `/v1/chat/completions` untuk dihubungkan ke project VTuber.
- **Sistem API Key Terintegrasi**:
  - Terhubung ke WhatsApp Bot, Telegram Bot, dan Project VTuber (`/v1/chat/completions` & `/api/chat`).
- **Continuous Self-Learning & Anti-Halusinasi**:
  - AI secara otomatis mengekstrak fakta, preferensi pengguna (suka/tidak suka), janji, dan peristiwa dari percakapan.
  - Bersih dari token sistem, meta-commentary, dan narasi novel orang ketiga.
- **Antarmuka Web Modern (Clean Dark Blue)**:
  - Tampilan profesional clean dark blue tanpa glow/slop atau emoji berlebihan.

---

## Cara Menjalankan

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

## Struktur Direktori

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
