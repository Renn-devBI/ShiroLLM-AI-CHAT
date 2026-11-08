"""
Module Real-Time Web Intelligence & Multilingual Multi-Source Verification (v2).
Mendukung:
1. Klasifikasi Intent Multibahasa (ID, EN, JA, KO, ZH, ES, FR, DE, PT, RU, AR) + register_language()
2. Penyelarasan Jam Sistem vs HTTP Server Date (WIB, WITA, WIT, JST)
3. Pembuatan Kueri Cerdas (Injeksi Tahun Berjalan, Variasi Global/Inggris)
4. Pencarian Multi-Sumber Adaptif (3 s/d 10 sumber independen)
5. Verifikasi Silang (Anti-Sindikasi Berita, Deteksi Konflik Angka/Fakta, Peringkat Entitas)
6. Penapisan Memori Jangka Panjang (Hanya fakta 'verified' yang boleh disimpan)
"""

import os
import re
import time
import math
import json
import socket
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple, Callable

# ---------------------------------------------------------------------------
# 1. ZONA WAKTU & SINKRONISASI JAM TERVERIFIKASI
# ---------------------------------------------------------------------------

OFFSET_WIB = timezone(timedelta(hours=7), name="WIB")
OFFSET_WITA = timezone(timedelta(hours=8), name="WITA")
OFFSET_WIT = timezone(timedelta(hours=9), name="WIT")
OFFSET_JST = timezone(timedelta(hours=9), name="JST")

_CLOCK_CACHE = {"offset_seconds": 0.0, "last_check": 0.0}

def get_verified_now(
    server_urls: Optional[List[str]] = None,
    timeout: float = 3.0,
    force_refresh: bool = False
) -> datetime:
    """
    Mengembalikan waktu datetime (UTC) saat ini yang telah diverifikasi dengan
    header 'Date' dari HTTP server independen. Jika selisih jam sistem lokal > 120 detik,
    median offset server digunakan untuk mengoreksi waktu sistem.
    """
    now_mono = time.monotonic()
    if not force_refresh and (now_mono - _CLOCK_CACHE["last_check"] < 3600.0):
        corr_sec = _CLOCK_CACHE["offset_seconds"]
        return datetime.now(timezone.utc) + timedelta(seconds=corr_sec)

    servers = server_urls or [
        "https://www.cloudflare.com",
        "https://www.google.com",
        "https://1.1.1.1",
        "https://www.wikipedia.org"
    ]

    offsets = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ShiroIntel/2.0"}

    for url in servers:
        try:
            req = urllib.request.Request(url, headers=headers, method="HEAD")
            t_send = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                date_hdr = resp.headers.get("Date")
                t_recv = time.time()
            if date_hdr:
                server_dt = parsedate_to_datetime(date_hdr)
                if server_dt.tzinfo is None:
                    server_dt = server_dt.replace(tzinfo=timezone.utc)
                else:
                    server_dt = server_dt.astimezone(timezone.utc)
                rtt = max(0.0, t_recv - t_send)
                local_mid = datetime.fromtimestamp(t_send + rtt / 2.0, tz=timezone.utc)
                diff = (server_dt - local_mid).total_seconds()
                offsets.append(diff)
        except Exception:
            continue

    chosen_offset = 0.0
    if offsets:
        offsets.sort()
        mid = len(offsets) // 2
        median_diff = (offsets[mid] if len(offsets) % 2 != 0 else (offsets[mid - 1] + offsets[mid]) / 2.0)
        # Jika selisih lebih dari 120 detik, pakai koreksi server
        if abs(median_diff) > 120.0:
            chosen_offset = median_diff

    _CLOCK_CACHE["offset_seconds"] = chosen_offset
    _CLOCK_CACHE["last_check"] = now_mono

    return datetime.now(timezone.utc) + timedelta(seconds=chosen_offset)


HARI_INDONESIA = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN_INDONESIA = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
]

def format_verified_time_info() -> Dict[str, Any]:
    """
    Format informasi waktu lengkap dalam zona WIB, WITA, WIT, dan JST.
    """
    now_utc = get_verified_now()
    now_wib = now_utc.astimezone(OFFSET_WIB)
    now_jst = now_utc.astimezone(OFFSET_JST)

    hari_nama = HARI_INDONESIA[now_wib.weekday()]
    bulan_nama = BULAN_INDONESIA[now_wib.month]

    summary = (
        f"Saat ini adalah hari {hari_nama}, tanggal {now_wib.day} {bulan_nama} {now_wib.year}.\n"
        f"Waktu real-time Indonesia: {now_wib.strftime('%H:%M:%S')} WIB | "
        f"Waktu Tokyo (JST): {now_jst.strftime('%H:%M:%S')} JST."
    )
    return {
        "success": True,
        "summary": summary,
        "day": hari_nama,
        "date": f"{now_wib.day} {bulan_nama} {now_wib.year}",
        "year": now_wib.year,
        "time_wib": now_wib.strftime("%H:%M:%S"),
        "time_jst": now_jst.strftime("%H:%M:%S"),
        "iso": now_wib.isoformat()
    }


def time_prompt_block() -> str:
    """
    Blok prompt waktu singkat yang selalu disuntikkan ke konteks Shiro.
    """
    info = format_verified_time_info()
    return (
        f"[Waktu & Kalender Nyata Real-Time]:\n"
        f"- Hari & Tanggal: {info['day']}, {info['date']}\n"
        f"- Jam Terkini: {info['time_wib']} WIB / {info['time_jst']} JST\n"
        f"- Tahun Berjalan: {info['year']}\n"
    )

# ---------------------------------------------------------------------------
# 2. LEKSIKON MULTIBAHASA & KLASIFIKASI INTENT
# ---------------------------------------------------------------------------

@dataclass
class LanguageLexicon:
    code: str
    temporal_words: List[str]
    trend_words: List[str]
    inquiry_words: List[str]
    officeholder_words: List[str]
    personal_signals: List[str]
    time_only_patterns: List[str]
    fillers: List[str]
    year_markers: List[str]


LANGUAGE_REGISTRY: Dict[str, LanguageLexicon] = {}

def register_language(lex: LanguageLexicon):
    LANGUAGE_REGISTRY[lex.code] = lex


