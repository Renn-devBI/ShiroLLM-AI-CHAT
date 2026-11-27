# -*- coding: utf-8 -*-
"""
Multi-Engine Reverse Image Search & Anti-Hallucination Grounding Module
Menjalankan pencarian balik gambar paralel lintas 6 engine menggunakan profil browser Mozilla Firefox:
  1. Google Lens (umum, objek, karakter, anime, orang, produk, tempat)
  2. trace.moe (scene & episode anime persis dengan timestamp)
  3. Yandex Visual Search (CBIR tags, situs cocok, & gambar serupa)
  4. IQDB (multi-booru anime/fanart matching)
  5. SauceNAO (ilustrasi, manga, Pixiv, Danbooru, AniDB)
  6. Bing Visual Search (umum, tokoh, landmark, halaman web cocok)

Seluruh kandidat lintas engine digabungkan & diberikan ke AI untuk diverifikasi bersama pengamatan visual
sehingga AI tidak pernah menebak asal-asalan atau berhalusinasi.
"""

import io
import os
import re
import json
import time
import uuid
import base64
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from shiro.agent.network import get_firefox_headers, get_firefox_session

try:
    from PIL import Image
except ImportError:
    Image = None


_CODE_OR_DEBUG_RE = re.compile(
    r"\b(?:error|traceback|exception|stack\s*trace|syntaxerror|typeerror|nameerror|"
    r"perbaiki\s+kode|fix\s+(?:bug|error|code)|debug|refactor|lint|css|tailwind|"
    r"json|yaml|compile|build\s+error|npm\s+err|pip\s+err|eslint)\b",
    re.IGNORECASE,
)

_IDENTIFY_OR_LOOKUP_RE = re.compile(
    r"(?:"
    r"\b(?:apa\s+ini|ini\s+apa|gambar\s+apa|foto\s+apa|dari\s+mana|siapa\s+ini|"
    r"siapa\s+dia|siapa\s+karakter|siapa\s+nama|karakter\s+apa|tokoh\s+siapa|"
    r"anime\s+apa|dari\s+anime|judul\s+anime|manga\s+apa|manhwa\s+apa|film\s+apa|"
    r"movie|drama\s+apa|game\s+apa|lagu\s+apa|produk\s+apa|merk\s+apa|merek\s+apa|"
    r"tempat\s+apa|dimana\s+ini|di\s+mana\s+ini|lokasi\s+mana|hewan\s+apa|tanaman\s+apa|"
    r"sumber|source|sauce|episode\s+berapa|scene\s+apa|cari\s+tahu|carikan|cariin|"
    r"identifikasi|identify|reverse\s+search|google\s+lens|lens|miri[p]?\s+apa)\b"
    r"|what\s+(?:is\s+this|anime|character|movie|game|product|place)|who\s+is\s+this"
    r")",
    re.IGNORECASE,
)


def should_run_reverse_image_search(
    user_text: str,
    has_image: bool = True,
    has_video: bool = False,
) -> bool:
    """
    Menentukan apakah gambar unggahan harus melewati pipeline Reverse Image Search multi-engine.
    Berlaku luas untuk seluruh identifikasi visual (anime, karakter, produk, tokoh, lokasi, umum)
    dan hanya melewati screenshot murni error/debugging kode tanpa niat identifikasi.
    """
    if not has_image:
        return False

    txt = (user_text or "").strip()
    if not txt:
        # User mengirim gambar tanpa pertanyaan teks -> bantu identifikasi
        return True

    if _IDENTIFY_OR_LOOKUP_RE.search(txt):
        return True

    # Jika pengguna jelas menanyakan error/kode/debugging tanpa niat cari tahu sumber/identitas, lewati
    if _CODE_OR_DEBUG_RE.search(txt):
        return False

    # Video multimodal panjang fokus ke alur video kecuali user memang minta cari tahu/identifikasi
    if has_video:
        return False

    # Default aman: jalankan reverse image search agar pertanyaan umum tentang gambar juga tergrounding
    return True


