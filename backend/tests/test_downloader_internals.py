"""downloader.py'ning ichki yordamchi funksiyalari: qayta urinish siyosati,
fayl nomini tozalash, format tanlash va MP4 (ISO-BMFF) tahlili."""
import io
import os

import pytest

import downloader


class TestIsTransient:
    @pytest.mark.parametrize("message", [
        "HTTP Error 403: Forbidden",
        "unable to download video data: HTTP Error 403: Forbidden",
        "Connection reset by peer",
        "The read operation timed out",
        "Incomplete data received",
    ])
    def test_treats_network_errors_as_transient(self, message):
        assert downloader._is_transient(RuntimeError(message)) is True

    @pytest.mark.parametrize("message", [
        "Video unavailable",
        "Private video. Sign in if you've been granted access to this video",
        "This video is age-restricted",
        "Format topilmadi: 999",
    ])
    def test_permanent_errors_are_not_retried(self, message):
        # Bularni qayta urinish befoyda — foydalanuvchiga darhol
        # qaytarilishi kerak, 3 marta bekorga tortmasdan.
        assert downloader._is_transient(RuntimeError(message)) is False


class TestWithRetries:
    def test_returns_immediately_on_success(self):
        calls = []

        def action():
            calls.append(1)
            return "done"

        assert downloader._with_retries("job_success_000", action) == "done"
        assert len(calls) == 1

    def test_retries_transient_then_succeeds(self, monkeypatch):
        monkeypatch.setattr(downloader, "RETRY_DELAY_SECONDS", 0)  # testni tezlashtiramiz
        calls = []

        def action():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("HTTP Error 403: Forbidden")
            return "recovered"

        assert downloader._with_retries("job_retry_0000", action) == "recovered"
        assert len(calls) == 3, "403 xatosida qayta urinilmadi"

    def test_gives_up_after_max_attempts(self, monkeypatch):
        monkeypatch.setattr(downloader, "RETRY_DELAY_SECONDS", 0)
        calls = []

        def action():
            calls.append(1)
            raise RuntimeError("HTTP Error 403: Forbidden")

        with pytest.raises(RuntimeError, match="403"):
            downloader._with_retries("job_giveup_000", action)
        assert len(calls) == downloader.DOWNLOAD_ATTEMPTS

    def test_does_not_retry_permanent_error(self, monkeypatch):
        monkeypatch.setattr(downloader, "RETRY_DELAY_SECONDS", 0)
        calls = []

        def action():
            calls.append(1)
            raise RuntimeError("Video unavailable")

        with pytest.raises(RuntimeError, match="Video unavailable"):
            downloader._with_retries("job_permanent0", action)
        assert len(calls) == 1, "doimiy xatoda ham qayta urinildi (trafik isrofi)"


class TestFetchChunk:
    """`_fetch_chunk` — bitta Range so'rovini butun faylni qayta boshlamasdan
    joyida qayta so'raydigan qatlam (TestWithRetries'ning bo'lak darajasidagi
    hamkasbi)."""

    def test_returns_immediately_on_success(self):
        calls = []

        class FakeYdl:
            def urlopen(self, req):
                calls.append(req)
                return io.BytesIO(b"data")

        result = downloader._fetch_chunk(FakeYdl(), "http://x", {}, 0, 99)
        assert result == b"data"
        assert len(calls) == 1

    def test_retries_transient_then_succeeds(self, monkeypatch):
        monkeypatch.setattr(downloader, "CHUNK_RETRY_DELAY_SECONDS", 0)
        calls = []

        class FakeYdl:
            def urlopen(self, req):
                calls.append(1)
                if len(calls) < 3:
                    raise RuntimeError("HTTP Error 403: Forbidden")
                return io.BytesIO(b"ok")

        result = downloader._fetch_chunk(FakeYdl(), "http://x", {}, 0, 99)
        assert result == b"ok"
        assert len(calls) == 3

    def test_gives_up_after_max_attempts(self, monkeypatch):
        monkeypatch.setattr(downloader, "CHUNK_RETRY_DELAY_SECONDS", 0)
        calls = []

        class FakeYdl:
            def urlopen(self, req):
                calls.append(1)
                raise RuntimeError("HTTP Error 403: Forbidden")

        with pytest.raises(RuntimeError, match="403"):
            downloader._fetch_chunk(FakeYdl(), "http://x", {}, 0, 99)
        assert len(calls) == downloader.CHUNK_RETRY_ATTEMPTS

    def test_does_not_retry_permanent_error(self, monkeypatch):
        monkeypatch.setattr(downloader, "CHUNK_RETRY_DELAY_SECONDS", 0)
        calls = []

        class FakeYdl:
            def urlopen(self, req):
                calls.append(1)
                raise RuntimeError("Video unavailable")

        with pytest.raises(RuntimeError, match="Video unavailable"):
            downloader._fetch_chunk(FakeYdl(), "http://x", {}, 0, 99)
        assert len(calls) == 1, "doimiy xatoda ham qayta urinildi (trafik isrofi)"