# 1. Bahasa Indonesia (id)
register_language(LanguageLexicon(
    code="id",
    temporal_words=[
        "tahun ini", "saat ini", "sekarang", "hari ini", "bulan ini", "minggu ini",
        "musim ini", "terbaru", "terkini", "update", "kemarin", "baru rilis",
        "mendatang", "besok", "lusa", "jadwal rilis", "jadwal tayang", "lagi tayang",
        "sedang tayang", "tayang hari ini", "tayang", "on-going", "ongoing", "airing"
    ],
    trend_words=[
        "populer", "trending", "viral", "terbaik", "top", "rekomendasi",
        "peringkat", "favorit", "terlaris", "unggulan", "juara", "pemenang",
        "skor", "klasemen", "harga", "kurs", "spesifikasi", "review", "ulasan"
    ],
    inquiry_words=[
        "cari tahu", "carikan", "cariin", "tolong cek", "coba cek", "lihatin",
        "info tentang", "informasi tentang", "berita", "artikel", "kabar",
        "ada info", "apakah sudah rilis", "kapan rilis", "apa saja", "apa aja",
        "ada apa saja", "ada apa aja", "daftar", "list", "sebutkan", "apa yang",
        "mana saja", "mana aja"
    ],
    officeholder_words=[
        "siapa presiden", "siapa wakil presiden", "siapa menteri", "siapa ceo",
        "siapa ketua", "siapa juara", "siapa pemenang", "siapa gubernur"
    ],
    personal_signals=[
        "aku capek", "aku lelah", "aku sedih", "aku bingung", "aku galau",
        "patah hati", "lagi sedih", "perasaanku", "peluk", "sayang kamu",
        "kamu lagi apa", "lagi ngapain", "kangen", "sayang shiro", "aku lapar"
    ],
    time_only_patterns=[
        r"(?:hari|tanggal|jam|waktu|bulan|tahun)\s+(?:apa|berapa|sekarang|ini)",
        r"(?:sekarang|saat ini)\s+(?:hari|tanggal|jam|pukul|waktu)\s+(?:apa|berapa)",
        r"(?:cek|lihat|tahu)\s+(?:saat ini|sekarang)\s+hari\s+apa",
        r"hari\s+apa\s+(?:saat ini|sekarang|hari ini)",
        r"tanggal\s+berapa\s+(?:saat ini|sekarang|hari ini)"
    ],
    fillers=["tolong", "coba", "dong", "sih", "ya", "kak", "shiro", "dek", "mohon", "apa saja", "apa aja"],
    year_markers=["tahun ini", "saat ini"]
))

# 2. Bahasa Inggris (en)
register_language(LanguageLexicon(
    code="en",
    temporal_words=[
        "this year", "currently", "now", "today", "this month", "this week",
        "this season", "latest", "recent", "update", "newest", "upcoming", "released"
    ],
    trend_words=[
        "popular", "trending", "viral", "best", "top", "recommended", "ranking",
        "favorite", "bestseller", "winner", "score", "standings", "price", "specs", "review"
    ],
    inquiry_words=[
        "find out", "look up", "check", "search for", "info about", "information about",
        "news", "article", "what is the latest", "when is the release"
    ],
    officeholder_words=[
        "who is the president", "who is the prime minister", "who is the ceo", "who won"
    ],
    personal_signals=[
        "i am tired", "i'm tired", "i'm sad", "i feel sad", "heartbroken", "hug me",
        "i love you", "what are you doing", "i miss you", "i'm so tired"
    ],
    time_only_patterns=[
        r"what\s+(?:day|date|time)\s+is\s+it",
        r"what\s+is\s+today'?s\s+(?:date|day)",
        r"current\s+(?:time|date|day)",
        r"tell\s+me\s+the\s+(?:time|date|day)"
    ],
    fillers=["please", "can you", "could you", "tell me", "shiro", "hey"],
    year_markers=["this year", "currently"]
))

# 3. Bahasa Jepang (ja)
register_language(LanguageLexicon(
    code="ja",
    temporal_words=["今年", "現在", "今", "今日", "今月", "今週", "最新", "最近", "アップデート", "新作", "発売日"],
    trend_words=["人気", "トレンド", "おすすめ", "ランキング", "最高", "トップ", "受賞", "優勝", "価格", "レビュー"],
    inquiry_words=["調べて", "検索して", "教えて", "ニュース", "情報", "記事", "どうなっている"],
    officeholder_words=["大統領は誰", "首相は誰", "社長は誰", "勝者は誰"],
    personal_signals=["疲れた", "寂しい", "悲しい", "辛い", "抱きしめて", "大好き", "何してるの", "会いたい"],
    time_only_patterns=[r"今何時", r"今日は何曜日", r"今日は何日", r"現在の日時"],
    fillers=["お願い", "教えて", "シロ", "ちょっと", "ねえ"],
    year_markers=["今年", "現在"]
))

# 4. Bahasa Korea (ko)
register_language(LanguageLexicon(
    code="ko",
    temporal_words=["올해", "현재", "지금", "오늘", "이번 달", "이번 주", "최신", "업데이트", "출시일"],
    trend_words=["인기", "트렌드", "추천", "랭킹", "최고", "톱", "우승", "가격", "리뷰"],
    inquiry_words=["알아봐줘", "검색해줘", "알려줘", "뉴스", "정보", "기사"],
    officeholder_words=["대통령은 누구", "총리는 누구", "대표는 누구"],
    personal_signals=["피곤해", "우울해", "슬퍼", "안아줘", "사랑해", "보고싶어", "뭐해"],
    time_only_patterns=[r"지금 몇 시", r"오늘 무슨 요일", r"오늘 며칠"],
    fillers=["부탁해", "시로", "좀"],
    year_markers=["올해", "현재"]
))

# 5. Bahasa Mandarin (zh)
register_language(LanguageLexicon(
    code="zh",
    temporal_words=["今年", "目前", "现在", "今天", "本月", "本周", "最新", "最近", "更新", "发售日"],
    trend_words=["热门", "流行", "推荐", "排行榜", "最好", "顶级", "冠军", "价格", "评测"],
    inquiry_words=["查一下", "搜索", "告诉我", "新闻", "资讯", "文章"],
    officeholder_words=["总统是谁", "总理是谁", "ceo是谁", "谁赢了"],
    personal_signals=["我好累", "难过", "伤心", "抱抱我", "我爱你", "你在干嘛", "想你"],
    time_only_patterns=[r"现在几点", r"今天星期几", r"今天是几号"],
    fillers=["请", "帮我", "白", "一下"],
    year_markers=["今年", "目前"]
))

