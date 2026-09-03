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


class TestSearchGlobalMode:
    def test_searches_candidates_and_skips_videos_without_transcript(self, monkeypatch):
        monkeypatch.setattr(fetch, "search_videos", lambda q, max_results: [
            {"video_id": "v1", "title": "T1", "channel_id": "UC1", "channel_name": "Ch1"},
            {"video_id": "v2", "title": "T2", "channel_id": "UC2", "channel_name": "Ch2"},
        ])

        def fake_fetch_transcript(video_id, languages=None):
            if video_id == "v1":
                return [{"text": "salom test iborasi", "start": 3.0, "duration": 2.0}]
            return None  # v2 uchun subtitr yo'q

        monkeypatch.setattr(fetch, "fetch_transcript", fake_fetch_transcript)

        results = search.search("test iborasi")

        assert len(results) == 1
        assert results[0]["video_id"] == "v1"
        assert results[0]["start_time"] == 3.0
        assert results[0]["url"] == "https://youtube.com/watch?v=v1&t=3s"

    def test_blocked_video_is_skipped_and_not_cached(self, monkeypatch):
        # `TranscriptFetchBlocked` (IP limiti va h.k.) shu video haqida
        # emas — keshga "subtitr yo'q" deb yozib qo'yilmasligi kerak,
        # aks holda blok tugagandan keyin ham 24 soat qayta urinilmasdi.
        monkeypatch.setattr(fetch, "search_videos", lambda q, max_results: [
            {"video_id": "v1", "title": "T1", "channel_id": "UC1", "channel_name": "Ch1"},
        ])

        def fake_fetch_transcript(video_id, languages=None):
            raise fetch.TranscriptFetchBlocked("IP bloklangan")

        monkeypatch.setattr(fetch, "fetch_transcript", fake_fetch_transcript)

        results = search.search("test")

        assert results == []
        assert cache.transcript_cache.get("v1") is None

    def test_second_call_uses_cache_instead_of_refetching(self, monkeypatch):
        monkeypatch.setattr(fetch, "search_videos", lambda q, max_results: [
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

        def fake_list(playlist_id, max_results=None):
            list_calls["n"] += 1
            return [{"video_id": "v1", "title": "Video 1"}]

        monkeypatch.setattr(fetch, "resolve_channel", fake_resolve)
        monkeypatch.setattr(fetch, "list_channel_videos", fake_list)
        monkeypatch.setattr(fetch, "fetch_transcript", lambda video_id, languages=None: [
            {"text": "bu yerda maxsus ibora bor", "start": 10.0, "duration": 2.0}
        ])

        results1 = search.search("maxsus ibora", channel_id="UCabc")
        results2 = search.search("maxsus ibora", channel_id="UCabc")

        assert len(results1) == 1
        assert results1[0]["channel_name"] == "Test Kanal"
        assert results1 == results2
        assert resolve_calls["n"] == 2  # har chaqiruvda kanal aniqlanadi (arzon, 1 unit)
        assert list_calls["n"] == 1  # video ro'yxati faqat BIRINCHI marta olinadi

    def test_video_without_transcript_is_not_retried_on_next_search(self, monkeypatch):
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "Kanal", "uploads_playlist_id": "UUabc",
        })
        monkeypatch.setattr(fetch, "list_channel_videos", lambda playlist_id, max_results=None: [
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
        monkeypatch.setattr(fetch, "list_channel_videos", lambda playlist_id, max_results=None: [
            {"video_id": "v1", "title": "Video 1"}
        ])
        monkeypatch.setattr(fetch, "fetch_transcript", lambda video_id, languages=None: [
            {"text": "salom ibora", "start": 1.0, "duration": 1.0}
        ])

        results = search.search("salom ibora", channel_id="https://www.youtube.com/@IShowSpeed")

        assert len(results) == 1
        assert results[0]["channel_name"] == "IShowSpeed"

    def test_results_are_scoped_to_the_requested_channel(self, monkeypatch):
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "Kanal A", "uploads_playlist_id": "UUabc",
        })
        monkeypatch.setattr(fetch, "list_channel_videos", lambda playlist_id, max_results=None: [
            {"video_id": "v1", "title": "Video 1"}
        ])
        monkeypatch.setattr(fetch, "fetch_transcript", lambda video_id, languages=None: [
            {"text": "umumiy so'z", "start": 1.0, "duration": 1.0}
        ])
        search.search("umumiy so'z", channel_id="UCabc")  # UCabc'ni indexlab qo'yadi

        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCxyz", "title": "Kanal B", "uploads_playlist_id": "UUxyz",
        })
        results = search.search("umumiy so'z", channel_id="UCxyz")

        assert results == []  # UCabc'dagi moslik UCxyz qidiruviga chiqmasligi kerak


class TestIndexChannel:
    @pytest.fixture(autouse=True)
    def _isolated_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "TRANSCRIPT_DB_FILE", str(tmp_path / "index_channel_test.db"))

    def test_force_reindex_refetches_transcripts(self, monkeypatch):
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCabc", "title": "Kanal", "uploads_playlist_id": "UUabc",
        })
        monkeypatch.setattr(fetch, "list_channel_videos", lambda playlist_id, max_results=None: [
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
        monkeypatch.setattr(fetch, "list_channel_videos", lambda playlist_id, max_results=None: [
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

        # Blok "tugagandan" keyin (endi muvaffaqiyatli) qayta chaqirilsa,
        # video haqiqatan ham qayta uriniladi — abadiy o'tkazib yuborilmaydi.
        monkeypatch.setattr(fetch, "fetch_transcript", lambda video_id, languages=None: [
            {"text": "endi ishlayapti", "start": 0.0, "duration": 1.0}
        ])
        search.index_channel("UCabc")

        assert store.is_channel_indexed(info["channel_id"]) is True
        assert store.get_video_segments("v1") == [{"text": "endi ishlayapti", "start_time": 0.0, "end_time": 1.0}]
