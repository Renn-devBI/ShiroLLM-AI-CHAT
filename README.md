# ShiroLLM-AI-CHAT

[![Open AI in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Renn-devBI/ShiroLLM-AI-CHAT/blob/main/Shiro_LLMA_Colab.ipynb)
[![Open Voice Changer in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Renn-devBI/ShiroLLM-AI-CHAT/blob/main/Shiro_VoiceChanger_Colab.ipynb)
![Python Version](https://img.shields.io/badge/Python-3.10%20%7C%203.11-blue)
![Architecture](https://img.shields.io/badge/Architecture-Modular%20v2.5-brightgreen)
![Tests](https://img.shields.io/badge/Tests-Passed-success)

Asisten AI percakapan interaktif dengan arsitektur kognitif berbasis persona Shiro, dilengkapi memori episodik & semantik, pemahaman multimodal vision, integrasi web browsing, normalisasi typo bahasa gaul, serta ekspor dataset continuous learning otomatis.

---

## Fitur Utama

- **Model Resmi Google Colab**:
  - Qwen3-32B: Model utama penalaran kognitif tingkat lanjut (Colab Pro / A100 GPU).
  - Qwen2.5-VL-7B-Instruct: Multimodal vision untuk pemahaman kamera webcam real-time dan analisis gambar.
  - Qwen2.5-7B-Instruct: Model efisien untuk alokasi GPU T4 standar.
- **Arsitektur Modular**:
  - Terbagi ke modul `shiro.nlp`, `shiro.llm`, `shiro.memory`, `shiro.web`, `shiro.training`, dan `shiro.pipeline`.
- **Web Browsing & MediaWiki Integration**:
  - Ekstraksi informasi web dan ensiklopedia fandom/wikipedia secara otomatis.
- **Typo & Slang Auto-Correction**:
  - Normalisasi otomatis kesalahan pengetikan dan singkatan bahasa Indonesia percakapan.
- **Cognitive Memory & Atomic Persistence**:
  - Penyimpanan profil pengguna, relasi, fakta semantik, dan riwayat obrolan secara atomic dan aman.
- **Web UI Modern**:
  - Antarmuka web responsif dengan dukungan tema dark/light, syntax highlighting, pengunduhan kode satu-klik, diagram Mermaid, dan smart auto-scroll.
- **Static Web UI Preview (Node.js & Vercel)**:
  - Tampilan demo web statis identik di folder `Preview-Demo` yang siap dideploy langsung ke Vercel tanpa dependensi runtime AI lokal.

---

## Cara Menjalankan

### Opsi 1: Google Colab (Akselerasi GPU)

Buka notebook resmi di Google Colab:
1. [Shiro_LLMA_Colab.ipynb](Shiro_LLMA_Colab.ipynb) - Server AI Chatting, Multimodal Vision, Memori Google Drive, dan Web UI Shiro.
2. [Shiro_VoiceChanger_Colab.ipynb](Shiro_VoiceChanger_Colab.ipynb) - Real-Time Voice Changer (RVC MMVCServerSIO) dengan tunneling Cloudflare / Ngrok.

Pastikan runtime menggunakan GPU (Runtime -> Change runtime type -> T4 GPU atau A100). Jalankan setiap sel secara berurutan.

---

### Opsi 2: Menjalankan Lokal (Python Server)

1. Clone repositori:
   ```bash
   git clone https://github.com/Renn-devBI/ShiroLLM-AI-CHAT.git
   cd ShiroLLM-AI-CHAT
   ```

2. Buat virtual environment dan install dependencies:
   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\Activate
   # Linux / macOS
   source venv/bin/activate

   pip install -r requirements.txt
   ```

3. Unduh model AI:
   ```bash
   python download_model.py
   ```

4. Jalankan aplikasi:
   ```bash
   python app.py
   ```
   Buka peramban di `http://127.0.0.1:7474`.

---

### Opsi 3: Preview Web UI (Node.js & Vercel)

Untuk mencoba antarmuka web secara cepat tanpa mengunduh model AI:
```bash
cd Preview-Demo
npm install
npm start
```
Buka peramban di `http://localhost:7474`. Folder ini juga dapat langsung dideploy ke Vercel.

---

## Struktur Repositori

```
Shiro-LLMA/
├── app.py                      # Entry point utama server Flask
├── download_model.py           # Skrip unduh otomatis bobot model GGUF
├── export_training_data.py     # CLI ekspor dataset continuous learning
├── Shiro_LLMA_Colab.ipynb      # Notebook resmi Google Colab
├── templates/                  # Template antarmuka web (index.html, pipeline.html)
├── static/                     # Aset web (script.js, style.css)
├── shiro/                      # Paket inti modular Shiro
│   ├── config.py               # Konfigurasi sistem dan path
│   ├── persona.py              # Definisi sistem prompt kognitif
│   ├── llm/                    # Loader model dan pembersih output
│   ├── nlp/                    # Normalisasi teks dan klasifikasi emosi
│   ├── memory/                 # Pengelola memori kognitif dan sesi
│   ├── web/                    # Integrasi web reader dan API
│   ├── training/               # Pipeline ekspor dataset
│   └── pipeline/               # Trace eksekusi neural real-time
├── Preview-Demo/               # Paket demo statis Node.js & Vercel
│   ├── api/index.js            # Express server & mock API
│   ├── server.js               # Entry point Node.js lokal
│   ├── vercel.json             # Konfigurasi deployment Vercel
│   ├── templates/              # HTML antarmuka identik
│   └── static/                 # CSS dan JavaScript identik
├── data/templates/             # Template memori bersih bebas data pribadi
├── tests/                      # Unit test suite sistem
└── README.md
```

---

## Pengujian Sistem

Jalankan seluruh test suite dengan unittest:
```bash
python -m unittest discover -s tests -v
```

---

## Lisensi

Open Source - Dikembangkan oleh Shiro Core Team untuk tujuan riset dan eksplorasi asisten AI percakapan.