# 6. Bahasa Spanyol (es)
register_language(LanguageLexicon(
    code="es",
    temporal_words=["este año", "actualmente", "ahora", "hoy", "este mes", "esta semana", "último", "reciente", "novedades"],
    trend_words=["popular", "tendencia", "viral", "mejor", "top", "recomendado", "ranking", "ganador", "precio"],
    inquiry_words=["averigua", "busca", "revisa", "información sobre", "noticias", "artículo"],
    officeholder_words=["quién es el presidente", "quién es el primer ministro", "quién ganó"],
    personal_signals=["estoy cansado", "estoy triste", "abrázame", "te amo", "qué haces", "te extraño"],
    time_only_patterns=[r"qué hora es", r"qué día es hoy", r"cuál es la fecha de hoy"],
    fillers=["por favor", "puedes", "dime", "shiro"],
    year_markers=["este año", "actualmente"]
))

# 7. Bahasa Prancis (fr)
register_language(LanguageLexicon(
    code="fr",
    temporal_words=["cette année", "actuellement", "maintenant", "aujourd'hui", "ce mois-ci", "cette semaine", "dernier", "récent"],
    trend_words=["populaire", "tendance", "meilleur", "top", "recommandé", "classement", "gagnant", "prix"],
    inquiry_words=["renseigne-toi", "cherche", "vérifie", "informations sur", "actualités", "article"],
    officeholder_words=["qui est le président", "qui a gagné"],
    personal_signals=["je suis fatigué", "je suis triste", "serre-moi", "je t'aime", "tu fais quoi"],
    time_only_patterns=[r"quelle heure est-il", r"quel jour sommes-nous", r"quelle est la date d'aujourd'hui"],
    fillers=["s'il te plaît", "peux-tu", "dis-moi", "shiro"],
    year_markers=["cette année", "actuellement"]
))

# 8. Bahasa Jerman (de)
register_language(LanguageLexicon(
    code="de",
    temporal_words=["dieses jahr", "derzeit", "jetzt", "heute", "diesen monat", "diese woche", "neueste", "aktuell"],
    trend_words=["beliebt", "trending", "beste", "top", "empfohlen", "rangliste", "gewinner", "preis"],
    inquiry_words=["finde heraus", "suche", "prüfe", "informationen über", "nachrichten", "artikel"],
    officeholder_words=["wer ist der präsident", "wer ist der kanzler", "wer hat gewonnen"],
    personal_signals=["ich bin müde", "ich bin traurig", "umarm mich", "ich liebe dich", "was machst du"],
    time_only_patterns=[r"wie viel uhr ist es", r"welcher tag ist heute", r"welches datum haben wir"],
    fillers=["bitte", "kannst du", "sag mir", "shiro"],
    year_markers=["dieses jahr", "derzeit"]
))

# 9. Bahasa Portugis (pt)
register_language(LanguageLexicon(
    code="pt",
    temporal_words=["este ano", "deste ano", "atualmente", "actualmente", "agora", "hoje", "este mês", "esta semana", "último", "recente"],
    trend_words=["melhores", "melhor", "popular", "tendência", "top", "recomendado", "ranking", "vencedor", "preço"],
    inquiry_words=["descubra", "procure", "verifique", "informações sobre", "notícias", "artigo"],
    officeholder_words=["quem é o presidente", "quem ganhou"],
    personal_signals=["estou cansado", "estou triste", "me abraça", "eu te amo", "o que você está fazendo"],
    time_only_patterns=[r"que horas são", r"que dia é hoje", r"qual é a data de hoje"],
    fillers=["por favor", "você pode", "me diga", "shiro", "quais", "são", "os"],
    year_markers=["este ano", "deste ano", "atualmente"]
))

# 10. Bahasa Rusia (ru)
register_language(LanguageLexicon(
    code="ru",
    temporal_words=["в этом году", "сейчас", "сегодня", "в этом месяце", "на этой неделе", "последний", "свежий", "новинки"],
    trend_words=["популярный", "популярные", "самые популярные", "тренды", "лучший", "лучшие", "топ", "рекомендации", "рейтинг", "победитель", "цена"],
    inquiry_words=["узнай", "найди", "проверь", "информация о", "новости", "статья", "какие"],
    officeholder_words=["кто президент", "кто победил"],
    personal_signals=["я устал", "мне грустно", "обними меня", "я люблю тебя", "что делаешь"],
    time_only_patterns=[r"который час", r"какой сегодня день", r"какое сегодня число"],
    fillers=["пожалуйста", "скажи мне", "широ"],
    year_markers=["в этом году", "сейчас"]
))

# 11. Bahasa Arab (ar)
register_language(LanguageLexicon(
    code="ar",
    temporal_words=["هذا العام", "حاليا", "الآن", "اليوم", "هذا الشهر", "هذا الأسبوع", "أحدث", "جديد"],
    trend_words=["شائع", "شعبية", "الأكثر", "أكثر", "ترند", "أفضل", "أعلى", "موصى به", "ترتيب", "الفائز", "سعر"],
    inquiry_words=["اكتشف", "ابحث عن", "تحقق من", "معلومات عن", "أخبار", "مقال"],
    officeholder_words=["من هو الرئيس", "من فاز"],
    personal_signals=["أنا متعب", "أنا حزين", "احضني", "أحبك", "ماذا تفعل"],
    time_only_patterns=[r"كم الساعة", r"ما هو اليوم", r"ما هو تاريخ اليوم"],
    fillers=["من فضلك", "هل يمكنك", "أخبرني", "شيرو"],
    year_markers=["هذا العام", "حاليا"]
))


def detect_query_language(text: str) -> str:
    """
    Mendeteksi kode bahasa teks (id, en, ja, ko, zh, ru, ar, es, fr, de, pt)
    berdasarkan skrip dan kemunculan leksikon khas.
    """
    if not text:
        return "id"

    # 1. Deteksi berbasis skrip karakter
    if re.search(r'[\u3040-\u30ff]', text):
        return "ja"
    if re.search(r'[\uac00-\ud7af]', text):
        return "ko"
    if re.search(r'[\u4e00-\u9fff]', text):
        return "zh"
    if re.search(r'[\u0400-\u04ff]', text):
        return "ru"
    if re.search(r'[\u0600-\u06ff]', text):
        return "ar"

    lower = text.lower()
    
    # 2. Skor kecocokan kata untuk bahasa berbasis alfabet Latin dan bahasa terdaftar lainnya
    best_lang = "id"
    best_matches = 0

    for code, lex in LANGUAGE_REGISTRY.items():
        if code in ["ja", "ko", "zh", "ru", "ar"]:
            continue
        matches = 0
        all_words = lex.temporal_words + lex.trend_words + lex.inquiry_words + lex.personal_signals + lex.fillers
        for w in all_words:
            if re.search(r'\b' + re.escape(w) + r'\b', lower):
                matches += 1
        if matches > best_matches:
            best_matches = matches
            best_lang = code
        for w in all_words:
            if re.search(r'\b' + re.escape(w) + r'\b', lower):
                matches += 1
        if matches > best_matches:
            best_matches = matches
            best_lang = code

    # Fallback jika tidak ada kata yang cocok: cek stopword khas Indonesia vs Inggris
    if best_matches == 0:
        if any(w in lower.split() for w in ["yang", "di", "ini", "apa", "saat", "dan", "kamu", "kakak", "aku"]):
            return "id"
        if any(w in lower.split() for w in ["the", "is", "what", "how", "this", "and", "you", "for"]):
            return "en"

    return best_lang


