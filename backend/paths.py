"""Writable data-directory resolution and a small on-disk config store.

By default (source checkout, `.bat` scripts, Docker) everything below
resolves relative to this file's location, exactly as it did before this
module existed — nothing changes for those workflows.

A packaged desktop build sets two environment variables *before* importing
any other backend module:

- ``APP_DATA_DIR``    — writable per-user folder for downloads/config/cache
                         (e.g. ``%LocalAppData%\\YouTubeDownloader``), since
                         the install folder itself may not be writable.
- ``APP_RUNTIME_DIR``  — read-only folder holding bundled ffmpeg/Node/Python
                         binaries that ship inside the installer. Absent
                         when running from source, in which case callers
                         fall back to whatever's on the system PATH.
"""
import json
import os
import sys
import threading

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_config_lock = threading.Lock()


def _base_dir() -> str:
    return os.environ.get("APP_DATA_DIR") or _BACKEND_DIR


DOWNLOADS_DIR = os.path.join(_base_dir(), "downloads")
SEPARATE_TMP_DIR = os.path.join(DOWNLOADS_DIR, "_separate_tmp")
NUMBA_CACHE_DIR = os.path.join(_base_dir(), "_numba_cache")
LOGS_DIR = os.path.join(_base_dir(), "logs")
CONFIG_FILE = os.path.join(_base_dir(), "config.json")
TRANSCRIPT_DB_FILE = os.path.join(_base_dir(), "transcript_search.db")

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(SEPARATE_TMP_DIR, exist_ok=True)
os.makedirs(NUMBA_CACHE_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

_DEFAULT_CONFIG = {
    "bot_token": None,
    "gpu": None,  # None = not probed yet, True/False = cached nvidia-smi result
    "ai_installed": False,
    "first_run_done": False,
    # Cookie'larni fayl o'rniga to'g'ridan-to'g'ri brauzerdan olish, masalan
    # "firefox" yoki "chrome:Profile 1". None bo'lsa — cookie fayli ishlatiladi.
    # Batafsil: downloader.COOKIES_FROM_BROWSER izohiga qarang.
    "cookies_from_browser": None,
}


def read_config() -> dict:
    if not os.path.isfile(CONFIG_FILE):
        return dict(_DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT_CONFIG)
    return {**_DEFAULT_CONFIG, **data}


def write_config(**updates) -> dict:
    """Merge ``updates`` into the stored config and persist it (atomic write).

    Locked around the whole read-modify-write: without this, two threads in
    this process (e.g. ai_setup.py's background install thread writing
    `gpu=...` while the tray app's GUI thread writes `bot_token=...`) can
    both read the same on-disk state, and whichever writes last silently
    drops the other's update. (Doesn't protect against a *separate process*
    — e.g. Docker's api/bot containers — writing concurrently; the atomic
    `os.replace` at least keeps the file itself from getting corrupted.)
    """
    with _config_lock:
        merged = {**read_config(), **updates}
        tmp_path = CONFIG_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)
        os.replace(tmp_path, CONFIG_FILE)
        return merged


# ---------------------------------------------------------------------------
# Bundled read-only assets (ffmpeg/Node/AI runtime). None when running from
# source with no packaged runtime present.
# ---------------------------------------------------------------------------

def _runtime_root() -> str | None:
    root = os.environ.get("APP_RUNTIME_DIR")
    return root if root and os.path.isdir(root) else None


def bundled_ffmpeg_dir() -> str | None:
    root = _runtime_root()
    if not root:
        return None
    candidate = os.path.join(root, "ffmpeg", "bin")
    return candidate if os.path.isdir(candidate) else None


def bundled_node_exe() -> str | None:
    root = _runtime_root()
    if not root:
        return None
    candidate = os.path.join(root, "node", "node.exe")
    return candidate if os.path.isfile(candidate) else None


def runtime_python_exe() -> str:
    """Interpreter used for `pip install`-ing the optional AI dependencies.

    Under a packaged build this is the bundled portable Python (the same one
    running this very process); AI packages are installed straight into its
    site-packages so `demucs`/`audio-separator` console scripts appear in its
    ``Scripts`` folder immediately, with no restart needed. From source, it's
    just the current interpreter (matches today's `install_ai.bat` behavior).
    """
    root = _runtime_root()
    if root:
        candidate = os.path.join(root, "python.exe")
        if os.path.isfile(candidate):
            return candidate
    return sys.executable


def runtime_scripts_dir() -> str:
    return os.path.join(os.path.dirname(runtime_python_exe()), "Scripts")


def default_cookies_file() -> str | None:
    """YTDLP_COOKIES_FILE aniq berilmagan bo'lsa ham, foydalanuvchi cookie
    faylini odatiy joyga (backend papkasi yoki paketlangan qurilmada
    ma'lumotlar papkasi) qo'yishi bilan avtomatik topiladi.

    Fayl nomi QAT'IY EMAS: brauzer kengaytmalari eksport faylini har xil
    nomlaydi — "cookies.txt", "www.youtube.com_cookies.txt" va h.k. Shuning
    uchun `*cookies*.txt` naqshiga mos kelganlarning ichidan ENG YANGISI
    (mtime bo'yicha) tanlanadi. Natijada qayta eksport qilingan fayl darhol
    kuchga kiradi — eskisini o'chirish yoki nomini o'zgartirish shart emas.
    """
    directories = []
    for directory in (_base_dir(), _BACKEND_DIR):
        if directory not in directories and os.path.isdir(directory):
            directories.append(directory)

    candidates = []
    for directory in directories:
        for name in os.listdir(directory):
            lowered = name.lower()
            if not lowered.endswith(".txt") or "cookies" not in lowered:
                continue
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                candidates.append(candidate)

    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def bundled_bgutil_server_dir() -> str | None:
    """Lokal "bgutil" PO token HTTP serverining (`server/build/main.js`)
    qurilgan nusxasi joylashgan papka — topilsa, downloader.py uni avtomatik
    fon jarayoni sifatida ishga tushiradi (pot_server.py'ga qarang)."""
    override = os.environ.get("BGUTIL_SERVER_DIR")
    if override and os.path.isdir(override):
        return override
    root = _runtime_root()
    if root:
        candidate = os.path.join(root, "bgutil", "server")
        if os.path.isdir(candidate):
            return candidate
    # Dev-qulaylik: bgutil-ytdlp-pot-provider'ning o'zi ham "script mode" uchun
    # shu joyni standart deb hisoblaydi — qo'lda shu yerga klonlab qurilgan
    # bo'lsa (server/README.md), avtomatik topiladi.
    home_candidate = os.path.join(os.path.expanduser("~"), "bgutil-ytdlp-pot-provider", "server")
    return home_candidate if os.path.isdir(home_candidate) else None
