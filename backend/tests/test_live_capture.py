"""Jonli efirni yozib olish (`start_live_capture`/`stop_live_capture`) —
tarmoqqa yoki haqiqiy ffmpeg'ga chiqmasdan: `yt_dlp.YoutubeDL` va
`subprocess.Popen` soxtalashtiriladi. Asosiy tekshiruv — ffmpeg buyrug'i
to'g'ri qurilishi (video/audio inputlar, -map, chiqish konteyneri) va
job holati (queued -> downloading -> finished/error/stopping) to'g'ri
o'tishi."""
import os
import shutil
import time

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


class _FakeProc:
    """`subprocess.Popen`ning testlar uchun yengil o'rnini bosuvchisi.
    `wait()` chaqirilganda (yoki `block_until_terminate=True` bo'lsa —
    faqat `terminate()`dan keyin) `out_path`ga soxta fayl yozadi, xuddi
    ffmpeg chiqish faylini yozgani kabi."""

    def __init__(self, out_path, stdout_lines=(), returncode=0, block_until_terminate=False):
        self.stdout = iter(stdout_lines)
        self.stderr = iter(())
        self._out_path = out_path
        self._returncode = returncode
        self._block = block_until_terminate
        self._terminated = False
        self._poll_result = None

    def wait(self):
        if self._block:
            for _ in range(200):
                if self._terminated:
                    break
                time.sleep(0.01)
        with open(self._out_path, "wb") as f:
            f.write(b"fake media bytes")
        self._poll_result = self._returncode
        return self._returncode

    def poll(self):
        return self._poll_result

    def terminate(self):
        self._terminated = True


def _live_info(is_live=True):
    return {
        "is_live": is_live,
        "formats": [
            {"format_id": "137", "url": "https://example.com/video.m3u8",
             "http_headers": {"User-Agent": "UA-test"}},
            {"format_id": "140", "url": "https://example.com/audio.m3u8", "http_headers": {}},
        ],
    }


@pytest.fixture
def fake_live(monkeypatch):
    """`info` (extract_info natijasi) va Popen chaqiruvi qanday `proc`
    qaytarishini o'rnatadi; qaytgan dict orqali qurilgan ffmpeg
    argumentlariga (`["args"]`) va soxta jarayonga (`["proc"]`) kirish
    mumkin."""
    calls = {}

    def install(info, proc_factory=None):
        monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", lambda opts: _FakeYdl(info))
        # Ba'zi dev mashinalarida `~/bgutil-ytdlp-pot-provider/server` haqiqatan
        # ham mavjud bo'lishi mumkin — shunda `ydl_opts_ctx` haqiqiy (sekin,
        # ~4s) jarayon ishga tushirishga urinardi. Bu yerda unga umuman
        # ehtiyoj yo'q (extract_info soxtalashtirilgan).
        monkeypatch.setattr(downloader.pot_server, "ensure_running", lambda: None)
        # Yozib olish tugagach ishga tushadigan yakuniy remux — bu ham
        # haqiqiy ffmpeg'ga chiqadi; testlarda shunchaki manba faylni
        # nusxalash bilan simulyatsiya qilinadi (haqiqiy `_run_ffmpeg`
        # `-i <src> ... -y <dst>` ko'rinishida chaqiriladi).
        def fake_run_ffmpeg(args):
            shutil.copyfile(args[1], args[-1])

        monkeypatch.setattr(downloader, "_run_ffmpeg", fake_run_ffmpeg)

        def fake_spawn(args):
            calls["args"] = args
            out_path = args[-1]
            proc = (proc_factory or _FakeProc)(out_path)
            calls["proc"] = proc
            return proc

        monkeypatch.setattr(downloader, "_spawn_ffmpeg", fake_spawn)
        return calls

    return install


