"""separator.py: yuklab olish oqimidagi xato holatlari va qayta urinish —
haqiqiy yt-dlp/AI chaqirilmaydi, hammasi monkeypatch qilinadi."""
import os
import time

import pytest

import ai_setup
import separator


def _wait_for_status(job_id, statuses, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        progress = separator.get_progress(job_id)
        if progress and progress.get("status") in statuses:
            return progress
        time.sleep(0.05)
    return separator.get_progress(job_id)


@pytest.fixture(autouse=True)
def _skip_ai_install(monkeypatch):
    # AI allaqachon o'rnatilgan deb hisoblaymiz — testlar 2-3 GB yuklamasin.
    monkeypatch.setattr(ai_setup, "is_ai_installed", lambda: True)


class TestMissingSourceFile:
    def test_reports_clear_error_when_download_produced_nothing(self, monkeypatch):
        """Yuklash "muvaffaqiyatli" tugab, lekin fayl yaratilmasa —
        foydalanuvchi TUSHUNARLI xato ko'rishi kerak.

        Avval bu yerda `next()` default'siz ishlatilar, natijada
        `StopIteration()` ko'tarilib, generic `except Exception` uni ushlab,
        foydalanuvchiga BO'SH xato matni (`error: ""`) qaytarardi.
        """
        monkeypatch.setattr(separator, "_download_source", lambda *a, **k: None)

        job_id = separator.start_separation("https://www.youtube.com/watch?v=abc", "140")
        progress = _wait_for_status(job_id, {"error", "finished"})

        assert progress["status"] == "error"
        assert progress.get("error"), "xato matni bo'sh — sabab tushunarsiz qoladi"
        assert "source" in progress["error"].lower() or "audio" in progress["error"].lower()

        separator.jobs.pop(job_id, None)


class TestDownloadRetry:
    def test_retries_transient_403(self, monkeypatch):
        monkeypatch.setattr(separator, "_RETRY_DELAY_SECONDS", 0)
        attempts = []

        class _FakeYdl:
            def __init__(self, opts):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def download(self, urls):
                attempts.append(1)
                if len(attempts) < 3:
                    raise RuntimeError("HTTP Error 403: Forbidden")

        monkeypatch.setattr(separator.yt_dlp, "YoutubeDL", _FakeYdl)

        job_id = "sepretry000000000000000000000aa"
        with separator.jobs_lock:
            separator.jobs[job_id] = {"status": "downloading", "percent": 0, "created_at": time.time()}
        work_dir = os.path.join(separator.SEPARATE_TMP_DIR, job_id)
        os.makedirs(work_dir, exist_ok=True)
        try:
            separator._download_source(job_id, "https://www.youtube.com/watch?v=abc", {}, work_dir)
            assert len(attempts) == 3, "403 xatosida qayta urinilmadi"
        finally:
            separator.jobs.pop(job_id, None)

    def test_does_not_retry_permanent_error(self, monkeypatch):
        monkeypatch.setattr(separator, "_RETRY_DELAY_SECONDS", 0)
        attempts = []

        class _FakeYdl:
            def __init__(self, opts):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def download(self, urls):
                attempts.append(1)
                raise RuntimeError("Video unavailable")

        monkeypatch.setattr(separator.yt_dlp, "YoutubeDL", _FakeYdl)

        job_id = "sepnoretry0000000000000000000aa"
        with separator.jobs_lock:
            separator.jobs[job_id] = {"status": "downloading", "percent": 0, "created_at": time.time()}
        work_dir = os.path.join(separator.SEPARATE_TMP_DIR, job_id)
        os.makedirs(work_dir, exist_ok=True)
        try:
            with pytest.raises(RuntimeError, match="Video unavailable"):
                separator._download_source(job_id, "https://www.youtube.com/watch?v=abc", {}, work_dir)
            assert len(attempts) == 1
        finally:
            separator.jobs.pop(job_id, None)

    def test_discards_partial_source_before_retry(self, tmp_path):
        # Qayta urinish oldidan yarim yuklangan fayl o'chirilishi kerak —
        # aks holda yt-dlp uni "davom ettirishga" urinib, xuddi shu 403'ni
        # qayta olardi.
        (tmp_path / "source.m4a").write_bytes(b"partial")
        (tmp_path / "keep_me.txt").write_bytes(b"unrelated")

        separator._discard_source_files(str(tmp_path))

        assert not (tmp_path / "source.m4a").exists()
        assert (tmp_path / "keep_me.txt").exists(), "aloqasiz fayl o'chirilmasligi kerak"


class TestEngineValidation:
    def test_rejects_unknown_engine_immediately(self):
        with pytest.raises(ValueError, match="dvigatel"):
            separator.start_separation("https://www.youtube.com/watch?v=abc", "140", engine="bogus")

    def test_known_engines_present(self):
        assert set(separator.ENGINES) == {"demucs", "uvr"}
