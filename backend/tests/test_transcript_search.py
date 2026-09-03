"""transcript/search.py: kanal va global rejimlarni bir xil natija shakliga
birlashtiruvchi asosiy mantiq. `fetch`/`store` chaqiruvlari monkeypatch
qilinadi — na YouTube API'ga, na haqiqiy SQLite fayliga tegilmaydi
(kanal rejimi testlari uchun `paths.TRANSCRIPT_DB_FILE` alohida vaqtinchalik
faylga yo'naltiriladi)."""
import pytest

import paths
from transcript import cache, fetch, search, store


@pytest.fixture(autouse=True)
def _clear_global_cache():
    cache.transcript_cache.clear()
    yield
    cache.transcript_cache.clear()


class TestExtractMatches:
    def test_finds_case_insensitive_substring(self):
        segments = [{"text": "Salom HAMMAGA", "start_time": 0.0, "end_time": 1.0}]
        matches = search._extract_matches(segments, "hammaga")
        assert len(matches) == 1
        assert matches[0]["start_time"] == 0.0

    def test_includes_surrounding_context(self):
        segments = [
            {"text": "birinchi gap", "start_time": 0.0, "end_time": 1.0},
            {"text": "bu yerda maqsad so'zi bor", "start_time": 1.0, "end_time": 2.0},
            {"text": "uchinchi gap", "start_time": 2.0, "end_time": 3.0},
        ]
        matches = search._extract_matches(segments, "maqsad", context_size=1)
        assert matches[0]["text"] == "birinchi gap bu yerda maqsad so'zi bor uchinchi gap"

    def test_context_is_clamped_at_boundaries(self):
        # Moslik ro'yxatning boshida/oxirida bo'lsa, `context_size` chetdan
        # tashqariga chiqib IndexError bermasligi kerak.
        segments = [{"text": "yagona segment ichida maqsad so'zi", "start_time": 0.0, "end_time": 1.0}]
        matches = search._extract_matches(segments, "maqsad", context_size=1)
        assert matches[0]["text"] == "yagona segment ichida maqsad so'zi"

    def test_no_match_returns_empty_list(self):
        segments = [{"text": "hech narsa", "start_time": 0.0, "end_time": 1.0}]
        assert search._extract_matches(segments, "topilmaydigan") == []

    def test_caps_matches_per_video(self):
        segments = [
            {"text": "takror so'z", "start_time": float(i), "end_time": float(i + 1)}
            for i in range(search.MAX_MATCHES_PER_VIDEO + 5)
        ]
        matches = search._extract_matches(segments, "takror")
        assert len(matches) == search.MAX_MATCHES_PER_VIDEO


class TestBuildResult:
    def test_builds_expected_shape_and_timestamped_link(self):
        result = search._build_result("vid1", "Sarlavha", "Kanal nomi", {"text": "kontekst", "start_time": 83.0})
        assert result == {
            "video_id": "vid1",
            "video_title": "Sarlavha",
            "channel_name": "Kanal nomi",
            "text": "kontekst",
            "start_time": 83.0,
            "url": "https://youtube.com/watch?v=vid1&t=83s",
        }


class TestNormalizeSegments:
    def test_collapses_internal_whitespace_and_computes_end_time(self):
        raw = [{"text": "salom\ndunyo  ", "start": 1.5, "duration": 2.0}]
        normalized = search._normalize_segments(raw)
        assert normalized == [{"text": "salom dunyo", "start_time": 1.5, "end_time": 3.5}]

    def test_drops_empty_text_segments(self):
        raw = [{"text": "   ", "start": 0.0, "duration": 1.0}]
        assert search._normalize_segments(raw) == []


class TestSearchValidation:
    def test_raises_on_empty_query(self):
        with pytest.raises(ValueError):
            search.search("   ")

    def test_raises_on_malformed_published_after(self):
        with pytest.raises(ValueError):
            search.search("test", published_after="not-a-date")

    def test_raises_on_malformed_published_before(self):
        with pytest.raises(ValueError):
            search.search("test", published_before="2023/01/01")