@dataclass
class IntentResult:
    kind: str  # "time", "search", "none"
    lang: str
    score: float
    confidence: float
    raw_query: str
    reasons: List[str] = field(default_factory=list)


def classify_intent(text: str) -> IntentResult:
    """
    Mengklasifikasikan input pengguna menjadi 'time', 'search', atau 'none'.
    Skor dihitung dari:
    - Temporal words (+2.0 s/d +3.0)
    - Trend / Ranking (+1.5 s/d +2.0)
    - Inquiry (+1.5)
    - Officeholder question (+2.5)
    - Tahun berjalan angka (+1.5)
    - Explicit search (+3.0)
    - Personal / Curhat signal (-3.0)
    Ambang batas pencarian web: score >= 2.5
    """
    raw = (text or "").strip()
    if not raw:
        return IntentResult(kind="none", lang="id", score=0.0, confidence=1.0, raw_query="")

    lower = raw.lower()
    detected_lang = detect_query_language(raw)

    # Selalu cek bahasa terdeteksi + EN + ID (karena pengguna sering mencampur bahasa)
    langs_to_check = {detected_lang, "en", "id"}

    # 1. Pengecekan Waktu Murni (Jam / Hari / Tanggal)
    for lcode in langs_to_check:
        lex = LANGUAGE_REGISTRY.get(lcode)
        if not lex:
            continue
        for pat in lex.time_only_patterns:
            if re.search(pat, lower):
                # Pastikan ini pertanyaan waktu murni, bukan menanyakan artikel/berita
                if not any(k in lower for k in ["anime", "berita", "artikel", "harga", "skor", "film"]):
                    return IntentResult(
                        kind="time",
                        lang=detected_lang,
                        score=5.0,
                        confidence=0.95,
                        raw_query=raw,
                        reasons=[f"Pola waktu murni: '{pat}' ({lcode})"]
                    )

    # 2. Pengecekan Skor Pencarian Web Semantik
    score = 0.0
    reasons = []

    # Sinyal eksplisit perintah cari
    explicit_cmds = [
        "cari di web", "googling", "browsing", "search the web", "search google",
        "tolong carikan artikel", "cari berita", "cek di internet", "search online"
    ]
    for cmd in explicit_cmds:
        if cmd in lower:
            score += 3.0
            reasons.append(f"Perintah eksplisit: {cmd}")
            break

    # Sinyal spesifik web / situs / platform konten
    site_triggers = [
        "otakudesu", "samehadaku", "anoboy", "komikcast", "myanimelist", "mal", "anilist",
        "netflix", "iqiyi", "bilibili", "bstation", "crunchyroll", "wikipedia", "youtube",
        "detik", "kompas", "cnn", "kumparan", "tirto", "github", "reddit", "twitter"
    ]
    for st in site_triggers:
        if st in lower:
            score += 2.5
            reasons.append(f"Penyebutan platform/situs: '{st}'")
            break

    web_mention = re.search(r'\b(?:di\s+)?(?:web|situs|website)\s+([a-zA-Z0-9\-_]+)', lower)
    if web_mention and not any(st in lower for st in site_triggers):
        score += 2.0
        reasons.append(f"Penyebutan web: '{web_mention.group(0)}'")

    # Sinyal domain konten & media
    content_domain_words = [
        "anime", "manga", "film", "movie", "bioskop", "drakor", "drama", "series",
        "game", "lagu", "musik", "jadwal", "episode", "chapter", "komik"
    ]
    for cw in content_domain_words:
        if cw in lower:
            score += 1.5
            reasons.append(f"Topik Konten: '{cw}'")
            break

    # Cek leksikon temporal, tren, inkuiri, pemegang jabatan
    found_temporal = False
    found_trend = False
    found_inquiry = False
    found_office = False

    for lcode in langs_to_check:
        lex = LANGUAGE_REGISTRY.get(lcode)
        if not lex:
            continue

        if not found_temporal:
            for w in lex.temporal_words:
                if w in lower:
                    score += 2.0
                    found_temporal = True
                    reasons.append(f"Temporal: '{w}' ({lcode})")
                    break

        if not found_trend:
            for w in lex.trend_words:
                if w in lower:
                    score += 1.5
                    found_trend = True
                    reasons.append(f"Tren/Peringkat: '{w}' ({lcode})")
                    break

        if not found_inquiry:
            for w in lex.inquiry_words:
                if w in lower:
                    score += 1.5
                    found_inquiry = True
                    reasons.append(f"Inkuiri: '{w}' ({lcode})")
                    break

        if not found_office:
            for w in lex.officeholder_words:
                if w in lower:
                    score += 2.5
                    found_office = True
                    reasons.append(f"Pemegang jabatan: '{w}' ({lcode})")
                    break

    # Cek angka tahun berjalan atau tahun depan (2025, 2026, 2027)
    curr_yr = datetime.now().year
    years_to_check = [str(curr_yr), str(curr_yr - 1), str(curr_yr + 1)]
    for y_str in years_to_check:
        if y_str in lower:
            score += 1.5
            reasons.append(f"Tahun: {y_str}")
            break

    # Filter Sinyal Personal / Curhat (Anti False-Positive)
    # Jika pengguna sedang curhat emosional ("aku capek", "i feel sad", "疲れた"), kurangi 3.0 poin
    for lcode in langs_to_check:
        lex = LANGUAGE_REGISTRY.get(lcode)
        if not lex:
            continue
        for sig in lex.personal_signals:
            if sig in lower:
                score -= 3.0
                reasons.append(f"Sinyal personal/curhat (-3.0): '{sig}' ({lcode})")
                break

    kind = "search" if score >= 2.5 else "none"
    conf = min(0.99, max(0.1, score / 4.0))

    return IntentResult(
        kind=kind,
        lang=detected_lang,
        score=score,
        confidence=conf,
        raw_query=raw,
        reasons=reasons
    )