class TestSanitizeFilename:
    @pytest.mark.parametrize("raw,forbidden", [
        ('a/b\\c', "/\\"),
        ('what: is <this>?', ':<>?'),
        ('pipe|and*star', '|*'),
        ('quote"here', '"'),
    ])
    def test_strips_invalid_windows_chars(self, raw, forbidden):
        result = downloader._sanitize_filename(raw)
        for ch in forbidden:
            assert ch not in result

    def test_prevents_path_traversal(self):
        # Video sarlavhasi foydalanuvchi/YouTube nazoratidagi matn — u
        # DOWNLOADS_DIR'dan tashqariga chiqib keta olmasligi kerak.
        result = downloader._sanitize_filename("../../../../windows/system32/evil")
        assert "/" not in result and "\\" not in result
        joined = os.path.join(downloader.DOWNLOADS_DIR, result + ".mp4")
        assert os.path.realpath(joined).startswith(os.path.realpath(downloader.DOWNLOADS_DIR))

    def test_falls_back_when_everything_stripped(self):
        assert downloader._sanitize_filename("///") == "video"
        assert downloader._sanitize_filename("") == "video"
        assert downloader._sanitize_filename("...") == "video"

    def test_truncates_long_names(self):
        assert len(downloader._sanitize_filename("x" * 500)) <= 150

    def test_keeps_unicode_titles(self):
        # Uzbek/kirill/emoji sarlavhalar buzilmasligi kerak.
        assert downloader._sanitize_filename("Salom dunyo — ЖЖ 🎬") == "Salom dunyo — ЖЖ 🎬"


class TestUniquePath:
    def test_appends_counter_when_name_taken(self, tmp_path):
        base = "collide"
        first = downloader._unique_path(str(tmp_path), base, ".mp4")
        open(first, "wb").close()
        second = downloader._unique_path(str(tmp_path), base, ".mp4")

        assert first != second
        assert os.path.basename(first) == "collide.mp4"
        assert os.path.basename(second) == "collide (2).mp4"


class TestSelectFormat:
    def test_finds_requested_format(self):
        info = {"formats": [{"format_id": "137"}, {"format_id": "140"}]}
        assert downloader._select_format(info, "140")["format_id"] == "140"

    def test_raises_for_missing_format(self):
        with pytest.raises(RuntimeError, match="Format topilmadi"):
            downloader._select_format({"formats": [{"format_id": "137"}]}, "999")


class TestParseSidx:
    def test_rejects_truncated_content(self):
        assert downloader._parse_sidx(b"\x00" * 4) is None

    def test_rejects_nested_sidx_reference(self):
        # reference_type=1 (eng yuqori bit) = ichma-ich sidx — qo'llab-
        # quvvatlanmaydi, xavfsizlik uchun None qaytarishi kerak (aks holda
        # noto'g'ri bayt oralig'i hisoblanardi).
        content = bytearray()
        content += b"\x00\x00\x00\x00"              # version 0 + flags
        content += b"\x00\x00\x00\x01"              # reference_ID
        content += (1000).to_bytes(4, "big")        # timescale
        content += b"\x00" * 8                      # earliest_pt + first_offset (v0)
        content += b"\x00\x00"                      # reserved
        content += (1).to_bytes(2, "big")           # reference_count = 1
        content += (0x80000000 | 100).to_bytes(4, "big")  # reference_type=1
        content += (500).to_bytes(4, "big")         # subsegment_duration
        content += b"\x00" * 4                      # SAP
        assert downloader._parse_sidx(bytes(content)) is None

    def test_parses_valid_sidx(self):
        content = bytearray()
        content += b"\x00\x00\x00\x00"
        content += b"\x00\x00\x00\x01"
        content += (1000).to_bytes(4, "big")        # timescale
        content += b"\x00" * 8
        content += b"\x00\x00"
        content += (2).to_bytes(2, "big")           # 2 ta segment
        for size, dur in ((100, 500), (200, 700)):
            content += size.to_bytes(4, "big")      # reference_type=0 + size
            content += dur.to_bytes(4, "big")
            content += b"\x00" * 4

        parsed = downloader._parse_sidx(bytes(content))
        assert parsed is not None
        timescale, segments = parsed
        assert timescale == 1000
        assert segments == [(500, 100), (700, 200)]


class TestIterTopBoxes:
    def test_parses_simple_boxes(self):
        # Ikkita oddiy box: "ftyp" (16 bayt) va "moov" (16 bayt).
        data = (16).to_bytes(4, "big") + b"ftyp" + b"\x00" * 8
        data += (16).to_bytes(4, "big") + b"moov" + b"\x00" * 8
        boxes = [b[0] for b in downloader._iter_top_boxes(data)]
        assert boxes == [b"ftyp", b"moov"]

    def test_stops_on_impossible_size(self):
        # E'lon qilingan hajm mavjud ma'lumotdan katta — cheksiz tsikl yoki
        # noto'g'ri o'qish o'rniga to'xtashi kerak.
        data = (999999).to_bytes(4, "big") + b"moov" + b"\x00" * 8
        assert list(downloader._iter_top_boxes(data)) == []


class TestPlayerClientOrder:
    """`ydl_opts_ctx` beradigan mijozlar ro'yxati. TARTIB shu yerda
    tekshiriladi, chunki u tasodifiy emas: bir xil format_id bir nechta
    mijozdan kelganda yt-dlp ro'yxatdagi BIRINCHI mijozning URL'ini oladi,
    va faqat "tv_simply" URL'lari ~10 MB'dan keyin 403 bermaydi
    (downloader.py'dagi izohga qarang)."""

    def test_tv_simply_is_first(self):
        with downloader.ydl_opts_ctx({}) as opts:
            clients = opts["extractor_args"]["youtube"]["player_client"]
        assert clients[0] == "tv_simply"

    def test_cookie_capable_clients_remain_as_fallback(self):
        # "tv_simply" cookie yubormaydi (yt-dlp'da SUPPORTS_COOKIES=False),
        # shuning uchun yosh cheklovli / yopiq videolar uchun cookie
        # qo'llaydigan mijozlar ro'yxatda qolishi shart.
        with downloader.ydl_opts_ctx({}) as opts:
            clients = opts["extractor_args"]["youtube"]["player_client"]
        assert "web_embedded" in clients
        assert "mweb" in clients
