"""FastAPI /api/transcript/search qatlami — `search.search()` monkeypatch
qilinadi, faqat HTTP status/validatsiya/xato-xabar qatlami tekshiriladi
(test_api.py'dagi TestClipRangeValidation uslubiga o'xshash)."""
import pytest
from fastapi.testclient import TestClient

import main
from transcript import fetch
from transcript import find_source as find_source_module
from transcript import search as search_module


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def no_network_catch_up(monkeypatch):
    """``/find-source`` endi qidirishdan oldin indeksni yangilaydi. Testlar
    tarmoqqa chiqmasligi uchun standart holatda bu bosqich o'chiriladi;
    yangilashning O'ZINI tekshiradigan testlar buni qayta belgilaydi."""
    monkeypatch.setattr(
        search_module, "catch_up",
        lambda channel_ref=None, **kw: {"indexed": 0, "pending": 0, "blocked": False},
    )


class TestTranscriptSearchEndpoint:
    def test_returns_results_for_valid_query(self, client, monkeypatch):
        monkeypatch.setattr(
            search_module, "search",
            lambda query, channel_id=None, max_videos=None, context_size=1,
            published_after=None, published_before=None: {
                "results": [
                    {
                        "video_id": "v1", "video_title": "T", "channel_name": "Ch",
                        "text": "x", "start_time": 1.0, "url": "https://youtube.com/watch?v=v1&t=1s",
                    }
                ],
                "blocked": False,
            },
        )

        res = client.post("/api/transcript/search", json={"query": "salom"})

        assert res.status_code == 200
        body = res.json()
        assert body["mode"] == "global"
        assert body["count"] == 1
        assert body["results"][0]["video_id"] == "v1"
        assert body["blocked"] is False

    def test_channel_mode_used_when_channel_id_given(self, client, monkeypatch):
        captured = {}

        def fake_search(query, channel_id=None, max_videos=None, context_size=1,
                         published_after=None, published_before=None):
            captured["channel_id"] = channel_id
            return {"results": [], "blocked": False}

        monkeypatch.setattr(search_module, "search", fake_search)

        res = client.post("/api/transcript/search", json={"query": "salom", "channel_id": "UCabc"})

        assert res.status_code == 200
        assert res.json()["mode"] == "channel"
        assert captured["channel_id"] == "UCabc"

    def test_empty_results_return_empty_list_not_error(self, client, monkeypatch):
        monkeypatch.setattr(search_module, "search", lambda *a, **k: {"results": [], "blocked": False})

        res = client.post("/api/transcript/search", json={"query": "topilmaydigan ibora"})

        assert res.status_code == 200
        assert res.json() == {
            "query": "topilmaydigan ibora", "mode": "global", "count": 0, "results": [], "blocked": False,
        }

    def test_blocked_flag_is_surfaced_when_indexing_was_blocked(self, client, monkeypatch):
        # Bo'sh natija YouTube tomonidan bloklanish sabab bo'lishi mumkin —
        # frontend buni "hech narsa topilmadi"dan farqlab ko'rsatishi uchun
        # `blocked` javobda to'g'ri uzatilishi kerak.
        monkeypatch.setattr(search_module, "search", lambda *a, **k: {"results": [], "blocked": True})

        res = client.post("/api/transcript/search", json={"query": "salom", "channel_id": "UCabc"})

        assert res.status_code == 200
        assert res.json()["blocked"] is True

    def test_rejects_empty_query_with_400(self, client, monkeypatch):
        def boom(*a, **k):
            raise ValueError("Qidiruv so'zi bo'sh bo'lishi mumkin emas")

        monkeypatch.setattr(search_module, "search", boom)

        res = client.post("/api/transcript/search", json={"query": "   "})

        assert res.status_code == 400

    def test_missing_api_key_returns_500(self, client, monkeypatch):
        def boom(*a, **k):
            raise fetch.ConfigError("YOUTUBE_API_KEY o'rnatilmagan")

        monkeypatch.setattr(search_module, "search", boom)

        res = client.post("/api/transcript/search", json={"query": "salom"})

        assert res.status_code == 500
        assert "YOUTUBE_API_KEY" in res.json()["detail"]

    def test_unexpected_error_returns_400_not_500(self, client, monkeypatch):
        # main.py'dagi qolgan endpointlar (masalan api_info) bilan bir xil
        # konvensiya: kutilmagan xatolar ham 400 + tushunarli xabar bilan
        # qaytadi, xom stack-trace/500 emas.
        def boom(*a, **k):
            raise RuntimeError("YouTube vaqtincha javob bermadi")

        monkeypatch.setattr(search_module, "search", boom)

        res = client.post("/api/transcript/search", json={"query": "salom"})

        assert res.status_code == 400
        assert "YouTube vaqtincha javob bermadi" in res.json()["detail"]

    def test_clamps_max_videos_to_fifty(self, client, monkeypatch):
        captured = {}

        def fake_search(query, channel_id=None, max_videos=None, context_size=1,
                         published_after=None, published_before=None):
            captured["max_videos"] = max_videos
            return {"results": [], "blocked": False}

        monkeypatch.setattr(search_module, "search", fake_search)

        res = client.post("/api/transcript/search", json={"query": "salom", "max_videos": 999})

        assert res.status_code == 200
        assert captured["max_videos"] == 50

    def test_allows_higher_max_videos_ceiling_when_date_range_given(self, client, monkeypatch):
        # 50 juda faol kanalda sana oralig'ining atigi bir necha haftasini
        # qamrab olardi — sana oralig'i berilganda chegara ancha yuqoriroq
        # bo'lishi kerak (`search.py`dagi `DEFAULT_DATE_RANGE_MAX_VIDEOS`ga qarang).
        captured = {}

        def fake_search(query, channel_id=None, max_videos=None, context_size=1,
                         published_after=None, published_before=None):
            captured["max_videos"] = max_videos
            return {"results": [], "blocked": False}

        monkeypatch.setattr(search_module, "search", fake_search)

        res = client.post("/api/transcript/search", json={
            "query": "salom", "max_videos": 999, "published_after": "2023-01-01",
        })

        assert res.status_code == 200
        assert captured["max_videos"] == 500

    def test_missing_query_field_returns_422(self, client):
        res = client.post("/api/transcript/search", json={})
        assert res.status_code == 422

    def test_published_date_range_is_passed_through(self, client, monkeypatch):
        captured = {}

        def fake_search(query, channel_id=None, max_videos=None, context_size=1,
                         published_after=None, published_before=None):
            captured["published_after"] = published_after
            captured["published_before"] = published_before
            return {"results": [], "blocked": False}

        monkeypatch.setattr(search_module, "search", fake_search)

        res = client.post("/api/transcript/search", json={
            "query": "salom", "published_after": "2023-01-01", "published_before": "2023-03-31",
        })

        assert res.status_code == 200
        assert captured["published_after"] == "2023-01-01"
        assert captured["published_before"] == "2023-03-31"

    def test_find_source_returns_match(self, client, monkeypatch):
        captured = {}

        def fake_find_source(clip_url, channel_id=None):
            captured["clip_url"] = clip_url
            captured["channel_id"] = channel_id
            return {
                "found": True, "confident": True, "clip_id": "B4uytxWGWEk", "clip_language": "uz",
                "match": {
                    "video_id": "VoL8U_UF0do", "video_title": "45 million in Thailand",
                    "channel_name": "IShowSpeed", "published_at": "2025-10-21",
                    "start_time": 6015.0, "score": 33.6, "matched_terms": ["marker"],
                    "url": "https://youtube.com/watch?v=VoL8U_UF0do&t=6015s",
                },
            }

        monkeypatch.setattr(find_source_module, "find_source", fake_find_source)

        res = client.post("/api/transcript/find-source", json={
            "clip_url": "https://youtube.com/shorts/B4uytxWGWEk", "channel_id": "UCabc",
        })

        assert res.status_code == 200
        body = res.json()
        assert body["found"] is True
        assert body["match"]["video_id"] == "VoL8U_UF0do"
        assert captured["channel_id"] == "UCabc"

    def test_find_source_not_found_is_200_not_error(self, client, monkeypatch):
        monkeypatch.setattr(find_source_module, "find_source", lambda *a, **k: {
            "found": False, "confident": False, "clip_id": "x", "clip_language": None, "match": None,
        })

        res = client.post("/api/transcript/find-source", json={"clip_url": "B4uytxWGWEk"})

        assert res.status_code == 200
        assert res.json()["found"] is False

    def test_find_source_blocked_returns_503(self, client, monkeypatch):
        def boom(*a, **k):
            raise fetch.TranscriptFetchBlocked("HTTP Error 429")

        monkeypatch.setattr(find_source_module, "find_source", boom)

        res = client.post("/api/transcript/find-source", json={"clip_url": "B4uytxWGWEk"})

        assert res.status_code == 503

    def test_find_source_bad_url_returns_400(self, client, monkeypatch):
        def boom(*a, **k):
            raise ValueError("Video ID aniqlanmadi")

        monkeypatch.setattr(find_source_module, "find_source", boom)

        res = client.post("/api/transcript/find-source", json={"clip_url": "https://example.com/x"})

        assert res.status_code == 400

    def test_find_source_missing_clip_url_returns_422(self, client):
        res = client.post("/api/transcript/find-source", json={})
        assert res.status_code == 422

    def test_find_source_updates_the_index_before_searching(self, client, monkeypatch):
        # Kanal bir marta indexlangach, keyin chiqqan streamlar indeksga
        # tushmasdi — ya'ni kechagi streamdan olingan klip hech qachon
        # topilmasdi va foydalanuvchi kanalni qo'lda qayta indexlashi
        # kerak bo'lardi. Endi bu avtomatik bajariladi.
        order = []
        monkeypatch.setattr(search_module, "catch_up", lambda channel_ref=None, **kw: (
            order.append(("catch_up", channel_ref)) or {"indexed": 3, "pending": 0, "blocked": False}
        ))
        monkeypatch.setattr(find_source_module, "find_source", lambda *a, **k: (
            order.append(("find_source", None)) or {
                "found": False, "confident": False, "clip_id": "x",
                "clip_language": None, "match": None,
            }
        ))

        res = client.post("/api/transcript/find-source",
                          json={"clip_url": "B4uytxWGWEk", "channel_id": "@IShowSpeed"})

        assert res.status_code == 200
        assert order == [("catch_up", "@IShowSpeed"), ("find_source", None)]
        assert res.json()["catch_up"]["indexed"] == 3

    def test_find_source_still_works_when_index_update_fails(self, client, monkeypatch):
        # Yangilash — qulaylik, majburiy shart emas: API kaliti yo'q yoki
        # YouTube bloklagan bo'lsa ham, mavjud indeks ustida qidiruv
        # davom etishi kerak.
        def boom(channel_ref=None, **kw):
            raise fetch.ConfigError("YOUTUBE_API_KEY o'rnatilmagan")

        monkeypatch.setattr(search_module, "catch_up", boom)
        monkeypatch.setattr(find_source_module, "find_source", lambda *a, **k: {
            "found": True, "confident": True, "clip_id": "x", "clip_language": "en",
            "match": {"video_id": "v1", "video_title": "T", "channel_name": "C",
                      "published_at": None, "start_time": 1.0, "score": 20.0,
                      "margin": 3.0, "matched_terms": ["a"], "url": "https://y/watch?v=v1"},
        })

        res = client.post("/api/transcript/find-source", json={"clip_url": "B4uytxWGWEk"})

        assert res.status_code == 200
        assert res.json()["found"] is True
        assert "YOUTUBE_API_KEY" in res.json()["catch_up"]["error"]

    def test_invalid_date_format_returns_400(self, client, monkeypatch):
        monkeypatch.setattr(search_module, "search", lambda *a, **k: (_ for _ in ()).throw(
            ValueError("Invalid isoformat string: 'not-a-date'")
        ))

        res = client.post("/api/transcript/search", json={"query": "salom", "published_after": "not-a-date"})

        assert res.status_code == 400