class TestSearchMaxVideosDefaults:
    # 2026-09-03: haqiqiy IShowSpeed kanaliga qarshi tekshiruvda topilgan
    # muammo — "1 yil oldin" so'ralganda ``DEFAULT_INDEX_MAX_VIDEOS`` (25)
    # ishlatilgani uchun juda faol kanalda atigi ~3 haftalik videolar
    # ko'rib chiqildi, so'ralgan yillik oraliqqa umuman yetib bormadi.
    def test_uses_recency_default_without_date_range(self, monkeypatch):
        captured = {}

        def fake_search_channel(query, channel_ref, max_videos, context_size, published_after=None, published_before=None):
            captured["max_videos"] = max_videos
            return [], False

        monkeypatch.setattr(search, "_search_channel", fake_search_channel)

        search.search("test", channel_id="UCabc")

        assert captured["max_videos"] == search.DEFAULT_INDEX_MAX_VIDEOS

    def test_uses_much_higher_default_with_date_range(self, monkeypatch):
        captured = {}

        def fake_search_channel(query, channel_ref, max_videos, context_size, published_after=None, published_before=None):
            captured["max_videos"] = max_videos
            return [], False

        monkeypatch.setattr(search, "_search_channel", fake_search_channel)

        search.search("test", channel_id="UCabc", published_after="2023-01-01")

        assert captured["max_videos"] == search.DEFAULT_DATE_RANGE_MAX_VIDEOS
        assert search.DEFAULT_DATE_RANGE_MAX_VIDEOS > search.DEFAULT_INDEX_MAX_VIDEOS

    def test_explicit_max_videos_overrides_date_range_default(self, monkeypatch):
        captured = {}

        def fake_search_channel(query, channel_ref, max_videos, context_size, published_after=None, published_before=None):
            captured["max_videos"] = max_videos
            return [], False

        monkeypatch.setattr(search, "_search_channel", fake_search_channel)

        search.search("test", channel_id="UCabc", max_videos=10, published_after="2023-01-01")

        assert captured["max_videos"] == 10


class TestSearchGlobalMode:
    def test_searches_candidates_and_skips_videos_without_transcript(self, monkeypatch):
        monkeypatch.setattr(fetch, "search_videos", lambda q, max_results, **kw: [
            {"video_id": "v1", "title": "T1", "channel_id": "UC1", "channel_name": "Ch1"},
            {"video_id": "v2", "title": "T2", "channel_id": "UC2", "channel_name": "Ch2"},
        ])

        def fake_fetch_transcript(video_id, languages=None):
            if video_id == "v1":
                return [{"text": "salom test iborasi", "start": 3.0, "duration": 2.0}]
            return None  # v2 uchun subtitr yo'q

        monkeypatch.setattr(fetch, "fetch_transcript", fake_fetch_transcript)

        data = search.search("test iborasi")

        assert data["blocked"] is False
        results = data["results"]
        assert len(results) == 1
        assert results[0]["video_id"] == "v1"
        assert results[0]["start_time"] == 3.0
        assert results[0]["url"] == "https://youtube.com/watch?v=v1&t=3s"

    def test_blocked_video_is_skipped_and_not_cached(self, monkeypatch):
        # `TranscriptFetchBlocked` (IP limiti va h.k.) shu video haqida
        # emas — keshga "subtitr yo'q" deb yozib qo'yilmasligi kerak,
        # aks holda blok tugagandan keyin ham 24 soat qayta urinilmasdi.
        monkeypatch.setattr(fetch, "search_videos", lambda q, max_results, **kw: [
            {"video_id": "v1", "title": "T1", "channel_id": "UC1", "channel_name": "Ch1"},
        ])

        def fake_fetch_transcript(video_id, languages=None):
            raise fetch.TranscriptFetchBlocked("IP bloklangan")

        monkeypatch.setattr(fetch, "fetch_transcript", fake_fetch_transcript)

        data = search.search("test")

        assert data["results"] == []
        assert data["blocked"] is True
        assert cache.transcript_cache.get("v1") is None

    def test_second_call_uses_cache_instead_of_refetching(self, monkeypatch):
        monkeypatch.setattr(fetch, "search_videos", lambda q, max_results, **kw: [
            {"video_id": "v1", "title": "T1", "channel_id": "UC1", "channel_name": "Ch1"},
        ])
        call_count = {"n": 0}

        def fake_fetch_transcript(video_id, languages=None):
            call_count["n"] += 1
            return [{"text": "qayta so'ralmaydigan matn", "start": 0.0, "duration": 1.0}]

        monkeypatch.setattr(fetch, "fetch_transcript", fake_fetch_transcript)

        search.search("qayta so'ralmaydigan")
        search.search("qayta so'ralmaydigan")

        assert call_count["n"] == 1


