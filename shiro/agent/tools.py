# -*- coding: utf-8 -*-
"""
Shiro AI Agent Tools
Autonomous tool collection for web searching, weather observation,
webpage browsing, mathematical computation, and real-time world state inquiry.
All requests are routed using Cloudflare 1.1.1.1 and authentic Mozilla headers.
"""

import re
import os
import time
import subprocess
import shutil
import platform
import math
import json
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from shiro.agent.network import (
    MOZILLA_HEADERS,
    get_agent_session,
    fetch_html_content,
    resolve_dns_cloudflare
)

# WMO Weather interpretation code table
WMO_WEATHER_CODES = {
    0: "Cerah (Clear sky)",
    1: "Cerah Berawan (Mainly clear)",
    2: "Sebagian Berawan (Partly cloudy)",
    3: "Mendung / Berawan Tebal (Overcast)",
    45: "Berkabut (Fog)",
    48: "Kabut Rime (Depositing rime fog)",
    51: "Gerimis Ringan (Light drizzle)",
    53: "Gerimis Sedang (Moderate drizzle)",
    55: "Gerimis Lebat (Dense drizzle)",
    61: "Hujan Ringan (Slight rain)",
    63: "Hujan Sedang (Moderate rain)",
    65: "Hujan Lebat (Heavy rain)",
    71: "Salju Ringan (Slight snow)",
    73: "Salju Sedang (Moderate snow)",
    75: "Salju Lebat (Heavy snow)",
    77: "Butiran Salju (Snow grains)",
    80: "Hujan Rintik-Rintik (Slight rain showers)",
    81: "Hujan Deras Lokal (Moderate rain showers)",
    82: "Hujan Sangat Lebat (Violent rain showers)",
    85: "Hujan Salju Ringan (Slight snow showers)",
    86: "Hujan Salju Lebat (Heavy snow showers)",
    95: "Badai Petir (Thunderstorm)",
    96: "Badai Petir disertai Es Ringan (Thunderstorm with slight hail)",
    99: "Badai Petir disertai Es Lebat (Thunderstorm with heavy hail)"
}

# Known coordinates for fast fallback
COMMON_COORDINATES = {
    "tokyo": (35.6895, 139.6917, "Asia/Tokyo", "Tokyo, Jepang"),
    "jakarta": (-6.2146, 106.8451, "Asia/Jakarta", "Jakarta, Indonesia"),
    "bandung": (-6.9175, 107.6191, "Asia/Jakarta", "Bandung, Indonesia"),
    "surabaya": (-7.2575, 112.7521, "Asia/Jakarta", "Surabaya, Indonesia"),
    "yogyakarta": (-7.7956, 110.3695, "Asia/Jakarta", "Yogyakarta, Indonesia"),
    "medan": (3.5952, 98.6722, "Asia/Jakarta", "Medan, Indonesia"),
    "semarang": (-7.0051, 110.4381, "Asia/Jakarta", "Semarang, Indonesia"),
    "bali": (-8.4095, 115.1889, "Asia/Makassar", "Bali, Indonesia"),
    "denpasar": (-8.6705, 115.2126, "Asia/Makassar", "Denpasar, Bali, Indonesia"),
    "kyoto": (35.0116, 135.7681, "Asia/Tokyo", "Kyoto, Jepang"),
    "osaka": (34.6937, 135.5023, "Asia/Tokyo", "Osaka, Jepang"),
    "seoul": (37.5665, 126.9780, "Asia/Seoul", "Seoul, Korea Selatan"),
    "singapore": (1.3521, 103.8198, "Asia/Singapore", "Singapura"),
    "london": (51.5074, -0.1278, "Europe/London", "London, Inggris"),
    "new york": (40.7128, -74.0060, "America/New_York", "New York, USA"),
    "paris": (48.8566, 2.3522, "Europe/Paris", "Paris, Prancis"),
    "sydney": (-33.8688, 151.2093, "Australia/Sydney", "Sydney, Australia"),
}

