"""Lokal "bgutil" PO (Proof-of-Origin) token HTTP serverini avtomatik
boshqaradi — https://github.com/Brainicism/bgutil-ytdlp-pot-provider

YouTube tobora ko'proq holatlarda (hatto rezidensial IP'larda ham) so'rovlar
bilan birga haqiqiy PO token talab qiladi, aks holda "Sign in to confirm
you're not a bot" xatosi beradi. Cookie bilan ham chetlab o'tish mumkin
(downloader.py'dagi COOKIES_FILE), lekin PO token cookie'ga bog'liq
bo'lmagan, barqarorroq muqobil/qo'shimcha.

Docker orqali serverga joylashtirilganda (Dockerfile/docker-compose.yml)
bu server alohida konteyner sifatida ishlaydi va YTDLP_POT_BASE_URL orqali
ko'rsatiladi — bu modul faqat o'sha env var berilmagan holatda (lokal
Windows ishga tushirish) ishga tushadi.
"""
import atexit
import os
import subprocess
import threading
import time
import urllib.request

import paths

PORT = 4416
BASE_URL = f"http://127.0.0.1:{PORT}"

_lock = threading.Lock()
_process: subprocess.Popen | None = None


def _is_up() -> bool:
    try:
        urllib.request.urlopen(f"{BASE_URL}/ping", timeout=0.5)
        return True
    except Exception:
        return False


def _stop() -> None:
    global _process
    if _process is not None and _process.poll() is None:
        _process.terminate()
    _process = None


def ensure_running() -> str | None:
    """Lokal bgutil serveri topilsa (paths.bundled_bgutil_server_dir()),
    uni bir martalik fon jarayoni sifatida ishga tushiradi (allaqachon
    ishlab turgan bo'lsa — qayta ishga tushirmaydi) va bazaviy URL'ni
    qaytaradi. Server topilmasa yoki ishga tushmasa, None qaytaradi — bunda
    chaqiruvchi (downloader.py) PO token'siz, faqat cookie/JS runtime bilan
    davom etadi."""
    if _is_up():
        return BASE_URL

    server_dir = paths.bundled_bgutil_server_dir()
    if not server_dir:
        return None
    main_js = os.path.join(server_dir, "build", "main.js")
    if not os.path.isfile(main_js):
        return None

    with _lock:
        global _process
        if _process is None or _process.poll() is not None:
            if _is_up():  # boshqa thread/jarayon shu orada ishga tushirgan bo'lishi mumkin
                return BASE_URL
            node_exe = paths.bundled_node_exe() or "node"
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                _process = subprocess.Popen(
                    [node_exe, main_js, "--port", str(PORT)],
                    cwd=server_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
            except OSError:
                # node_exe topilmadi (masalan, paketlangan qurilmada Node
                # bundle qilinmagan, tizimda ham o'rnatilmagan) — PO token
                # ixtiyoriy, shuning uchun shu yerda yutib, None qaytaramiz.
                return None
            atexit.register(_stop)

    for _ in range(40):  # ~4s gacha startup kutamiz
        if _is_up():
            return BASE_URL
        time.sleep(0.1)
    return BASE_URL if _is_up() else None
