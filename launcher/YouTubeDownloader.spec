# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — YouTube Downloader tray app (Web UI + Telegram bot).

Quri (build.bat orqali yoki qo'lda):
    pyinstaller launcher/YouTubeDownloader.spec --noconfirm

Natija: dist/YouTubeDownloader/YouTubeDownloader.exe — build.bat bu qadamdan
so'ng ffmpeg.exe/ffprobe.exe'ni shu papka ichidagi runtime/ffmpeg/bin/'ga
nusxalaydi (paths.py shu joyni APP_RUNTIME_DIR sifatida avtomatik topadi).
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

REPO_ROOT = Path(SPECPATH).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"
LAUNCHER_DIR = REPO_ROOT / "launcher"
FRONTEND_DIR = REPO_ROOT / "frontend"

datas = [(str(FRONTEND_DIR), "frontend")]
binaries = []
hiddenimports = [
    "main", "bot", "downloader", "separator", "paths", "pot_server", "ai_setup",
    "bot_ui", "bot_ui.callbacks", "bot_ui.keyboards", "bot_ui.state", "bot_ui.texts",
    "token_dialog",
    "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on", "uvicorn.logging",
    "pystray._win32",
]

# yt_dlp/uvicorn/aiogram/pydantic o'zining ko'p qismini dinamik (lazy) import
# qiladi — oddiy statik tahlil buni ko'rmaydi, shuning uchun to'liq yig'ib olamiz.
for pkg in ("yt_dlp", "uvicorn", "aiogram", "pydantic", "pydantic_core", "fastapi", "starlette", "pystray"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# "Ovozni ajratish (AI)" funksiyasi (Demucs/UVR) alohida, o'rnatilgandan
# keyingi Python muhitida subprocess orqali ishlaydi (ai_setup.py) — asosiy
# .exe ichiga hech qachon kiritilmasligi kerak (gigabayt o'lchamli bo'lardi).
excludes = ["torch", "torchaudio", "demucs", "audio_separator", "numba", "librosa"]

a = Analysis(
    [str(LAUNCHER_DIR / "tray_app.py")],
    pathex=[str(BACKEND_DIR), str(LAUNCHER_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YouTubeDownloader",
    console=False,
    icon=str(LAUNCHER_DIR / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="YouTubeDownloader",
)
