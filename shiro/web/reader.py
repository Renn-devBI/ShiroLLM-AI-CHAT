# -*- coding: utf-8 -*-
"""
Web Reader & Online Knowledge Ingestion Module for Shiro LLMA
Memungkinkan Shiro mengakses internet, membaca halaman web (HTML),
melewati proteksi Cloudflare/Anti-Bot sederhana, membersihkan tag HTML,
dan mengintegrasikan pengetahuan yang dipelajari ke dalam ingatan (RDF)
serta dataset pelatihan (training_data).
"""

import os
import re
import json
import shutil
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

# Coba import requests dan bs4
try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# Coba import curl_cffi untuk bypass Cloudflare TLS fingerprint
try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

# Realistic modern browser headers
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}

def extract_urls(text: str) -> List[str]:
    """Ekstrak semua URL http:// atau https:// dari teks input"""
    if not text:
        return []
    url_pattern = r'https?://[^\s<>"\')]+'
    urls = re.findall(url_pattern, text)
    # Bersihkan tanda baca di ujung URL jika terbawa
    cleaned_urls = []
    for u in urls:
        u = u.rstrip(".,;:!?)'\"")
        if u and u not in cleaned_urls:
            cleaned_urls.append(u)
    return cleaned_urls

def detect_web_intent(text: str) -> Dict[str, Any]:
    """
    Deteksi apakah pesan user meminta membaca URL atau melakukan pencarian online.
    """
    urls = extract_urls(text)
    if urls:
        return {
            "type": "url",
            "urls": urls,
            "query": None
        }

    # Normalisasi typo dan singkatan sebelum mencocokkan kata kunci
    try:
        from shiro.nlp.typo import normalize_typos
        normalized_text, _ = normalize_typos(text)
    except Exception:
        normalized_text = text

    # Kata kunci pencarian online (toleran terhadap typo/singkatan)
    search_keywords = [
        "cari di web", "cari di internet", "browsing tentang", "browsing dong",
        "search online", "cari info tentang", "cari informasi tentang",
        "cek di internet", "baca web tentang", "buka website", "cariin tentang",
        "googling tentang", "baca tentang", "info tentang", "cek info"
    ]
    for candidate in [text.lower(), normalized_text.lower()]:
        for kw in search_keywords:
            if kw in candidate:
                query = re.sub(rf".*?{re.escape(kw)}", "", normalized_text, flags=re.IGNORECASE).strip(" :?,.!")
                if query:
                    return {
                        "type": "search",
                        "urls": [],
                        "query": query
                    }

    # Klasifikasi intent pencarian semantik (tanpa kata kunci kaku)
    try:
        from shiro.web.realtime_intel import classify_intent
        intel = classify_intent(text)
        if intel.kind == "search":
            return {
                "type": "search",
                "urls": [],
                "query": text.strip()
            }
    except Exception:
        pass

    return {
        "type": "none",
        "urls": [],
        "query": None
    }