def _wait_until(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestCommandBuilding:
    def test_combined_video_audio_uses_mkv_and_maps_both_streams(self, fake_live):
        calls = fake_live(_live_info())
        job_id = downloader.start_live_capture(
            "https://www.youtube.com/watch?v=abc", "137", "140", False,
        )
        assert _wait_until(lambda: "args" in calls)
        args = calls["args"]

        # Yozib olish paytida (foydalanuvchi istalgan payt to'xtatishi mumkin
        # bo'lgani uchun) TO'G'RIDAN-TO'G'RI MKV'ga emas, MPEG-TS'ga
        # yoziladi — yakuniy MKV'ga o'tkazish `run()` ichida keyinroq (yozib
        # olish tugagach) alohida remux orqali bajariladi.
        assert args[-1] == os.path.join(downloader.DOWNLOADS_DIR, f"{job_id}.ts")
        assert args.count("-i") == 2
        video_pos = args.index("https://example.com/video.m3u8")
        audio_pos = args.index("https://example.com/audio.m3u8")
        assert video_pos < audio_pos, "video input audio'dan oldin bo'lishi kerak (index 0:v)"
        assert "0:v:0" in args
        assert "1:a:0" in args
        assert "-c" in args and "copy" in args
        assert "-f" in args and "mpegts" in args
        # video format uchun http_headers -headers orqali uzatilishi kerak.
        headers_idx = args.index("-headers")
        assert "User-Agent: UA-test" in args[headers_idx + 1]

        assert _wait_until(lambda: downloader.get_progress(job_id)["status"] == "finished")
        downloader.cleanup_job(job_id)

    def test_single_video_input_uses_no_map_restriction(self, fake_live):
        # Jonli efirlarda ko'pincha alohida audio-only format umuman
        # bo'lmaydi — tanlangan video format o'zi ichida audio bilan birga
        # keladi ("progressive"). Bunday holda `-map {idx}:v:0` qo'yish
        # ichidagi audioni chiqarib tashlab, OVOZSIZ fayl berardi (haqiqiy
        # xato — shu testda tuzatilgan). To'g'ri xatti-harakat: `-map`ni
        # umuman qo'llamaslik, shunda yagona kirishning BARCHA oqimlari
        # (video + bor bo'lsa audio) o'zi chiqishga tushadi.
        calls = fake_live(_live_info())
        job_id = downloader.start_live_capture(
            "https://www.youtube.com/watch?v=abc", "137", None, False,
        )
        assert _wait_until(lambda: "args" in calls)
        args = calls["args"]
        assert args.count("-i") == 1
        assert "-map" not in args
        _wait_until(lambda: downloader.get_progress(job_id)["status"] == "finished")
        downloader.cleanup_job(job_id)

    def test_audio_only_transcodes_to_mp3(self, fake_live):
        calls = fake_live(_live_info())
        job_id = downloader.start_live_capture(
            "https://www.youtube.com/watch?v=abc", None, "140", True,
        )
        assert _wait_until(lambda: "args" in calls)
        args = calls["args"]
        assert args[-1] == os.path.join(downloader.DOWNLOADS_DIR, f"{job_id}.mp3")
        assert "libmp3lame" in args
        assert "-f" in args and "mp3" in args
        assert "-vn" in args
        _wait_until(lambda: downloader.get_progress(job_id)["status"] == "finished")
        downloader.cleanup_job(job_id)

    def test_audio_only_falls_back_to_video_format_when_no_separate_audio_track(self, fake_live):
        # Ko'pchilik jonli efirlarda alohida audio-only trek umuman yo'q —
        # audio_format_id berilmasa ham, tanlangan video (odatda audio o'z
        # ichiga qo'shilgan) format manba sifatida ishlatilishi kerak.
        calls = fake_live(_live_info())
        job_id = downloader.start_live_capture(
            "https://www.youtube.com/watch?v=abc", "137", None, True,
        )
        assert _wait_until(lambda: "args" in calls)
        args = calls["args"]
        assert args.count("-i") == 1
        assert "https://example.com/video.m3u8" in args
        assert args[-1] == os.path.join(downloader.DOWNLOADS_DIR, f"{job_id}.mp3")
        assert "-vn" in args
        assert "libmp3lame" in args
        assert _wait_until(lambda: downloader.get_progress(job_id)["status"] == "finished")
        downloader.cleanup_job(job_id)


class TestLiveCaptureLifecycle:
    def test_rejects_when_not_actually_live(self, fake_live):
        fake_live(_live_info(is_live=False))
        job_id = downloader.start_live_capture(
            "https://www.youtube.com/watch?v=abc", "137", "140", False,
        )
        assert _wait_until(lambda: downloader.get_progress(job_id)["status"] == "error")
        assert "jonli efirda emas" in downloader.get_progress(job_id)["error"]

    def test_reports_progress_from_ffmpeg_out_time(self, fake_live):
        stdout_lines = [
            "frame=10\n", "out_time=00:00:05.250000\n", "progress=continue\n",
            "frame=20\n", "out_time=00:01:07.000000\n", "progress=continue\n",
        ]
        calls = fake_live(_live_info(), lambda out_path: _FakeProc(out_path, stdout_lines=stdout_lines))
        job_id = downloader.start_live_capture(
            "https://www.youtube.com/watch?v=abc", "137", "140", False,
        )
        assert _wait_until(lambda: downloader.get_progress(job_id).get("elapsed", 0) >= 67)
        progress = downloader.get_progress(job_id)
        assert progress["elapsed"] == 67.0
        _wait_until(lambda: downloader.get_progress(job_id)["status"] == "finished")
        downloader.cleanup_job(job_id)

    def test_finished_job_exposes_downloadable_file(self, fake_live):
        fake_live(_live_info())
        job_id = downloader.start_live_capture(
            "https://www.youtube.com/watch?v=abc", "137", "140", False, title="Mening efirim",
        )
        assert _wait_until(lambda: downloader.get_progress(job_id)["status"] == "finished")
        progress = downloader.get_progress(job_id)
        assert os.path.exists(progress["file"])
        assert os.path.basename(progress["file"]).startswith("Mening efirim")
        # Yozib olish .ts'da bo'lsa ham, yakuniy remux'dan keyingi fayl
        # foydalanuvchiga .mkv sifatida taqdim etilishi kerak.
        assert progress["file"].endswith(".mkv")
        downloader.cleanup_job(job_id)

    def test_missing_format_id_surfaces_as_job_error(self, fake_live):
        fake_live(_live_info())
        job_id = downloader.start_live_capture(
            "https://www.youtube.com/watch?v=abc", "999-does-not-exist", "140", False,
        )
        assert _wait_until(lambda: downloader.get_progress(job_id)["status"] == "error")
        assert "Format topilmadi" in downloader.get_progress(job_id)["error"]


class TestStopLiveCapture:
    def test_returns_false_for_unknown_job(self):
        assert downloader.stop_live_capture("nosuchjob0000000000000000000000") is False

    def test_stop_terminates_process_and_marks_stopping_then_finished(self, fake_live):
        calls = fake_live(
            _live_info(),
            lambda out_path: _FakeProc(out_path, block_until_terminate=True),
        )
        job_id = downloader.start_live_capture(
            "https://www.youtube.com/watch?v=abc", "137", "140", False,
        )
        assert _wait_until(lambda: downloader.get_progress(job_id)["status"] == "downloading")

        assert downloader.stop_live_capture(job_id) is True
        # `stop_live_capture` job holatini sinxron ravishda o'zi o'zgartiradi
        # (fon thread'ni kutmasdan) — darhol tekshirish mumkin.
        assert downloader.get_progress(job_id)["status"] == "stopping"
        assert calls["proc"]._terminated is True

        # Fon thread `terminate()`dan keyin `wait()`dan chiqib, xuddi efir
        # tabiiy tugagandagidek `finished`ga o'tishi kerak.
        assert _wait_until(lambda: downloader.get_progress(job_id)["status"] == "finished")
        downloader.cleanup_job(job_id)

    def test_stop_returns_false_once_job_already_finished(self, fake_live):
        fake_live(_live_info())
        job_id = downloader.start_live_capture(
            "https://www.youtube.com/watch?v=abc", "137", "140", False,
        )
        assert _wait_until(lambda: downloader.get_progress(job_id)["status"] == "finished")
        assert downloader.stop_live_capture(job_id) is False
        downloader.cleanup_job(job_id)
