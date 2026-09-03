"""transcript/fetch.py: kanal identifikatorini ajratish va Data API v3
chaqiruvlari — haqiqiy google-api-python-client ishlatilmaydi, `_client()`
o'rniga soxta (fake) YouTube resurs obyekti monkeypatch qilinadi."""
import pytest
from youtube_transcript_api._errors import IpBlocked

from transcript import fetch


class _Exec:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return self._data


class _Endpoint:
    """`.channels()`/`.search()`/`.playlistItems()` — har biri `.list(**kw)`
    chaqirilganda berilgan `handler(**kw)` natijasini qaytaradi."""

    def __init__(self, handler):
        self._handler = handler

    def list(self, **kwargs):
        return _Exec(self._handler(**kwargs))


class FakeYouTube:
    def __init__(self, channels=None, search=None, playlist_items=None):
        self._channels = channels or (lambda **kw: {"items": []})
        self._search = search or (lambda **kw: {"items": []})
        self._playlist_items = playlist_items or (lambda **kw: {"items": []})

    def channels(self):
        return _Endpoint(self._channels)

    def search(self):
        return _Endpoint(self._search)

    def playlistItems(self):
        return _Endpoint(self._playlist_items)


class TestParseChannelRef:
    @pytest.mark.parametrize("ref,expected", [
        ("@IShowSpeed", ("handle", "IShowSpeed")),
        ("IShowSpeed", ("handle", "IShowSpeed")),
        ("https://www.youtube.com/@IShowSpeed", ("handle", "IShowSpeed")),
        ("https://www.youtube.com/@IShowSpeed/videos", ("handle", "IShowSpeed")),
        ("https://www.youtube.com/user/OldSchoolName", ("username", "OldSchoolName")),
    ])
    def test_parses_common_formats(self, ref, expected):
        assert fetch._parse_channel_ref(ref) == expected

    def test_parses_raw_channel_id(self):
        channel_id = "UC" + "x" * 22
        assert fetch._parse_channel_ref(channel_id) == ("id", channel_id)

    def test_parses_channel_url_with_id(self):
        channel_id = "UC" + "y" * 22
        assert fetch._parse_channel_ref(f"https://www.youtube.com/channel/{channel_id}") == ("id", channel_id)


class TestResolveChannel:
    def test_resolves_by_handle(self, monkeypatch):
        channel_id = "UC" + "a" * 22

        def channels(**kw):
            if kw.get("forHandle") == "@IShowSpeed":
                return {"items": [{
                    "id": channel_id,
                    "snippet": {"title": "IShowSpeed"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU" + "a" * 22}},
                }]}
            return {"items": []}

        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(channels=channels))

        info = fetch.resolve_channel("https://www.youtube.com/@IShowSpeed")

        assert info == {
            "channel_id": channel_id,
            "title": "IShowSpeed",
            "uploads_playlist_id": "UU" + "a" * 22,
        }

    def test_falls_back_to_search_when_handle_lookup_is_empty(self, monkeypatch):
        # Eskirgan "/c/nom" qisqa havolasi haqiqiy @handle bo'lmasligi mumkin
        # — shunda channels.list(forHandle=...) bo'sh qaytaradi va
        # search.list orqali topilishi kerak.
        channel_id = "UC" + "b" * 22

        def channels(**kw):
            if kw.get("id") == channel_id:
                return {"items": [{
                    "id": channel_id,
                    "snippet": {"title": "Legacy Channel"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU" + "b" * 22}},
                }]}
            return {"items": []}

        def search(**kw):
            return {"items": [{"snippet": {"channelId": channel_id}}]}

        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(channels=channels, search=search))

        info = fetch.resolve_channel("https://www.youtube.com/c/LegacyName")

        assert info["channel_id"] == channel_id
        assert info["title"] == "Legacy Channel"

    def test_raises_value_error_when_channel_not_found(self, monkeypatch):
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube())

        with pytest.raises(ValueError):
            fetch.resolve_channel("@totally-nonexistent-channel-xyz")

    def test_unescapes_html_entities_in_title(self, monkeypatch):
        # Haqiqiy Data API sarlavhalarni HTML-entity qilib qaytaradi
        # (masalan "Guetta &amp; Bebe Rexha") — IShowSpeed kanaliga qarshi
        # jonli tekshiruvda topilgan haqiqiy xatti-harakat.
        channel_id = "UC" + "c" * 22
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(channels=lambda **kw: {"items": [{
            "id": channel_id,
            "snippet": {"title": "Guetta &amp; Bebe Rexha"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU" + "c" * 22}},
        }]}))

        info = fetch.resolve_channel(channel_id)

        assert info["title"] == "Guetta & Bebe Rexha"


