"""YouTube Downloader — tray launcher.

Yagona kirish nuqtasi: paketlangan (plug-and-play) versiyada Start Menu/Ish
stoli yorlig'i shu faylni `pythonw.exe` orqali (konsol oynasiz) ishga
tushiradi. Manba koddan sinash uchun to'g'ridan-to'g'ri ham ishlatish mumkin:

    python launcher/tray_app.py

Bajaradigan ishlar: yozish mumkin bo'lgan ma'lumotlar papkasini (%LocalAppData%)
aniqlaydi, birinchi ishga tushirishda (ixtiyoriy) Telegram bot tokenini
so'raydi, Web UI serverini (uvicorn, `backend/main.py`) va — token
kiritilgan bo'lsa — Telegram botni (`backend/bot.py`) alohida fon
thread'larida ishga tushiradi, va boshqarish uchun tizim tray'ida icon
ko'rsatadi: Ochish / To'xtatish-Ishga tushirish / Yuklamalar / Sozlamalar /
Chiqish.
"""
from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Windowed (konsolsiz) PyInstaller build'da sys.stdout/stderr None bo'ladi —
# uvicorn kabi kutubxonalar (masalan .isatty() chaqirib) shunga tayanadi va
# aks holda shu yerda kutilmagan AttributeError bilan qulaydi.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

LAUNCHER_DIR = Path(__file__).resolve().parent
# Paketlangan (PyInstaller) qurilmada `__file__` bundle ichidagi (sintetik)
# yo'lga ishora qiladi — .exe qaysi papkada joylashgani aniqlash uchun
# `sys.executable` ishlatiladi. Manba koddan ishga tushirilganda ikkalasi
# bir xil natija beradi (repo ildizi).
REPO_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else LAUNCHER_DIR.parent
BACKEND_DIR = LAUNCHER_DIR.parent / "backend"

HOST = "127.0.0.1"
PORT = 8000


def _default_app_data_dir() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return os.path.join(local_app_data, "YouTubeDownloader")


def _default_runtime_dir() -> str | None:
    # Paketlangan installer'da repo ildizi o'rnida ilova papkasi bo'ladi va
    # unda "runtime" (bundle qilingan Python/ffmpeg/Node) joylashgan bo'ladi.
    # Manba koddan ishga tushirilganda bu papka mavjud emas — shunda None, va
    # backend hamma narsa uchun tizim PATH'iga tayanadi (bugungidek).
    candidate = REPO_ROOT / "runtime"
    return str(candidate) if candidate.is_dir() else None


def _prepare_environment() -> None:
    os.environ.setdefault("APP_DATA_DIR", _default_app_data_dir())
    os.makedirs(os.environ["APP_DATA_DIR"], exist_ok=True)
    runtime_dir = _default_runtime_dir()
    if runtime_dir:
        os.environ.setdefault("APP_RUNTIME_DIR", runtime_dir)
    # `import main` / `import bot` / `import paths` kabi backend modullarini
    # bare-import bilan topish uchun — start.bat ham `cd backend` qilib xuddi
    # shunday ishlaydi.
    sys.path.insert(0, str(BACKEND_DIR))
    sys.path.insert(0, str(LAUNCHER_DIR))


_prepare_environment()

import paths  # noqa: E402
import token_dialog  # noqa: E402


def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("tray_app")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        os.path.join(paths.LOGS_DIR, "launcher.log"), maxBytes=1_000_000, backupCount=2, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    return logger


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def _show_fatal_error(message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, "YouTube Downloader — kutilmagan xatolik", 0x10)


class ServerManager:
    """FastAPI serverini (`backend/main.py`) alohida thread'da boshqaradi."""

    def __init__(self, host: str = HOST, port: int = PORT) -> None:
        self.host = host
        self.port = port
        self._server = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._server is not None and not self._server.should_exit

    def start(self) -> None:
        if self.running:
            return
        import uvicorn

        config = uvicorn.Config(
            "main:app", host=self.host, port=self.port, log_level="warning", log_config=None,
        )
        self._server = uvicorn.Server(config)

        def run_logged() -> None:
            try:
                self._server.run()
            except Exception:
                logging.getLogger("tray_app").exception("Server thread crashed")

        self._thread = threading.Thread(target=run_logged, daemon=True)
        self._thread.start()
        for _ in range(100):  # ~5s gacha startup kutamiz
            if getattr(self._server, "started", False):
                break
            time.sleep(0.05)

    def stop(self) -> None:
        if not self._server:
            return
        self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=10)
        self._server = None
        self._thread = None