class TestSearchChannelMode:
    @pytest.fixture(autouse=True)
    def _isolated_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "TRANSCRIPT_DB_FILE", str(tmp_path / "search_channel_test.db"))

    def test_indexes_channel_once_then_reuses_stored_data(self, monkeypatch):
        resolve_calls = {"n": 0}

        def fake_resolve(ref):
            resolve_calls["n"] += 1
            return {"channel_id": "UCabc", "title": "Test Kanal", "uploads_playlist_id": "UUabc"}

        list_calls = {"n": 0}

        def fake_list(playlist_id, max_results=None, **kw):
            list_calls["n"] += 1
            return [{"video_id": "v1", "title": "Video 1"}]

        monkeypatch.setattr(fetch, "resolve_channel", fake_resolve)
        monkeypatch.setattr(fetch, "list_channel_videos", fake_list)
        monkeypatch.setattr(fetch, "fetch_transcript", lambda video_id, languages=None: [
            {"text": "bu yerda maxsus ibora bor", "start": 10.0, "duration": 2.0}
        ])

        results1 = search.search("maxsus ibora", channel_id="UCabc")["results"]
        results2 = search.search("maxsus ibora", channel_id="UCabc")["results"]

        assert len(results1) == 1
        assert results1[0]["channel_name"] == "Test Kanal"
        assert results1 == results2
        assert resolve_calls["n"] == 2  # har chaqiruvda kanal aniqlanadi (arzon, 1 unit)
        assert list_calls["n"] == 1  # video ro'yxati faqat BIRINCHI marta olinadi

    def test_video_without_transcript_is_not_retried_on_next_search(self, monkeypatch):
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "Kanal", "uploads_playlist_id": "UUabc",
        })
        monkeypatch.setattr(fetch, "list_channel_videos", lambda playlist_id, max_results=None, **kw: [
            {"video_id": "v1", "title": "Video 1"}
        ])
        transcript_calls = {"n": 0}

        def fake_transcript(video_id, languages=None):
            transcript_calls["n"] += 1
            return None

        monkeypatch.setattr(fetch, "fetch_transcript", fake_transcript)

        search.search("hech narsa", channel_id="UCabc")
        search.search("hech narsa", channel_id="UCabc")

        assert transcript_calls["n"] == 1

    def test_accepts_full_channel_url_not_just_raw_id(self, monkeypatch):
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "IShowSpeed", "uploads_playlist_id": "UUabc",
        })
        monkeypatch.setattr(fetch, "list_channel_videos", lambda playlist_id, max_results=None, **kw: [
            {"video_id": "v1", "title": "Video 1"}
        ])
        monkeypatch.setattr(fetch, "fetch_transcript", lambda video_id, languages=None: [
            {"text": "salom ibora", "start": 1.0, "duration": 1.0}
        ])

        results = search.search("salom ibora", channel_id="https://www.youtube.com/@IShowSpeed")["results"]

        assert len(results) == 1
        assert results[0]["channel_name"] == "IShowSpeed"

    def test_results_are_scoped_to_the_requested_channel(self, monkeypatch):
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "Kanal A", "uploads_playlist_id": "UUabc",
        })
        monkeypatch.setattr(fetch, "list_channel_videos", lambda playlist_id, max_results=None, **kw: [
            {"video_id": "v1", "title": "Video 1"}
        ])
        monkeypatch.setattr(fetch, "fetch_transcript", lambda video_id, languages=None: [
            {"text": "umumiy so'z", "start": 1.0, "duration": 1.0}
        ])
        search.search("umumiy so'z", channel_id="UCabc")  # UCabc'ni indexlab qo'yadi

        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCxyz", "title": "Kanal B", "uploads_playlist_id": "UUxyz",
        })
        results = search.search("umumiy so'z", channel_id="UCxyz")["results"]

        assert results == []  # UCabc'dagi moslik UCxyz qidiruviga chiqmasligi kerak


