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
