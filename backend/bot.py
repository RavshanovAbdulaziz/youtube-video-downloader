import asyncio
import logging
import os
import uuid

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import downloader
import separator

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEB_UI_URL = os.environ.get("WEB_UI_URL", "")
LOCAL_API_BASE_URL = os.environ.get("LOCAL_API_BASE_URL", "")
# 50MB — standart Telegram Bot API cheklovi. Lokal Bot API server (--local
# rejimda, LOCAL_API_BASE_URL orqali) ishlatilsa, cheklov 2000MB'gacha ko'tariladi.
_DEFAULT_MAX_MB = "1900" if LOCAL_API_BASE_URL else "49"
MAX_TELEGRAM_MB = int(os.environ.get("MAX_TELEGRAM_MB", _DEFAULT_MAX_MB))

router = Router()

# token -> {"url", "title", "audio_format_id", "resolutions": [...]}
contexts: dict[str, dict] = {}


def _original_audio_format_id(audio_tracks: list[dict]) -> str | None:
    return audio_tracks[0]["format_id"] if audio_tracks else None


def _build_keyboard(token: str, resolutions: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for r in resolutions[:6]:
        rows.append([InlineKeyboardButton(text=f"🎬 {r['label']}", callback_data=f"dl:{token}:{r['format_id']}")])
    rows.append([InlineKeyboardButton(text="🎵 Faqat audio", callback_data=f"da:{token}")])
    rows.append([
        InlineKeyboardButton(text="🎤 Ajratish (Demucs)", callback_data=f"sd:{token}"),
        InlineKeyboardButton(text="🎤 Ajratish (UVR)", callback_data=f"su:{token}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(
        "Salom! YouTube havolasini yuboring — video/audio yuklab olish yoki "
        "ovozni ajratish (AI) imkoniyatlarini taklif qilaman."
    )


@router.message(F.text.contains("http"))
async def on_url(message: Message) -> None:
    url = message.text.strip()
    status = await message.answer("Ma'lumot olinmoqda...")
    try:
        info = await asyncio.to_thread(downloader.get_info, url)
    except Exception as e:
        await status.edit_text(f"Xatolik: {e}")
        return

    token = uuid.uuid4().hex[:8]
    contexts[token] = {
        "url": url,
        "title": info.get("title"),
        "audio_format_id": _original_audio_format_id(info.get("audio_tracks", [])),
        "resolutions": info.get("resolutions", []),
    }

    await status.edit_text(
        f"🎬 {info.get('title') or url}\n\nNima qilaylik?",
        reply_markup=_build_keyboard(token, info.get("resolutions", [])),
    )


async def _safe_edit(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def _send_result_file(message: Message, path: str, caption: str = "") -> None:
    size_mb = os.path.getsize(path) / 1024 / 1024
    if size_mb > MAX_TELEGRAM_MB:
        note = f"Fayl juda katta ({size_mb:.0f} MB), Telegram orqali yuborib bo'lmaydi."
        if WEB_UI_URL:
            note += f"\nWeb UI orqali qayta urinib ko'ring: {WEB_UI_URL}"
        await message.answer(note)
        return

    ext = os.path.splitext(path)[1].lower()
    file = FSInputFile(path)
    if ext == ".mp4":
        await message.answer_video(file, caption=caption)
    elif ext == ".mp3":
        await message.answer_audio(file, caption=caption)
    else:
        await message.answer_document(file, caption=caption)


async def _poll_download(message: Message, job_id: str) -> None:
    last_text = None
    while True:
        await asyncio.sleep(1.5)
        progress = downloader.get_progress(job_id)
        if not progress:
            return
        status = progress.get("status")
        if status == "downloading":
            pct = progress.get("percent")
            text = f"Yuklanmoqda: {pct if pct is not None else 0}%"
        elif status == "merging":
            text = "Video va audio birlashtirilmoqda..."
        elif status == "finished":
            await _safe_edit(message, "Tayyor! Yuborilmoqda...")
            await _send_result_file(message, progress["file"])
            downloader.cleanup_job(job_id)
            return
        elif status == "error":
            await _safe_edit(message, f"Xatolik: {progress.get('error')}")
            return
        else:
            continue
        if text != last_text:
            await _safe_edit(message, text)
            last_text = text


async def _poll_separate(message: Message, job_id: str) -> None:
    last_text = None
    while True:
        await asyncio.sleep(1.5)
        progress = separator.get_progress(job_id)
        if not progress:
            return
        status = progress.get("status")
        pct = progress.get("percent", 0)
        if status == "downloading":
            text = f"Audio yuklab olinmoqda: {pct}%"
        elif status == "separating":
            text = f"Ajratilmoqda: {pct}% (bir necha daqiqa vaqt olishi mumkin)"
        elif status == "finished":
            await _safe_edit(message, "Tayyor! Yuborilmoqda...")
            await _send_result_file(message, progress["speech_file"], caption="Gap (speech)")
            separator.cleanup_file(job_id, "speech")
            await _send_result_file(message, progress["background_file"], caption="Fon (background)")
            separator.cleanup_file(job_id, "background")
            return
        elif status == "error":
            await _safe_edit(message, f"Xatolik: {progress.get('error')}")
            return
        else:
            continue
        if text != last_text:
            await _safe_edit(message, text)
            last_text = text


@router.callback_query(F.data.startswith("dl:"))
async def on_download_video(callback: CallbackQuery) -> None:
    _, token, video_format_id = callback.data.split(":", 2)
    ctx = contexts.get(token)
    if not ctx:
        await callback.answer("Muddati tugagan, havolani qayta yuboring.", show_alert=True)
        return
    await callback.answer()
    job_id = downloader.start_download(
        ctx["url"], video_format_id, ctx["audio_format_id"], False, ctx["title"]
    )
    await callback.message.edit_text("Boshlanmoqda...")
    asyncio.create_task(_poll_download(callback.message, job_id))


@router.callback_query(F.data.startswith("da:"))
async def on_download_audio(callback: CallbackQuery) -> None:
    _, token = callback.data.split(":", 1)
    ctx = contexts.get(token)
    if not ctx:
        await callback.answer("Muddati tugagan, havolani qayta yuboring.", show_alert=True)
        return
    await callback.answer()
    job_id = downloader.start_download(ctx["url"], None, ctx["audio_format_id"], True, ctx["title"])
    await callback.message.edit_text("Boshlanmoqda...")
    asyncio.create_task(_poll_download(callback.message, job_id))


@router.callback_query(F.data.startswith("sd:") | F.data.startswith("su:"))
async def on_separate(callback: CallbackQuery) -> None:
    engine_prefix, token = callback.data.split(":", 1)
    engine = "demucs" if engine_prefix == "sd" else "uvr"
    ctx = contexts.get(token)
    if not ctx:
        await callback.answer("Muddati tugagan, havolani qayta yuboring.", show_alert=True)
        return
    if not ctx["audio_format_id"]:
        await callback.answer("Bu video uchun audio trek topilmadi.", show_alert=True)
        return
    await callback.answer()
    job_id = separator.start_separation(ctx["url"], ctx["audio_format_id"], ctx["title"], engine)
    await callback.message.edit_text("Boshlanmoqda...")
    asyncio.create_task(_poll_separate(callback.message, job_id))


async def main() -> None:
    session = None
    if LOCAL_API_BASE_URL:
        session = AiohttpSession(api=TelegramAPIServer.from_base(LOCAL_API_BASE_URL, is_local=True))
    bot = Bot(BOT_TOKEN, session=session)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
