"""
Unit Tests untuk Real-Time Web Intelligence & Multilingual Multi-Source Verification (v2).
11 Tes Offline:
1. Intent dalam 12 Bahasa (Termasuk register_language)
2. Curhat / Sinyal Personal Tidak Memicu Pencarian Web
3. Injeksi Tahun Berjalan Otomatis
4. Pembuatan Varian Kueri Global / Inggris
5. Koreksi Waktu Server & Fallback
6. Eskalasi Sumber Adaptif (Ketika sumber awal belum mencapai keyakinan cukup)
7. Anti-Sindikasi: Salinan Berita Identik Dihitung 1 Sumber Independen
8. Deteksi Konflik Angka / Harga (Tidak Boleh Masuk storable_facts)
9. Penanganan Kasus Tanpa Hasil Pencarian
10. Ketahanan Terhadap Provider / Fetcher yang Error
11. Verifikasi Silang Sukses (>= 2 Sumber Sepakat -> Verified & Masuk storable_facts)
"""

import unittest
from datetime import datetime, timezone, timedelta
from shiro.web.realtime_intel import (
    classify_intent,
    build_queries,
    get_verified_now,
    time_prompt_block,
    format_verified_time_info,
    register_language,
    LanguageLexicon,
    research,
    ResearchConfig,
    RawSearchResult,
    FetchedDocument,
    is_syndicated_copy,
    cross_verify_documents,
    wrap_search_fn
)


