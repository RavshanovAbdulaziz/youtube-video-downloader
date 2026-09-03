"""get_info()'ning format tahlili — yt-dlp'ga chiqmasdan, soxta `info`
lug'ati bilan. Aynan shu mantiq buzilganda UI'da Audio/AI ajratish tablari
yo'qolib qolgan edi (audio_tracks bo'sh chiqqani uchun)."""
import pytest

import downloader


class _FakeYdl:
    def __init__(self, info):
        self._info = info

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return self._info


@pytest.fixture
def fake_extract(monkeypatch):
    def _install(info):
        monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", lambda opts: _FakeYdl(info))
    return _install


def _video(fid, height, vcodec="avc1.4d401f", **extra):
    base = {
        "format_id": fid, "vcodec": vcodec, "acodec": "none",
        "height": height, "width": height * 16 // 9, "ext": "mp4", "fps": 30,
    }
    base.update(extra)
    return base


def _audio(fid, acodec="mp4a.40.2", **extra):
    base = {"format_id": fid, "vcodec": "none", "acodec": acodec, "ext": "m4a", "abr": 128}
    base.update(extra)
    return base


class TestAudioTracks:
    def test_extracts_single_audio_track(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100,
            "formats": [_video("137", 1080), _audio("140")],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")

        assert len(info["audio_tracks"]) == 1, "audio trek topilmadi — Audio/AI tablari yo'qoladi"
        assert info["audio_tracks"][0]["format_id"] == "140"
        assert info["audio_tracks"][0]["is_original"] is True

    def test_empty_when_no_audio_only_formats(self, fake_extract):
        # Faqat progressive (video+audio birga) formatlar — bu aynan
        # "web_safari/SABR" holati edi: audio_tracks bo'sh chiqardi.
        fake_extract({
            "title": "T", "duration": 100,
            "formats": [_video("18", 360, acodec="mp4a.40.2")],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        assert info["audio_tracks"] == []

    def test_groups_dubbed_tracks_by_language(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100,
            "formats": [
                _video("137", 1080),
                _audio("140-en", language="en", language_preference=10),
                _audio("140-ru", language="ru", language_preference=-1),
                _audio("140-uz", language="uz", language_preference=-1),
            ],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")

        assert len(info["audio_tracks"]) == 3
        # Original trek birinchi bo'lishi kerak.
        assert info["audio_tracks"][0]["is_original"] is True
        assert info["audio_tracks"][0]["lang_code"] == "en"
        assert "original" in info["audio_tracks"][0]["label"]

    def test_prefers_aac_over_opus_for_same_language(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100,
            "formats": [
                _video("137", 1080),
                _audio("251", acodec="opus", abr=160),   # yuqoriroq bitrate, lekin opus
                _audio("140", acodec="mp4a.40.2", abr=128),
            ],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        # mp4 konteynerida AAC kengroq qo'llab-quvvatlanadi — u tanlanishi kerak.
        assert info["audio_tracks"][0]["format_id"] == "140"


class TestResolutions:
    def test_deduplicates_by_height_and_sorts_desc(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100,
            "formats": [
                _video("160", 144), _video("137", 1080),
                _video("136", 720), _audio("140"),
            ],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")

        heights = [r["height"] for r in info["resolutions"]]
        assert heights == sorted(heights, reverse=True), "sifatlar kamayish tartibida emas"
        assert heights == [1080, 720, 144]

    def test_prefers_h264_over_vp9_at_same_height(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100,
            "formats": [
                _video("248", 1080, vcodec="vp9", tbr=5000),
                _video("137", 1080, vcodec="avc1.640028", tbr=3000),
                _audio("140"),
            ],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        # avc1 deyarli hamma playerda ochiladi — bitrate pastroq bo'lsa ham u tanlanadi.
        assert info["resolutions"][0]["format_id"] == "137"

    def test_labels_high_fps(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100,
            "formats": [_video("299", 1080, fps=60), _audio("140")],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        assert info["resolutions"][0]["label"] == "1080p60"

    def test_falls_back_to_progressive_when_no_video_only(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100,
            "formats": [_video("18", 360, acodec="mp4a.40.2")],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        assert len(info["resolutions"]) == 1
        assert info["resolutions"][0]["has_audio"] is True
        assert info["has_video_only_streams"] is False

    def test_skips_formats_without_height(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100,
            "formats": [
                {"format_id": "sb0", "vcodec": "images", "acodec": "none", "ext": "mhtml"},
                _video("137", 1080), _audio("140"),
            ],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        # Storyboard (sb0) sifat ro'yxatiga tushmasligi kerak.
        assert [r["format_id"] for r in info["resolutions"]] == ["137"]


class TestIsLive:
    def test_true_for_ongoing_live_stream(self, fake_extract):
        fake_extract({
            "title": "T", "duration": None, "is_live": True,
            "formats": [_video("96", 1080), _audio("140")],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        assert info["is_live"] is True

    def test_false_for_regular_video(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100,
            "formats": [_video("137", 1080), _audio("140")],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        assert info["is_live"] is False

    def test_false_when_key_missing_entirely(self, fake_extract):
        # `is_live` ba'zi extraktorlarda umuman qaytmasligi mumkin — bo'lmasa
        # "False" deb hisoblanishi kerak, KeyError emas.
        fake_extract({"title": "T", "duration": 100, "formats": [_video("137", 1080)]})
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        assert info["is_live"] is False


class TestSubtitles:
    def test_manual_subs_always_included(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100, "formats": [_video("137", 1080)],
            "subtitles": {"en": [{"ext": "vtt"}], "zz-unknown": [{"ext": "vtt"}]},
            "automatic_captions": {},
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        codes = {s["lang_code"] for s in info["subtitles"]}
        # Qo'lda qo'shilgan subtitrlar kodi notanish bo'lsa ham ko'rsatiladi.
        assert codes == {"en", "zz-unknown"}
        assert all(s["auto"] is False for s in info["subtitles"])

    def test_auto_subs_limited_to_known_languages(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100, "formats": [_video("137", 1080)],
            "subtitles": {},
            "automatic_captions": {"uz": [{"ext": "vtt"}], "xx-nonsense": [{"ext": "vtt"}]},
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        codes = {s["lang_code"] for s in info["subtitles"]}
        # Avtomatik subtitrlar yuzlab tilga tarjima qilinadi — faqat
        # tanilganlari ko'rsatiladi, aks holda ro'yxat shishib ketardi.
        assert codes == {"uz"}

    def test_manual_wins_over_auto_for_same_language(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100, "formats": [_video("137", 1080)],
            "subtitles": {"en": [{"ext": "vtt"}]},
            "automatic_captions": {"en": [{"ext": "vtt"}]},
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        en = [s for s in info["subtitles"] if s["lang_code"] == "en"]
        assert len(en) == 1 and en[0]["auto"] is False

    def test_empty_track_lists_ignored(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 100, "formats": [_video("137", 1080)],
            "subtitles": {"en": []},
            "automatic_captions": {},
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        assert info["subtitles"] == []


class TestLinkStartTime:
    """Havolaga qo'shilgan vaqt belgisi (`?t=`) — YouTube ulashish oynasidagi
    "Start at" katakchasi va transcript qidiruvimiz bergan havolalar shu
    orqali klip slayderining boshlanish nuqtasini oldindan belgilaydi."""

    @pytest.mark.parametrize("url,expected", [
        # "Start at" katakchasi belgilanganda ulashish paneli beradigan shakl.
        ("https://www.youtube.com/live/aqSZK-rCm7w?si=puWUloi&t=375", 375),
        # transcript/search.py'dagi _youtube_link aynan shunday yozadi.
        ("https://youtube.com/watch?v=abc&t=375s", 375),
        ("https://youtu.be/abc?t=1h2m3s", 3723),
        ("https://www.youtube.com/watch?v=abc&t=2m30s", 150),
        ("https://www.youtube.com/watch?v=abc&t=1h", 3600),
        # Embed havolalari `start=`, eski ko'chirmalar esa `#t=` ishlatadi.
        ("https://www.youtube.com/embed/abc?start=90", 90),
        ("https://www.youtube.com/watch?v=abc#t=90", 90),
    ])
    def test_parses_supported_forms(self, url, expected):
        assert downloader.parse_start_time(url) == expected

    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v=abc",
        "https://www.youtube.com/watch?v=abc&t=0",
        "https://www.youtube.com/watch?v=abc&t=",
        "https://www.youtube.com/watch?v=abc&t=notatime",
        "https://www.youtube.com/watch?v=abc&t=12x",
    ])
    def test_returns_none_without_usable_timestamp(self, url):
        assert downloader.parse_start_time(url) is None

    def test_get_info_exposes_start_time(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 600,
            "formats": [_video("137", 1080), _audio("140")],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc&t=375")
        assert info["start_time"] == 375

    def test_get_info_start_time_none_without_timestamp(self, fake_extract):
        fake_extract({
            "title": "T", "duration": 600,
            "formats": [_video("137", 1080), _audio("140")],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc")
        assert info["start_time"] is None

    def test_ignores_timestamp_beyond_duration(self, fake_extract):
        # Boshqa (uzunroq) videodan ko'chirilgan havola — dastakni video
        # tashqarisiga surib qo'ymaslik uchun e'tiborga olinmaydi.
        fake_extract({
            "title": "T", "duration": 100,
            "formats": [_video("137", 1080), _audio("140")],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc&t=500")
        assert info["start_time"] is None

    def test_keeps_timestamp_when_duration_unknown(self, fake_extract):
        # Jonli efir / davomiyligi noma'lum bo'lgan holat — vaqt belgisini
        # tekshiradigan chegara yo'q, shuning uchun u shundayligicha qoladi.
        fake_extract({
            "title": "T", "duration": None,
            "formats": [_video("137", 1080), _audio("140")],
        })
        info = downloader.get_info("https://www.youtube.com/watch?v=abc&t=42")
        assert info["start_time"] == 42
