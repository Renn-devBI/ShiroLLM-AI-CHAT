# 🐳 Panduan Docker Shiro LLMA

Dokumen ini menggabungkan seluruh instruksi penggunaan Docker dan Docker Compose untuk menjalankan Shiro LLMA dalam container terisolasi dengan dukungan GPU CUDA atau CPU fallback.

---

## 1. Persiapan Awal

Pastikan Anda telah menginstal:
* [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS) atau `docker-ce` (Linux).
* [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (khusus jika menggunakan akselerasi GPU NVIDIA).

---

## 2. Menjalankan Menggunakan Docker Compose (Direkomendasikan)

### A. Windows (PowerShell)
```powershell
.\run-docker.ps1
```

### B. Linux / macOS (Bash)
```bash
chmod +x run-docker.sh
./run-docker.sh
```

### C. Manual Docker Compose
```bash
docker compose up -d --build
```
Akses Web UI di browser Anda melalui: `http://localhost:7474`

---

## 3. Volume & Penyimpanan Data

Docker Compose telah mengonfigurasi mounting volume otomatis agar data dan model tidak hilang saat container direstart:
* `./model:/app/model` : Tempat penyimpanan model GGUF.
* `./profile:/app/profile` : Foto profil pengguna dan Shiro.
* `./training_data:/app/training_data` : Dataset hasil percakapan & pembelajaran online.
* `./ingatan_shiro.json:/app/ingatan_shiro.json` : Berkas memori kognitif.

---

## 4. Menghentikan Container

```bash
docker compose down
```
