# ShiroLLM-AI-CHAT

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Renn-devBI/ShiroLLM-AI-CHAT/blob/main/Shiro_LLMA_Colab.ipynb)
![Python Version](https://img.shields.io/badge/Python-3.10%20%7C%203.11-blue)
![Architecture](https://img.shields.io/badge/Architecture-Modular%20v2.5-brightgreen)
![Tests](https://img.shields.io/badge/Tests-14%20Passed-success)

Asisten AI percakapan cerdas dengan persona adik manja, cerdas, dan setia (**Shiro**), dilengkapi arsitektur memori kognitif berjangka panjang, pemahaman multimodal vision, integrasi web browsing cerdas, normalisasi typo bahasa gaul, serta ekspor dataset continuous learning otomatis.

---

## ✨ Fitur Unggulan

- **3 Model Resmi Google Colab (GPU Akselerasi)**:
  - `Qwen3-32B` *(Model Utama ⭐)*: Penalaran mendalam, sangat cerdas, anti-halusinasi untuk Colab Pro/A100 (~19.8 GB).
  - `Qwen2.5-VL-7B-Instruct` *(Multimodal Vision 👁️)*: Pemahaman kamera webcam real-time & kirim gambar (mendukung Web UI & Project VTuber, ~5.6 GB).
  - `Qwen2.5-7B-Instruct` *(Ringan & Cepat ⚡)*: Super efisien di GPU T4 standar Colab gratis (~5.4 GB).
- **Arsitektur Modular `shiro/`**:
  - Kode terstruktur rapi ke dalam modul `shiro.nlp`, `shiro.llm`, `shiro.memory`, `shiro.web`, `shiro.training`, dan `shiro.pipeline`.
- **Web Browsing & MediaWiki Integration**:
  - Membaca link web dan artikel ensiklopedia fandom/wikipedia secara otomatis melalui MediaWiki API bypass untuk menghindari blokir Cloudflare.
- **Typo & Slang Auto-Correction**:
  - Otomatis menormalisasi salah ketik (typo) dan singkatan gaul bahasa Indonesia tanpa merusak kata kerja maupun ekspresi emosional.
- **Cognitive Memory & Google Drive Atomic Sync**:
  - Menyimpan profil pengguna, relasi, fakta RDF, dan riwayat obrolan secara atomic (bebas korupsi file). Di Colab, memori otomatis dicadangkan dan dipulihkan dari Google Drive.
- **Continuous Learning Auto-Export**:
  - Mengonversi interaksi menjadi dataset format Alpaca, ChatML, dan ShareGPT untuk fine-tuning lanjutan.
- **Clean Anti-CoT & Formatted Output**:
  - Filter otomatis pemikir internal (`<thought>`, CoT leaks) dengan preservasi format paragraf dan baris baru (`Shift+Enter`).

---

## 🚀 Cara Menjalankan

### Opsi 1: Google Colab (Paling Mudah & Gratis GPU)
1. Buka [`Shiro_LLMA_Colab.ipynb`](Shiro_LLMA_Colab.ipynb) dengan mengklik tombol **Open In Colab** di atas.
2. Pastikan Runtime menggunakan GPU (**Runtime** -> **Change runtime type** -> **T4 GPU**).
3. Jalankan semua cell secara berurutan.
4. Buka URL publik Cloudflare Tunnel yang ditampilkan di terminal output.

---

### Opsi 2: Menggunakan Docker (Rekomendasi Lokal)
```bash
# Windows
.\run-docker.ps1

# Linux / Mac
chmod +x run-docker.sh
./run-docker.sh
```
Akses di browser melalui: `http://localhost:7474`
*(Panduan lengkap: [docs/DOCKER.md](docs/DOCKER.md))*

---

### Opsi 3: Menjalankan Manual di Komputer Lokal

1. **Clone Repository**:
   ```bash
   git clone https://github.com/Renn-devBI/ShiroLLM-AI-CHAT.git
   cd ShiroLLM-AI-CHAT
   ```

2. **Buat Virtual Environment & Install Dependencies**:
   ```bash
   python -m venv venv
   # Windows PowerShell
   .\venv\Scripts\Activate
   # Linux / macOS
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
   Akses Web UI di: `http://127.0.0.1:7474`

---

## 📂 Struktur Repositori

```
Shiro-LLMA/
├── web.py                      # Main Flask web server & API endpoints
├── Shiro_LLMA_Colab.ipynb      # Notebook Colab siap pakai 1-klik
├── export_training_data.py     # CLI export dataset chat & vision
├── download_model.py           # Auto downloader model GGUF
├── docker-compose.yml          # Konfigurasi container Docker
├── Dockerfile                  # Base build image Docker
│
├── shiro/                      # 📦 Paket Inti Modular
│   ├── config.py               # Konstanta path & konfigurasi sistem
│   ├── persona.py              # Single source of truth system prompt
│   ├── llm/                    # Output cleaner & loader Llama GGUF
│   ├── nlp/                    # Normalizer typo & classifier emosi
│   ├── memory/                 # Memori kognitif & Drive atomic sync
│   ├── web/                    # MediaWiki API & web content reader
│   ├── training/               # Exporter Alpaca/ChatML/ShareGPT
│   └── pipeline/               # Real-time SSE execution tracer
│
├── data/
│   └── templates/              # Template awal memori bersih (privasi aman)
├── docs/                       # Dokumentasi lengkap
│   ├── ARCHITECTURE.md         # Diagram alur pipeline & modul
│   ├── CONFIGURATION.md        # Variabel lingkungan & API OpenAI
│   └── DOCKER.md               # Panduan deployment Docker
├── tests/                      # Unit test suite
├── templates/                  # Frontend HTML (UI Chat modern)
└── static/                     # Assets CSS, JavaScript, avatar
```

---

## 🧪 Menjalankan Pengujian (Unit Tests)

Jalankan test suite menggunakan Python standard library:
```bash
python -m unittest discover -s tests -v
```

---

## 📚 Dokumentasi Lanjutan

- [Arsitektur Sistem & Neural Pipeline](docs/ARCHITECTURE.md)
- [Panduan Konfigurasi & Integrasi API](docs/CONFIGURATION.md)
- [Panduan Deployment Docker](docs/DOCKER.md)

---

## 📜 Lisensi
Open Source - Dibuat untuk tujuan eksplorasi AI interaktif dan percakapan karakter.