def _decode_and_prepare_image(
    image_src: str,
    max_dim: int = 1280,
    min_dim: int = 16,
) -> Optional[Tuple[bytes, str]]:
    """
    Mendekode data URI / base64 / path file menjadi bytes JPEG/PNG siap kirim ke engine pencarian balik.
    Mengabaikan gambar uji 1x1 pixel atau data placeholder tidak valid (< min_dim).
    """
    if not image_src or not isinstance(image_src, str):
        return None
    s = image_src.strip()
    raw_bytes = b""
    try:
        if s.startswith("data:"):
            if "," not in s:
                return None
            b64_part = s.split(",", 1)[1].strip()
            raw_bytes = base64.b64decode(b64_part, validate=False)
        elif os.path.isfile(s):
            with open(s, "rb") as f_in:
                raw_bytes = f_in.read()
        else:
            raw_bytes = base64.b64decode(s, validate=False)
    except Exception:
        return None

    if not raw_bytes or len(raw_bytes) < 64:
        return None

    if Image is not None:
        try:
            with Image.open(io.BytesIO(raw_bytes)) as im:
                w, h = im.size
                if w < min_dim or h < min_dim:
                    return None
                rgb_im = im.convert("RGB")
                if max(w, h) > max_dim:
                    rgb_im.thumbnail((max_dim, max_dim))
                out_buf = io.BytesIO()
                rgb_im.save(out_buf, format="JPEG", quality=88, optimize=True)
                return out_buf.getvalue(), "image/jpeg"
        except Exception:
            return None

    # Fallback tanpa Pillow: periksa header JPEG/PNG minimal
    if raw_bytes[:3] == b"\xff\xd8\xff":
        return raw_bytes, "image/jpeg"
    if raw_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return raw_bytes, "image/png"
    return None