def geocode_city(city_name: str) -> Optional[Dict[str, Any]]:
    """Mencari koordinat kota via Open-Meteo Geocoding API atau fallback koordinat lokal"""
    c_clean = city_name.strip().lower()
    if c_clean in COMMON_COORDINATES:
        lat, lon, tz, full_name = COMMON_COORDINATES[c_clean]
        return {
            "name": full_name,
            "latitude": lat,
            "longitude": lon,
            "timezone": tz
        }

    # Query geocoding API
    try:
        session = get_agent_session()
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city_name)}&count=1&language=id&format=json"
        resp = session.get(geo_url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                r = results[0]
                country = r.get("country", "")
                name = r.get("name", city_name)
                full = f"{name}, {country}" if country else name
                return {
                    "name": full,
                    "latitude": r.get("latitude"),
                    "longitude": r.get("longitude"),
                    "timezone": r.get("timezone", "auto")
                }
    except Exception:
        pass
        
    return None

def check_weather(locations: List[str]) -> Dict[str, Any]:
    """
    Mengambil data cuaca real-time (suhu, hujan, kelembaban, kondisi)
    untuk satu atau banyak kota secara langsung melalui Open-Meteo & Cloudflare 1.1.1.1.
    """
    if not locations:
        locations = ["Jakarta"]

    report_items = []
    structured_data = []

    session = get_agent_session()

    for loc in locations:
        loc_str = loc.strip()
        geo = geocode_city(loc_str)
        if not geo:
            report_items.append(f"- **{loc_str}**: Lokasi tidak ditemukan dalam database geocoding.")
            continue

        lat = geo["latitude"]
        lon = geo["longitude"]
        tz = geo["timezone"]
        full_loc = geo["name"]

        try:
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}&"
                f"current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code&"
                f"timezone={tz}"
            )
            resp = session.get(weather_url, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current", {})
                temp = current.get("temperature_2m", 0.0)
                feels_like = current.get("apparent_temperature", temp)
                humidity = current.get("relative_humidity_2m", 0)
                rain = current.get("rain", 0.0)
                precip = current.get("precipitation", 0.0)
                wcode = current.get("weather_code", 0)
                condition_desc = WMO_WEATHER_CODES.get(wcode, "Normal")

                is_raining = (rain > 0.0 or precip > 0.0 or wcode in [51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99])
                rain_text = f"🌧️ Hujan ({rain or precip} mm)" if is_raining else "☀️ Tidak hujan (0.0 mm)"

                item_summary = (
                    f"- **{full_loc}**:\n"
                    f"  • Suhu: **{temp}°C** (Terasa seperti: {feels_like}°C)\n"
                    f"  • Kondisi: **{condition_desc}**\n"
                    f"  • Status Hujan: **{rain_text}**\n"
                    f"  • Kelembaban Udara: **{humidity}%**\n"
                    f"  • Waktu Lokal: {current.get('time', 'Sekarang')}"
                )
                report_items.append(item_summary)
                structured_data.append({
                    "location": full_loc,
                    "temperature": temp,
                    "feels_like": feels_like,
                    "condition": condition_desc,
                    "is_raining": is_raining,
                    "rain_mm": rain or precip,
                    "humidity": humidity
                })
            else:
                report_items.append(f"- **{full_loc}**: Gagal mengambil data cuaca (HTTP {resp.status_code}).")
        except Exception as e:
            report_items.append(f"- **{full_loc}**: Kendala jaringan saat mengakses satelit cuaca: {e}")

    summary_text = "\n".join(report_items)
    return {
        "success": bool(structured_data),
        "summary": summary_text,
        "data": structured_data
    }

def search_web_images(query: str, max_images: int = 4) -> List[Dict[str, str]]:
    """
    Mencari URL gambar yang relevan di web (Bing Images dengan fallback Wikimedia Commons)
    untuk disajikan sebagai referensi visual atau disematkan dalam jawaban AI Agent.
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    images: List[Dict[str, str]] = []
    seen_urls = set()
    session = get_agent_session()

    def _is_valid_img_url(u: str) -> bool:
        if not u or not isinstance(u, str):
            return False
        lu = u.strip().lower()
        if not (lu.startswith("http://") or lu.startswith("https://")):
            return False
        if any(bad in lu for bad in ("bing.net/th?id=oip", "data:image", ".svg", "favicon", "logo-small", "1x1.")):
            # Bing th?id=OIP sebenarnya thumbnail valid, hanya hindari data:image & icon/1x1
            if "bing.net/th?id=oip" not in lu:
                return False
        return True

    # 1. Bing Images HTML (iusc JSON metadata -> murl/purl/t)
    try:
        img_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(clean_q)}&form=HDRSC2&first=1"
        resp = session.get(img_url, timeout=5)
        if resp.status_code == 200 and BeautifulSoup:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a_el in soup.select("a.iusc"):
                m_raw = a_el.get("m")
                if not m_raw:
                    continue
                try:
                    meta = json.loads(m_raw)
                except Exception:
                    continue
                murl = str(meta.get("murl") or meta.get("turl") or "").strip()
                purl = str(meta.get("purl") or "").strip()
                title = str(meta.get("t") or clean_q).strip()
                if _is_valid_img_url(murl) and murl not in seen_urls:
                    seen_urls.add(murl)
                    images.append({
                        "url": murl,
                        "title": title[:120] or clean_q,
                        "source_url": purl,
                        "source": "Bing Images",
                    })
                    if len(images) >= max_images:
                        return images
    except Exception:
        pass

    # 2. Fallback Wikimedia Commons API (open web image metadata)
    if len(images) < max_images:
        try:
            wm_url = (
                "https://commons.wikimedia.org/w/api.php?action=query&generator=search"
                f"&gsrsearch={urllib.parse.quote(clean_q)}&gsrnamespace=6&gsrlimit={max_images}"
                "&prop=imageinfo&iiprop=url|mime&format=json"
            )
            r_wm = session.get(wm_url, timeout=5)
            if r_wm.status_code == 200:
                pages = (r_wm.json().get("query") or {}).get("pages") or {}
                for page in pages.values():
                    infos = page.get("imageinfo") or []
                    if not infos:
                        continue
                    i0 = infos[0]
                    mime = str(i0.get("mime") or "").lower()
                    u = str(i0.get("url") or "").strip()
                    if mime.startswith("image/") and "svg" not in mime and _is_valid_img_url(u) and u not in seen_urls:
                        seen_urls.add(u)
                        images.append({
                            "url": u,
                            "title": str(page.get("title") or clean_q).replace("File:", "").strip()[:120],
                            "source_url": str(i0.get("descriptionurl") or u),
                            "source": "Wikimedia Commons",
                        })
                        if len(images) >= max_images:
                            break
        except Exception:
            pass

    return images


def search_google_web(query: str, max_results: int = 6, include_images: bool = True) -> Dict[str, Any]:
    """
    Melakukan pencarian web & browser komprehensif menggunakan Bing HTML, DuckDuckGo HTML,
    Google News RSS, Wikipedia, serta pencarian gambar web melalui header Mozilla dan Cloudflare 1.1.1.1.
    """
    clean_q = query.strip()
    if not clean_q:
        return {"success": False, "summary": "Query pencarian kosong", "results": [], "images": []}

    results = []
    session = get_agent_session()

    # 1. Bing HTML Search
    try:
        bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(clean_q)}&setlang=id-id&cc=ID"
        resp = session.get(bing_url, timeout=7)
        if resp.status_code == 200 and BeautifulSoup:
            soup = BeautifulSoup(resp.text, "html.parser")
            algo_items = soup.select("li.b_algo")
            for item in algo_items[:max_results]:
                title_elem = item.select_one("h2 a")
                snippet_elem = item.select_one(".b_caption p, .b_algoSlug, p")
                if title_elem:
                    title = title_elem.text.strip()
                    link = title_elem.get("href", "")
                    snippet = snippet_elem.text.strip() if snippet_elem else ""
                    if title and link and not any(bad in link.lower() for bad in ["scholar.google", "pinkbike"]):
                        results.append({
                            "title": title,
                            "url": link,
                            "snippet": snippet,
                            "source": "Bing Search"
                        })
    except Exception:
        pass

    # 1b. DuckDuckGo HTML fallback jika Bing memberi sedikit hasil
    if len(results) < 2:
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_q)}"
            resp_ddg = session.get(ddg_url, timeout=6)
            if resp_ddg.status_code == 200 and BeautifulSoup:
                soup_ddg = BeautifulSoup(resp_ddg.text, "html.parser")
                for res_el in soup_ddg.select(".result"):
                    if len(results) >= max_results:
                        break
                    a_el = res_el.select_one("a.result__a")
                    sn_el = res_el.select_one(".result__snippet")
                    if not a_el:
                        continue
                    title = a_el.get_text(" ", strip=True)
                    raw_href = a_el.get("href", "")
                    if "uddg=" in raw_href:
                        qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                        raw_href = (qs.get("uddg") or [raw_href])[0]
                    snippet = sn_el.get_text(" ", strip=True) if sn_el else ""
                    if title and raw_href.startswith("http") and not any(r["url"] == raw_href for r in results):
                        results.append({
                            "title": title,
                            "url": raw_href,
                            "snippet": snippet,
                            "source": "DuckDuckGo"
                        })
        except Exception:
            pass

    # 2. Google News RSS Search untuk informasi real-time dan jadwal rilis
    try:
        news_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(clean_q)}&hl=id&gl=ID&ceid=ID:id"
        resp_news = session.get(news_url, timeout=6)
        if resp_news.status_code == 200 and BeautifulSoup:
            soup_news = BeautifulSoup(resp_news.text, "xml")
            items = soup_news.find_all("item")
            for it in items:
                if len(results) >= (max_results * 2):
                    break
                t = it.title.text.strip() if it.title else ""
                l = it.link.text.strip() if it.link else ""
                pub = it.pubDate.text.strip() if it.pubDate else ""
                if t and l and not any(r["url"] == l for r in results):
                    results.append({
                        "title": t,
                        "url": l,
                        "snippet": f"Publikasi: {pub}",
                        "source": "Google News"
                    })
    except Exception:
        pass

    # 3. Wikipedia API Search sebagai fallback fakta ensiklopedis
    if not results:
        try:
            wiki_url = f"https://id.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_q)}&utf8=1&format=json&srlimit={max_results}"
            r_wiki = session.get(wiki_url, timeout=6)
            if r_wiki.status_code == 200:
                wiki_data = r_wiki.json()
                for item in wiki_data.get("query", {}).get("search", []):
                    title = item.get("title", "")
                    raw_snip = item.get("snippet", "")
                    clean_snip = re.sub(r'<[^>]+>', '', raw_snip).strip()
                    page_url = f"https://id.wikipedia.org/wiki/{urllib.parse.quote(title)}"
                    results.append({
                        "title": title,
                        "url": page_url,
                        "snippet": clean_snip,
                        "source": "Wikipedia"
                    })
        except Exception:
            pass

    images: List[Dict[str, str]] = []
    if include_images:
        try:
            images = search_web_images(clean_q, max_images=4)
        except Exception:
            images = []

    # Format ringkasan hasil
    if results or images:
        lines = [f"Ditemukan {len(results)} sumber web untuk: '{clean_q}':"]
        for i, res in enumerate(results, 1):
            lines.append(f"{i}. [{res['title']}]({res['url']}) ({res['source']})")
            if res['snippet']:
                lines.append(f"   {res['snippet']}")
        if images:
            lines.append("\nGambar terkait dari web:")
            for im in images[:4]:
                lines.append(f"- ![{im['title']}]({im['url']})")
        summary_text = "\n".join(lines)
        return {
            "success": True,
            "summary": summary_text,
            "results": results,
            "images": images,
        }
    else:
        return {
            "success": False,
            "summary": f"Pencarian web untuk '{clean_q}' tidak menghasilkan data relevan.",
            "results": [],
            "images": [],
        }

def open_and_read_webpage(url: str, max_chars: int = 3500) -> Dict[str, Any]:
    """
    Membuka halaman web dan mengekstrak teks bersih beserta gambar relevan
    menggunakan header Mozilla, BeautifulSoup, serta fallback browser headless bila halaman JS-rendered.
    """
    ok, html, err = fetch_html_content(url, timeout=12)
    if (not ok or not html or len(html) < 250):
        # Fallback opsional menggunakan browser headless jika terpasang untuk halaman JS-rendered
        browser_bin = find_available_browser()
        if browser_bin:
            try:
                res_dom = subprocess.run(
                    [browser_bin, "--headless", "--disable-gpu", "--no-sandbox", "--dump-dom", url],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if res_dom.returncode == 0 and res_dom.stdout and len(res_dom.stdout) > len(html or ""):
                    html = res_dom.stdout
                    ok = True
            except Exception:
                pass

    if not ok or not html:
        return {
            "success": False,
            "url": url,
            "title": "Gagal Membuka",
            "content": f"Tidak dapat memuat halaman ({err or 'Koneksi gagal'}).",
            "images": [],
        }

    title = "Halaman Web"
    content = ""
    page_images: List[Dict[str, str]] = []
    seen_imgs = set()

    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Ekstrak og:image / twitter:image & img relevan sebelum elemen noise dihapus
        for meta_prop in [("meta", {"property": "og:image"}), ("meta", {"name": "twitter:image"})]:
            m_tag = soup.find(meta_prop[0], meta_prop[1])
            if m_tag and m_tag.get("content"):
                abs_u = urllib.parse.urljoin(url, str(m_tag.get("content")).strip())
                if abs_u.startswith(("http://", "https://")) and abs_u not in seen_imgs:
                    seen_imgs.add(abs_u)
                    page_images.append({"url": abs_u, "title": title[:100], "source_url": url})

        for img_tag in soup.select("article img, main img, img"):
            if len(page_images) >= 4:
                break
            src = (img_tag.get("src") or img_tag.get("data-src") or "").strip()
            if not src or src.startswith("data:") or any(bad in src.lower() for bad in ("icon", "avatar", "sprite", "logo", ".svg")):
                continue
            abs_u = urllib.parse.urljoin(url, src)
            if abs_u.startswith(("http://", "https://")) and abs_u not in seen_imgs:
                seen_imgs.add(abs_u)
                alt_txt = str(img_tag.get("alt") or title or "Web Image").strip()[:100]
                page_images.append({"url": abs_u, "title": alt_txt, "source_url": url})

        # Hilangkan elemen noise
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "svg", "noscript", "form", "button"]):
            tag.decompose()

        # Pilih elemen artikel utama
        main_elem = soup.select_one("article, main, [role='main'], #content, .content, .post-content")
        target = main_elem if main_elem else (soup.body if soup.body else soup)
        content = " ".join(target.stripped_strings)
    else:
        # Fallback regex
        title_m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if title_m:
            title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
        cleaned = re.sub(r'<(script|style|nav|footer|header)[^>]*>.*?</\1>', '', html, flags=re.IGNORECASE | re.DOTALL)
        content = " ".join(re.sub(r'<[^>]+>', ' ', cleaned).split())

    content = re.sub(r'\s+', ' ', content).strip()
    if len(content) > max_chars:
        content = content[:max_chars] + " ... (konten dipotong untuk batas memori context)"

    return {
        "success": True,
        "url": url,
        "title": title,
        "content": content,
        "images": page_images,
    }

def calculate_math(expression: str) -> Dict[str, Any]:
    """Mengevaluasi ekspresi matematika sederhana secara aman"""
    clean_expr = expression.strip().lower()
    # Ganti operator umum
    clean_expr = clean_expr.replace("x", "*").replace(":", "/").replace("^", "**")
    # Hanya izinkan karakter numerik dan simbol math dasar
    if not re.match(r'^[0-9+\-*/().\s*^%]+$', clean_expr):
        return {
            "success": False,
            "expression": expression,
            "result": None,
            "error": "Ekspresi mengandung karakter tidak aman."
        }

    try:
        allowed_names = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "pi": math.pi}
        res = eval(clean_expr, {"__builtins__": None}, allowed_names)
        return {
            "success": True,
            "expression": expression,
            "result": res,
            "summary": f"Hasil hitungan `{expression}` = **{res}**"
        }
    except Exception as e:
        return {
            "success": False,
            "expression": expression,
            "result": None,
            "error": str(e)
        }

def get_current_time_info() -> Dict[str, Any]:
    """Mengambil informasi tanggal, hari, dan waktu real-time yang terverifikasi dalam zona WIB dan JST"""
    try:
        from shiro.web.realtime_intel import format_verified_time_info
        info = format_verified_time_info()
        wib_str = f"{info['day']}, {info['date']} - Jam {info['time_wib']} WIB"
        jst_str = f"{info['time_jst']} JST (Waktu Jepang)"
        summary = (
            f"📅 Waktu Sekarang:\n"
            f"• Indonesia (WIB): **{wib_str}**\n"
            f"• Jepang (JST)    : **{jst_str}**"
        )
        return {
            "success": True,
            "wib": wib_str,
            "jst": jst_str,
            "summary": summary
        }
    except Exception:
        pass

    now_utc = datetime.now(timezone.utc)
    wib_tz = timezone(timedelta(hours=7))
    jst_tz = timezone(timedelta(hours=9))

    now_wib = now_utc.astimezone(wib_tz)
    now_jst = now_utc.astimezone(jst_tz)

    days_id = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    months_id = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

    day_name = days_id[now_wib.weekday()]
    month_name = months_id[now_wib.month - 1]

    wib_str = now_wib.strftime(f"{day_name}, %d {month_name} %Y - Jam %H:%M WIB")
    jst_str = now_jst.strftime("%H:%M JST (Waktu Jepang)")

    summary = (
        f"📅 Waktu Sekarang:\n"
        f"• Indonesia (WIB): **{wib_str}**\n"
        f"• Jepang (JST)    : **{jst_str}**"
    )

    return {
        "success": True,
        "wib": wib_str,
        "jst": jst_str,
        "summary": summary
    }

def find_available_browser() -> Optional[str]:
    """Mencari executable browser yang tersedia di sistem (Windows, Linux, & Google Colab)"""
    candidates = [
        # Windows candidates
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        # Linux & Google Colab candidates
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
        # PATH searches
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium-browser"),
        shutil.which("chromium"),
        shutil.which("chrome"),
        shutil.which("msedge"),
        shutil.which("brave"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None

def _fetch_cloud_screenshot(clean_url: str, abs_out_path: str) -> bool:
    """Mengambil screenshot web melalui engine cloud rendering (tanpa browser lokal, 100% kompatibel Colab)"""
    encoded_url = urllib.parse.quote_plus(clean_url)
    session = get_agent_session()

    # Urutkan engine cloud berdasarkan keandalan & render instan:
    # 1. thum.io: Render instan berkecepatan tinggi (format PNG asli > 100KB)
    # 2. microlink.io: Headless Chrome cloud (format PNG jernih)
    # 3. wordpress mshots: (Hanya terima gambar render selesai > 15KB JPEG/PNG, tolak GIF placeholder 'Generating Preview...')
    engines = [
        ("thum.io", f"https://image.thum.io/get/width/1280/crop/800/{clean_url}"),
        ("microlink", f"https://api.microlink.io?url={encoded_url}&screenshot=true&embed=screenshot.url"),
        ("mshots", f"https://s0.wp.com/mshots/v1/{encoded_url}?w=1280&h=800"),
    ]

    for name, engine_url in engines:
        try:
            max_attempts = 3 if name == "mshots" else 1
            for attempt in range(max_attempts):
                resp = session.get(engine_url, timeout=12)
                if resp.status_code == 200 and len(resp.content) > 1024:
                    content_type = resp.headers.get("content-type", "").lower()
                    # DETEKSI: WordPress mshots mengembalikan file image/gif ~8KB bertuliskan 'Generating Preview...'
                    # Jangan simpan GIF placeholder ini!
                    if name == "mshots" and ("gif" in content_type or resp.content[:4] == b'GIF8' or len(resp.content) < 15000):
                        if attempt < max_attempts - 1:
                            time.sleep(2)
                            continue
                        else:
                            break

                    # Pastikan data yang diterima adalah gambar biner asli (PNG / JPEG / WebP) dan bukan placeholder
                    is_valid = (
                        len(resp.content) > 10000 and
                        resp.content[:4] in [b'\x89PNG', b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1', b'RIFF']
                    )
                    if is_valid:
                        with open(abs_out_path, "wb") as f:
                            f.write(resp.content)
                        if os.path.exists(abs_out_path) and os.path.getsize(abs_out_path) > 10000:
                            return True
        except Exception:
            continue
    return False

def take_web_screenshot(url: str, output_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Mengambil tangkapan layar (screenshot) website secara multi-tier:
    1. Mencoba browser headless lokal (Chrome/Chromium/Edge/Brave) jika terpasang
    2. Otomatis fallback ke Cloud Headless Screenshot Engine (aktif jika di Google Colab / tanpa browser lokal)
    Menyimpannya ke folder data/uploads/screenshots/ untuk ditampilkan ke pengguna.
    """
    if not url:
        return {"success": False, "error": "URL kosong", "summary": "Gagal mengambil screenshot: URL tidak diberikan."}

    clean_url = url.strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = "https://" + clean_url

    upload_dir = os.path.abspath(os.path.join("data", "uploads", "screenshots"))
    os.makedirs(upload_dir, exist_ok=True)

    timestamp = int(time.time() * 1000)
    filename = output_name or f"screenshot_{timestamp}.png"
    if not any(filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg"]):
        filename += ".png"
    abs_out_path = os.path.join(upload_dir, filename)

    method_used = ""
    # TIER 1: Coba browser lokal jika ada
    browser_bin = find_available_browser()
    if browser_bin:
        cmd = [
            browser_bin,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            f"--screenshot={abs_out_path}",
            "--window-size=1280,800",
            "--hide-scrollbars",
            clean_url
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if os.path.exists(abs_out_path) and os.path.getsize(abs_out_path) > 1024:
                method_used = f"Browser Lokal ({os.path.basename(browser_bin)})"
        except Exception:
            pass

    # TIER 2: Fallback ke Cloud Headless Screenshot Engine (Google Colab / Tanpa Browser)
    if not method_used or not os.path.exists(abs_out_path) or os.path.getsize(abs_out_path) <= 1024:
        if _fetch_cloud_screenshot(clean_url, abs_out_path):
            method_used = "Cloud Headless Engine (Colab / Multi-OS)"

    if os.path.exists(abs_out_path) and os.path.getsize(abs_out_path) > 0:
        rel_url = f"/images/screenshots/{filename}"
        file_size = os.path.getsize(abs_out_path)
        summary = f"Tangkapan layar untuk situs {clean_url} berhasil diambil via {method_used} ({file_size} bytes)."
        return {
            "success": True,
            "url": clean_url,
            "image_url": rel_url,
            "file_path": abs_out_path,
            "filename": filename,
            "file_size": file_size,
            "engine": method_used,
            "summary": summary
        }
    else:
        return {
            "success": False,
            "url": clean_url,
            "error": "Gagal mengambil screenshot dari semua engine (lokal & cloud)",
            "summary": f"Gagal mengambil screenshot dari {clean_url}. Pastikan situs aktif dan dapat diakses publik."
        }

def execute_powershell_command(command: str) -> Dict[str, Any]:
    """
    Mengeksekusi perintah terminal / shell secara aman dan multi-platform:
    - Di Windows PC: Menggunakan PowerShell
    - Di Linux / Google Colab: Menggunakan Bash / Shell
    """
    if not command:
        return {"success": False, "error": "Perintah kosong", "summary": "Tidak ada perintah yang diberikan."}

    clean_cmd = command.strip()
    clean_cmd = re.sub(r'^(?:powershell(?:\.exe)?|bash|sh|cmd|ps\s*:?|jalankan(?:\s+perintah)?\s*:?)\s*', '', clean_cmd, flags=re.IGNORECASE).strip()

    is_windows = os.name == 'nt' or platform.system().lower() == 'windows'

    # Filter perintah destruktif
    dangerous_patterns = [
        r'\bformat\s+[a-z]:', r'\bdiskpart\b', r'\bdel\s+/[sfq]\s+c:\\windows\b',
        r'\brm\s+-[rf]{1,2}\s+/\b', r'\bmkfs\b', r':\(\)\{\s*:\|:&\s*\};:'
    ]
    for dp in dangerous_patterns:
        if re.search(dp, clean_cmd, re.IGNORECASE):
            return {
                "success": False,
                "command": clean_cmd,
                "error": "Perintah berbahaya diblokir demi keamanan sistem",
                "summary": f"Perintah '{clean_cmd}' diblokir karena berpotensi merusak sistem."
            }

    if is_windows:
        cmd_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", clean_cmd]
        env_label = "PowerShell (PC)"
    else:
        # Linux / Google Colab
        if shutil.which("pwsh"):
            cmd_args = ["pwsh", "-NoProfile", "-Command", clean_cmd]
            env_label = "PowerShell Core (Linux / Colab)"
        else:
            cmd_args = ["bash", "-c", clean_cmd]
            env_label = "Bash (Google Colab / Linux)"

    try:
        res = subprocess.run(cmd_args, capture_output=True, text=True, timeout=30)
        stdout = res.stdout.strip()
        stderr = res.stderr.strip()
        is_success = res.returncode == 0

        if len(stdout) > 3000:
            stdout_display = stdout[:3000] + f"\n... [Output dipotong, total {len(stdout)} karakter]"
        else:
            stdout_display = stdout

        if is_success:
            summary = (
                f"Perintah `{clean_cmd}` berhasil dieksekusi di {env_label} (Exit Code: 0).\n"
                f"Hasil Terminal Output:\n{stdout_display if stdout_display else '(Perintah berhasil dijalankan tanpa teks output)'}"
            )
        else:
            summary = (
                f"Perintah `{clean_cmd}` selesai dengan kode status error {res.returncode} di {env_label}.\n"
                f"Pesan Error / Output:\n{stderr or stdout_display}"
            )

        return {
            "success": is_success,
            "command": clean_cmd,
            "environment": env_label,
            "returncode": res.returncode,
            "stdout": stdout_display,
            "stderr": stderr,
            "summary": summary
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "command": clean_cmd,
            "error": "Timeout 30 detik terlampaui",
            "summary": f"Perintah `{clean_cmd}` berjalan melebihi batas waktu (timeout 30 detik)."
        }
    except Exception as e:
        return {
            "success": False,
            "command": clean_cmd,
            "error": str(e),
            "summary": f"Gagal mengeksekusi perintah `{clean_cmd}`: {str(e)}"
        }

def detect_agent_intent(text: str, conversation_history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Menganalisis pesan pengguna dan mendeteksi apakah membutuhkan eksekusi tool AI Agent:
    - screenshot: Mengambil tangkapan layar website via browser headless
    - powershell: Menjalankan perintah PowerShell di PC lokal
    - weather: Pengecekan cuaca, suhu, hujan di lokasi tertentu
    - search: Pencarian informasi Google/Web terkini
    - browse: Membuka URL web secara langsung
    - math: Perhitungan matematika
    - time: Pengecekan tanggal/jam sekarang
    - none: Obrolan santai biasa (tanpa tool)
    """
    if not text:
        return {"intent": "none", "params": {}}

    text_lower = text.lower().strip()

    # Ekstrak semua URL yang ada dalam teks
    url_pattern = r'https?://[^\s<>"\')]+'
    urls = re.findall(url_pattern, text)

    # 1. Deteksi Screenshot Web
    screenshot_triggers = [
        "screenshot", "tangkapan layar", "ss web", "ss situs", "ambil gambar web",
        "foto web", "screenshoot", "screen capture", "tangkapan web"
    ]
    if any(st in text_lower for st in screenshot_triggers):
        if urls:
            return {
                "intent": "screenshot",
                "params": {"url": urls[0].rstrip(".,;:!?)'\"")}
            }
        m_domain = re.search(r'(?:web|situs|halaman|url)\s+([a-zA-Z0-9.\-_]+\.[a-z]{2,})', text_lower)
        if m_domain:
            return {
                "intent": "screenshot",
                "params": {"url": m_domain.group(1)}
            }
        for word in text.split():
            clean_word = word.strip(".,;:!?()\"'")
            if "." in clean_word and len(clean_word.split(".")[-1]) in [2, 3, 4] and not clean_word.endswith("."):
                return {
                    "intent": "screenshot",
                    "params": {"url": clean_word}
                }
        # Cek konteks percakapan riwayat sebelumnya jika merujuk ke URL lalu ("itu", "tadi", "tersebut", "barusan")
        if conversation_history:
            for past_msg in reversed(conversation_history):
                past_content = past_msg.get("content", "") or ""
                past_urls = re.findall(url_pattern, past_content)
                if past_urls:
                    return {
                        "intent": "screenshot",
                        "params": {"url": past_urls[-1].rstrip(".,;:!?)'\"")}
                    }

    # 2. Deteksi Pengendalian PC / PowerShell Terminal
    ps_triggers = [
        "powershell", "jalankan di pc", "perintah powershell", "run command",
        "terminal pc", "eksekusi perintah", "buka aplikasi", "buka notepad",
        "cek proses pc", "cek spesifikasi pc", "cmd pc", "jalankan perintah"
    ]
    if any(pt in text_lower for pt in ps_triggers):
        cmd_extracted = ""
        m_cmd = re.search(r'(?:powershell|perintah|terminal|cmd)\s*[:=]\s*(.+)$', text, flags=re.IGNORECASE)
        if m_cmd:
            cmd_extracted = m_cmd.group(1).strip()
        elif "buka notepad" in text_lower:
            cmd_extracted = "Start-Process notepad"
        elif "cek spesifikasi pc" in text_lower or "spesifikasi pc" in text_lower:
            cmd_extracted = "Get-CimInstance Win32_OperatingSystem | Select-Object Caption, OSArchitecture, TotalVisibleMemorySize, FreePhysicalMemory"
        elif "cek proses" in text_lower:
            cmd_extracted = "Get-Process | Sort-Object CPU -Descending | Select-Object -First 8 -Property Name, CPU, WorkingSet"
        else:
            for pt in ps_triggers:
                if pt in text_lower:
                    cmd_extracted = re.sub(rf".*?{re.escape(pt)}", "", text, flags=re.IGNORECASE).strip(" :?,.!")
                    break
        if cmd_extracted:
            return {
                "intent": "powershell",
                "params": {"command": cmd_extracted}
            }

    # 2b. Deteksi Permintaan Pengemasan / Kompresi File (.zip, .tar.gz, .7z, .tar, dll.)
    try:
        from shiro.agent.packager import detect_archive_request
        arch_req = detect_archive_request(text)
        if arch_req:
            return {
                "intent": "archive",
                "params": arch_req
            }
    except Exception:
        pass

    # 2c. Deteksi Permintaan Pembuatan / Render Video MP4 Programatik
    try:
        from shiro.vision.video import detect_video_generation_request
        vid_req = detect_video_generation_request(text)
        if vid_req:
            return {
                "intent": "generate_video",
                "params": vid_req
            }
    except Exception:
        pass

    # 3. Deteksi URL langsung untuk dibaca kontennya (browse)
    if urls:
        target_url = urls[0].rstrip(".,;:!?)'\"")
        return {
            "intent": "browse",
            "params": {"url": target_url}
        }
    browse_triggers = ["baca web", "buka web", "cek web", "lihat web", "baca situs", "buka situs"]
    if any(bt in text_lower for bt in browse_triggers) and conversation_history:
        for past_msg in reversed(conversation_history):
            past_content = past_msg.get("content", "") or ""
            past_urls = re.findall(url_pattern, past_content)
            if past_urls:
                return {
                    "intent": "browse",
                    "params": {"url": past_urls[-1].rstrip(".,;:!?)'\"")}
                }

    # 2. Deteksi Cuaca & Hujan
    weather_triggers = [
        "cuaca", "hujan", "suhu sekarang", "derajat", "gerimis", "ramalan cuaca",
        "weather", "apakah hujan", "lagi hujan", "panas kah", "dingin kah"
    ]
    if any(wt in text_lower for wt in weather_triggers):
        # Ekstrak kota yang disebut
        found_cities = []
        city_candidates = [
            "tokyo", "jakarta", "bandung", "surabaya", "yogyakarta", "medan",
            "semarang", "bali", "denpasar", "kyoto", "osaka", "seoul",
            "singapore", "singapura", "london", "paris", "new york", "sydney",
            "malang", "bogor", "depok", "tangerang", "bekasi"
        ]
        for c in city_candidates:
            if re.search(rf"\b{c}\b", text_lower):
                found_cities.append(c.capitalize() if c != "singapura" else "Singapore")

        # Jika tidak ada kota spesifik terdeteksi namun ada kata "di [Nama Kota]"
        if not found_cities:
            m_city = re.search(r'\b(?:di|untuk|daerah|wilayah)\s+([A-Z][a-z]+|[a-zA-Z]+)', text)
            if m_city:
                cand = m_city.group(1).strip()
                if cand.lower() not in ["luar", "sana", "sini", "tempat", "mana", "hari", "sekarang", "indonesia"]:
                    found_cities.append(cand)

        # Default jika user hanya bilang "apakah hujan?" atau "cek cuaca sekarang"
        if not found_cities:
            found_cities = ["Jakarta", "Tokyo"]

        return {
            "intent": "weather",
            "params": {"locations": found_cities}
        }

    # 3. Deteksi Perhitungan Matematika
    # Contoh: "hitung 15 * 25", "berapa (1540 * 25) + 380", "1500 + 400"
    math_match = re.search(r'(?:hitung|berapa\s+hasil\s+dari|kalkulasi)?\s*([0-9(][0-9\s()+\-*/.^x:]{2,}[0-9)])', text_lower)
    if math_match:
        expr = math_match.group(1).strip()
        # Pastikan operator aritmatika diapit angka/kurung (cegah salah deteksi seperti 'RTX 5090' -> 'x 5090')
        if re.search(r'[0-9)]\s*[+\-*/^x:]\s*[0-9(]', expr):
            # Pastikan bukan sekadar tanggal seperti 2024-10-12
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', expr):
                return {
                    "intent": "math",
                    "params": {"expression": expr}
                }

    # 4. Deteksi Waktu / Jam / Kalender (Real-Time Intel Multibahasa)
    try:
        from shiro.web.realtime_intel import classify_intent
        intel_res = classify_intent(text)
        if intel_res.kind == "time":
            return {
                "intent": "time",
                "params": {}
            }
        elif intel_res.kind == "search":
            return {
                "intent": "search",
                "params": {"query": text.strip()}
            }
    except Exception:
        pass

    time_triggers = ["jam berapa", "tanggal berapa", "hari apa sekarang", "waktu sekarang", "sekarang jam", "hari ini tanggal"]
    if any(tt in text_lower for tt in time_triggers):
        return {
            "intent": "time",
            "params": {}
        }

    # 5. Deteksi Pencarian Web / Gambar / Informasi Umum Otomatis
    # Hindari salah deteksi sebagai pencarian web jika user sedang curhat pribadi atau meminta membuat/mengedit kode UI/file
    is_coding_or_chat_personal = bool(
        re.search(r'\b(buatkan\s+(?:website|aplikasi|program|kode|script|skrip|login|halaman|video)|perbaiki\s+(?:kode|bug|error|tampilan|file)|edit\s+file|curhat|aku\s+(?:sedih|capek|lelah|galau))\b', text_lower)
    )

    image_search_triggers = [
        "cari gambar", "carikan gambar", "cariin gambar", "cari foto", "carikan foto", "cariin foto",
        "find image", "find picture", "search image", "gambar tentang", "foto tentang",
    ]
    for ist in image_search_triggers:
        if ist in text_lower and not is_coding_or_chat_personal:
            q_img = re.sub(rf".*?{re.escape(ist)}", "", text, flags=re.IGNORECASE).strip(" :?,.!")
            q_img = re.sub(r'\b(dong|ya|kak|shiro)\b', '', q_img, flags=re.IGNORECASE).strip(" :?,.!")
            if not q_img or len(q_img) < 2:
                q_img = text.strip()
            return {
                "intent": "search",
                "params": {"query": q_img, "wants_images": True}
            }

    search_triggers = [
        "cari di web", "cari di google", "cari di browser", "cek di browser", "buka browser",
        "googling", "search the web", "search online", "search", "cari info",
        "cari informasi", "carikan informasi", "cariin informasi", "carikan info", "cariin info",
        "carikan sumber", "cari sumber", "cari source", "carikan source", "cari referensi", "carikan referensi",
        "cari link", "carikan link", "cari tahu tentang", "carikan berita", "cari berita",
        "browsing", "berita tentang", "cek di internet", "cek info",
        "spesifikasi", "spek ", "siapa itu", "siapa presiden", "siapa penemu",
        "apa itu", "kapan rilis", "siapa pemenang", "harga sekarang", "kurs dollar",
        "harga bitcoin", "fakta tentang", "sejarah tentang", "profil tentang",
        "look up", "search for", "find info", "who is", "what is the latest"
    ]
    if not is_coding_or_chat_personal:
        for st in search_triggers:
            if st in text_lower:
                # Ekstrak query pencarian
                q = re.sub(rf".*?{re.escape(st)}", "", text, flags=re.IGNORECASE).strip(" :?,.!")
                if st in ("spesifikasi", "spek ", "siapa itu", "apa itu", "kapan rilis", "siapa pemenang", "siapa presiden", "siapa penemu"):
                    q = text.strip(" ?.!").strip()
                elif not q or len(q) < 3:
                    q = text.strip()
                return {
                    "intent": "search",
                    "params": {"query": q, "wants_images": any(k in text_lower for k in ("gambar", "foto", "image", "visual"))}
                }

        # Fallback: permintaan "cari ..." / "carikan ..." umum yang tidak menyebut file/coding
        m_generic_cari = re.match(r'^(?:tolong\s+|coba\s+|shiro[,\s]+)?(?:carikan|cariin|cari)\s+(.{3,})$', text_lower)
        if m_generic_cari and not any(fc in text_lower for fc in ("file", "berkas", "bug", "error", "kode", "syntax")):
            q_gen = m_generic_cari.group(1).strip(" :?,.!")
            return {
                "intent": "search",
                "params": {"query": q_gen, "wants_images": any(k in text_lower for k in ("gambar", "foto", "image", "visual"))}
            }

    return {"intent": "none", "params": {}}
