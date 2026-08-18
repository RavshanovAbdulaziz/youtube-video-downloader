"""Job holati, tozalash (cleanup) va eskirgan job'larni yig'ib olish (reaper)
— tarmoqqa chiqmaydi, faqat holat boshqaruvi tekshiriladi."""
import os
import time

import downloader
import separator


def _make_file(directory: str, name: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "wb") as f:
        f.write(b"test payload")
    return path


class TestDownloaderCleanup:
    def test_cleanup_removes_job_and_file(self):
        path = _make_file(downloader.DOWNLOADS_DIR, "cleanup_test.mp4")
        job_id = "cleanuptest0000000000000000000a"
        with downloader.jobs_lock:
            downloader.jobs[job_id] = {"status": "finished", "file": path, "created_at": time.time()}

        downloader.cleanup_job(job_id)

        assert job_id not in downloader.jobs
        assert not os.path.exists(path)

    def test_cleanup_is_idempotent(self):
        # Ikkinchi marta chaqirilganda (masalan foydalanuvchi ikki marta
        # bosganda) xato ko'tarmasligi kerak.
        downloader.cleanup_job("nonexistentjob00000000000000000")

    def test_cleanup_survives_missing_file(self):
        job_id = "cleanupmissing00000000000000000"
        with downloader.jobs_lock:
            downloader.jobs[job_id] = {
                "status": "finished",
                "file": os.path.join(downloader.DOWNLOADS_DIR, "nope_not_here.mp4"),
                "created_at": time.time(),
            }
        downloader.cleanup_job(job_id)
        assert job_id not in downloader.jobs

    def test_get_progress_returns_none_for_unknown(self):
        assert downloader.get_progress("definitelynotajobid000000000000") is None


class TestDownloaderReaper:
    def _reap_once(self):
        """`_reap_stale_jobs` ichidagi bir tsiklning aynan o'zi (u cheksiz
        `while True: sleep(600)` bo'lgani uchun to'g'ridan-to'g'ri chaqirib
        bo'lmaydi)."""
        now = time.time()
        with downloader.jobs_lock:
            stale = [
                jid for jid, job in downloader.jobs.items()
                if now - job.get("created_at", now) > downloader._JOB_TTL_SECONDS
            ]
        for jid in stale:
            downloader.cleanup_job(jid)

    def test_reaps_stale_job_and_its_file(self):
        path = _make_file(downloader.DOWNLOADS_DIR, "stale_test.mp4")
        job_id = "staletest000000000000000000000a"
        with downloader.jobs_lock:
            downloader.jobs[job_id] = {
                "status": "finished",
                "file": path,
                "created_at": time.time() - downloader._JOB_TTL_SECONDS - 60,
            }

        self._reap_once()

        assert job_id not in downloader.jobs, "eskirgan job tozalanmadi"
        assert not os.path.exists(path), "eskirgan job fayli o'chirilmadi"

    def test_keeps_fresh_job(self):
        path = _make_file(downloader.DOWNLOADS_DIR, "fresh_test.mp4")
        job_id = "freshtest000000000000000000000a"
        with downloader.jobs_lock:
            downloader.jobs[job_id] = {"status": "finished", "file": path, "created_at": time.time()}
        try:
            self._reap_once()
            assert job_id in downloader.jobs, "yangi job xato bilan tozalandi"
            assert os.path.exists(path)
        finally:
            downloader.cleanup_job(job_id)

    def test_reaps_errored_job_that_has_no_file(self):
        # Xato bilan tugagan job'da "file" kaliti umuman bo'lmaydi — reaper
        # shunda ham yiqilmasligi va yozuvni tozalashi kerak (aynan shu
        # holat avval xotirada abadiy qolib ketardi).
        job_id = "erroredstale0000000000000000000"
        with downloader.jobs_lock:
            downloader.jobs[job_id] = {
                "status": "error",
                "error": "HTTP Error 403: Forbidden",
                "created_at": time.time() - downloader._JOB_TTL_SECONDS - 60,
            }

        self._reap_once()

        assert job_id not in downloader.jobs


class TestSeparatorCleanup:
    def test_cleanup_file_removes_only_requested_side(self):
        speech = _make_file(separator.DOWNLOADS_DIR, "sep_speech.mp3")
        background = _make_file(separator.DOWNLOADS_DIR, "sep_background.mp3")
        job_id = "septest00000000000000000000000a"
        with separator.jobs_lock:
            separator.jobs[job_id] = {
                "status": "finished", "speech_file": speech,
                "background_file": background, "created_at": time.time(),
            }

        separator.cleanup_file(job_id, "speech")

        assert not os.path.exists(speech)
        assert os.path.exists(background), "faqat so'ralgan fayl o'chirilishi kerak edi"
        # Bitta fayl qolgani uchun job hali saqlanib turishi kerak.
        assert job_id in separator.jobs

        separator.cleanup_file(job_id, "background")
        assert not os.path.exists(background)
        # Ikkalasi ham olingach — job butunlay yo'q qilinadi.
        assert job_id not in separator.jobs

    def test_cleanup_file_unknown_job_is_noop(self):
        separator.cleanup_file("nosuchjob0000000000000000000000", "speech")


class TestSeparatorReaper:
    def _reap_once(self):
        now = time.time()
        with separator.jobs_lock:
            stale = [
                jid for jid, job in separator.jobs.items()
                if now - job.get("created_at", now) > separator._JOB_TTL_SECONDS
            ]
            stale_jobs = [(jid, separator.jobs.pop(jid)) for jid in stale]
        for _jid, job in stale_jobs:
            for key in ("speech_file", "background_file"):
                path = job.get(key)
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def test_reaps_abandoned_separation_files(self):
        # Mijoz faqat bitta faylni olib, ikkinchisini hech qachon so'ramasa —
        # avval o'sha mp3 diskda abadiy qolardi.
        speech = _make_file(separator.DOWNLOADS_DIR, "abandoned_speech.mp3")
        background = _make_file(separator.DOWNLOADS_DIR, "abandoned_background.mp3")
        job_id = "sepstale00000000000000000000000"
        with separator.jobs_lock:
            separator.jobs[job_id] = {
                "status": "finished", "speech_file": speech, "background_file": background,
                "created_at": time.time() - separator._JOB_TTL_SECONDS - 60,
            }

        self._reap_once()

        assert job_id not in separator.jobs
        assert not os.path.exists(speech)
        assert not os.path.exists(background)