class TestRealtimeIntelV2(unittest.TestCase):

    def test_01_multilingual_intent_12_languages(self):
        """1. Uji klasifikasi intent pada 12 bahasa (11 bawaan + 1 bahasa baru via register_language)"""
        # Register bahasa ke-12: Bahasa Italia (it)
        register_language(LanguageLexicon(
            code="it",
            temporal_words=["quest'anno", "attualmente", "oggi", "ultimo"],
            trend_words=["popolare", "popolari", "migliore", "migliori", "prezzo"],
            inquiry_words=["scopri", "cerca", "notizie"],
            officeholder_words=["chi è il presidente"],
            personal_signals=["sono stanco", "abbracciami"],
            time_only_patterns=[r"che ore sono", r"che giorno è oggi"],
            fillers=["per favore", "shiro"],
            year_markers=["quest'anno"]
        ))

        test_cases = [
            ("id", "anime populer tahun ini apa", "search"),
            ("id", "tolong cari tahu saat ini hari apa", "time"),
            ("id", "oke lupakan anime hari ini yang tayang di web otakudesu apa saja", "search"),
            ("id", "oke yang lagi tayang musim ini anime apa saja", "search"),
            ("en", "what are the most popular anime this year", "search"),
            ("en", "what day is it today", "time"),
            ("ja", "今年の人気アニメは何ですか", "search"),
            ("ja", "今日は何曜日", "time"),
            ("ko", "올해 가장 인기 있는 애니메이션은 무엇인가요", "search"),
            ("ko", "오늘 무슨 요일", "time"),
            ("zh", "今年最热门的动画有哪些", "search"),
            ("zh", "今天星期几", "time"),
            ("es", "cuáles son los animes más populares de este año", "search"),
            ("es", "qué día es hoy", "time"),
            ("fr", "quels sont les animes les plus populaires de cette année", "search"),
            ("de", "was sind die beliebtesten animes dieses jahr", "search"),
            ("pt", "quais são os melhores animes deste ano", "search"),
            ("ru", "какие самые популярные аниме в этом году", "search"),
            ("ar", "ما هي أكثر مسلسلات الأنمي شعبية هذا العام", "search"),
            ("it", "quali sono gli anime più popolari di quest'anno", "search"),
        ]

        for lang, query, expected_kind in test_cases:
            res = classify_intent(query)
            self.assertEqual(
                res.kind,
                expected_kind,
                f"Gagal untuk bahasa '{lang}' pada query '{query}': dapat {res.kind}, alasan: {res.reasons}"
            )

    def test_02_curhat_personal_signals_no_search(self):
        """2. Uji filter curhat personal agar tidak memicu pencarian web"""
        curhat_queries = [
            "hari ini aku capek banget kak, peluk aku dong",
            "aku lagi sedih dan patah hati karena dia nggak suka aku",
            "today i feel so tired and sad, please stay with me",
            "今日本当に疲れたよ、寂しい",
            "aku bingung dan sedih dengan perasaanku sekarang"
        ]
        for q in curhat_queries:
            res = classify_intent(q)
            self.assertNotEqual(
                res.kind,
                "search",
                f"Curhat '{q}' seharusnya TIDAK memicu search! Dapat: {res.kind}, skor: {res.score}"
            )

    def test_03_year_injection_in_queries(self):
        """3. Uji injeksi tahun berjalan secara otomatis pada frasa temporal"""
        curr_yr = datetime.now().year
        # Indonesia
        queries_id = build_queries("anime populer tahun ini apa", current_year=curr_yr)
        self.assertTrue(any(str(curr_yr) in q.query for q in queries_id))
        self.assertFalse(any("tahun ini" in q.query for q in queries_id))

        # English
        queries_en = build_queries("popular anime this year", current_year=curr_yr)
        self.assertTrue(any(str(curr_yr) in q.query for q in queries_en))

        # Keyword 'terbaru' tanpa tahun
        queries_latest = build_queries("rekomendasi hp gaming terbaru", current_year=curr_yr)
        self.assertTrue(any(str(curr_yr) in q.query for q in queries_latest))

    def test_04_english_query_variant_generation(self):
        """4. Uji pembuatan varian kueri bahasa Inggris untuk kueri non-Inggris"""
        queries = build_queries("anime populer tahun ini apa")
        langs = [q.lang for q in queries]
        self.assertIn("en", langs, "Harus menyertakan varian kueri bahasa Inggris")

        # Test dengan custom LLM rewrite function
        def mock_rewrite(txt, target_lang):
            return "best anime 2026 ranking"

        queries_llm = build_queries("anime populer tahun ini apa", llm_rewrite=mock_rewrite)
        en_qs = [q.query for q in queries_llm if q.lang == "en"]
        self.assertTrue(len(en_qs) > 0)
        self.assertEqual(en_qs[0], "best anime 2026 ranking")

    def test_05_verified_clock_and_fallback(self):
        """5. Uji verifikasi waktu server dan format zona waktu"""
        now = get_verified_now(server_urls=[])
        self.assertIsInstance(now, datetime)
        info = format_verified_time_info()
        self.assertTrue(info["success"])
        self.assertIn("WIB", info["summary"])
        self.assertIn("JST", info["summary"])
        self.assertEqual(info["year"], now.year)

        block = time_prompt_block()
        self.assertIn("[Waktu & Kalender Nyata Real-Time]:", block)
        self.assertIn(str(now.year), block)

    def test_06_source_escalation_when_confidence_low(self):
        """6. Uji eskalasi sumber adaptif ketika ronde awal belum mencapai keyakinan 0.6"""
        search_calls = []

        def mock_search(q, lang, limit):
            search_calls.append(q)
            return [
                RawSearchResult(title=f"Source {i}", url=f"https://domain{i}.com/page", snippet=f"Snippet {i}", score=1.0)
                for i in range(1, 8)
            ]

        fetch_count = [0]

        def mock_fetch(url):
            fetch_count[0] += 1
            # Domain 1-2 memberikan teks berbeda sehingga belum verified
            # Domain 3-5 sepakat
            if "domain1" in url:
                return "Anime terpopuler adalah Solo Leveling Season 2 di platform streaming."
            elif "domain2" in url:
                return "Daftar rilis musim dingin mencakup Frieren dan Kusuriya."
            elif "domain3" in url:
                return "Anime terpopuler adalah Solo Leveling Season 2 dengan rating tertinggi."
            elif "domain4" in url:
                return "Solo Leveling Season 2 menjadi anime terpopuler tahun ini."
            return "Informasi umum lainnya."

        cfg = ResearchConfig(default_sources=2, batch_size=2, min_confidence=0.6, min_agree=2)
        res = research("anime populer tahun ini", mock_search, mock_fetch, cfg=cfg)

        # Harus membaca lebih dari default_sources (2) karena diekalasikan ke domain3 dan domain4
        self.assertGreater(fetch_count[0], 2)
        self.assertGreaterEqual(res.independent_sources_count, 3)
        self.assertTrue(res.confidence >= 0.6)

    def test_07_syndicated_copies_counted_as_one_source(self):
        """7. Uji anti-sindikasi: berita salinan identik dari kantor berita dihitung sebagai 1 sumber independen"""
        text_a = (
            "JAKARTA - Pemerintah mengumumkan peluncuran satelit komunikasi baru "
            "dengan kapasitas 150 Gbps senilai Rp 8,5 triliun pada kuartal ketiga."
        )
        # Salinan hampir identik di media lain
        text_b = (
            "JAKARTA - Pemerintah secara resmi mengumumkan peluncuran satelit komunikasi baru "
            "dengan kapasitas 150 Gbps senilai Rp 8,5 triliun pada kuartal ketiga nanti."
        )
        doc1 = FetchedDocument(url="https://media-a.com/news1", domain="media-a.com", title="A", full_text=text_a, snippet="", is_full_article=True)
        doc2 = FetchedDocument(url="https://media-b.com/news1", domain="media-b.com", title="B", full_text=text_b, snippet="", is_full_article=True)

        self.assertTrue(is_syndicated_copy(doc1, doc2))

        # Jalankan cross-verification: karena sindikasi, keduanya berada di 1 kelompok independen sehingga berstatus 'single'
        cfg = ResearchConfig(min_agree=2)
        facts, conf = cross_verify_documents("satelit komunikasi", [doc1, doc2], cfg)
        for f in facts:
            self.assertNotEqual(f.status, "verified", "Salinan sindikasi tidak boleh dihitung sebagai 2 sumber independen!")

    def test_08_price_conflict_detection_not_stored(self):
        """8. Uji deteksi konflik angka/harga: diberi status 'conflict' dan TIDAK masuk storable_facts"""
        doc1 = FetchedDocument(
            url="https://gadget-a.com/review",
            domain="gadget-a.com",
            title="Review A",
            full_text="Harga resmi smartphone X di Indonesia dibanderol Rp 15.999.000 untuk varian dasar.",
            snippet="",
            is_full_article=True
        )
        doc2 = FetchedDocument(
            url="https://gadget-b.com/review",
            domain="gadget-b.com",
            title="Review B",
            full_text="Harga resmi smartphone X di Indonesia dibanderol Rp 18.999.000 untuk varian dasar.",
            snippet="",
            is_full_article=True
        )

        cfg = ResearchConfig(min_agree=2, cluster_overlap=0.4)
        facts, conf = cross_verify_documents("harga resmi smartphone X", [doc1, doc2], cfg)

        conflicts = [f for f in facts if f.status == "conflict"]
        self.assertTrue(len(conflicts) > 0, "Harus mendeteksi konflik harga 15.999.000 vs 18.999.000")

        # Buat dummy ResearchResult dan verifikasi storable_facts()
        from shiro.web.realtime_intel import ResearchResult
        res = ResearchResult(
            topic="harga smartphone x",
            verified_facts=facts,
            confidence=conf,
            independent_sources_count=2,
            all_documents=[doc1, doc2],
            prompt_block="",
            summary_text=""
        )
        storable = res.storable_facts()
        self.assertEqual(len(storable), 0, "Fakta berstatus 'conflict' TIDAK boleh masuk ke storable_facts!")

    def test_09_empty_search_results_graceful(self):
        """9. Uji penanganan ketika mesin pencari tidak menemukan hasil apa pun"""
        def empty_search(q, lang, limit):
            return []

        def dummy_fetch(url):
            return ""

        res = research("topik_aneh_yang_tidak_mungkin_ada_12345", empty_search, dummy_fetch)
        self.assertEqual(res.confidence, 0.0)
        self.assertEqual(res.independent_sources_count, 0)
        self.assertEqual(len(res.storable_facts()), 0)
        self.assertIn("Tidak ada hasil", res.summary_text)

    def test_10_resilient_to_provider_errors(self):
        """10. Uji ketahanan terhadap provider atau fetcher yang melempar exception"""
        def error_search(q, lang, limit):
            raise ConnectionResetError("Koneksi ditolak oleh search engine")

        def error_fetch(url):
            raise TimeoutError("Halaman web timeout")

        # Tidak boleh crash / melempar exception ke luar
        res = research("berita terkini", error_search, error_fetch)
        self.assertIsInstance(res.summary_text, str)
        self.assertEqual(len(res.storable_facts()), 0)

    def test_11_successful_multi_source_verification(self):
        """11. Uji verifikasi multi-sumber sukses: >= 2 sumber sepakat -> status verified & masuk storable_facts"""
        doc1 = FetchedDocument(
            url="https://kompas.com/anime-2026",
            domain="kompas.com",
            title="Anime 2026 Kompas",
            full_text="Solo Leveling Season 2 resmi menjadi anime paling populer tahun 2026 dengan jutaan penonton.",
            snippet="",
            is_full_article=True,
            credibility=1.3
        )
        doc2 = FetchedDocument(
            url="https://antaranews.com/anime-populer",
            domain="antaranews.com",
            title="Antara News",
            full_text="Anime Solo Leveling Season 2 dinobatkan sebagai anime paling populer tahun 2026 secara global.",
            snippet="",
            is_full_article=True,
            credibility=1.3
        )

        cfg = ResearchConfig(min_agree=2)
        facts, conf = cross_verify_documents("anime paling populer tahun 2026", [doc1, doc2], cfg)

        verified = [f for f in facts if f.status == "verified"]
        self.assertTrue(len(verified) > 0, "Klaim yang didukung Kompas dan Antara harus berstatus 'verified'")
        self.assertGreaterEqual(conf, 0.6)

        from shiro.web.realtime_intel import ResearchResult
        res = ResearchResult(
            topic="anime paling populer tahun 2026",
            verified_facts=facts,
            confidence=conf,
            independent_sources_count=2,
            all_documents=[doc1, doc2],
            prompt_block="",
            summary_text=""
        )
        storable = res.storable_facts()
        self.assertGreater(len(storable), 0, "Fakta verified HARUS masuk ke storable_facts untuk memori")
        self.assertEqual(storable[0]["predicate"], "fakta_terverifikasi")
        self.assertIn("kompas.com", storable[0]["domains"])


if __name__ == "__main__":
    unittest.main()
