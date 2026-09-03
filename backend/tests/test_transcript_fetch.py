"""transcript/fetch.py: kanal identifikatorini ajratish va Data API v3
chaqiruvlari — haqiqiy google-api-python-client ishlatilmaydi, `_client()`
o'rniga soxta (fake) YouTube resurs obyekti monkeypatch qilinadi.
Transkript olish (`fetch_transcript`) uchun esa `downloader.ydl_opts_ctx`
va `yt_dlp.YoutubeDL` soxtalashtiriladi — na tarmoqqa, na haqiqiy yt-dlp/PO
token serveriga tegilmaydi."""
import contextlib
import io
import json

import pytest

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

    def test_extracts_published_at_date(self, monkeypatch):
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(playlist_items=lambda **kw: {
            "items": [{
                "snippet": {"title": "V1", "resourceId": {"kind": "youtube#video", "videoId": "id1"}},
                "contentDetails": {"videoPublishedAt": "2023-02-15T10:30:00Z"},
            }],
        }))

        videos = fetch.list_channel_videos("UUxxxx")

        assert videos[0]["published_at"] == "2023-02-15"

    def test_falls_back_to_snippet_published_at_when_content_details_missing(self, monkeypatch):
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(playlist_items=lambda **kw: {
            "items": [{
                "snippet": {
                    "title": "V1", "publishedAt": "2023-05-01T00:00:00Z",
                    "resourceId": {"kind": "youtube#video", "videoId": "id1"},
                },
            }],
        }))

        videos = fetch.list_channel_videos("UUxxxx")

        assert videos[0]["published_at"] == "2023-05-01"