class TestIndexChannel:
    @pytest.fixture(autouse=True)
    def _isolated_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "TRANSCRIPT_DB_FILE", str(tmp_path / "index_channel_test.db"))

    def test_force_reindex_refetches_transcripts(self, monkeypatch):
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "Kanal", "uploads_playlist_id": "UUabc",
        })
        monkeypatch.setattr(fetch, "list_channel_videos", lambda playlist_id, max_results=None, **kw: [
            {"video_id": "v1", "title": "Video 1"}
        ])
        calls = {"n": 0}

        def fake_transcript(video_id, languages=None):
            calls["n"] += 1
            return [{"text": f"versiya {calls['n']}", "start": 0.0, "duration": 1.0}]

        monkeypatch.setattr(fetch, "fetch_transcript", fake_transcript)

        search.index_channel("UCabc")
        search.index_channel("UCabc")
        assert calls["n"] == 1

        search.index_channel("UCabc", force=True)
        assert calls["n"] == 2

    def test_blocked_videos_are_not_marked_indexed_and_channel_stays_unindexed(self, monkeypatch):
        # Haqiqiy IShowSpeed kanaliga qarshi jonli tekshiruvda topilgan
        # muammo: YouTube IP'ni bloklasa, avvalgi kod barcha videolarni
        # "tekshirilgan, subtitri yo'q" deb belgilab, kanalni ham "to'liq
        # indexlangan" deb qo'yardi — blok tugagandan keyin ham natija
        # abadiy bo'sh qolardi. Endi bloklangan videolar/kanal indexlangan
        # deb belgilanmasligi, keyingi chaqiruvda qayta urinilishi kerak.
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "Kanal", "uploads_playlist_id": "UUabc",
        })
        monkeypatch.setattr(fetch, "list_channel_videos", lambda playlist_id, max_results=None, **kw: [
            {"video_id": "v1", "title": "Video 1"}
        ])
        calls = {"n": 0}

        def fake_transcript(video_id, languages=None):
            calls["n"] += 1
            raise fetch.TranscriptFetchBlocked("IP bloklangan")

        monkeypatch.setattr(fetch, "fetch_transcript", fake_transcript)

        info = search.index_channel("UCabc")

        assert store.is_channel_indexed(info["channel_id"]) is False
        assert store.is_video_indexed("v1") is False
        # Chaqiruvchi (`search()`) bloklanishni "hech narsa topilmadi"dan
        # farqlab foydalanuvchiga ko'rsata olishi uchun bu bayroq kerak.
        assert info["blocked"] is True

        # Blok "tugagandan" keyin (endi muvaffaqiyatli) qayta chaqirilsa,
        # video haqiqatan ham qayta uriniladi — abadiy o'tkazib yuborilmaydi.
        monkeypatch.setattr(fetch, "fetch_transcript", lambda video_id, languages=None: [
            {"text": "endi ishlayapti", "start": 0.0, "duration": 1.0}
        ])
        search.index_channel("UCabc")

        assert store.is_channel_indexed(info["channel_id"]) is True
        assert store.get_video_segments("v1") == [{"text": "endi ishlayapti", "start_time": 0.0, "end_time": 1.0}]

    def test_date_ranged_indexing_does_not_touch_channel_level_indexed_flag(self, monkeypatch):
        # Sana oralig'i bilan indexlash "eng so'nggi N video" kesimidan
        # butunlay boshqa — kanalni "to'liq indexlangan" deb belgilasa,
        # keyingi (oralig'siz) qidiruv ham indexlangan deb noto'g'ri
        # o'ylab, videolarni tekshirmay qolib ketardi.
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "Kanal", "uploads_playlist_id": "UUabc",
        })
        captured_kwargs = {}

        def fake_list(playlist_id, max_results=None, **kw):
            captured_kwargs.update(kw)
            return [{"video_id": "old_vid", "title": "Eski video", "published_at": "2023-02-01"}]

        monkeypatch.setattr(fetch, "list_channel_videos", fake_list)
        monkeypatch.setattr(fetch, "fetch_transcript", lambda video_id, languages=None: [
            {"text": "2023-yilgi kontent", "start": 0.0, "duration": 1.0}
        ])

        info = search.index_channel("UCabc", published_after="2023-01-01", published_before="2023-03-01")

        assert captured_kwargs == {"published_after": "2023-01-01", "published_before": "2023-03-01"}
        assert info["blocked"] is False
        assert store.is_video_indexed("old_vid") is True
        # ASOSIY tekshiruv: kanal DARAJASIDA "to'liq indexlangan" deb
        # BELGILANMAGAN — bu boshqa (recency) indexlash holati.
        assert store.is_channel_indexed("UCabc") is False

    def test_published_at_flows_from_list_channel_videos_to_store(self, monkeypatch):
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "Kanal", "uploads_playlist_id": "UUabc",
        })
        monkeypatch.setattr(fetch, "list_channel_videos", lambda playlist_id, max_results=None, **kw: [
            {"video_id": "v1", "title": "Video 1", "published_at": "2023-07-04"}
        ])
        monkeypatch.setattr(fetch, "fetch_transcript", lambda video_id, languages=None: [
            {"text": "sana bilan", "start": 0.0, "duration": 1.0}
        ])

        search.index_channel("UCabc")

        assert store.find_matching_video_ids("UCabc", "sana", published_after="2023-06-01") == ["v1"]
        assert store.find_matching_video_ids("UCabc", "sana", published_after="2023-08-01") == []