class TestListChannelVideos:
    def test_paginates_until_no_next_token(self, monkeypatch):
        pages = {
            None: {
                "items": [{"snippet": {"title": "V1", "resourceId": {"kind": "youtube#video", "videoId": "id1"}}}],
                "nextPageToken": "page2",
            },
            "page2": {
                "items": [{"snippet": {"title": "V2", "resourceId": {"kind": "youtube#video", "videoId": "id2"}}}],
            },
        }
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(
            playlist_items=lambda **kw: pages[kw.get("pageToken")]
        ))

        videos = fetch.list_channel_videos("UUxxxx")

        assert [v["video_id"] for v in videos] == ["id1", "id2"]

    def test_stops_once_max_results_reached(self, monkeypatch):
        call_count = {"n": 0}

        def playlist_items(**kw):
            call_count["n"] += 1
            n = call_count["n"]
            return {
                "items": [{"snippet": {"title": f"V{n}", "resourceId": {"kind": "youtube#video", "videoId": f"id{n}"}}}],
                "nextPageToken": f"page{n + 1}",
            }

        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(playlist_items=playlist_items))

        videos = fetch.list_channel_videos("UUxxxx", max_results=2)

        assert len(videos) == 2
        assert call_count["n"] == 2

    def test_skips_non_video_playlist_items(self, monkeypatch):
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(playlist_items=lambda **kw: {
            "items": [
                {"snippet": {"title": "O'chirilgan", "resourceId": {"kind": "youtube#somethingElse"}}},
                {"snippet": {"title": "V1", "resourceId": {"kind": "youtube#video", "videoId": "id1"}}},
            ]
        }))

        videos = fetch.list_channel_videos("UUxxxx")

        assert [v["video_id"] for v in videos] == ["id1"]


class TestSearchVideos:
    def test_returns_parsed_candidates(self, monkeypatch):
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(search=lambda **kw: {
            "items": [{"id": {"videoId": "vid1"}, "snippet": {"title": "T1", "channelId": "UC1", "channelTitle": "Ch1"}}]
        }))

        videos = fetch.search_videos("hello world")

        assert videos == [{"video_id": "vid1", "title": "T1", "channel_id": "UC1", "channel_name": "Ch1"}]

    def test_clamps_max_results_to_fifty(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(
            search=lambda **kw: seen.update(kw) or {"items": []}
        ))

        fetch.search_videos("q", max_results=500)

        assert seen["maxResults"] == 50

    def test_unescapes_html_entities_in_title_and_channel_name(self, monkeypatch):
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(search=lambda **kw: {
            "items": [{
                "id": {"videoId": "vid1"},
                "snippet": {"title": "Let&#39;s Go", "channelId": "UC1", "channelTitle": "Guetta &amp; Friends"},
            }]
        }))

        videos = fetch.search_videos("q")

        assert videos[0]["title"] == "Let's Go"
        assert videos[0]["channel_name"] == "Guetta & Friends"

    def test_skips_items_without_video_id(self, monkeypatch):
        # Playlist/kanal natijalari aralashib qolsa (`id.videoId` yo'q) —
        # KeyError bilan qulamasligi kerak.
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(search=lambda **kw: {
            "items": [{"id": {"kind": "youtube#channel"}, "snippet": {"title": "Kanal"}}]
        }))

        assert fetch.search_videos("q") == []


