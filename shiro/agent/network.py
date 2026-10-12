# -*- coding: utf-8 -*-
"""
Shiro AI Agent Network Layer
Provides high-resilience networking via Cloudflare 1.1.1.1 DNS over HTTPS (DoH)
and authentic Mozilla Firefox HTTP headers to bypass anti-bot and ISP blocks.
"""

import ssl
import json
import socket
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, Tuple

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    requests = None

# Authentic Mozilla Firefox browser headers
MOZILLA_HEADERS: Dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1"
}

# Cache for DNS resolution to avoid repeated queries
_DNS_CACHE: Dict[str, str] = {}

def resolve_dns_cloudflare(hostname: str, timeout: float = 3.0) -> Optional[str]:
    """
    Melakukan resolusi DNS melalui Cloudflare 1.1.1.1 DNS over HTTPS (DoH).
    Mengembalikan alamat IP (IPv4) host yang dituju atau None jika gagal.
    """
    if not hostname:
        return None
        
    hostname = hostname.strip().lower()
    
    # Periksa IP langsung (IPv4)
    parts = hostname.split(".")
    if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
        return hostname

    # Periksa cache
    if hostname in _DNS_CACHE:
        return _DNS_CACHE[hostname]

    doh_url = f"https://1.1.1.1/dns-query?name={urllib.parse.quote(hostname)}&type=A"
    req = urllib.request.Request(
        doh_url,
        headers={
            "Accept": "application/dns-json",
            "User-Agent": MOZILLA_HEADERS["User-Agent"]
        }
    )
    
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            answers = data.get("Answer", [])
            for ans in answers:
                if ans.get("type") == 1 and ans.get("data"):  # Type 1 = A record (IPv4)
                    ip = ans["data"].strip()
                    _DNS_CACHE[hostname] = ip
                    return ip
    except Exception as e:
        # Fallback ke socket gethostbyname jika DoH terhambat
        try:
            ip = socket.gethostbyname(hostname)
            _DNS_CACHE[hostname] = ip
            return ip
        except Exception:
            pass
            
    return None

def get_agent_session() -> Any:
    """Membuat requests.Session dengan konfigurasi Mozilla & SSL toleran"""
    if requests is None:
        return None
    session = requests.Session()
    session.headers.update(MOZILLA_HEADERS)
    session.verify = False
    return session

def fetch_html_content(url: str, timeout: int = 10) -> Tuple[bool, str, Optional[str]]:
    """
    Mengambil konten HTML dari URL menggunakan header Mozilla dan SSL bypass.
    Returns: (success: bool, html_text: str, error_message: Optional[str])
    """
    if not url:
        return False, "", "URL kosong"

    # Resolusi host awal dengan Cloudflare 1.1.1.1 jika memungkinkan
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    if hostname:
        resolve_dns_cloudflare(hostname)

    if requests:
        try:
            session = get_agent_session()
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            if resp.status_code == 200:
                # Gunakan apparent_encoding jika tersedia untuk UTF-8/CP1252
                encoding = resp.encoding or "utf-8"
                return True, resp.text, None
            else:
                return False, resp.text, f"HTTP {resp.status_code}"
        except Exception as e_req:
            # Lanjut ke urllib fallback
            pass

    # Urllib fallback
    try:
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers=MOZILLA_HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw = resp.read()
            try:
                html = raw.decode("utf-8")
            except UnicodeDecodeError:
                html = raw.decode("latin-1", errors="ignore")
            return True, html, None
    except Exception as e_url:
        return False, "", str(e_url)