def save_uploaded_image_for_resend(
    img_bytes: bytes,
    ext: str = "jpg",
    base_dir: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """
    Menyimpan salinan gambar unggahan ke data/generated_files agar memiliki URL lokal (/api/artifacts/...?inline=1)
    sehingga AI dapat mengirim ulang gambar pengguna atau menautkannya di chat.
    """
    if not img_bytes:
        return None
    try:
        from shiro.agent.packager import GENERATED_ARTIFACTS_DIR
        target_root = base_dir or GENERATED_ARTIFACTS_DIR
        bundle_id = f"uimg_{uuid.uuid4().hex[:10]}"
        bundle_dir = os.path.abspath(os.path.join(target_root, bundle_id))
        os.makedirs(bundle_dir, exist_ok=True)
        clean_ext = ext.lower().lstrip(".") or "jpg"
        if clean_ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            clean_ext = "jpg"
        filename = f"uploaded_image.{clean_ext}"
        disk_path = os.path.join(bundle_dir, filename)
        with open(disk_path, "wb") as out_f:
            out_f.write(img_bytes)
        url = f"/api/artifacts/{bundle_id}/{filename}?inline=1"
        return {"id": bundle_id, "filename": filename, "url": url, "path": disk_path}
    except Exception:
        return None


def _fmt_timestamp(sec: Any) -> str:
    try:
        total = max(0, int(round(float(sec))))
        m, s = divmod(total, 60)
        return f"{m:02d}:{s:02d}"
    except Exception:
        return ""


def search_tracemoe(img_bytes: bytes, timeout: int = 10) -> List[Dict[str, Any]]:
    """Engine 1: trace.moe Anime Scene Search API (judul anime, episode, timestamp, & screenshot frame)."""
    if not img_bytes:
        return []
    results: List[Dict[str, Any]] = []
    sess = get_firefox_session(prefer_curl_cffi=False)
    if sess is None:
        return []
    headers = get_firefox_headers(referer="https://trace.moe/", accept="application/json, */*;q=0.8")
    headers["Content-Type"] = "image/jpeg"
    try:
        resp = sess.post(
            "https://api.trace.moe/search?anilistInfo&cutBorders",
            data=img_bytes,
            headers=headers,
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
        payload = resp.json() or {}
        for item in (payload.get("result") or [])[:5]:
            anilist = item.get("anilist") if isinstance(item.get("anilist"), dict) else {}
            titles = anilist.get("title") if isinstance(anilist.get("title"), dict) else {}
            title = str(
                titles.get("romaji")
                or titles.get("english")
                or titles.get("native")
                or item.get("filename")
                or "Anime Match"
            ).strip()
            alt_title = str(titles.get("english") or titles.get("native") or "").strip()
            if alt_title and alt_title.lower() != title.lower():
                display_title = f"{title} ({alt_title})"
            else:
                display_title = title
            sim_pct = round(float(item.get("similarity") or 0.0) * 100.0, 1)
            ep = item.get("episode")
            ts_from = _fmt_timestamp(item.get("from"))
            anilist_id = anilist.get("id")
            src_url = f"https://anilist.co/anime/{anilist_id}" if anilist_id else "https://trace.moe/"
            detail_bits = []
            if ep is not None:
                detail_bits.append(f"Episode {ep}")
            if ts_from:
                detail_bits.append(f"Timestamp {ts_from}")
            if anilist.get("isAdult"):
                detail_bits.append("18+")
            results.append({
                "engine": "trace.moe",
                "title": display_title,
                "raw_title": title,
                "similarity": sim_pct,
                "url": src_url,
                "image_url": str(item.get("image") or "").strip(),
                "details": " · ".join(detail_bits) if detail_bits else str(item.get("filename") or ""),
            })
    except Exception:
        return []
    return results


def _parse_google_lens_response(html_text: str, page_url: str = "https://lens.google.com/") -> List[Dict[str, Any]]:
    """Mengekstrak label entity, visual match, URL sumber, & thumbnail dari HTML/JSON Google Lens."""
    if not html_text:
        return []
    results: List[Dict[str, Any]] = []
    seen_keys = set()

    def _add(title: str, url: str = "", img: str = "", details: str = "", sim: Optional[float] = None):
        t = re.sub(r"\s+", " ", str(title or "")).strip()
        if not t or len(t) < 2 or t.lower() in ("google", "google lens", "sign in", "feedback", "search"):
            return
        u = str(url or "").strip()
        if u and not u.startswith(("http://", "https://")):
            u = urllib.parse.urljoin(page_url, u) if u.startswith("/") else ""
        key = (t.lower(), u.lower())
        if key in seen_keys:
            return
        seen_keys.add(key)
        results.append({
            "engine": "Google Lens",
            "title": t[:140],
            "raw_title": t[:140],
            "similarity": sim,
            "url": u or "https://lens.google.com/",
            "image_url": str(img or "").strip(),
            "details": details[:160],
        })

    if BeautifulSoup:
        soup = BeautifulSoup(html_text, "html.parser")
        for a in soup.select("a[href]"):
            href = str(a.get("href") or "").strip()
            if not href.startswith(("http://", "https://")) or "google.com" in href.lower() or "gstatic.com" in href.lower():
                continue
            title = a.get_text(" ", strip=True) or str(a.get("aria-label") or "").strip()
            img_el = a.find("img")
            img_src = ""
            if img_el:
                img_src = str(img_el.get("src") or img_el.get("data-src") or "").strip()
                if not title:
                    title = str(img_el.get("alt") or "").strip()
            if title and len(title) >= 3:
                _add(title, url=href, img=img_src, details="Google Lens visual match")
                if len(results) >= 6:
                    break

    # Ekstrak pola JSON AF_initDataCallback / visual match URL & title
    if len(results) < 5:
        for m in re.finditer(
            r'\["([^"\n\\]{3,120})","(https?://(?!www\.google\.|lens\.google\.|encrypted-tbn)[^"\s\\]+)"',
            html_text,
        ):
            cand_title, cand_url = m.group(1), m.group(2)
            _add(cand_title, url=cand_url, details="Google Lens matched source")
            if len(results) >= 6:
                break

    # Ekstrak label ringkasan entity/best guess jika tersedia
    for pat in (
        r'"([^"\n\\]{3,90})"\s*,\s*"(?:Anime|Manga|Television series|Character|Film|Video game|Person|Product|Artwork)"',
        r'aria-label="([^"\n]{4,100})"',
    ):
        for m in re.finditer(pat, html_text, re.IGNORECASE):
            lbl = m.group(1).strip()
            if any(skip in lbl.lower() for skip in ("close", "menu", "search by", "upload", "google", "crop")):
                continue
            _add(lbl, details="Google Lens entity label")
            if len(results) >= 7:
                break

    return results[:6]


def search_google_lens(img_bytes: bytes, timeout: int = 10) -> List[Dict[str, Any]]:
    """Engine 2: Google Lens visual upload search menggunakan Mozilla Firefox session."""
    if not img_bytes:
        return []
    sess = get_firefox_session(prefer_curl_cffi=True)
    if sess is None:
        return []
    headers = get_firefox_headers(referer="https://lens.google.com/")
    ts_ms = int(time.time() * 1000)
    upload_url = f"https://lens.google.com/v3/upload?hl=en&re=df&st={ts_ms}"
    try:
        resp = sess.post(
            upload_url,
            files={"encoded_image": ("image.jpg", img_bytes, "image/jpeg")},
            data={"image_content": ""},
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code == 200 and resp.text:
            parsed = _parse_google_lens_response(resp.text, page_url=str(getattr(resp, "url", upload_url)))
            if parsed:
                return parsed
    except Exception:
        pass
    return []


def _parse_yandex_cbir_response(raw_text: str) -> List[Dict[str, Any]]:
    """Mengekstrak CBIR tags, best guess, situs cocok, & thumbnail dari respons Yandex Visual Search."""
    if not raw_text:
        return []
    results: List[Dict[str, Any]] = []
    seen = set()

    def _add(title: str, url: str = "", img: str = "", details: str = ""):
        t = re.sub(r"\s+", " ", str(title or "")).strip()
        if not t or len(t) < 2:
            return
        k = (t.lower(), str(url or "").lower())
        if k in seen:
            return
        seen.add(k)
        results.append({
            "engine": "Yandex Visual",
            "title": t[:140],
            "raw_title": t[:140],
            "similarity": None,
            "url": url or "https://yandex.com/images/",
            "image_url": img,
            "details": details[:160],
        })

    # Coba parse JSON terlebih dahulu (jika format=json)
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            raw_dumps = json.dumps(data, ensure_ascii=False)
            raw_text = raw_dumps
    except Exception:
        pass

    # Ekstrak JSON state Yandex (tags / sites / similar)
    for m in re.finditer(r'"title"\s*:\s*"([^"\\]{3,120})"[^}]{0,220}"url"\s*:\s*"(https?://[^"\\]+)"', raw_text):
        t, u = m.group(1), m.group(2)
        if "yandex." in u.lower():
            continue
        _add(t, url=u, details="Yandex matched webpage")
        if len(results) >= 6:
            break

    # Ekstrak CBIR tags (kata kunci identifikasi objek/anime)
    for m in re.finditer(r'"text"\s*:\s*"([^"\\]{3,80})"[^}]{0,100}"(?:tag|cbir|query)"', raw_text, re.IGNORECASE):
        _add(m.group(1), details="Yandex visual tag")

    if BeautifulSoup and "<html" in raw_text.lower():
        soup = BeautifulSoup(raw_text, "html.parser")
        for tag_el in soup.select(".Tags-Item, .CbirTags-Item, .CbirObjectResponse-Title, .CbirSites-ItemTitle a"):
            txt = tag_el.get_text(" ", strip=True)
            href = tag_el.get("href") or ""
            _add(txt, url=href, details="Yandex visual recognition")
            if len(results) >= 6:
                break

    return results[:6]


def search_yandex_images(img_bytes: bytes, timeout: int = 10) -> List[Dict[str, Any]]:
    """Engine 3: Yandex Visual Search (CBIR) menggunakan Mozilla Firefox headers."""
    if not img_bytes:
        return []
    sess = get_firefox_session(prefer_curl_cffi=True)
    if sess is None:
        return []
    headers = get_firefox_headers(referer="https://yandex.com/images/")
    try:
        upload_url = (
            "https://yandex.com/images/search?rpt=imageview&format=json"
            "&request=%7B%22blocks%22%3A%5B%7B%22block%22%3A%22b-page_type_search-by-image__link%22%7D%5D%7D"
        )
        resp = sess.post(
            upload_url,
            files={"upfile": ("image.jpg", img_bytes, "image/jpeg")},
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code == 200 and resp.text:
            parsed = _parse_yandex_cbir_response(resp.text)
            if parsed:
                return parsed
            # Cek apakah JSON mengembalikan URL halaman hasil CBIR
            try:
                j = resp.json()
                cbir_path = ""
                for blk in (j.get("blocks") or []):
                    params = blk.get("params") or {}
                    if isinstance(params, dict) and params.get("url"):
                        cbir_path = str(params["url"])
                        break
                if cbir_path:
                    full_cbir = urllib.parse.urljoin("https://yandex.com/images/search", cbir_path)
                    r2 = sess.get(full_cbir, headers=headers, timeout=timeout, allow_redirects=True)
                    if r2.status_code == 200 and r2.text:
                        return _parse_yandex_cbir_response(r2.text)
            except Exception:
                pass
    except Exception:
        pass
    return []


def _parse_iqdb_html(html_text: str) -> List[Dict[str, Any]]:
    """Parser hasil HTML dari iqdb.org (tabel kecocokan anime/fanart)."""
    if not html_text or not BeautifulSoup:
        return []
    soup = BeautifulSoup(html_text, "html.parser")
    results: List[Dict[str, Any]] = []
    for tbl in soup.select("#pages div table"):
        th = tbl.find("th")
        header_txt = th.get_text(" ", strip=True) if th else ""
        if "Your image" in header_txt or "No relevant matches" in header_txt:
            continue
        full_txt = tbl.get_text(" ", strip=True)
        sim_m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%\s*similarity", full_txt, re.IGNORECASE)
        sim_val = float(sim_m.group(1)) if sim_m else None
        a_el = tbl.select_one("td.image a") or tbl.find("a", href=True)
        href = str(a_el.get("href") or "").strip() if a_el else ""
        if href.startswith("//"):
            href = "https:" + href
        img_el = tbl.find("img")
        thumb = str(img_el.get("src") or "").strip() if img_el else ""
        if thumb.startswith("/"):
            thumb = "https://iqdb.org" + thumb
        title = str(img_el.get("alt") or img_el.get("title") or "").strip() if img_el else ""
        if not title:
            title = header_txt or "IQDB Match"
        # Bersihkan prefix booru tags jika ada "Tags: ..."
        tags_m = re.search(r"Tags:\s*([^\n]+)", title)
        if tags_m:
            title = tags_m.group(1).strip()
        if href or sim_val:
            results.append({
                "engine": "IQDB",
                "title": title[:140],
                "raw_title": title[:140],
                "similarity": sim_val,
                "url": href or "https://iqdb.org/",
                "image_url": thumb,
                "details": f"{header_txt} · {sim_val}% similarity" if sim_val is not None else header_txt,
            })
        if len(results) >= 5:
            break
    return results


def search_iqdb(img_bytes: bytes, timeout: int = 10) -> List[Dict[str, Any]]:
    """Engine 4: IQDB reverse image search untuk ilustrasi/anime menggunakan Mozilla Firefox headers."""
    if not img_bytes:
        return []
    sess = get_firefox_session(prefer_curl_cffi=False)
    if sess is None:
        return []
    headers = get_firefox_headers(referer="https://iqdb.org/")
    try:
        resp = sess.post(
            "https://iqdb.org/",
            files={"file": ("image.jpg", img_bytes, "image/jpeg")},
            headers=headers,
            timeout=timeout,
        )
        if resp.status_code == 200 and resp.text:
            return _parse_iqdb_html(resp.text)
    except Exception:
        pass
    return []


def search_saucenao(img_bytes: bytes, timeout: int = 10) -> List[Dict[str, Any]]:
    """Engine 5: SauceNAO JSON reverse image search untuk anime, manga, dan ilustrasi."""
    if not img_bytes:
        return []
    sess = get_firefox_session(prefer_curl_cffi=False)
    if sess is None:
        return []
    headers = get_firefox_headers(referer="https://saucenao.com/", accept="application/json, text/plain, */*")
    params = {"output_type": "2", "numres": "5"}
    api_key = (os.environ.get("SAUCENAO_API_KEY") or "").strip()
    if api_key:
        params["api_key"] = api_key
    try:
        resp = sess.post(
            "https://saucenao.com/search.php",
            params=params,
            files={"file": ("image.jpg", img_bytes, "image/jpeg")},
            headers=headers,
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
        payload = resp.json() or {}
        results: List[Dict[str, Any]] = []
        for item in (payload.get("results") or [])[:5]:
            hdr = item.get("header") or {}
            dat = item.get("data") or {}
            try:
                sim_val = round(float(hdr.get("similarity") or 0.0), 1)
            except Exception:
                sim_val = 0.0
            title = str(
                dat.get("source")
                or dat.get("title")
                or dat.get("material")
                or dat.get("jp_name")
                or dat.get("eng_name")
                or hdr.get("index_name")
                or "SauceNAO Match"
            ).strip()
            chars = str(dat.get("characters") or "").strip()
            part = str(dat.get("part") or "").strip()
            ext_urls = dat.get("ext_urls") or []
            src_url = str(ext_urls[0]).strip() if ext_urls else "https://saucenao.com/"
            details_parts = []
            if chars:
                details_parts.append(f"Karakter: {chars}")
            if part:
                details_parts.append(f"Ep/Part: {part}")
            if dat.get("author_name") or dat.get("creator"):
                details_parts.append(f"Kreator: {dat.get('author_name') or dat.get('creator')}")
            results.append({
                "engine": "SauceNAO",
                "title": title[:140],
                "raw_title": title[:140],
                "similarity": sim_val,
                "url": src_url,
                "image_url": str(hdr.get("thumbnail") or "").strip(),
                "details": " · ".join(details_parts) or str(hdr.get("index_name") or ""),
            })
        return results
    except Exception:
        return []


def _parse_bing_visual_html(html_text: str) -> List[Dict[str, Any]]:
    """Parser respons HTML/JSON dari Bing Visual Search."""
    if not html_text:
        return []
    results: List[Dict[str, Any]] = []
    seen = set()

    def _add(title: str, url: str = "", img: str = "", details: str = ""):
        t = re.sub(r"\s+", " ", str(title or "")).strip()
        if not t or len(t) < 2:
            return
        k = (t.lower(), str(url or "").lower())
        if k in seen:
            return
        seen.add(k)
        results.append({
            "engine": "Bing Visual",
            "title": t[:140],
            "raw_title": t[:140],
            "similarity": None,
            "url": url or "https://www.bing.com/visualsearch",
            "image_url": img,
            "details": details[:160],
        })

    for m in re.finditer(
        r'"name"\s*:\s*"([^"\\]{3,120})"[^}]{0,220}"hostPageUrl"\s*:\s*"(https?://[^"\\]+)"(?:[^}]{0,200}"thumbnailUrl"\s*:\s*"(https?://[^"\\]+)")?',
        html_text,
    ):
        _add(m.group(1), url=m.group(2), img=m.group(3) or "", details="Bing visual match")
        if len(results) >= 5:
            break

    if BeautifulSoup and len(results) < 5:
        soup = BeautifulSoup(html_text, "html.parser")
        for a in soup.select("a.richImgLnk, a.iusc, .b_entityTitle a, a[data-hosturl]"):
            title = str(a.get("aria-label") or a.get_text(" ", strip=True) or "").strip()
            href = str(a.get("data-hosturl") or a.get("href") or "").strip()
            if href.startswith("/"):
                href = urllib.parse.urljoin("https://www.bing.com", href)
            img_el = a.find("img")
            img_src = str(img_el.get("src") or img_el.get("data-src") or "").strip() if img_el else ""
            _add(title, url=href, img=img_src, details="Bing visual match")
            if len(results) >= 5:
                break

    return results[:5]


def search_bing_visual(img_bytes: bytes, timeout: int = 10) -> List[Dict[str, Any]]:
    """Engine 6: Bing Visual Search menggunakan Mozilla Firefox session."""
    if not img_bytes:
        return []
    sess = get_firefox_session(prefer_curl_cffi=True)
    if sess is None:
        return []
    headers = get_firefox_headers(referer="https://www.bing.com/visualsearch")
    try:
        b64_img = base64.b64encode(img_bytes).decode("ascii")
        resp = sess.post(
            "https://www.bing.com/images/detail/search?iss=sbiupload&FORM=ANCMS1&sbifsz=1&sbifnm=image.jpg&thw=200&thh=200",
            data={"imageBin": b64_img},
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code == 200 and resp.text:
            return _parse_bing_visual_html(resp.text)
    except Exception:
        pass
    return []


def _normalize_title_key(title: str) -> str:
    s = re.sub(r"\([^)]*\)", " ", str(title or "").lower())
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return " ".join(s.split()[:4])


def run_multi_engine_reverse_image_search(
    images: List[str],
    user_query: str = "",
    max_candidates: int = 15,
    timeout: int = 10,
    include_web_verify: bool = True,
) -> Dict[str, Any]:
    """
    Menjalankan seluruh 6 engine Reverse Image Search (Google Lens, trace.moe, Yandex, IQDB, SauceNAO, Bing)
    secara paralel dan menyusun laporan kandidat + aturan anti-halusinasi ketat untuk AI Agent.
    """
    empty_res: Dict[str, Any] = {
        "success": False,
        "engines_tried": 0,
        "engines_succeeded": 0,
        "candidates": [],
        "sources": [],
        "matched_images": [],
        "uploaded_image_url": None,
        "steps": [],
        "prompt_context": "",
        "summary": "Tidak ada gambar valid untuk dianalisis engine.",
    }
    if not images:
        return empty_res

    prepared = None
    for im_src in images:
        prepared = _decode_and_prepare_image(im_src)
        if prepared is not None:
            break
    if prepared is None:
        return empty_res

    img_bytes, mime_type = prepared
    ext = "png" if "png" in mime_type else "jpg"
    saved_local = save_uploaded_image_for_resend(img_bytes, ext=ext)
    uploaded_image_url = saved_local["url"] if saved_local else None

    engines = [
        ("Google Lens", search_google_lens),
        ("trace.moe", search_tracemoe),
        ("Yandex Visual", search_yandex_images),
        ("IQDB", search_iqdb),
        ("SauceNAO", search_saucenao),
        ("Bing Visual", search_bing_visual),
    ]

    results_by_engine: Dict[str, List[Dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=len(engines)) as pool:
        future_map = {pool.submit(fn, img_bytes, timeout): eng_name for eng_name, fn in engines}
        for fut in as_completed(future_map):
            eng_name = future_map[fut]
            try:
                eng_rows = fut.result() or []
            except Exception:
                eng_rows = []
            results_by_engine[eng_name] = list(eng_rows)

    all_candidates: List[Dict[str, Any]] = []
    title_engine_votes: Dict[str, set] = {}
    engines_succeeded = 0

    for eng_name, _ in engines:
        rows = results_by_engine.get(eng_name) or []
        if rows:
            engines_succeeded += 1
        for row in rows:
            t_key = _normalize_title_key(row.get("raw_title") or row.get("title") or "")
            if t_key:
                title_engine_votes.setdefault(t_key, set()).add(eng_name)
            all_candidates.append(dict(row))

    # Hitung consensus score agar kandidat yang disepakati banyak engine dan bersimilarity tinggi naik ke atas
    for cand in all_candidates:
        t_key = _normalize_title_key(cand.get("raw_title") or cand.get("title") or "")
        vote_cnt = len(title_engine_votes.get(t_key, set())) if t_key else 1
        sim = cand.get("similarity")
        base_score = float(sim) if isinstance(sim, (int, float)) else 52.0
        consensus_score = base_score + (max(0, vote_cnt - 1) * 18.0)
        cand["engine_votes"] = vote_cnt
        cand["consensus_score"] = round(consensus_score, 1)

    all_candidates.sort(key=lambda c: c.get("consensus_score", 0.0), reverse=True)
    top_candidates = all_candidates[:max_candidates]

    sources: List[Dict[str, str]] = []
    matched_images: List[Dict[str, str]] = []
    seen_src = set()
    seen_img = set()

    for cand in top_candidates:
        u = str(cand.get("url") or "").strip()
        if u.startswith(("http://", "https://")) and u not in seen_src:
            seen_src.add(u)
            sources.append({
                "title": f"[{cand['engine']}] {cand['title']}"[:120],
                "url": u,
                "domain": cand["engine"],
                "snippet": cand.get("details") or "",
            })
        iu = str(cand.get("image_url") or "").strip()
        if iu.startswith(("http://", "https://")) and iu not in seen_img:
            seen_img.add(iu)
            matched_images.append({
                "url": iu,
                "title": f"[{cand['engine']}] {cand['title']}"[:100],
                "source_url": u,
                "source": cand["engine"],
            })

    # Verifikasi silang teks web untuk kandidat terkuat agar info lengkap & bebas karangan
    web_verify_summary = ""
    top_confident = [
        c for c in top_candidates
        if (c.get("similarity") is not None and float(c["similarity"]) >= 75.0) or c.get("engine_votes", 1) >= 2
    ]
    if include_web_verify and top_candidates and (top_confident or top_candidates[0].get("raw_title")):
        verify_q = str((top_confident[0] if top_confident else top_candidates[0]).get("raw_title") or top_candidates[0]["title"]).strip()
        if len(verify_q) >= 3:
            try:
                from shiro.agent.tools import search_google_web
                w_res = search_google_web(verify_q, max_results=3, include_images=True)
                if w_res.get("success"):
                    web_verify_summary = str(w_res.get("summary") or "")[:1500]
                    for wr in (w_res.get("results") or [])[:3]:
                        wu = str(wr.get("url") or "").strip()
                        if wu.startswith(("http://", "https://")) and wu not in seen_src:
                            seen_src.add(wu)
                            sources.append({
                                "title": str(wr.get("title") or verify_q)[:120],
                                "url": wu,
                                "domain": str(wr.get("source") or "Web Verify"),
                                "snippet": str(wr.get("snippet") or "")[:180],
                            })
                    for wi in (w_res.get("images") or [])[:3]:
                        wiu = str(wi.get("url") or "").strip()
                        if wiu.startswith(("http://", "https://")) and wiu not in seen_img:
                            seen_img.add(wiu)
                            matched_images.append(wi)
            except Exception:
                pass

    # Bangun prompt_context ketat anti-halusinasi dengan SEMUA kandidat lintas engine
    lines: List[str] = [
        "[HASIL REVERSE IMAGE SEARCH MULTI-ENGINE REAL-TIME (Mozilla Firefox Pipeline)]:",
        f"- Engine yang dijalankan: {', '.join(name for name, _ in engines)} ({engines_succeeded}/{len(engines)} mengembalikan kandidat).",
    ]
    if uploaded_image_url:
        lines.append(
            f"- Salinan URL gambar unggahan pengguna (untuk dikirim ulang jika diminta): `{uploaded_image_url}`"
        )

    if top_candidates:
        lines.append("\nKandidat kecocokan dari seluruh engine (peringkat gabungan konsensus & kemiripan):")
        for idx, cand in enumerate(top_candidates, 1):
            sim_lbl = f" | Kemiripan: {cand['similarity']}%" if cand.get("similarity") is not None else ""
            votes_lbl = f" | Sepakat {cand['engine_votes']} engine" if cand.get("engine_votes", 1) > 1 else ""
            det_lbl = f" | Info: {cand['details']}" if cand.get("details") else ""
            img_lbl = f" | Gambar: {cand['image_url']}" if cand.get("image_url") else ""
            lines.append(
                f"{idx}. [{cand['engine']}] **{cand['title']}**{sim_lbl}{votes_lbl}{det_lbl}\n"
                f"   Sumber: {cand['url']}{img_lbl}"
            )
    else:
        lines.append(
            "\n- PERHATIAN: Keenam engine Reverse Image Search (Google Lens, trace.moe, Yandex, IQDB, SauceNAO, Bing) "
            "TIDAK menemukan kecocokan terverifikasi atau koneksi eksternal sedang terbatas."
        )

    if web_verify_summary:
        lines.append(f"\n[Verifikasi Silang Web untuk Kandidat Teratas]:\n{web_verify_summary}")

    if matched_images:
        lines.append("\nGambar referensi/kecocokan yang dapat kamu tampilkan/kirim di chat via `![Keterangan](url)` atau `[[AGENT_TOOL:send_image|url=...|caption=...]]`:")
        for m_im in matched_images[:6]:
            lines.append(f"- ![{m_im['title']}]({m_im['url']})")

    lines.append(
        "\n[ATURAN MUTLAK ANTI-HALUSINASI & PENGIRIMAN GAMBAR]:\n"
        "1. Bandingkan langsung pengamatan visualmu pada gambar dengan SEMUA kandidat dari Google Lens, trace.moe, Yandex, IQDB, SauceNAO, dan Bing di atas.\n"
        "2. Jika satu atau lebih kandidat JELAS cocok secara visual (misalnya kemiripan tinggi >= 80% atau cocok karakter/seragam/adegan), pilih kandidat yang BENAR-BENAR cocok dan jelaskan alasannya beserta sumber/episode jika ada.\n"
        "3. DILARANG KERAS mengarang atau menebak judul anime/film/tokoh/produk lain di luar bukti visual & kandidat! Jika semua engine nihil atau tidak ada kandidat yang cocok secara meyakinkan, JAWAB JUJUR bahwa identifikasi pasti belum dapat dipastikan tanpa mengarang judul fiktif, sambil menyebutkan detail visual nyata atau kandidat terdekat bila ada.\n"
        "4. Bila pengguna meminta gambar referensi atau mengirim ulang gambar, kamu DAPAT menyisipkan gambar Markdown `![Keterangan](url)` atau memanggil `[[AGENT_TOOL:send_image|url=...|caption=...]]`."
    )

    eng_counts_txt = ", ".join(f"{n}:{len(results_by_engine.get(n) or [])}" for n, _ in engines)
    steps = [
        {
            "id": "reverse_image_search",
            "title": "Reverse Image Search (6 Engines: Google Lens, trace.moe, Yandex, IQDB, SauceNAO, Bing)",
            "status": "done",
            "feedback": f"Checked 6 engines ({eng_counts_txt}); collected {len(top_candidates)} candidate(s) & {len(matched_images)} image(s).",
        }
    ]
    if web_verify_summary:
        steps.append({
            "id": "reverse_image_verify",
            "title": "Cross-Verify Top Visual Match via Web",
            "status": "done",
            "feedback": f"Verified candidate details & {len(sources)} source(s) to prevent hallucination.",
        })

    return {
        "success": bool(top_candidates),
        "engines_tried": len(engines),
        "engines_succeeded": engines_succeeded,
        "candidates": top_candidates,
        "sources": sources[:10],
        "matched_images": matched_images[:8],
        "uploaded_image_url": uploaded_image_url,
        "steps": steps,
        "prompt_context": "\n".join(lines),
        "summary": (
            f"Multi-engine reverse image search ({engines_succeeded}/6 engines): "
            f"{len(top_candidates)} candidate(s), {len(matched_images)} image(s)."
        ),
    }