class TestReadBackendEnvFallback:
    def test_reads_key_from_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("BOT_TOKEN=xyz\nYOUTUBE_API_KEY=AIzaTest123\n", encoding="utf-8")

        assert fetch._read_backend_env_fallback("YOUTUBE_API_KEY", str(env_file)) == "AIzaTest123"

    def test_returns_empty_string_when_key_absent(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("BOT_TOKEN=xyz\n", encoding="utf-8")

        assert fetch._read_backend_env_fallback("YOUTUBE_API_KEY", str(env_file)) == ""

    def test_returns_empty_string_when_file_missing(self, tmp_path):
        assert fetch._read_backend_env_fallback("YOUTUBE_API_KEY", str(tmp_path / "no_such.env")) == ""


class TestClientConfig:
    def test_raises_config_error_without_api_key_anywhere(self, monkeypatch, tmp_path):
        fetch._client.cache_clear()
        monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
        monkeypatch.setattr(fetch, "_BACKEND_ENV_FILE", str(tmp_path / "no_such.env"))

        with pytest.raises(fetch.ConfigError):
            fetch._client()

        fetch._client.cache_clear()

    def test_falls_back_to_backend_env_file_when_env_var_missing(self, monkeypatch, tmp_path):
        # start.bat/tray_app.py orqali ishga tushirilganda backend/.env
        # hech qachon avtomatik process env'ga yuklanmaydi — shu holatni
        # simulyatsiya qiladi (haqiqiy IShowSpeed kanaliga qarshi jonli
        # tekshiruvda aynan shu muammo topilgan edi).
        fetch._client.cache_clear()
        monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("YOUTUBE_API_KEY=AIzaFromFile\n", encoding="utf-8")
        monkeypatch.setattr(fetch, "_BACKEND_ENV_FILE", str(env_file))

        seen_keys = {}
        monkeypatch.setattr(fetch, "build", lambda *a, **kw: seen_keys.setdefault("key", kw.get("developerKey")))

        fetch._client()

        assert seen_keys["key"] == "AIzaFromFile"
        fetch._client.cache_clear()


class TestFetchTranscript:
    def test_returns_raw_data_on_success(self, monkeypatch):
        class _FakeTranscript:
            def to_raw_data(self):
                return [{"text": "salom", "start": 0.0, "duration": 1.5}]

        class _FakeApi:
            def fetch(self, video_id, languages=None):
                assert video_id == "abc123"
                return _FakeTranscript()

        monkeypatch.setattr(fetch, "YouTubeTranscriptApi", _FakeApi)

        assert fetch.fetch_transcript("abc123") == [{"text": "salom", "start": 0.0, "duration": 1.5}]

    @pytest.mark.parametrize("exc_cls", [
        fetch.TranscriptsDisabled, fetch.NoTranscriptFound, fetch.VideoUnavailable,
        fetch.VideoUnplayable, fetch.AgeRestricted, fetch.InvalidVideoId,
    ])
    def test_returns_none_for_permanently_unavailable_video(self, monkeypatch, exc_cls):
        # `__new__` orqali (constructor argumentlarisiz) — bu sinflarning
        # ba'zilari (masalan `VideoUnplayable`) murakkab argumentlar talab
        # qiladi, testda faqat isinstance() moslikni tekshiramiz.
        class _FakeApi:
            def fetch(self, video_id, languages=None):
                raise exc_cls.__new__(exc_cls)

        monkeypatch.setattr(fetch, "YouTubeTranscriptApi", _FakeApi)

        assert fetch.fetch_transcript("abc123") is None

    def test_raises_transcript_fetch_blocked_when_youtube_blocks_the_request(self, monkeypatch):
        # IP bloklanish/PO token va h.k. — bu video haqida emas, shuning
        # uchun "subtitr yo'q" bilan bir xil `None`ga aralashtirilmasligi
        # kerak (aks holda channel indexlashda video abadiy "tekshirilgan,
        # subtitri yo'q" deb qolib ketardi — haqiqiy IShowSpeed jonli
        # tekshiruvida aynan shu holat yuz berdi).
        class _FakeApi:
            def fetch(self, video_id, languages=None):
                raise IpBlocked(video_id)

        monkeypatch.setattr(fetch, "YouTubeTranscriptApi", _FakeApi)

        with pytest.raises(fetch.TranscriptFetchBlocked):
            fetch.fetch_transcript("abc123")

    def test_unexpected_exception_is_treated_as_blocked_not_permanent(self, monkeypatch):
        class _FakeApi:
            def fetch(self, video_id, languages=None):
                raise ConnectionError("timeout")

        monkeypatch.setattr(fetch, "YouTubeTranscriptApi", _FakeApi)

        with pytest.raises(fetch.TranscriptFetchBlocked):
            fetch.fetch_transcript("abc123")