def clean_html_content(html: str, max_chars: int = 3500) -> Tuple[str, str]:
    """
    Membersihkan HTML menjadi teks murni yang padat informasi,
    menghapus tag script, style, iklan, nav, footer agar pas dalam context window.
    """
    title = "Web Page"
    if not html:
        return title, ""

    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Buang elemen yang tidak relevan / noise
        noise_tags = [
            "script", "style", "noscript", "svg", "canvas", "header", "footer",
            "nav", "aside", "form", "button", "input", "select", "textarea",
            "iframe", "meta", "link"
        ]
        for tag in soup(noise_tags):
            tag.decompose()

        # Prioritaskan elemen konten utama jika ada
        main_content = None
        for selector in ["article", "main", "[role='main']", "#content", ".content", ".post-content", ".article-body"]:
            elem = soup.select_one(selector)
            if elem:
                main_content = elem
                break

        target = main_content if main_content else (soup.body if soup.body else soup)
        text = " ".join(target.stripped_strings)
    else:
        # Fallback regex sederhana jika BeautifulSoup tidak tersedia
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
        cleaned = re.sub(r'<(script|style|nav|footer|header)[^>]*>.*?</\1>', '', html, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
        text = " ".join(cleaned.split())

    # Normalisasi spasi dan batasi panjang karakter agar tidak melebihi konteks LLM
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + " ... (konten web dipotong untuk efisiensi context)"
    return title, text

def fetch_fandom_mediawiki(url: str, timeout: int = 12) -> Optional[Dict[str, Any]]:
    """
    Ekstrak artikel dari Fandom / Wikia / Wikipedia menggunakan MediaWiki API resmi.
    Menghindari blokir Cloudflare Managed Challenge pada halaman HTML desktop Fandom!
    """
    m = re.match(r'https?://([^/]+)(?:/([a-zA-Z-]+))?/wiki/([^/?#]+)', url)
    if not m:
        return None
    domain = m.group(1).lower()
    if "fandom.com" not in domain and "wikia.org" not in domain and "wikipedia.org" not in domain:
        return None
    subpath = f"/{m.group(2)}" if m.group(2) else ""
    page = urllib.parse.unquote(m.group(3)).replace("_", " ")
    
    if "wikipedia.org" in domain:
        api_url = f"https://{domain}/w/api.php"
    else:
        api_url = f"https://{domain}{subpath}/api.php"
    params = {
        "action": "parse",
        "page": page,
        "prop": "text",
        "format": "json"
    }
    try:
        req_headers = dict(BROWSER_HEADERS)
        if requests:
            r = requests.get(api_url, params=params, headers=req_headers, timeout=timeout, verify=False)
            if r.status_code == 200:
                data = r.json()
                raw_html = data.get("parse", {}).get("text", {}).get("*", "")
                if raw_html:
                    page_title = data.get("parse", {}).get("title", page)
                    _, clean_text = clean_html_content(raw_html, max_chars=4000)
                    return {
                        "success": True,
                        "url": url,
                        "title": f"{page_title} - {domain}",
                        "content": clean_text,
                        "error": None,
                        "is_cloudflare": False
                    }
    except Exception as e_api:
        pass
    return None

def fetch_url(url: str, timeout: int = 12) -> Dict[str, Any]:
    """
    Mengambil isi URL dengan penanganan Cloudflare / Anti-Bot:
    1. Otomatis gunakan MediaWiki API untuk Fandom/Wikia/Wikipedia (Bypass Cloudflare 100%)
    2. Menggunakan curl_cffi jika tersedia (TLS Fingerprint Impersonation Chrome 124)
    3. Fallback ke requests dengan browser headers
    4. Fallback ke urllib.request
    """
    # 0. Penanganan khusus Fandom / Wikia / MediaWiki untuk menghindari Cloudflare block
    wiki_res = fetch_fandom_mediawiki(url, timeout=timeout)
    if wiki_res and wiki_res.get("success"):
        return wiki_res

    result = {
        "success": False,
        "url": url,
        "title": "Tanpa Judul",
        "content": "",
        "error": None,
        "is_cloudflare": False
    }

    html = ""
    # Metode 1: curl_cffi (Bypass Cloudflare / TLS fingerprint)
    if curl_requests:
        try:
            resp = curl_requests.get(
                url,
                headers=BROWSER_HEADERS,
                impersonate="chrome124",
                timeout=timeout,
                verify=False
            )
            if resp.status_code == 200:
                html = resp.text
        except Exception as e_curl:
            pass

    # Metode 2: requests biasa
    if not html and requests:
        try:
            session = requests.Session()
            resp = session.get(url, headers=BROWSER_HEADERS, timeout=timeout, allow_redirects=True, verify=False)
            if resp.status_code == 200:
                html = resp.text
            elif resp.status_code in [403, 503]:
                if any(x in resp.text.lower() for x in ["cloudflare", "just a moment", "turnstile", "ray id"]):
                    result["is_cloudflare"] = True
                    result["error"] = "Halaman web dilindungi oleh Cloudflare Bot Protection / Turnstile Challenge."
        except Exception as e_req:
            pass

    # Metode 3: urllib fallback
    if not html and not result["is_cloudflare"]:
        try:
            req = urllib.request.Request(url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                # Coba decode utf-8 atau latin-1
                try:
                    html = raw.decode("utf-8")
                except UnicodeDecodeError:
                    html = raw.decode("latin-1", errors="ignore")
        except Exception as e_url:
            result["error"] = str(e_url)

    if html:
        # Cek apakah ada indikasi layar blokir Cloudflare
        if "just a moment..." in html.lower() and "cloudflare" in html.lower():
            result["is_cloudflare"] = True
            result["error"] = "Halaman web terhalang Cloudflare Challenge."
            return result

        title, content = clean_html_content(html)
        result["success"] = True
        result["title"] = title
        result["content"] = content
        result["error"] = None

    return result

def search_wikipedia_online(query: str, lang: str = "id", max_results: int = 2) -> Dict[str, Any]:
    """
    Pencarian ensiklopedia online Wikipedia (Sangat stabil dan tidak terblokir ISP).
    Mencari artikel Wikipedia dan mengambil ringkasan intinya.
    """
    result = {
        "success": False,
        "query": query,
        "results": []
    }
    if not query:
        return result

    # Coba Bahasa Indonesia terlebih dahulu
    for current_lang in [lang, "en"]:
        api_url = f"https://{current_lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "utf8": "1",
            "format": "json",
            "srlimit": max_results
        }
        try:
            encoded_url = api_url + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(encoded_url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            
            search_items = data.get("query", {}).get("search", [])
            if search_items:
                extracted = []
                for item in search_items:
                    page_title = item.get("title", "")
                    raw_snippet = item.get("snippet", "")
                    clean_snippet = re.sub(r'<[^>]+>', '', raw_snippet).strip()
                    page_url = f"https://{current_lang}.wikipedia.org/wiki/{urllib.parse.quote(page_title)}"
                    extracted.append({
                        "title": page_title,
                        "url": page_url,
                        "snippet": clean_snippet
                    })
                result["success"] = True
                result["results"] = extracted
                return result
        except Exception:
            continue
    return result

def append_to_training_dataset(
    instruction: str,
    output: str,
    base_dir: str = "training_data",
    source: str = "online_web_learning"
):
    """
    Menyimpan pasangan tanya-jawab dari hasil pembacaan web ke dataset training Shiro
    dalam format Alpaca, ChatML, dan ShareGPT secara permanen!
    """
    if not instruction or not output:
        return

    # Bersihkan output jika ada CoT/think tags
    if "<think>" in output or "</think>" in output:
        output = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL).strip()

    if len(output) < 5:
        return

    from shiro.persona import DATASET_SYSTEM_PROMPT
    SYSTEM_PROMPT = DATASET_SYSTEM_PROMPT

    chat_dir = os.path.join(base_dir, "chat")
    os.makedirs(chat_dir, exist_ok=True)

    alpaca_sample = {
        "instruction": instruction.strip(),
        "input": "",
        "output": output.strip(),
        "system": SYSTEM_PROMPT,
        "source": source,
        "timestamp": datetime.now().isoformat()
    }

    # 1. Update shiro_alpaca_train.json
    for path in [
        os.path.join(base_dir, "shiro_alpaca_train.json"),
        os.path.join(chat_dir, "shiro_alpaca_train.json")
    ]:
        data = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = []
            except Exception:
                data = []
        # Cek duplikat instruksi serupa
        if not any(d.get("instruction", "").strip().lower() == instruction.strip().lower() for d in data):
            data.append(alpaca_sample)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e_write:
                print(f"Warning writing Alpaca training file: {e_write}")

    # 2. Update shiro_chatml_train.jsonl
    for path in [
        os.path.join(base_dir, "shiro_chatml_train.jsonl"),
        os.path.join(chat_dir, "shiro_chatml_train.jsonl")
    ]:
        chatml_sample = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": instruction.strip()},
                {"role": "assistant", "content": output.strip()}
            ]
        }
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(chatml_sample, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # 3. Update shiro_sharegpt_train.json
    for path in [
        os.path.join(base_dir, "shiro_sharegpt_train.json"),
        os.path.join(chat_dir, "shiro_sharegpt_train.json")
    ]:
        sharegpt_data = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    sharegpt_data = json.load(f)
                    if not isinstance(sharegpt_data, list):
                        sharegpt_data = []
            except Exception:
                sharegpt_data = []
        new_sharegpt_item = {
            "id": f"shiro_web_{len(sharegpt_data)+1:04d}",
            "conversations": [
                {"from": "system", "value": SYSTEM_PROMPT},
                {"from": "human", "value": instruction.strip()},
                {"from": "gpt", "value": output.strip()}
            ]
        }
        sharegpt_data.append(new_sharegpt_item)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(sharegpt_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # 4. Auto-sync ke Google Drive jika Drive aktif
    drive_dir = os.environ.get("SHIRO_DRIVE_DIR")
    if not drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
        drive_dir = "/content/drive/MyDrive/Shiro_Memory"
    if drive_dir and os.path.exists(drive_dir):
        try:
            drive_train = os.path.join(drive_dir, "training_data")
            shutil.copytree(base_dir, drive_train, dirs_exist_ok=True)
        except Exception:
            pass

def integrate_web_knowledge(
    memory_manager,
    user_input: str,
    assistant_reply: str,
    web_title: str,
    url_or_query: str,
    web_content: str
):
    """
    Menyimpan hasil bacaan web secara menyeluruh:
    1. Menyimpan fakta RDF ke dalam memory.knowledge_base["facts"]
    2. Menyimpan interaksi ke learned_patterns
    3. Menyimpan ke dataset pelatihan training_data (Alpaca, ChatML, ShareGPT)
    4. Menyimpan ingatan & otomatis sync ke Google Drive
    """
    if not memory_manager or not assistant_reply:
        return

    # 1. Tambahkan fakta semantik RDF ke knowledge_base
    try:
        subject = web_title[:60] if web_title and web_title != "Tanpa Judul" else url_or_query[:60]
        summary_fact = web_content[:200].strip() if web_content else assistant_reply[:200].strip()
        if hasattr(memory_manager, 'add_fact'):
            memory_manager.add_fact(
                subject=subject,
                predicate="informasi_web",
                obj=summary_fact,
                confidence=0.95
            )
        else:
            facts = memory_manager.knowledge_base.setdefault("facts", [])
            facts.append({
                "subject": subject,
                "predicate": "informasi_web",
                "object": summary_fact,
                "confidence": 0.95,
                "created_at": datetime.now().isoformat()
            })
    except Exception as e_fact:
        print(f"Warning saving web fact: {e_fact}")

    # 2. Rekam pola belajar (few-shot exemplars)
    try:
        memory_manager.record_learned_pattern(user_input, assistant_reply, quality=1.0)
    except Exception as e_pat:
        print(f"Warning recording learned pattern: {e_pat}")

    # 3. Masukkan ke file dataset training_data (Alpaca, ChatML, ShareGPT)
    try:
        append_to_training_dataset(
            instruction=user_input,
            output=assistant_reply,
            source=f"web_read: {url_or_query}"
        )
    except Exception as e_train:
        print(f"Warning appending web data to training dataset: {e_train}")

    # 4. Simpan ingatan ke file JSON dan sync ke Google Drive
    try:
        memory_manager.save_memory()
    except Exception as e_save:
        print(f"Warning saving memory after web learning: {e_save}")


# ==============================================================================
# LIVE TARGET WEBSITE DOM & STRUCTURE INSPECTOR (UNTUK TUGAS SCRAPING AGENT)
# ==============================================================================

FIREFOX_INSPECT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "DNT": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

_SCRAPE_INTENT_KEYWORDS = (
    "scraping", "scrape", "scraper", "crawl", "crawler", "crawling",
    "cheerio", "playwright", "puppeteer", "beautifulsoup", "bs4",
    "scrapy", "selenium", "parse html", "parsing html",
    "ambil data dari", "ekstrak data dari", "ekstrak dari",
    "image-proxy", "proxy gambar", "deep scraping",
)

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1")


def _is_remote_http_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme in ("http", "https") and bool(host) and host not in _LOCAL_HOSTS
    except Exception:
        return False


def detect_scraping_target_urls(text: str) -> Tuple[bool, List[str], List[str]]:
    """
    Mendeteksi apakah pengguna meminta pembuatan/eksekusi web scraper terhadap URL remote.
    Mengembalikan (is_scraping_task, base_urls, template_urls).
    URL localhost/127.0.0.1 otomatis diabaikan sebagai target scraping.
    """
    if not text:
        return False, [], []
    low = text.lower()
    has_scrape_kw = any(kw in low for kw in _SCRAPE_INTENT_KEYWORDS)
    if not has_scrape_kw:
        return False, [], []

    raw_urls = extract_urls(text)
    base_urls: List[str] = []
    template_urls: List[str] = []

    for u in raw_urls:
        clean_u = u.rstrip("`.,;:!?)'\"")
        if not _is_remote_http_url(clean_u):
            continue
        if "{" in clean_u and "}" in clean_u:
            if clean_u not in template_urls:
                template_urls.append(clean_u)
            # Pastikan origin homepage juga masuk base_urls
            parsed = urllib.parse.urlparse(clean_u)
            origin = f"{parsed.scheme}://{parsed.netloc}/"
            if origin not in base_urls:
                base_urls.append(origin)
        else:
            if clean_u not in base_urls:
                base_urls.append(clean_u)

    return bool(base_urls or template_urls), base_urls, template_urls


def fetch_raw_html(url: str, timeout: int = 10, referer: Optional[str] = None) -> Dict[str, Any]:
    """
    Mengambil HTML mentah beserta metadata HTTP (status, final_url, header anti-bot, cookies)
    menggunakan profil header Mozilla Firefox agar agent bisa menginspeksi struktur web target secara nyata.
    """
    res: Dict[str, Any] = {
        "success": False,
        "url": url,
        "final_url": url,
        "status_code": 0,
        "html": "",
        "server": "",
        "cookies_count": 0,
        "is_cloudflare": False,
        "anti_bot_signals": [],
        "error": None,
    }
    headers = dict(FIREFOX_INSPECT_HEADERS)
    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin"

    def _check_antibot(status_code: int, body: str, resp_headers: Dict[str, str]):
        low_b = (body or "").lower()
        signals: List[str] = []
        srv = str(resp_headers.get("server") or resp_headers.get("Server") or "")
        if "cloudflare" in srv.lower() or "cf-ray" in {k.lower() for k in resp_headers.keys()}:
            signals.append("Cloudflare")
        if status_code in (403, 429, 503):
            signals.append(f"HTTP {status_code}")
        if any(tok in low_b for tok in ("just a moment", "cf-turnstile", "checking your browser", "attention required", "challenge-platform")):
            signals.append("Cloudflare/Turnstile Challenge")
            res["is_cloudflare"] = True
        if any(tok in low_b for tok in ("g-recaptcha", "h-captcha", "captcha")):
            signals.append("CAPTCHA")
        res["server"] = srv
        res["anti_bot_signals"] = signals

    # 1. Coba curl_cffi bila tersedia
    if curl_requests:
        try:
            r = curl_requests.get(url, headers=headers, impersonate="firefox133", timeout=timeout, verify=False, allow_redirects=True)
            res["status_code"] = int(r.status_code)
            res["final_url"] = str(getattr(r, "url", url))
            res["cookies_count"] = len(getattr(r, "cookies", {}) or {})
            _check_antibot(res["status_code"], r.text, dict(getattr(r, "headers", {}) or {}))
            if r.status_code == 200 and r.text and not res["is_cloudflare"]:
                res["html"] = r.text
                res["success"] = True
                return res
        except Exception as e_c:
            res["error"] = str(e_c)

    # 2. Coba requests.Session
    if requests:
        try:
            sess = requests.Session()
            r = sess.get(url, headers=headers, timeout=timeout, verify=False, allow_redirects=True)
            res["status_code"] = int(r.status_code)
            res["final_url"] = str(r.url)
            res["cookies_count"] = len(sess.cookies)
            _check_antibot(res["status_code"], r.text, dict(r.headers))
            if r.status_code == 200 and r.text and not res["is_cloudflare"]:
                res["html"] = r.text
                res["success"] = True
                res["error"] = None
                return res
            elif not res["html"] and r.text:
                res["html"] = r.text[:4000]
        except Exception as e_r:
            res["error"] = str(e_r)

    # 3. Fallback urllib
    if not res["success"] and not res["is_cloudflare"]:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                body = raw.decode("utf-8", errors="ignore")
                res["status_code"] = int(getattr(resp, "status", 200))
                res["final_url"] = str(resp.geturl())
                _check_antibot(res["status_code"], body, dict(resp.headers))
                if not res["is_cloudflare"] and body:
                    res["html"] = body
                    res["success"] = True
                    res["error"] = None
        except Exception as e_u:
            res["error"] = res["error"] or str(e_u)

    return res


def _compact_element_html(el: Any, max_len: int = 480) -> str:
    """Merapikan cuplikan HTML 1 elemen DOM agar mudah dibaca LLM tanpa noise script/style."""
    if not el:
        return ""
    raw = str(el)
    raw = re.sub(r"<(script|style|svg)[^>]*>[\s\S]*?</\1>", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s+", " ", raw).strip()
    if len(raw) > max_len:
        raw = raw[:max_len] + " ..."
    return raw


def analyze_html_structure(html: str, page_url: str) -> Dict[str, Any]:
    """
    Menganalisis struktur DOM nyata dari halaman HTML (form pencarian, selector container berulang,
    atribut gambar, judul/section penting, dan sampel tautan detail).
    """
    info: Dict[str, Any] = {
        "title": "",
        "forms": [],
        "repeating_containers": [],
        "key_sections": [],
        "image_attrs": [],
        "sample_detail_links": [],
    }
    if not html:
        return info

    parsed_base = urllib.parse.urlparse(page_url)
    base_host = (parsed_base.netloc or "").lower()

    if not BeautifulSoup:
        tm = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if tm:
            info["title"] = re.sub(r"\s+", " ", tm.group(1)).strip()
        return info

    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        info["title"] = soup.title.string.strip()

    # 1. Inspeksi <form> (khususnya search form)
    for form in soup.find_all("form")[:4]:
        action = form.get("action") or ""
        method = (form.get("method") or "GET").upper()
        inputs = []
        for inp in form.find_all(["input", "select"])[:6]:
            nm = inp.get("name")
            if nm:
                inputs.append(f"{nm}({inp.get('type') or inp.name}={inp.get('value') or ''})")
        info["forms"].append({
            "action": urllib.parse.urljoin(page_url, action) if action else page_url,
            "method": method,
            "inputs": inputs,
        })

    # 2. Cari container berulang (ul > li atau div/section dengan >= 2 anak sejenis berisi tautan/gambar)
    seen_sel = set()
    candidates = []
    for parent in soup.find_all(["ul", "ol", "div", "section", "main"]):
        p_classes = [c for c in (parent.get("class") or []) if c and len(c) < 40]
        p_id = parent.get("id") or ""
        if not p_classes and not p_id:
            continue
        p_sel = f"{parent.name}#{p_id}" if p_id else f"{parent.name}." + ".".join(p_classes[:2])
        if p_sel in seen_sel:
            continue
        # Hitung anak langsung berupa li/article/div yang berisi <a> atau <img>
        direct_items = [
            ch for ch in parent.find_all(recursive=False)
            if getattr(ch, "name", None) in ("li", "article", "div") and (ch.find("a") or ch.find("img"))
        ]
        if len(direct_items) >= 2:
            # Skip menu navigasi murni (nav/header/footer)
            anc_names = {a.name for a in parent.parents if getattr(a, "name", None)}
            if anc_names & {"nav", "header", "footer"}:
                continue
            first_item = direct_items[0]
            ch_cls = [c for c in (first_item.get("class") or []) if c and len(c) < 35]
            item_sel = f"{p_sel} > {first_item.name}" + (f".{ch_cls[0]}" if ch_cls else "")
            has_img = bool(first_item.find("img"))
            score = len(direct_items) + (8 if has_img else 0) + (4 if first_item.find(["h2", "h3", "h4"]) else 0)
            seen_sel.add(p_sel)
            candidates.append((score, item_sel, len(direct_items), _compact_element_html(first_item, 440)))

    candidates.sort(key=lambda x: x[0], reverse=True)
    for _, sel, cnt, snippet in candidates[:4]:
        info["repeating_containers"].append({
            "selector": sel,
            "count": cnt,
            "sample_html": snippet,
        })

    # 3. Bagian/section penting untuk halaman detail (sinopsis, info, daftar episode, dll.)
    detail_hint_re = re.compile(r"(sinop|synop|info|detail|episod|eps|genre|rating|score|thumb|foto|poster|venser|chivsrc|jdlrx)", re.IGNORECASE)
    seen_sec = set()
    for el in soup.find_all(["div", "section", "ul", "article", "h1", "h2"]):
        cls_list = [c for c in (el.get("class") or []) if c]
        el_id = el.get("id") or ""
        joined = " ".join(cls_list + ([el_id] if el_id else []))
        if not joined or not detail_hint_re.search(joined):
            continue
        sec_sel = f"{el.name}#{el_id}" if el_id else f"{el.name}." + ".".join(cls_list[:2])
        if sec_sel in seen_sec:
            continue
        seen_sec.add(sec_sel)
        txt = re.sub(r"\s+", " ", " ".join(el.stripped_strings))[:200]
        if txt:
            info["key_sections"].append({
                "selector": sec_sel,
                "text_preview": txt,
            })
        if len(info["key_sections"]) >= 6:
            break

    # 4. Pola atribut gambar (src vs data-src / data-lazy-src)
    img_samples = []
    for img in soup.find_all("img"):
        attrs_found = {}
        for attr in ("src", "data-src", "data-lazy-src", "srcset"):
            v = img.get(attr)
            if v and not str(v).startswith("data:image"):
                attrs_found[attr] = str(v)[:120]
        if attrs_found:
            img_samples.append(attrs_found)
        if len(img_samples) >= 3:
            break
    info["image_attrs"] = img_samples

    # 5. Sampel tautan konten di domain yang sama untuk deep-probe halaman detail
    skip_path_re = re.compile(r"/(?:tag|category|genres?|page|wp-content|wp-json|feed|author|contact|dmca|privacy)/?", re.IGNORECASE)
    seen_links = set()
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(page_url, str(a["href"]).strip())
        p = urllib.parse.urlparse(href)
        if p.netloc.lower() != base_host or p.path in ("", "/"):
            continue
        if skip_path_re.search(p.path) or p.query:
            continue
        label = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if len(label) < 3 or href in seen_links:
            continue
        seen_links.add(href)
        info["sample_detail_links"].append({"text": label[:80], "url": href})
        if len(info["sample_detail_links"]) >= 5:
            break

    return info


def inspect_target_website_for_scraping(user_text: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """
    Menjalankan inspeksi & analisis langsung (live DOM inspection) terhadap website target
    sebelum AI Agent merancang dan menulis kode scraper:
      Pass 1: Inspeksi halaman utama target (HTTP status, anti-bot/Cloudflare, form, DOM)
      Pass 2: Uji endpoint pencarian (bila ada template URL ?s={query} atau <form> pencarian)
      Pass 3: Uji 1 halaman detail konten nyata (bila diminta detail/sinopsis/episode)
    """
    is_scrape, base_urls, template_urls = detect_scraping_target_urls(user_text)
    if not is_scrape or not base_urls:
        return None

    target_url = base_urls[0]
    domain = urllib.parse.urlparse(target_url).netloc or target_url
    steps: List[Dict[str, Any]] = []
    report_blocks: List[str] = []

    def _format_dom_block(label: str, fetch_res: Dict[str, Any], dom_info: Optional[Dict[str, Any]]) -> str:
        lines = [
            f"### {label}",
            f"- URL: `{fetch_res.get('final_url') or fetch_res.get('url')}`",
            f"- HTTP Status: `{fetch_res.get('status_code')}` | Server: `{fetch_res.get('server') or 'unknown'}` | Cookies: `{fetch_res.get('cookies_count', 0)}`",
        ]
        if fetch_res.get("anti_bot_signals"):
            lines.append(f"- Anti-Bot / Proteksi Terdeteksi: `{', '.join(fetch_res['anti_bot_signals'])}`")
        if fetch_res.get("error"):
            lines.append(f"- Catatan Koneksi: `{fetch_res['error']}`")
        if dom_info:
            if dom_info.get("title"):
                lines.append(f"- Page `<title>`: `{dom_info['title']}`")
            if dom_info.get("forms"):
                for fm in dom_info["forms"][:2]:
                    lines.append(f"- Form: `{fm['method']} {fm['action']}` inputs=`{', '.join(fm['inputs'])}`")
            if dom_info.get("repeating_containers"):
                lines.append("- Selector Container Berulang (DOM Nyata):")
                for rc in dom_info["repeating_containers"][:3]:
                    lines.append(f"  * `{rc['selector']}` ({rc['count']} item) -> sampel HTML: `{rc['sample_html']}`")
            if dom_info.get("key_sections"):
                lines.append("- Selector Section/Konten Penting:")
                for ks in dom_info["key_sections"][:5]:
                    lines.append(f"  * `{ks['selector']}` -> \"{ks['text_preview']}\"")
            if dom_info.get("image_attrs"):
                lines.append(f"- Pola Atribut `<img>`: `{json.dumps(dom_info['image_attrs'][:2], ensure_ascii=False)}`")
        return "\n".join(lines)

    # Pass 1: Inspeksi Homepage / Target URL
    home_fetch = fetch_raw_html(target_url, timeout=timeout)
    home_dom = analyze_html_structure(home_fetch["html"], home_fetch["final_url"]) if home_fetch.get("success") else None
    report_blocks.append(_format_dom_block(f"Pass 1 - Homepage Target ({domain})", home_fetch, home_dom))
    steps.append({
        "id": "scrape_inspect_home",
        "title": f"Inspect Target Website ({domain})",
        "status": "done" if home_fetch.get("success") else "failed",
        "feedback": (
            f"HTTP {home_fetch['status_code']} · Title: {(home_dom or {}).get('title', '-')[:60]} · "
            f"{len((home_dom or {}).get('repeating_containers', []))} repeating DOM pattern(s) detected."
            if home_fetch.get("success")
            else f"HTTP {home_fetch['status_code']} · Proteksi/kendala: {', '.join(home_fetch.get('anti_bot_signals') or [home_fetch.get('error') or 'blocked'])}"
        ),
    })

    # Pass 2: Probe Search / Query Endpoint
    sample_query = "naruto" if any(k in user_text.lower() for k in ("anime", "otakudesu", "episode", "manga")) else "test"
    probe_search_url = ""
    if template_urls:
        probe_search_url = re.sub(r"\{[^}]+\}", urllib.parse.quote_plus(sample_query), template_urls[0])
    elif home_dom and home_dom.get("forms"):
        for fm in home_dom["forms"]:
            if fm["method"] == "GET" and fm["inputs"]:
                first_field = fm["inputs"][0].split("(")[0]
                sep = "&" if "?" in fm["action"] else "?"
                probe_search_url = f"{fm['action']}{sep}{urllib.parse.urlencode({first_field: sample_query})}"
                break

    search_dom: Optional[Dict[str, Any]] = None
    if probe_search_url:
        search_fetch = fetch_raw_html(probe_search_url, timeout=timeout, referer=target_url)
        search_dom = analyze_html_structure(search_fetch["html"], search_fetch["final_url"]) if search_fetch.get("success") else None
        report_blocks.append(_format_dom_block(f"Pass 2 - Live Search Endpoint Probe (?q={sample_query})", search_fetch, search_dom))
        steps.append({
            "id": "scrape_inspect_search",
            "title": f"Probe Search Endpoint ({domain})",
            "status": "done" if search_fetch.get("success") else "failed",
            "feedback": (
                f"HTTP {search_fetch['status_code']} · Found {len((search_dom or {}).get('repeating_containers', []))} result container(s) & "
                f"{len((search_dom or {}).get('sample_detail_links', []))} detail link(s)."
                if search_fetch.get("success")
                else f"Search probe HTTP {search_fetch['status_code']} ({', '.join(search_fetch.get('anti_bot_signals') or [search_fetch.get('error') or 'blocked'])})"
            ),
        })

    # Pass 3: Probe 1 Sample Detail Page (jika diminta detail/sinopsis/episode)
    wants_detail = any(k in user_text.lower() for k in ("detail", "sinopsis", "synopsis", "episode", "deep scraping", "/api/detail"))
    detail_link = None
    if search_dom and search_dom.get("sample_detail_links"):
        detail_link = search_dom["sample_detail_links"][0]["url"]
    elif home_dom and home_dom.get("sample_detail_links"):
        detail_link = home_dom["sample_detail_links"][0]["url"]

    if wants_detail and detail_link:
        detail_fetch = fetch_raw_html(detail_link, timeout=timeout, referer=probe_search_url or target_url)
        detail_dom = analyze_html_structure(detail_fetch["html"], detail_fetch["final_url"]) if detail_fetch.get("success") else None
        report_blocks.append(_format_dom_block("Pass 3 - Live Detail Page DOM Probe", detail_fetch, detail_dom))
        steps.append({
            "id": "scrape_inspect_detail",
            "title": f"Analyze Detail Page DOM ({domain})",
            "status": "done" if detail_fetch.get("success") else "failed",
            "feedback": (
                f"HTTP {detail_fetch['status_code']} · Inspected {len((detail_dom or {}).get('key_sections', []))} key section(s) & "
                f"{len((detail_dom or {}).get('repeating_containers', []))} list structure(s)."
                if detail_fetch.get("success")
                else f"Detail probe HTTP {detail_fetch['status_code']} ({', '.join(detail_fetch.get('anti_bot_signals') or [detail_fetch.get('error') or 'blocked'])})"
            ),
        })

    prompt_context = (
        f"\n\n[HASIL INSPEKSI LANGSUNG STRUKTUR DOM & JARINGAN TARGET SCRAPING ({domain})]:\n"
        + "\n\n".join(report_blocks)
        + "\n\n[ATURAN WAJIB AI AGENT SCRAPER]:\n"
        "1. Kamu SUDAH melakukan inspeksi langsung terhadap website target di atas — rancang arsitektur dan CSS selector scraper berdasarkan struktur HTML/DOM NYATA di atas, JANGAN menebak selector secara asal-asalan.\n"
        "2. Sediakan rantai fallback CSS selector yang tangguh (primary selector dari DOM hasil inspeksi + fallback selector) serta tangani atribut gambar yang ditemukan (`src`, `data-src`, `data-lazy-src`).\n"
        "3. Jika hasil inspeksi menunjukkan HTTP 403/503 atau Cloudflare/CAPTCHA, pastikan mekanisme fallback browser (Playwright Firefox / session cookie / solve-captcha) otomatis menangani kondisi tersebut dan juga tampilkan error/status yang informatif di UI (jangan diam kosong).\n"
        "4. Sebelum menulis kode, lakukan analisis singkat cara kerja situs target (endpoint pencarian, selector hasil, selector detail/episode, anti-bot, dan alur image proxy) lalu tulis kode produksi lengkap yang benar-benar cocok dengan DOM target.\n"
    )

    return {
        "target_url": target_url,
        "domain": domain,
        "steps": steps,
        "prompt_context": prompt_context,
        "summary": f"Inspected {domain} ({len(steps)} pass(es)) for live DOM selectors & anti-bot behavior.",
    }