class TestCatchUp:
    """Indeksni avtomatik yangilash — kanal bir marta indexlangach, ertasiga
    chiqqan streamlar indeksga tushmay qolardi va ulardan olingan klip hech
    qachon topilmasdi."""

    @pytest.fixture(autouse=True)
    def _isolated_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "TRANSCRIPT_DB_FILE", str(tmp_path / "catch_up_test.db"))

    def _seed(self, video_id="old_vid", published_at="2026-01-10", channel_id="UCabc"):
        store.save_video_segments(
            channel_id=channel_id, video_id=video_id, channel_name="Kanal",
            video_title="Eski", published_at=published_at,
            segments=[{"text": "eski matn", "start_time": 0.0, "end_time": 1.0}],
        )

    def _patch_channel(self, monkeypatch, videos):
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "Kanal", "uploads_playlist_id": "UUabc",
        })
        captured = {}

        def fake_list(playlist_id, max_results=None, published_after=None, published_before=None):
            captured["published_after"] = published_after
            return videos

        monkeypatch.setattr(fetch, "list_channel_videos", fake_list)
        monkeypatch.setattr(fetch, "fetch_transcript", lambda video_id, languages=None: [
            {"text": f"yangi {video_id}", "start": 0.0, "duration": 1.0}
        ])
        return captured

    def test_indexes_videos_published_after_the_newest_indexed_one(self, monkeypatch):
        self._seed(published_at="2026-01-10")
        self._patch_channel(monkeypatch, [
            {"video_id": "new_vid", "title": "Yangi", "published_at": "2026-01-12"},
        ])

        result = search.catch_up("UCabc")

        assert result["indexed"] == 1
        assert store.is_video_indexed("new_vid") is True

    def test_asks_youtube_only_for_videos_newer_than_the_index(self, monkeypatch):
        self._seed(published_at="2026-01-10")
        captured = self._patch_channel(monkeypatch, [])

        search.catch_up("UCabc")

        assert captured["published_after"] == "2026-01-10"

    def test_already_indexed_videos_are_not_refetched(self, monkeypatch):
        self._seed(video_id="old_vid", published_at="2026-01-10")
        self._patch_channel(monkeypatch, [
            {"video_id": "old_vid", "title": "Eski", "published_at": "2026-01-10"},
        ])

        assert search.catch_up("UCabc")["indexed"] == 0

    def test_reports_how_many_are_left_over_the_limit(self, monkeypatch):
        self._seed(published_at="2026-01-10")
        self._patch_channel(monkeypatch, [
            {"video_id": f"v{i}", "title": f"V{i}", "published_at": "2026-01-12"}
            for i in range(5)
        ])

        result = search.catch_up("UCabc", max_videos=2)

        assert result["indexed"] == 2
        assert result["pending"] == 3

    def test_updates_every_indexed_channel_when_none_is_given(self, monkeypatch):
        self._seed(video_id="a_old", channel_id="UCabc", published_at="2026-01-10")
        self._seed(video_id="b_old", channel_id="UCxyz", published_at="2026-01-10")
        seen = []

        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": ref, "title": "Kanal", "uploads_playlist_id": f"UU{ref}",
        })

        def fake_list(playlist_id, max_results=None, published_after=None, published_before=None):
            seen.append(playlist_id)
            return []

        monkeypatch.setattr(fetch, "list_channel_videos", fake_list)

        search.catch_up()

        assert sorted(seen) == ["UUUCabc", "UUUCxyz"]

    def test_channel_with_nothing_indexed_is_skipped(self, monkeypatch):
        # Bu "yangilash" emas, to'liq indexlash ishi — catch_up unga tegmaydi.
        called = []
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "Kanal", "uploads_playlist_id": "UUabc",
        })
        monkeypatch.setattr(fetch, "list_channel_videos",
                            lambda *a, **kw: called.append(1) or [])

        assert search.catch_up("UCabc") == {"indexed": 0, "pending": 0, "blocked": False}
        assert called == []

    def test_blocked_fetch_is_reported_and_video_stays_unindexed(self, monkeypatch):
        self._seed(published_at="2026-01-10")
        self._patch_channel(monkeypatch, [
            {"video_id": "new_vid", "title": "Yangi", "published_at": "2026-01-12"},
        ])

        def blocked(video_id, languages=None):
            raise fetch.TranscriptFetchBlocked("IP bloklangan")

        monkeypatch.setattr(fetch, "fetch_transcript", blocked)

        result = search.catch_up("UCabc")

        assert result["blocked"] is True
        assert store.is_video_indexed("new_vid") is False