class BotManager:
    """Telegram botni (`backend/bot.py`) alohida thread + event loop'da
    boshqaradi — `dp.stop_polling()` orqali toza to'xtatish uchun."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._dp = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, token: str) -> None:
        if self.running:
            return
        ready = threading.Event()

        def runner() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                import bot as bot_module

                bot_instance, self._dp = bot_module.build(token)
                ready.set()
                loop.run_until_complete(self._dp.start_polling(bot_instance))
            except Exception:
                logging.getLogger("tray_app").exception("Bot thread crashed (token noto'g'ri bo'lishi mumkin)")
            finally:
                ready.set()  # build() xato bersa ham stop() abadiy kutmasin
                loop.close()

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()
        ready.wait(timeout=10)

    def stop(self) -> None:
        if not self.running or self._dp is None or self._loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(self._dp.stop_polling(), self._loop)
        try:
            future.result(timeout=10)
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=10)
        self._thread = None
        self._loop = None
        self._dp = None


def _build_icon_image(running: bool):
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (219, 68, 55, 255) if running else (130, 130, 130, 255)
    draw.ellipse((4, 4, size - 4, size - 4), fill=color)
    draw.polygon([(24, 18), (24, 46), (48, 32)], fill=(255, 255, 255, 255))
    return img


def _build_tray_icon(server: ServerManager, bot_mgr: BotManager, logger: logging.Logger):
    import pystray

    def start_bot_if_configured() -> None:
        token = paths.read_config().get("bot_token")
        if token:
            bot_mgr.start(token)

    def on_open(icon, item) -> None:
        webbrowser.open(f"http://{server.host}:{server.port}")

    def on_toggle(icon, item) -> None:
        if server.running:
            logger.info("Server to'xtatilmoqda (tray)")
            server.stop()
            bot_mgr.stop()
        else:
            logger.info("Server ishga tushirilmoqda (tray)")
            server.start()
            start_bot_if_configured()
        icon.icon = _build_icon_image(server.running)

    def toggle_text(item) -> str:
        return "To'xtatish" if server.running else "Ishga tushirish"

    def on_downloads(icon, item) -> None:
        os.startfile(paths.DOWNLOADS_DIR)

    def on_settings(icon, item) -> None:
        cfg = paths.read_config()
        token = token_dialog.ask_bot_token(cfg.get("bot_token"))
        paths.write_config(bot_token=token)
        if bot_mgr.running:
            bot_mgr.stop()
        if token:
            bot_mgr.start(token)

    def on_exit(icon, item) -> None:
        logger.info("Chiqilmoqda (tray)")
        server.stop()
        bot_mgr.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Ochish (brauzerda)", on_open, default=True, enabled=lambda item: server.running),
        pystray.MenuItem(toggle_text, on_toggle),
        pystray.MenuItem("Yuklamalar papkasini ochish", on_downloads),
        pystray.MenuItem("Sozlamalar (bot token)...", on_settings),
        pystray.MenuItem("Chiqish", on_exit),
    )
    return pystray.Icon("youtube-downloader", _build_icon_image(server.running), "YouTube Downloader", menu)


def _run(logger: logging.Logger) -> None:
    if _port_in_use(HOST, PORT):
        logger.info("Server allaqachon ishlayapti (%s:%s) — brauzer ochiladi.", HOST, PORT)
        webbrowser.open(f"http://{HOST}:{PORT}")
        return

    cfg = paths.read_config()
    if not cfg.get("first_run_done"):
        token = token_dialog.ask_bot_token()
        cfg = paths.write_config(bot_token=token, first_run_done=True)

    server = ServerManager()
    bot_mgr = BotManager()
    server.start()
    logger.info("Server ishga tushdi: http://%s:%s", HOST, PORT)
    if cfg.get("bot_token"):
        bot_mgr.start(cfg["bot_token"])
        logger.info("Telegram bot ishga tushdi")

    icon = _build_tray_icon(server, bot_mgr, logger)

    def setup(ic) -> None:
        ic.visible = True
        webbrowser.open(f"http://{HOST}:{PORT}")

    icon.run(setup=setup)


def main() -> None:
    logger = _setup_logging()
    try:
        _run(logger)
    except Exception:
        tb = traceback.format_exc()
        logger.error("Kutilmagan xatolik:\n%s", tb)
        _show_fatal_error("Dastur kutilmagan xatolikka uchradi:\n\n" + tb[-1500:])
        sys.exit(1)


if __name__ == "__main__":
    main()
