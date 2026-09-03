"""FastAPI /api/transcript/search qatlami — `search.search()` monkeypatch
qilinadi, faqat HTTP status/validatsiya/xato-xabar qatlami tekshiriladi
(test_api.py'dagi TestClipRangeValidation uslubiga o'xshash)."""
import pytest
from fastapi.testclient import TestClient

import main
from transcript import fetch
from transcript import search as search_module


@pytest.fixture
def client():
    return TestClient(main.app)


class TestTranscriptSearchEndpoint:
    def test_returns_results_for_valid_query(self, client, monkeypatch):
        monkeypatch.setattr(
            search_module, "search",
            lambda query, channel_id=None, max_videos=None, context_size=1: [
                {
                    "video_id": "v1", "video_title": "T", "channel_name": "Ch",
                    "text": "x", "start_time": 1.0, "url": "https://youtube.com/watch?v=v1&t=1s",
                }
            ],
        )

        res = client.post("/api/transcript/search", json={"query": "salom"})

        assert res.status_code == 200
        body = res.json()
        assert body["mode"] == "global"
        assert body["count"] == 1
        assert body["results"][0]["video_id"] == "v1"

    def test_channel_mode_used_when_channel_id_given(self, client, monkeypatch):
        captured = {}

        def fake_search(query, channel_id=None, max_videos=None, context_size=1):
            captured["channel_id"] = channel_id
            return []

        monkeypatch.setattr(search_module, "search", fake_search)

        res = client.post("/api/transcript/search", json={"query": "salom", "channel_id": "UCabc"})

        assert res.status_code == 200
        assert res.json()["mode"] == "channel"
        assert captured["channel_id"] == "UCabc"

    def test_empty_results_return_empty_list_not_error(self, client, monkeypatch):
        monkeypatch.setattr(search_module, "search", lambda *a, **k: [])

        res = client.post("/api/transcript/search", json={"query": "topilmaydigan ibora"})

        assert res.status_code == 200
        assert res.json() == {"query": "topilmaydigan ibora", "mode": "global", "count": 0, "results": []}

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

        def fake_search(query, channel_id=None, max_videos=None, context_size=1):
            captured["max_videos"] = max_videos
            return []

        monkeypatch.setattr(search_module, "search", fake_search)

        res = client.post("/api/transcript/search", json={"query": "salom", "max_videos": 999})

        assert res.status_code == 200
        assert captured["max_videos"] == 50

    def test_missing_query_field_returns_422(self, client):
        res = client.post("/api/transcript/search", json={})
        assert res.status_code == 422
