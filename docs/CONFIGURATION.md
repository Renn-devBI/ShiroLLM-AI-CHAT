# ⚙️ Panduan Konfigurasi Shiro LLMA

Dokumen ini memuat seluruh opsi konfigurasi, variabel lingkungan (environment variables), pengaturan model LLM & Vision, serta konfigurasi API Key.

---

## 1. Variabel Lingkungan (Environment Variables)

| Variabel | Default | Keterangan |
|---|---|---|
| `SHIRO_API_KEY` | *(Otomatis dibuat)* | Kunci otentikasi API Key untuk integrasi eksternal (/v1/chat/completions) |
| `SHIRO_DRIVE_DIR` | `/content/drive/MyDrive/Shiro_Memory` | Direktori Google Drive untuk pencadangan & sinkronisasi otomatis |
| `SHIRO_CONTEXT_SIZE` | `4096` | Ukuran context window model Llama |
| `N_GPU_LAYERS` | `0` (CPU) / `-1` (Full GPU) | Jumlah layer model yang di-offload ke VRAM GPU NVIDIA |
| `GEMINI_API_KEY` | *(Opsional)* | API Key Gemini Flash untuk jembatan visual fallback pada model teks biasa |

---

## 2. Pemilihan Model (Model Selection)

Shiro LLMA mendukung model berformat GGUF yang disimpan di dalam direktori `model/`:

1. **Qwen3-32B-Q4_K_M.gguf** (Primary Recommended):
   * Penalaran mendalam, kepribadian ekspresif, pemahaman konteks panjang.
2. **Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf** (Multimodal Vision):
   * Mampu melihat foto, tangkapan layar, dan kamera real-time secara langsung melalui Vision Chat Handler.
3. **Qwen2.5-7B-Instruct-Q4_K_M.gguf** (Secondary / Low VRAM):
   * Ringan, cepat, cocok untuk perangkat dengan memori terbatas.

Penggantian model dapat dilakukan secara langsung di Web UI melalui menu **Pengaturan Model**.

---

## 3. Integrasi API Eksternal (OpenAI-Compatible)

Shiro LLMA menyediakan endpoint `/v1/chat/completions` yang kompatibel dengan protokol OpenAI:
* **Endpoint**: `http://localhost:7474/v1/chat/completions`
* **Header**: `Authorization: Bearer <SHIRO_API_KEY>`
* **Contoh Request**:
```json
{
  "model": "shiro",
  "messages": [
    {"role": "user", "content": "Halo Shiro, apa kabar?"}
  ],
  "temperature": 0.7
}
```
Kunci API tersimpan di `api_key.json` dan otomatis dicadangkan ke Google Drive jika berjalan di Google Colab.
