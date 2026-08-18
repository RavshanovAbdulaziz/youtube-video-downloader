"""FastAPI qatlamining validatsiyasi va xato holatlari — yt-dlp'ga
chiqmasdan (downloader funksiyalari monkeypatch qilinadi)."""
import time

import pytest
from fastapi.testclient import TestClient

import downloader
import main


@pytest.fixture
def client():
    return TestClient(main.app)


class TestHealth:
    def test_health_ok(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


class TestClipRangeValidation:
    """`_validate_clip_range` — noto'g'ri oraliq yt-dlp'ga umuman
    yetib bormasligi kerak."""

    def _post(self, client, **overrides):
        body = {
            "url": "https://www.youtube.com/watch?v=abc",
            "video_format_id": "137",
            "audio_format_id": "140",
            "audio_only": False,
        }
        body.update(overrides)
        return client.post("/api/download", json=body)

    def test_rejects_negative_start(self, client):
        res = self._post(client, start_time=-5, end_time=10)
        assert res.status_code == 400
        assert "manfiy" in res.json()["detail"]

    def test_rejects_negative_end(self, client):
        res = self._post(client, start_time=0, end_time=-1)
        assert res.status_code == 400

    def test_rejects_end_before_start(self, client):
        res = self._post(client, start_time=30, end_time=10)
        assert res.status_code == 400

    def test_rejects_end_equal_to_start(self, client):
        # Nol uzunlikdagi klip — ffmpeg bo'sh fayl chiqarardi.
        res = self._post(client, start_time=30, end_time=30)
        assert res.status_code == 400

    def test_accepts_valid_range(self, client, monkeypatch):
        monkeypatch.setattr(downloader, "start_download", lambda *a, **k: "fakejob123")
        res = self._post(client, start_time=10, end_time=20)
        assert res.status_code == 200
        assert res.json() == {"job_id": "fakejob123"}

    def test_requires_video_format_when_not_audio_only(self, client):
        res = client.post("/api/download", json={
            "url": "https://www.youtube.com/watch?v=abc",
            "video_format_id": None,
            "audio_only": False,
        })
        assert res.status_code == 400
        assert "video_format_id" in res.json()["detail"]


class TestProgressAndFile:
    def test_progress_404_for_unknown_job(self, client):
        res = client.get("/api/progress/nosuchjob00000000000000000000")
        assert res.status_code == 404

    def test_file_400_when_job_unfinished(self, client):
        job_id = "unfinishedjob000000000000000000"
        with downloader.jobs_lock:
            downloader.jobs[job_id] = {"status": "downloading", "percent": 50, "created_at": time.time()}
        try:
            res = client.get(f"/api/file/{job_id}")
            assert res.status_code == 400
        finally:
            with downloader.jobs_lock:
                downloader.jobs.pop(job_id, None)

    def test_file_400_for_errored_job(self, client):
        job_id = "erroredjob000000000000000000000"
        with downloader.jobs_lock:
            downloader.jobs[job_id] = {
                "status": "error", "error": "HTTP Error 403: Forbidden", "created_at": time.time(),
            }
        try:
            res = client.get(f"/api/file/{job_id}")
            assert res.status_code == 400
        finally:
            with downloader.jobs_lock:
                downloader.jobs.pop(job_id, None)

    def test_progress_reports_error_status(self, client):
        job_id = "progresserror00000000000000000a"
        with downloader.jobs_lock:
            downloader.jobs[job_id] = {
                "status": "error", "percent": 0,
                "error": "HTTP Error 403: Forbidden", "created_at": time.time(),
            }
        try:
            res = client.get(f"/api/progress/{job_id}")
            assert res.status_code == 200
            assert res.json()["status"] == "error"
            assert "403" in res.json()["error"]
        finally:
            with downloader.jobs_lock:
                downloader.jobs.pop(job_id, None)


class TestSeparateEndpoint:
    def test_rejects_unknown_engine(self, client):
        res = client.post("/api/separate", json={
            "url": "https://www.youtube.com/watch?v=abc",
            "audio_format_id": "140",
            "engine": "not_a_real_engine",
        })
        assert res.status_code == 400
        assert "dvigatel" in res.json()["detail"].lower()

    def test_rejects_bad_clip_range(self, client):
        res = client.post("/api/separate", json={
            "url": "https://www.youtube.com/watch?v=abc",
            "audio_format_id": "140",
            "engine": "demucs",
            "start_time": 50,
            "end_time": 20,
        })
        assert res.status_code == 400

    def test_separate_file_rejects_bad_which(self, client):
        res = client.get("/api/separate/file/somejob/../../etc/passwd")
        # Yo'l bo'ylab chiqib ketishga urinish marshrutga umuman tushmaydi
        # yoki "which" validatsiyasida rad etiladi — hech qachon 200 emas.
        assert res.status_code != 200

    def test_separate_file_rejects_unknown_which(self, client):
        res = client.get("/api/separate/file/somejob/vocals")
        assert res.status_code == 400


class TestInfoErrorHandling:
    def test_info_returns_400_on_extractor_failure(self, client, monkeypatch):
        def boom(url):
            raise RuntimeError("Video unavailable")

        monkeypatch.setattr(downloader, "get_info", boom)
        res = client.post("/api/info", json={"url": "https://www.youtube.com/watch?v=abc"})
        assert res.status_code == 400
        assert "Video unavailable" in res.json()["detail"]
