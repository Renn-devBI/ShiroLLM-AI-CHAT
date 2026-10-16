# Shiro AI Web UI Preview (Node.js & Vercel)

Versi statis mandiri dari antarmuka Web UI Shiro AI yang sepenuhnya identik dengan tampilan `app.py`. Paket ini menggunakan Node.js dan Express ringan tanpa dependensi bobot model AI lokal (GGUF), sehingga siap dideploy ke Vercel maupun dijalankan secara lokal.

---

## Cara Menjalankan Secara Lokal

1. Masuk ke direktori `Preview-Demo`:
   ```bash
   cd Preview-Demo
   ```

2. Pasang dependensi:
   ```bash
   npm install
   ```

3. Jalankan server:
   ```bash
   npm start
   ```

4. Akses melalui peramban web:
   ```
   http://localhost:7474
   ```

---

## Panduan Deployment ke Vercel

### Metode 1: Menggunakan Vercel CLI
```bash
npm install -g vercel
cd Preview-Demo
vercel
```

### Metode 2: Melalui Dashboard Vercel (Git Integration)
1. Import repositori GitHub ke dashboard Vercel.
2. Di bagian **Root Directory**, pilih folder `Preview-Demo`.
3. Klik **Deploy**. Vercel akan otomatis mengenali `vercel.json` dan mempublikasikan situs.

---

## Struktur Berkas Preview-Demo

- `api/index.js`: Server Express untuk routing statis dan simulasi API SSE chat, sesi, profil, dan inspektur.
- `server.js`: Titik masuk eksekusi server lokal pada port 7474.
- `templates/index.html`: Berkas HTML utama yang disalin langsung dari `templates/index.html` asli.
- `static/style.css`: Berkas stylesheet utama antarmuka Shiro.
- `static/script.js`: Skrip interaktif logika klien, auto-scroll, dan perender markdown.
- `profile/ai.json`: Profil avatar resmi Shiro.
- `vercel.json`: Konfigurasi rewrite serverless untuk Vercel.
- `package.json`: Definisi dependensi Node.js.