# ---------------------------------------------------------------------------
# 3. BUILD QUERIES (INJEKSI TAHUN & VARIAN MULTIBAHASA)
# ---------------------------------------------------------------------------

@dataclass
class SearchQuery:
    query: str
    lang: str
    is_primary: bool = True


def build_queries(
    user_input: str,
    detected_lang: Optional[str] = None,
    current_year: Optional[int] = None,
    llm_rewrite: Optional[Callable[[str, str], str]] = None
) -> List[SearchQuery]:
    """
    Membuat kueri pencarian yang dioptimalkan:
    1. Membuang filler percakapan sesuai bahasa
    2. Mengganti frasa 'tahun ini' dengan tahun aktual
    3. Menambahkan tahun jika ada kata 'terbaru / latest' tanpa tahun
    4. Menyertakan varian bahasa Inggris untuk menjangkau sumber global
    """
    if not user_input:
        return []

    lang = detected_lang or detect_query_language(user_input)
    yr = current_year or datetime.now().year

    clean = user_input.strip()

    # Hapus awalan percakapan transisi / reset (misal: "oke lupakan", "lupakan", "abaikan", "skip", "btw")
    clean = re.sub(
        r'^(?:oke\s+)?(?:lupakan(?:\s+(?:yang\s+)?tadi)?|abaikan|skip|ganti\s+topik|ngomong-ngomong|btw|by\s+the\s+way)\s*[,.:;!-]?\s*',
        '',
        clean,
        flags=re.IGNORECASE
    ).strip()

    # Hapus awalan perintah cari eksplisit jika ada
    clean = re.sub(
        r'^(?:tolong\s+)?(?:cari\s+(?:tahu|di\s+web|informasi|info|berita)?|googling|browsing|search\s+(?:the\s+web|for)?)\s*(?:tentang|mengenai|about)?\s*[:,-]?\s*',
        '',
        clean,
        flags=re.IGNORECASE
    ).strip()

    # Buang filler sesuai bahasa
    lex = LANGUAGE_REGISTRY.get(lang)
    if lex:
        for f in lex.fillers:
            clean = re.sub(r'\b' + re.escape(f) + r'\b', '', clean, flags=re.IGNORECASE).strip()

    # Ganti penanda 'tahun ini' / 'this year' dengan angka tahun
    clean_lower = clean.lower()
    has_year = any(str(y) in clean_lower for y in range(2020, 2035))

    subbed = False
    if lex:
        for ym in lex.year_markers:
            if ym in clean_lower:
                clean = re.sub(re.escape(ym), str(yr), clean, flags=re.IGNORECASE)
                subbed = True
                break

    if not subbed and not has_year:
        # Jika ada kata 'terbaru' / 'latest' tapi belum ada tahun, tambahkan tahun berjalan
        if any(w in clean_lower for w in ["terbaru", "terkini", "latest", "recent", "最新", "최신"]):
            clean = f"{clean} {yr}"

    # Bersihkan spasi ganda dan tanda baca tanya di akhir
    clean = re.sub(r'[\?؟!]+$', '', clean).strip()
    clean = re.sub(r'\s+', ' ', clean)

    queries: List[SearchQuery] = [SearchQuery(query=clean, lang=lang, is_primary=True)]

    # Buat varian bahasa Inggris jika bahasa utama bukan Inggris
    if lang != "en":
        en_query = ""
        if llm_rewrite:
            try:
                en_query = llm_rewrite(clean, "en")
            except Exception:
                en_query = ""
        
        # Kamus translasi cepat fallback ID -> EN
        if not en_query and lang == "id":
            id_to_en = {
                "anime populer": "popular anime",
                "terbaik": "best",
                "berita": "news",
                "terbaru": "latest",
                "harga": "price",
                "jadwal rilis": "release schedule",
                "film": "movies",
                "game": "games",
                "apa": "what"
            }
            tmp = clean.lower()
            for k, v in id_to_en.items():
                tmp = tmp.replace(k, v)
            if tmp != clean.lower():
                en_query = tmp

        if en_query and en_query.strip().lower() != clean.lower():
            queries.append(SearchQuery(query=en_query.strip(), lang="en", is_primary=False))

    return queries

# ---------------------------------------------------------------------------
# 4. KREDIBILITAS DOMAIN & KONFIGURASI PENELITIAN
# ---------------------------------------------------------------------------

DEFAULT_DOMAIN_CREDIBILITY: Dict[str, float] = {
    # Ensiklopedia & Basis Data Resmi
    "wikipedia.org": 1.4,
    "myanimelist.net": 1.4,
    "animenewsnetwork.com": 1.4,
    "imdb.com": 1.3,
    "github.com": 1.3,
    "gov": 1.5,
    "go.id": 1.5,
    "edu": 1.4,
    "ac.id": 1.4,

    # Media Berita Kredibel Indonesia & Global
    "antaranews.com": 1.3,
    "kompas.com": 1.3,
    "tempo.co": 1.25,
    "detik.com": 1.2,
    "cnnindonesia.com": 1.2,
    "bbc.com": 1.4,
    "reuters.com": 1.4,
    "apnews.com": 1.4,
    "theverge.com": 1.3,
    "techcrunch.com": 1.3,
    "ign.com": 1.3,

    # Forum & Media Sosial (Bobot Rendah)
    "reddit.com": 0.6,
    "quora.com": 0.5,
    "twitter.com": 0.5,
    "x.com": 0.5,
    "facebook.com": 0.4,
    "kaskus.co.id": 0.5,
    "tiktok.com": 0.4
}

def get_domain_weight(url: str, custom_table: Optional[Dict[str, float]] = None) -> float:
    table = custom_table or DEFAULT_DOMAIN_CREDIBILITY
    if not url:
        return 1.0
    try:
        domain = urllib.parse.urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        for d, weight in table.items():
            if domain == d or domain.endswith("." + d):
                return weight
    except Exception:
        pass
    return 1.0


@dataclass
class ResearchConfig:
    default_sources: int = 3
    max_sources: int = 10
    batch_size: int = 2
    min_agree: int = 2
    min_confidence: float = 0.6
    cluster_overlap: float = 0.50
    credibility: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_DOMAIN_CREDIBILITY))

# ---------------------------------------------------------------------------
# 5. PEMROSESAN TEKS, ANTI-SINDIKASI, & VERIFIKASI SILANG
# ---------------------------------------------------------------------------

@dataclass
class RawSearchResult:
    title: str
    url: str
    snippet: str
    source_engine: str = "web"
    score: float = 1.0


@dataclass
class FetchedDocument:
    url: str
    domain: str
    title: str
    full_text: str
    snippet: str
    is_full_article: bool
    credibility: float = 1.0