class TestListChannelVideosDateRange:
    def _item(self, video_id, published_date):
        return {
            "snippet": {"title": video_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}},
            "contentDetails": {"videoPublishedAt": f"{published_date}T00:00:00Z"},
        }

    def test_excludes_videos_newer_than_published_before(self, monkeypatch):
        # Playlist eng yangi-birinchi: "gacha" chegarasidan yangiroqlarini
        # o'tkazib yuborib, sahifalashni DAVOM ETTIRISH kerak (eskiroqlar
        # hali oldinda bo'lishi mumkin).
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(playlist_items=lambda **kw: {
            "items": [self._item("too_new", "2023-06-01"), self._item("in_range", "2023-03-01")],
        }))

        videos = fetch.list_channel_videos("UUxxxx", published_before="2023-04-01")

        assert [v["video_id"] for v in videos] == ["in_range"]

    def test_stops_pagination_once_older_than_published_after(self, monkeypatch):
        pages = {
            None: {
                "items": [self._item("in_range", "2023-02-01"), self._item("too_old", "2022-01-01")],
                "nextPageToken": "page2",
            },
            "page2": {
                # Bu sahifa umuman so'ralmasligi kerak — birinchi sahifada
                # allaqachon `published_after`dan eskiroq videoga yetilgan.
                "items": [self._item("never_reached", "2021-01-01")],
            },
        }
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(
            playlist_items=lambda **kw: pages[kw.get("pageToken")]
        ))

        videos = fetch.list_channel_videos("UUxxxx", published_after="2023-01-01")

        assert [v["video_id"] for v in videos] == ["in_range"]

    def test_max_results_caps_matched_videos_not_scanned_items(self, monkeypatch):
        # Sana oralig'ida `max_results` KO'RIB CHIQILGAN emas, MOS KELGAN
        # videolar soniga chegara — bitta sahifada mos kelmagan (juda yangi)
        # elementlar bo'lsa ham, keyingi sahifa hali so'ralishi kerak.
        pages = {
            None: {
                "items": [self._item("too_new", "2023-06-01")],
                "nextPageToken": "page2",
            },
            "page2": {
                "items": [self._item("match1", "2023-03-01"), self._item("match2", "2023-02-01")],
            },
        }
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(
            playlist_items=lambda **kw: pages[kw.get("pageToken")]
        ))

        videos = fetch.list_channel_videos(
            "UUxxxx", max_results=1, published_after="2023-01-01", published_before="2023-04-01",
        )

        assert [v["video_id"] for v in videos] == ["match1"]


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

    def test_passes_published_date_range_as_rfc3339_to_data_api(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(
            search=lambda **kw: seen.update(kw) or {"items": []}
        ))

        fetch.search_videos("q", published_after="2023-01-01", published_before="2023-03-31")

        assert seen["publishedAfter"] == "2023-01-01T00:00:00Z"
        assert seen["publishedBefore"] == "2023-03-31T23:59:59Z"

    def test_omits_date_params_when_not_given(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(fetch, "_client", lambda: FakeYouTube(
            search=lambda **kw: seen.update(kw) or {"items": []}
        ))

        fetch.search_videos("q")

        assert "publishedAfter" not in seen
        assert "publishedBefore" not in seen

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


class _FakeYdl:
    """`yt_dlp.YoutubeDL`ning testlar uchun yengil o'rnini bosuvchisi —
    `extract_info` berilgan `info`ni (yoki `error`ni) qaytaradi, `urlopen`
    esa berilgan xom baytlarni o'qiladigan oqim sifatida beradi (haqiqiy
    ``ydl.urlopen(url).read()`` chaqiruviga mos)."""

    def __init__(self, info=None, caption_bytes=b"", error=None):
        self._info = info
        self._caption_bytes = caption_bytes
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if self._error is not None:
            raise self._error
        return self._info

    def urlopen(self, url):
        return io.BytesIO(self._caption_bytes)


@pytest.fixture
def fake_ytdlp(monkeypatch):
    """`fetch_transcript` ichidagi `downloader.ydl_opts_ctx` va
    `yt_dlp.YoutubeDL`ni soxtalashtiradi — chaqiruvchi `info`/`caption_bytes`
    (muvaffaqiyat) yoki `error` (`extract_info` ko'taradigan xato) beradi."""
    def install(info=None, caption_bytes=b"", error=None):
        monkeypatch.setattr(fetch.downloader, "ydl_opts_ctx", lambda extra: contextlib.nullcontext({}))
        monkeypatch.setattr(fetch.yt_dlp, "YoutubeDL", lambda opts: _FakeYdl(info, caption_bytes, error))
    return install


def _json3_bytes(events: list[dict]) -> bytes:
    return json.dumps({"events": events}).encode("utf-8")


class TestFetchTranscript:
    def test_returns_parsed_segments_from_manual_subtitles(self, fake_ytdlp):
        info = {"subtitles": {"en": [{"ext": "json3", "url": "https://example.com/en.json3"}]}, "automatic_captions": {}}
        caption_bytes = _json3_bytes([{"tStartMs": 0, "dDurationMs": 1500, "segs": [{"utf8": "salom"}]}])
        fake_ytdlp(info=info, caption_bytes=caption_bytes)

        assert fetch.fetch_transcript("abc123", languages=["en"]) == [
            {"text": "salom", "start": 0.0, "duration": 1.5}
        ]

    def test_prefers_manual_subtitles_over_automatic_captions(self, fake_ytdlp):
        info = {
            "subtitles": {"en": [{"ext": "json3", "url": "https://example.com/manual.json3"}]},
            "automatic_captions": {"en": [{"ext": "json3", "url": "https://example.com/auto.json3"}]},
        }
        caption_bytes = _json3_bytes([{"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "qo'lda"}]}])
        fake_ytdlp(info=info, caption_bytes=caption_bytes)

        assert fetch.fetch_transcript("abc123", languages=["en"]) == [
            {"text": "qo'lda", "start": 0.0, "duration": 1.0}
        ]

    def test_falls_back_to_automatic_captions_when_no_manual_subtitles(self, fake_ytdlp):
        info = {"subtitles": {}, "automatic_captions": {"en": [{"ext": "json3", "url": "https://example.com/auto.json3"}]}}
        caption_bytes = _json3_bytes([{"tStartMs": 500, "dDurationMs": 2000, "segs": [{"utf8": "avto"}]}])
        fake_ytdlp(info=info, caption_bytes=caption_bytes)

        assert fetch.fetch_transcript("abc123", languages=["en"]) == [
            {"text": "avto", "start": 0.5, "duration": 2.0}
        ]

    def test_tries_languages_in_priority_order(self, fake_ytdlp):
        # 'uz' talab qilingan ro'yxatda birinchi, lekin faqat 'en' mavjud —
        # ro'yxatdagi keyingi til ishlatilishi kerak.
        info = {"subtitles": {}, "automatic_captions": {"en": [{"ext": "json3", "url": "https://example.com/en.json3"}]}}
        caption_bytes = _json3_bytes([{"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "hi"}]}])
        fake_ytdlp(info=info, caption_bytes=caption_bytes)

        assert fetch.fetch_transcript("abc123", languages=["uz", "en"]) is not None

    def test_returns_none_when_no_caption_in_requested_languages(self, fake_ytdlp):
        info = {"subtitles": {}, "automatic_captions": {"fr": [{"ext": "json3", "url": "x"}]}}
        fake_ytdlp(info=info)

        assert fetch.fetch_transcript("abc123", languages=["uz", "en"]) is None

    def test_returns_none_when_no_json3_format_available(self, fake_ytdlp):
        # json3'dan boshqa format (masalan faqat vtt) hozircha qo'llab-
        # quvvatlanmaydi — "subtitr yo'q" deb hisoblanadi.
        info = {"subtitles": {"en": [{"ext": "vtt", "url": "x"}]}, "automatic_captions": {}}
        fake_ytdlp(info=info)

        assert fetch.fetch_transcript("abc123", languages=["en"]) is None

    def test_skips_events_without_text(self, fake_ytdlp):
        info = {"subtitles": {"en": [{"ext": "json3", "url": "x"}]}, "automatic_captions": {}}
        caption_bytes = _json3_bytes([
            {"tStartMs": 0, "dDurationMs": 1000},  # "segs" umuman yo'q
            {"tStartMs": 1000, "dDurationMs": 1000, "segs": [{"utf8": "   "}]},  # faqat bo'shliq
            {"tStartMs": 2000, "dDurationMs": 1000, "segs": [{"utf8": "matn"}]},
        ])
        fake_ytdlp(info=info, caption_bytes=caption_bytes)

        assert fetch.fetch_transcript("abc123", languages=["en"]) == [
            {"text": "matn", "start": 2.0, "duration": 1.0}
        ]

    @pytest.mark.parametrize("message", [
        "ERROR: [youtube] abc123: Video unavailable",
        "ERROR: [youtube] abc123: Private video. Sign in if you've been granted access to this video",
        "This video has been removed by the uploader",
        "This video is no longer available because the YouTube account "
        "associated with this video has been terminated",
        "ERROR: [youtube] xyz789: This live event will begin in 12 hours.",
    ])
    def test_returns_none_for_permanently_unavailable_video(self, fake_ytdlp, message):
        fake_ytdlp(error=RuntimeError(message))

        assert fetch.fetch_transcript("abc123") is None

    def test_raises_transcript_fetch_blocked_for_unexpected_errors(self, fake_ytdlp):
        # Tarmoq xatosi / "Sign in to confirm you're not a bot" / PO token
        # muammosi va h.k. — bu VIDEO haqida emas, shuning uchun "subtitr
        # yo'q" bilan bir xil `None`ga aralashtirilmasligi kerak (aks holda
        # kanal indexlashda video abadiy "tekshirilgan, subtitri yo'q" deb
        # qolib ketardi — haqiqiy IShowSpeed jonli tekshiruvida aynan shu
        # holat, avvalgi youtube-transcript-api asosidagi kodda, yuz bergan).
        fake_ytdlp(error=RuntimeError("Sign in to confirm you're not a bot"))

        with pytest.raises(fetch.TranscriptFetchBlocked):
            fetch.fetch_transcript("abc123")

    def test_age_restriction_is_treated_as_temporary_not_permanent(self, fake_ytdlp):
        # Cookie sozlansa keyinroq ochilishi mumkin bo'lgan holat —
        # doimiy "subtitr yo'q" deb belgilanmasligi kerak.
        fake_ytdlp(error=RuntimeError("Sign in to confirm your age"))

        with pytest.raises(fetch.TranscriptFetchBlocked):
            fetch.fetch_transcript("abc123")
