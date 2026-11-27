# -*- coding: utf-8 -*-
"""
Shiro AI Agent Network Layer
Provides high-resilience networking via Cloudflare 1.1.1.1 DNS over HTTPS (DoH)
and authentic Mozilla Firefox HTTP headers to bypass anti-bot and ISP blocks.
"""

import ssl
import json
import socket
import ipaddress
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, Tuple

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    requests = None

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

# Authentic latest Mozilla Firefox browser headers
MOZILLA_HEADERS: Dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/jpeg,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1"
}

FIREFOX_IMAGE_HEADERS: Dict[str, str] = {
    "User-Agent": MOZILLA_HEADERS["User-Agent"],
    "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.8",
    "Accept-Language": MOZILLA_HEADERS["Accept-Language"],
    "DNT": "1",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
}

def get_firefox_headers(referer: Optional[str] = None, accept: Optional[str] = None) -> Dict[str, str]:
    """Mengembalikan salinan HTTP headers Mozilla Firefox otentik (opsional dengan Referer & Accept)."""
    headers = dict(MOZILLA_HEADERS)
    if accept:
        headers["Accept"] = accept
    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin" if referer.startswith("http") else "cross-site"
    return headers

def get_firefox_session(prefer_curl_cffi: bool = True) -> Any:
    """Membuat HTTP session berprofil Mozilla Firefox (curl_cffi TLS impersonation jika tersedia)."""
    if prefer_curl_cffi and curl_requests is not None:
        try:
            sess = curl_requests.Session(impersonate="firefox133")
            sess.headers.update(MOZILLA_HEADERS)
            sess.verify = False
            return sess
        except Exception:
            pass
    return get_agent_session()

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


def _is_disallowed_ip(ip_str: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        )
    except ValueError:
        return True


def is_safe_external_url(url: str) -> bool:
    """
    Memvalidasi URL eksternal http/https agar aman diambil server (mencegah SSRF ke localhost/LAN/metadata IP).
    """
    if not url or not isinstance(url, str):
        return False
    raw = url.strip()
    if len(raw) > 2048:
        return False
    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception:
        return False
    if parsed.scheme.lower() not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host in ("localhost", "ip6-localhost", "metadata.google.internal") or host.endswith((".local", ".internal", ".localhost")):
        return False

    # Jika host berupa literal IP, blokir rentang privat/loopback/link-local
    try:
        ipaddress.ip_address(host)
        return not _is_disallowed_ip(host)
    except ValueError:
        pass

    # Cek resolusi DNS lokal jika bisa di-resolve (blokir DNS yang mengarah ke privat/loopback)
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        for info in infos:
            addr = info[4][0]
            if _is_disallowed_ip(addr):
                return False
    except Exception:
        # Bisa saja host hanya dapat di-resolve lewat Cloudflare DoH; pastikan bukan domain lokal
        if "." not in host:
            return False
    return True


def fetch_image_bytes(
    url: str,
    referer: Optional[str] = None,
    timeout: int = 10,
    max_bytes: int = 15 * 1024 * 1024,
) -> Tuple[bool, bytes, str, Optional[str]]:
    """
    Mengunduh biner gambar eksternal dengan header Mozilla Firefox otentik & validasi SSRF/MIME.
    Mengembalikan (success, image_bytes, content_type, error_message).
    """
    if not is_safe_external_url(url):
        return False, b"", "", "URL tidak diizinkan atau bukan URL eksternal yang valid."

    headers = dict(FIREFOX_IMAGE_HEADERS)
    if referer and is_safe_external_url(referer):
        headers["Referer"] = referer
    else:
        parsed = urllib.parse.urlparse(url)
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    def _validate_and_trim(data: bytes, ctype: str) -> Tuple[bool, bytes, str, Optional[str]]:
        if not data:
            return False, b"", "", "Respons gambar kosong."
        if len(data) > max_bytes:
            return False, b"", "", "Ukuran gambar melebihi batas maksimal."
        clean_ct = (ctype or "").split(";")[0].strip().lower()
        if not clean_ct.startswith("image/"):
            # Deteksi magic bytes dasar untuk server yang mengirim octet-stream
            if data[:3] == b"\xff\xd8\xff":
                clean_ct = "image/jpeg"
            elif data[:8] == b"\x89PNG\r\n\x1a\n":
                clean_ct = "image/png"
            elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                clean_ct = "image/webp"
            elif data[:6] in (b"GIF87a", b"GIF89a"):
                clean_ct = "image/gif"
            else:
                return False, b"", "", f"Tipe konten bukan gambar ({clean_ct or 'unknown'})."
        return True, data, clean_ct, None

    if curl_requests is not None:
        try:
            r = curl_requests.get(url, headers=headers, impersonate="firefox133", timeout=timeout, verify=False, allow_redirects=True)
            if r.status_code == 200:
                ok, b, ct, err = _validate_and_trim(r.content, r.headers.get("Content-Type", ""))
                if ok:
                    return True, b, ct, None
        except Exception:
            pass

    if requests is not None:
        try:
            sess = get_agent_session()
            r = sess.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return _validate_and_trim(r.content, r.headers.get("Content-Type", ""))
            return False, b"", "", f"HTTP {r.status_code}"
        except Exception as e_req:
            err_msg = str(e_req)
    else:
        err_msg = "requests unavailable"

    try:
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw = resp.read(max_bytes + 1)
            ctype = resp.headers.get("Content-Type", "")
            return _validate_and_trim(raw, ctype)
    except Exception as e_u:
        return False, b"", "", err_msg or str(e_u)