@dataclass
class VerifiedFact:
    claim: str
    status: str  # "verified", "conflict", "single"
    supporting_sources: List[str]
    supporting_domains: List[str]
    conflicting_info: Optional[str] = None
    confidence: float = 0.5
    extracted_entities: List[str] = field(default_factory=list)


def extract_domain(url: str) -> str:
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return url


def tokenize_for_overlap(text: str) -> Set[str]:
    """
    Ekstrak token kata (atau bigram untuk CJK) untuk pencocokan overlap kemiripan.
    """
    if not text:
        return set()
    lower = text.lower()
    
    # Deteksi CJK
    cjk_chars = re.findall(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', lower)
    if len(cjk_chars) > len(lower) * 0.3:
        # Gunakan karakter unigram & bigram CJK
        bigrams = {cjk_chars[i] + cjk_chars[i+1] for i in range(len(cjk_chars) - 1)}
        return bigrams or set(cjk_chars)

    words = re.findall(r'[a-zA-Z0-9\u0400-\u04ff\u0600-\u06ff]+', lower)
    stopwords = {
        "dan", "atau", "yang", "di", "ke", "dari", "the", "and", "or", "in", "to", "is", "a", "an",
        "dengan", "menjadi", "sebagai", "secara", "adalah", "pada", "untuk", "oleh", "ini", "itu",
        "tersebut", "juga", "of", "with", "as", "by", "for", "on", "at"
    }
    return {w for w in words if len(w) > 2 and w not in stopwords}


def jaccard_similarity(s1: Set[str], s2: Set[str]) -> float:
    if not s1 or not s2:
        return 0.0
    inter = len(s1.intersection(s2))
    union = len(s1.union(s2))
    return inter / union if union > 0 else 0.0


def claim_similarity(s1: Set[str], s2: Set[str]) -> float:
    """
    Kombinasi Jaccard dan Overlap Coefficient untuk mendeteksi kesamaan klaim fakta
    antar sumber independen.
    """
    if not s1 or not s2:
        return 0.0
    inter = len(s1.intersection(s2))
    if inter == 0:
        return 0.0
    jaccard = inter / len(s1.union(s2))
    overlap = inter / min(len(s1), len(s2))
    return (jaccard * 0.4) + (overlap * 0.6)


def extract_numbers_and_currency(text: str) -> List[str]:
    """
    Mengekstrak angka, harga, persentase, atau tahun dari kalimat
    untuk deteksi konflik faktual.
    """
    patterns = [
        r'rp\.?\s*[\d\.,]+(?:\s*(?:juta|miliar|ribu|jt|rb))?',
        r'\$\s*[\d\.,]+(?:\s*(?:million|billion|k))?',
        r'\b\d+[\.,]\d+\b',
        r'\b\d{2,}\b'
    ]
    matches = []
    for p in patterns:
        for m in re.findall(p, text.lower()):
            clean_m = re.sub(r'\s+', '', m)
            if clean_m not in matches:
                matches.append(clean_m)
    return matches


def is_syndicated_copy(doc1: FetchedDocument, doc2: FetchedDocument) -> bool:
    """
    Mendeteksi apakah dua artikel merupakan salinan sindikasi kantor berita yang sama
    (kemiripan token >= 0.75 dan angka-angka identik).
    """
    tok1 = tokenize_for_overlap(doc1.full_text[:1200])
    tok2 = tokenize_for_overlap(doc2.full_text[:1200])
    sim = jaccard_similarity(tok1, tok2)
    if sim >= 0.75:
        num1 = set(extract_numbers_and_currency(doc1.full_text[:1000]))
        num2 = set(extract_numbers_and_currency(doc2.full_text[:1000]))
        if num1 == num2 and len(num1) > 0:
            return True
    return False


def extract_sentences(text: str) -> List[str]:
    """
    Memecah teks artikel menjadi kalimat-kalimat yang berdiri sendiri.
    """
    raw_sents = re.split(r'(?<=[.!?。！？])\s+', text)
    cleaned = []
    for s in raw_sents:
        s = s.strip()
        if len(s) > 20:
            cleaned.append(s)
    return cleaned


def cross_verify_documents(
    topic: str,
    documents: List[FetchedDocument],
    cfg: ResearchConfig
) -> Tuple[List[VerifiedFact], float]:
    """
    Melakukan verifikasi silang antar dokumen:
    1. Kelompokkan dokumen anti-sindikasi menjadi kelompok domain independen
    2. Ambil kalimat paling relevan dengan topik
    3. Kelompokkan klaim yang senada (overlap >= cluster_overlap)
    4. Tentukan status: 'verified', 'conflict', atau 'single'
    5. Hitung keyakinan keseluruhan
    """
    if not documents:
        return [], 0.0

    # 1. Anti-Sindikasi: Kelompokkan dokumen yang hampir identik
    unique_groups: List[List[FetchedDocument]] = []
    for doc in documents:
        merged = False
        for g in unique_groups:
            if is_syndicated_copy(doc, g[0]):
                g.append(doc)
                merged = True
                break
        if not merged:
            unique_groups.append([doc])

    topic_tokens = tokenize_for_overlap(topic)

    # 2. Kumpulkan kandidat klaim per kelompok independen
    CandidateClaim = Dict[str, Any]
    candidate_claims: List[CandidateClaim] = []

    for group_idx, group in enumerate(unique_groups):
        rep_doc = group[0]
        sentences = extract_sentences(rep_doc.full_text if rep_doc.is_full_article else rep_doc.snippet)
        
        # Ambil kalimat yang memiliki overlap dengan topik
        scored_sents = []
        for s in sentences:
            s_tok = tokenize_for_overlap(s)
            overlap = len(s_tok.intersection(topic_tokens))
            if overlap > 0:
                scored_sents.append((overlap, s, s_tok))
        
        scored_sents.sort(key=lambda x: x[0], reverse=True)
        # Ambil top 4 kalimat relevan per domain
        for _, s_text, s_tokens in scored_sents[:4]:
            candidate_claims.append({
                "group_id": group_idx,
                "domain": rep_doc.domain,
                "url": rep_doc.url,
                "text": s_text,
                "tokens": s_tokens,
                "numbers": extract_numbers_and_currency(s_text),
                "credibility": rep_doc.credibility
            })

    # 3. Kelompokkan klaim serupa (Clustering)
    clusters: List[List[CandidateClaim]] = []
    for claim in candidate_claims:
        placed = False
        for cl in clusters:
            # Bandingkan dengan perwakilan cluster
            rep = cl[0]
            sim = claim_similarity(claim["tokens"], rep["tokens"])
            if sim >= cfg.cluster_overlap:
                cl.append(claim)
                placed = True
                break
        if not placed:
            clusters.append([claim])

    verified_facts: List[VerifiedFact] = []

    # 4. Evaluasi Tiap Cluster
    for cl in clusters:
        # Hitung sumber independen (group_id unik)
        unique_group_ids = {c["group_id"] for c in cl}
        domains = list({c["domain"] for c in cl})
        urls = list({c["url"] for c in cl})
        
        # Cek konflik angka di dalam cluster antar kelompok independen
        nums_by_group: Dict[int, List[str]] = {}
        for c in cl:
            if c["numbers"]:
                nums_by_group[c["group_id"]] = c["numbers"]

        has_conflict = False
        conflict_msg = None
        if len(nums_by_group) >= 2:
            base_group = list(nums_by_group.keys())[0]
            base_nums = set(nums_by_group[base_group])
            for other_group, other_nums in nums_by_group.items():
                if other_group != base_group and base_nums and other_nums:
                    if set(other_nums) != base_nums:
                        has_conflict = True
                        conflict_msg = f"Perbedaan angka/nilai: {', '.join(base_nums)} vs {', '.join(other_nums)}"
                        break

        # Tentukan status klaim
        rep_text = max(cl, key=lambda c: len(c["text"]))["text"]

        if has_conflict:
            fact = VerifiedFact(
                claim=rep_text,
                status="conflict",
                supporting_sources=urls,
                supporting_domains=domains,
                conflicting_info=conflict_msg,
                confidence=0.3
            )
        elif len(unique_group_ids) >= cfg.min_agree:
            avg_cred = sum(c["credibility"] for c in cl) / len(cl)
            conf = min(0.98, 0.65 + (len(unique_group_ids) * 0.1) * (avg_cred / 1.0))
            fact = VerifiedFact(
                claim=rep_text,
                status="verified",
                supporting_sources=urls,
                supporting_domains=domains,
                confidence=round(conf, 2)
            )
        else:
            fact = VerifiedFact(
                claim=rep_text,
                status="single",
                supporting_sources=urls,
                supporting_domains=domains,
                confidence=0.4
            )

        verified_facts.append(fact)

    # 5. Hitung keyakinan akhir
    verified_only = [f for f in verified_facts if f.status == "verified"]
    if verified_only:
        top_confs = sorted([f.confidence for f in verified_only], reverse=True)[:3]
        overall_confidence = round(sum(top_confs) / len(top_confs), 2)
    else:
        overall_confidence = 0.35 if verified_facts else 0.1

    return verified_facts, overall_confidence

# ---------------------------------------------------------------------------
# 6. HASIL PENELITIAN & INTEGRASI PROMPT/MEMORI
# ---------------------------------------------------------------------------

@dataclass
class ResearchResult:
    topic: str
    verified_facts: List[VerifiedFact]
    confidence: float
    independent_sources_count: int
    all_documents: List[FetchedDocument]
    prompt_block: str
    summary_text: str

    def storable_facts(self) -> List[Dict[str, Any]]:
        """
        Hanya fakta berstatus 'verified' yang boleh disimpan ke memori jangka panjang
        (ingatan_shiro.json & dataset training). Fakta 'single' atau 'conflict' TIDAK disimpan!
        """
        storable = []
        now_iso = datetime.now().isoformat()
        for f in self.verified_facts:
            if f.status == "verified":
                storable.append({
                    "subject": self.topic[:80],
                    "predicate": "fakta_terverifikasi",
                    "object": f.claim[:400].strip(),
                    "confidence": f.confidence,
                    "sources": f.supporting_sources,
                    "domains": f.supporting_domains,
                    "created_at": now_iso
                })
        return storable


def build_research_prompt_block(
    topic: str,
    verified_facts: List[VerifiedFact],
    confidence: float,
    independent_sources_count: int
) -> str:
    """
    Menyusun blok fakta yang akan disuntikkan ke prompt neural LLM.
    """
    lines = [f"[Hasil Riset Nyata Web & Verifikasi Silang Real-Time]:"]
    lines.append(f"- Topik: {topic}")
    lines.append(f"- Sumber Independen Dikonfirmasi: {independent_sources_count} domain")
    lines.append(f"- Tingkat Keyakinan Verifikasi: {int(confidence * 100)}%")

    verified = [f for f in verified_facts if f.status == "verified"]
    conflicts = [f for f in verified_facts if f.status == "conflict"]
    singles = [f for f in verified_facts if f.status == "single"]

    if verified:
        lines.append("\n[FAKTA TERVERIFIKASI (Didukung Multi-Sumber Independen)]:")
        for idx, vf in enumerate(verified[:5], 1):
            src_str = ", ".join(vf.supporting_domains[:3])
            lines.append(f"{idx}. {vf.claim} (Sumber: {src_str})")

    if conflicts:
        lines.append("\n[PERINGATAN KONFLIK / PERBEDAAN DATA ANTAR SUMBER]:")
        for cf in conflicts[:2]:
            lines.append(f"- {cf.conflicting_info} (Konteks: {cf.claim[:120]}...)")
        lines.append("-> Instruksi: Sampaikan kepada Kakak bahwa ada perbedaan data di internet mengenai hal ini.")

    if singles and not verified:
        lines.append("\n[INFORMASI TUNGGAL (Belum diverifikasi silang)]:")
        for sf in singles[:3]:
            src_str = sf.supporting_domains[0] if sf.supporting_domains else "sumber web"
            lines.append(f"- Menurut {src_str}: {sf.claim}")
        lines.append("-> Instruksi: Karena baru dari 1 sumber, sebutkan secara jujur 'menurut kabar dari <sumber>...'.")

    if not verified and not singles:
        lines.append("\n[STATUS: Tidak ditemukan informasi yang cukup terkonfirmasi di internet saat ini.]")
        lines.append("-> Instruksi: Sampaikan dengan jujur bahwa informasinya belum bisa dipastikan.")

    lines.append("\n[Instruksi Karakter Shiro]:")
    lines.append("1. Gunakan fakta terverifikasi di atas untuk menjawab Kakak secara tepat dan percaya diri.")
    lines.append("2. JANGAN sebut nama tool, browser Mozilla, Cloudflare, atau format teknis.")
    lines.append("3. Tetap gunakan nada bicara manis, hangat, dan alami khas Shiro.")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 7. ORKESTRASI RISET MULTI-SUMBER ADAPTIF (research)
# ---------------------------------------------------------------------------

def research(
    user_query: str,
    search_fn: Callable[[str, str, int], List[RawSearchResult]],
    fetch_fn: Callable[[str], str],
    cfg: Optional[ResearchConfig] = None,
    llm_rewrite: Optional[Callable[[str, str], str]] = None
) -> ResearchResult:
    """
    Menjalankan alur pencarian multi-sumber adaptif:
    1. Buat kueri cerdas (asli + varian global)
    2. Cari di provider secara paralel
    3. Fusi peringkat RRF x kredibilitas
    4. Ronde 1: Baca minimal 3 sumber independen
    5. Verifikasi silang; eskalasi +2 sumber per ronde jika keyakinan < 0.6 (maks 10)
    6. Bangun hasil akhir terverifikasi
    """
    config = cfg or ResearchConfig()
    lang = detect_query_language(user_query)
    current_year = datetime.now().year

    queries = build_queries(user_query, detected_lang=lang, current_year=current_year, llm_rewrite=llm_rewrite)
    if not queries:
        queries = [SearchQuery(query=user_query, lang="id", is_primary=True)]

    # 1. Kumpulkan kandidat hasil pencarian dari semua kueri
    all_raw_candidates: List[RawSearchResult] = []
    seen_urls: Set[str] = set()

    for q in queries:
        try:
            results = search_fn(q.query, q.lang, 8)
            for r in results:
                if r.url and r.url not in seen_urls:
                    seen_urls.add(r.url)
                    all_raw_candidates.append(r)
        except Exception:
            continue

    if not all_raw_candidates:
        empty_prompt = build_research_prompt_block(user_query, [], 0.0, 0)
        return ResearchResult(
            topic=user_query,
            verified_facts=[],
            confidence=0.0,
            independent_sources_count=0,
            all_documents=[],
            prompt_block=empty_prompt,
            summary_text="Tidak ada hasil pencarian ditemukan."
        )

    # 2. Filter 1 domain = 1 kandidat terbaik (RRF + Kredibilitas)
    domain_best_candidate: Dict[str, RawSearchResult] = {}
    for r in all_raw_candidates:
        dom = extract_domain(r.url)
        cred = get_domain_weight(r.url, config.credibility)
        weighted_score = r.score * cred
        if dom not in domain_best_candidate or weighted_score > (domain_best_candidate[dom].score * get_domain_weight(domain_best_candidate[dom].url, config.credibility)):
            domain_best_candidate[dom] = r

    ranked_candidates = sorted(
        domain_best_candidate.values(),
        key=lambda r: r.score * get_domain_weight(r.url, config.credibility),
        reverse=True
    )

    # 3. Proses Pembacaan Adaptif & Verifikasi Silang Berjenjang
    fetched_docs: List[FetchedDocument] = []
    independent_domains: Set[str] = set()
    verified_facts: List[VerifiedFact] = []
    confidence = 0.0

    target_sources = config.default_sources
    cand_idx = 0
    max_fetch_attempts = min(20, len(ranked_candidates))

    while cand_idx < len(ranked_candidates) and cand_idx < max_fetch_attempts:
        # Ambil batch calon sumber
        batch = ranked_candidates[cand_idx : cand_idx + config.batch_size]
        cand_idx += len(batch)

        for cand in batch:
            dom = extract_domain(cand.url)
            cred = get_domain_weight(cand.url, config.credibility)
            is_full = False
            content = ""

            try:
                full_body = fetch_fn(cand.url)
                if full_body and len(full_body.strip()) >= 30:
                    content = full_body.strip()[:4000]
                    is_full = True
                    independent_domains.add(dom)
            except Exception:
                pass

            if not is_full:
                # Fallback ke snippet pencarian (bobot setengah, tidak dihitung domain penuh)
                content = cand.snippet
                cred = cred * 0.5

            doc = FetchedDocument(
                url=cand.url,
                domain=dom,
                title=cand.title,
                full_text=content,
                snippet=cand.snippet,
                is_full_article=is_full,
                credibility=cred
            )
            fetched_docs.append(doc)

        # Jalankan Verifikasi Silang
        facts, conf = cross_verify_documents(user_query, fetched_docs, config)
        verified_facts = facts
        confidence = conf

        # Berhenti jika syarat kecukupan terpenuhi:
        # >= 3 domain independen dan keyakinan >= 0.6
        if len(independent_domains) >= target_sources and confidence >= config.min_confidence:
            break

        # Eskalasi jika belum cukup
        if len(independent_domains) < config.max_sources:
            target_sources += config.batch_size
        else:
            break

    prompt_blk = build_research_prompt_block(
        user_query,
        verified_facts,
        confidence,
        len(independent_domains)
    )

    summary = (
        f"Riset selesai: {len(independent_domains)} domain independen diperiksa, "
        f"{len([f for f in verified_facts if f.status == 'verified'])} fakta terverifikasi "
        f"(Tingkat Keyakinan: {int(confidence * 100)}%)."
    )

    return ResearchResult(
        topic=user_query,
        verified_facts=verified_facts,
        confidence=confidence,
        independent_sources_count=len(independent_domains),
        all_documents=fetched_docs,
        prompt_block=prompt_blk,
        summary_text=summary
    )

# ---------------------------------------------------------------------------
# 8. HELPER PEMBUNGKUS (WRAPPER) FUNGSI PENCARIAN & PEMBACAAN
# ---------------------------------------------------------------------------

def wrap_search_fn(legacy_search_fn: Callable) -> Callable[[str, str, int], List[RawSearchResult]]:
    """
    Membungkus fungsi pencarian yang ada (seperti search_google_web / duckduckgo / bing)
    ke antarmuka standar RawSearchResult.
    """
    def _search(query: str, lang: str, limit: int) -> List[RawSearchResult]:
        out = []
        try:
            res = legacy_search_fn(query)
            if isinstance(res, dict):
                items = res.get("results", []) or res.get("items", [])
                for idx, it in enumerate(items[:limit]):
                    if isinstance(it, dict):
                        out.append(RawSearchResult(
                            title=it.get("title", "No Title"),
                            url=it.get("url", ""),
                            snippet=it.get("snippet", "") or it.get("description", ""),
                            source_engine="legacy_engine",
                            score=1.0 / (1.0 + idx * 0.1)
                        ))
        except Exception:
            pass
        return out
    return _search


def default_fetcher(url: str) -> str:
    """
    Fetcher default menggunakan open_and_read_webpage jika tersedia.
    """
    try:
        from shiro.agent.tools import open_and_read_webpage
        res = open_and_read_webpage(url)
        if isinstance(res, dict):
            return res.get("content", "")
    except Exception:
        pass
    return ""
