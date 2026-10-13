"""bot.py'dagi himoya qatlamlari: URL domen tekshiruvi (SSRF), ruxsat
ro'yxati va bir vaqtdagi job chegarasi."""
import asyncio
import importlib

import pytest

import bot


class TestIsSupportedUrl:
    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=abc",
        "https://m.youtube.com/watch?v=abc",
        "https://music.youtube.com/watch?v=abc",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/live/vf_EczgiP1s?si=ZWIdICGy6TUOayTT",
        "HTTPS://WWW.YOUTUBE.COM/watch?v=abc",  # bosh harflar
        "https://www.tiktok.com/@user/video/1234567890",
        "https://tiktok.com/@user/video/1234567890",
        "https://m.tiktok.com/v/1234567890.html",
        "https://vm.tiktok.com/ZSqWujsCY/",
        "https://vt.tiktok.com/ZSqWujsCY/",
        "HTTPS://WWW.TIKTOK.COM/@user/video/1234567890",  # bosh harflar
    ])
    def test_accepts_supported(self, url):
        assert bot._is_supported_url(url) is True

    @pytest.mark.parametrize("url", [
        # Domen "youtube.com"/"tiktok.com" bilan BOSHLANADI, lekin boshqa
        # saytga tegishli.
        "https://youtube.com.evil.example/watch?v=abc",
        "https://www.youtube.com.attacker.net/",
        "https://tiktok.com.evil.example/@user/video/123",
        # Yo'lida "youtube.com" bor, lekin host boshqa.
        "https://evil.example/youtube.com",
        # SSRF uchun klassik nishonlar.
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8000/api/download",
        "http://localhost/admin",
        "file:///etc/passwd",
        # Umuman URL emas (lekin "http" so'zi bor — bot filtri shunga tushadi).
        "salom http dunyo",
        "",
    ])
    def test_rejects_unsupported(self, url):
        assert bot._is_supported_url(url) is False

    def test_rejects_malformed_url_without_raising(self):
        # urlparse ba'zi noto'g'ri IPv6 qavslarida ValueError ko'taradi —
        # bu handler ichida ushlanishi kerak, aks holda bot qulaydi.
        assert bot._is_supported_url("http://[::1") is False


class TestIsAllowed:
    def test_open_by_default(self):
        # Standart holat: ro'yxat berilmagan — hamma uchun ochiq.
        assert bot.ALLOWED_USER_IDS is None
        assert bot._is_allowed(12345) is True
        assert bot._is_allowed(None) is True

    def test_allowlist_enforced(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "111,222, 333")
        reloaded = importlib.reload(bot)
        try:
            assert reloaded.ALLOWED_USER_IDS == {111, 222, 333}
            assert reloaded._is_allowed(111) is True
            assert reloaded._is_allowed(333) is True
            assert reloaded._is_allowed(999) is False
            # from_user bo'lmagan update ham rad etilishi kerak.
            assert reloaded._is_allowed(None) is False
        finally:
            monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
            importlib.reload(bot)


class TestJobSlots:
    def test_cap_enforced_and_released(self, monkeypatch):
        monkeypatch.setenv("MAX_CONCURRENT_JOBS", "2")
        reloaded = importlib.reload(bot)
        try:
            async def scenario():
                assert reloaded.MAX_CONCURRENT_JOBS == 2
                assert await reloaded._try_acquire_job_slot() is True
                assert await reloaded._try_acquire_job_slot() is True
                # Chegara to'ldi — uchinchisi NAVBATGA TURMASDAN rad etilishi
                # kerak (asyncio.Semaphore bo'lganda bu yerda muzlab qolardi).
                assert await reloaded._try_acquire_job_slot() is False
                await reloaded._release_job_slot()
                assert await reloaded._try_acquire_job_slot() is True

            asyncio.run(asyncio.wait_for(scenario(), timeout=5))
        finally:
            monkeypatch.delenv("MAX_CONCURRENT_JOBS", raising=False)
            importlib.reload(bot)

    def test_release_never_goes_negative(self):
        async def scenario():
            before = bot._active_jobs
            await bot._release_job_slot()
            await bot._release_job_slot()
            assert bot._active_jobs >= 0
            return before

        asyncio.run(scenario())
