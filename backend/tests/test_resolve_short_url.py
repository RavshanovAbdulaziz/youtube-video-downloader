"""downloader._resolve_short_url() — TikTok'ning vm./vt.tiktok.com kabi
ulashish havolalarini haqiqiy (brauzer taqlidi) so'rov bilan to'liq havolaga
aylantiradi. Bunga to'g'ridan-to'g'ri qaram bo'lish sabablari uchun
downloader.py'dagi izohga qarang: TikTok oddiy so'rovlarni ConnectionReset
bilan rad etishi mumkin, curl_cffi esa buni chetlab o'tadi."""
import pytest

import downloader


class _FakeResponse:
    def __init__(self, url):
        self.url = url


class _FakeCurlRequests:
    def __init__(self, resolved_url=None, exc=None):
        self._resolved_url = resolved_url
        self._exc = exc
        self.calls = []

    def head(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._exc:
            raise self._exc
        return _FakeResponse(self._resolved_url)


@pytest.fixture
def fake_curl(monkeypatch):
    def _install(resolved_url=None, exc=None):
        fake = _FakeCurlRequests(resolved_url, exc)
        monkeypatch.setattr(downloader, "_curl_requests", fake)
        return fake
    return _install


class TestResolveShortUrl:
    @pytest.mark.parametrize("url", [
        "https://vm.tiktok.com/ZTR45GpSF/",
        "https://vt.tiktok.com/ZSqWujsCY/",
        "https://www.tiktok.com/t/ZTRC5xgJp/",
        "https://tiktok.com/t/ZTRC5xgJp/",
    ])
    def test_resolves_tiktok_short_links(self, fake_curl, url):
        fake = fake_curl(resolved_url="https://www.tiktok.com/@user/video/1234567890")
        result = downloader._resolve_short_url(url)
        assert result == "https://www.tiktok.com/@user/video/1234567890"
        assert fake.calls[0][0] == url
        assert fake.calls[0][1]["impersonate"] == "safari"

    def test_leaves_non_short_urls_untouched(self, fake_curl):
        fake = fake_curl(resolved_url="https://should-not-be-used.example/")
        url = "https://www.youtube.com/watch?v=abc"
        assert downloader._resolve_short_url(url) == url
        assert fake.calls == []

    def test_leaves_full_tiktok_url_untouched(self, fake_curl):
        fake = fake_curl(resolved_url="https://should-not-be-used.example/")
        url = "https://www.tiktok.com/@user/video/1234567890"
        assert downloader._resolve_short_url(url) == url
        assert fake.calls == []

    def test_falls_back_to_original_on_request_failure(self, fake_curl):
        fake_curl(exc=RuntimeError("boom"))
        url = "https://vm.tiktok.com/ZTR45GpSF/"
        assert downloader._resolve_short_url(url) == url

    def test_falls_back_when_curl_cffi_unavailable(self, monkeypatch):
        monkeypatch.setattr(downloader, "_curl_requests", None)
        url = "https://vm.tiktok.com/ZTR45GpSF/"
        assert downloader._resolve_short_url(url) == url

    def test_rejects_malformed_url_without_raising(self, fake_curl):
        fake_curl(resolved_url="https://should-not-be-used.example/")
        assert downloader._resolve_short_url("http://[::1") == "http://[::1"


class TestDeprioritizeBlockedCurlCffiDefault:
    """TikTok'ning WAF'i curl_cffi'ning standart (wildcard `impersonate=True`
    so'ralganda tanlanadigan) "eng yangi Chrome" profilini bloklaydi —
    downloader.py'dagi _deprioritize_blocked_curl_cffi_default() izohiga
    qarang. Bu safari'ni ro'yxat boshiga chiqaradi, shu bilan yt-dlp'ning
    TikTok ekstraktori ishlatadigan wildcard so'rovlar endi bloklanmagan
    profilga tushadi."""

    def test_safari_sorted_first(self):
        from yt_dlp.networking._curlcffi import CurlCFFIRH

        targets = list(CurlCFFIRH._SUPPORTED_IMPERSONATE_TARGET_MAP)
        assert targets, "curl_cffi impersonate nishonlari ro'yxati bo'sh bo'lmasligi kerak"
        assert targets[0].client == "safari"

    def test_noop_when_curl_cffi_missing(self, monkeypatch):
        called = {}

        def fake_import(name, *args, **kwargs):
            if name == "yt_dlp.networking._curlcffi":
                raise ImportError("boom")
            called["other"] = True
            return real_import(name, *args, **kwargs)

        import builtins
        real_import = builtins.__import__
        monkeypatch.setattr(builtins, "__import__", fake_import)
        # Xatosiz qaytishi kerak — funksiya import xatosini jim ravishda tutadi.
        downloader._deprioritize_blocked_curl_cffi_default()
