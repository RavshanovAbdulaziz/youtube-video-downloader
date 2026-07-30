import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message

import downloader
import separator
from bot_ui import keyboards as kb
from bot_ui import texts
from bot_ui.callbacks import (
    DownloadAudioCB,
    DownloadSubtitleCB,
    DownloadVideoCB,
    MenuBackCB,
    MenuSeparateCB,
    MenuSubtitleCB,
    MenuVideoCB,
    PickLanguageCB,
    SeparateCB,
    SetLanguageCB,
)
from bot_ui.state import ContextStore, VideoContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# Eslatma: BOT_TOKEN modul darajasida O'QILMAYDI — tray launcher botni shaxsiy
# tokensiz ham (faqat Web UI rejimida) import qila olishi kerak, xatosiz.
# Token faqat build()/main() ga parametr sifatida beriladi (pastga qarang).
WEB_UI_URL = os.environ.get("WEB_UI_URL", "")
LOCAL_API_BASE_URL = os.environ.get("LOCAL_API_BASE_URL", "")
# 50MB — standart Telegram Bot API cheklovi. Lokal Bot API server (--local
# rejimda, LOCAL_API_BASE_URL orqali) ishlatilsa, cheklov 2000MB'gacha ko'tariladi.
_DEFAULT_MAX_MB = "1900" if LOCAL_API_BASE_URL else "49"
MAX_TELEGRAM_MB = int(os.environ.get("MAX_TELEGRAM_MB", _DEFAULT_MAX_MB))

router = Router()
store = ContextStore()


# ---------------------------------------------------------------------------
# Kartochka (thumbnail + caption) bilan ishlash
# ---------------------------------------------------------------------------

async def _send_info_card(message: Message, token: str, ctx: VideoContext) -> None:
    caption = texts.card_header(ctx)
    keyboard = kb.main_menu(ctx, token)
    if ctx.thumbnail:
        try:
            await message.answer_photo(ctx.thumbnail, caption=caption, reply_markup=keyboard)
            return
        except TelegramBadRequest:
            pass  # rasm topilmadi/yuklanmadi — oddiy matn xabariga tushamiz
    await message.answer(caption, reply_markup=keyboard)


async def _edit_card(message: Message, caption: str, keyboard=None) -> None:
    markup = keyboard if keyboard is not None else kb.EMPTY
    try:
        if message.photo:
            await message.edit_caption(caption=caption, reply_markup=markup)
        else:
            await message.edit_text(caption, reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


def _ctx_or_none(token: str) -> VideoContext | None:
    return store.get(token)


# ---------------------------------------------------------------------------
# Buyruqlar
# ---------------------------------------------------------------------------

@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(texts.START_TEXT)


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(texts.help_text(MAX_TELEGRAM_MB))


@router.message(F.text.contains("http"))
async def on_url(message: Message) -> None:
    url = message.text.strip()
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    status = await message.answer("⏳ Ma'lumot olinmoqda...")
    try:
        info = await asyncio.to_thread(downloader.get_info, url)
    except Exception as e:
        logger.warning("get_info failed for %s: %s", url, e)
        await status.edit_text(f"❌ Xatolik: {e}")
        return

    token = store.create(
        url=url,
        title=info.get("title"),
        duration=info.get("duration"),
        thumbnail=info.get("thumbnail"),
        resolutions=info.get("resolutions", []),
        audio_tracks=info.get("audio_tracks", []),
        subtitles=info.get("subtitles", []),
    )
    ctx = store.get(token)

    await status.delete()
    await _send_info_card(message, token, ctx)


# ---------------------------------------------------------------------------
# Menyu navigatsiyasi
# ---------------------------------------------------------------------------

@router.callback_query(MenuVideoCB.filter())
async def on_menu_video(callback: CallbackQuery, callback_data: MenuVideoCB) -> None:
    ctx = _ctx_or_none(callback_data.token)
    if not ctx:
        await callback.answer(texts.EXPIRED_ALERT, show_alert=True)
        return
    await callback.answer()
    await _edit_card(
        callback.message,
        texts.resolution_submenu_caption(ctx),
        kb.resolutions_menu(callback_data.token, ctx.resolutions),
    )


@router.callback_query(MenuSeparateCB.filter())
async def on_menu_separate(callback: CallbackQuery, callback_data: MenuSeparateCB) -> None:
    ctx = _ctx_or_none(callback_data.token)
    if not ctx:
        await callback.answer(texts.EXPIRED_ALERT, show_alert=True)
        return
    await callback.answer()
    await _edit_card(
        callback.message,
        texts.separate_submenu_caption(ctx),
        kb.separate_menu(callback_data.token),
    )


@router.callback_query(PickLanguageCB.filter())
async def on_pick_language(callback: CallbackQuery, callback_data: PickLanguageCB) -> None:
    ctx = _ctx_or_none(callback_data.token)
    if not ctx:
        await callback.answer(texts.EXPIRED_ALERT, show_alert=True)
        return
    await callback.answer()
    await _edit_card(
        callback.message,
        texts.language_submenu_caption(ctx),
        kb.language_menu(callback_data.token, ctx.audio_tracks),
    )


@router.callback_query(SetLanguageCB.filter())
async def on_set_language(callback: CallbackQuery, callback_data: SetLanguageCB) -> None:
    ctx = _ctx_or_none(callback_data.token)
    if not ctx:
        await callback.answer(texts.EXPIRED_ALERT, show_alert=True)
        return
    if 0 <= callback_data.index < len(ctx.audio_tracks):
        ctx.audio_index = callback_data.index
    await callback.answer("✅ Til o'zgartirildi")
    await _edit_card(callback.message, texts.card_header(ctx), kb.main_menu(ctx, callback_data.token))


@router.callback_query(MenuSubtitleCB.filter())
async def on_menu_subtitle(callback: CallbackQuery, callback_data: MenuSubtitleCB) -> None:
    ctx = _ctx_or_none(callback_data.token)
    if not ctx:
        await callback.answer(texts.EXPIRED_ALERT, show_alert=True)
        return
    await callback.answer()
    await _edit_card(
        callback.message,
        texts.subtitle_submenu_caption(ctx),
        kb.subtitle_menu(callback_data.token, ctx.subtitles),
    )


@router.callback_query(MenuBackCB.filter())
async def on_menu_back(callback: CallbackQuery, callback_data: MenuBackCB) -> None:
    ctx = _ctx_or_none(callback_data.token)
    if not ctx:
        await callback.answer(texts.EXPIRED_ALERT, show_alert=True)
        return
    await callback.answer()
    await _edit_card(callback.message, texts.card_header(ctx), kb.main_menu(ctx, callback_data.token))


# ---------------------------------------------------------------------------
# Progress kuzatuvchilar
# ---------------------------------------------------------------------------

async def _send_result_file(
    message: Message,
    path: str,
    caption: str = "",
    *,
    width: int | None = None,
    height: int | None = None,
    duration: float | None = None,
) -> None:
    size_mb = os.path.getsize(path) / 1024 / 1024
    if size_mb > MAX_TELEGRAM_MB:
        await message.answer(
            texts.too_large_text(size_mb, WEB_UI_URL),
            reply_markup=kb.web_ui_link(WEB_UI_URL) if WEB_UI_URL else None,
        )
        return

    ext = os.path.splitext(path)[1].lower()
    file = FSInputFile(path)
    action = {".mp4": ChatAction.UPLOAD_VIDEO, ".mp3": ChatAction.UPLOAD_VOICE}.get(ext, ChatAction.UPLOAD_DOCUMENT)
    await message.bot.send_chat_action(message.chat.id, action)

    if ext == ".mp4":
        await message.answer_video(
            file,
            caption=caption,
            width=width,
            height=height,
            duration=int(duration) if duration else None,
            supports_streaming=True,
        )
    elif ext == ".mp3":
        await message.answer_audio(file, caption=caption)
    else:
        await message.answer_document(file, caption=caption)


async def _safe_edit_text(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def _poll_download(
    message: Message,
    ctx: VideoContext,
    job_id: str,
    action_key: str,
    *,
    width: int | None = None,
    height: int | None = None,
) -> None:
    try:
        last_text = None
        while True:
            await asyncio.sleep(1.5)
            progress = downloader.get_progress(job_id)
            if not progress:
                return
            status = progress.get("status")
            if status == "downloading":
                text = texts.download_progress_caption(ctx, progress.get("percent"), progress.get("speed"))
            elif status == "merging":
                text = texts.merging_caption(ctx)
            elif status == "finished":
                await _safe_edit_text(message, texts.uploading_caption(ctx))
                await _send_result_file(
                    message, progress["file"], width=width, height=height, duration=ctx.duration
                )
                downloader.cleanup_job(job_id)
                return
            elif status == "error":
                await _safe_edit_text(message, texts.error_caption(ctx, progress.get("error")))
                return
            else:
                continue
            if text != last_text:
                await _safe_edit_text(message, text)
                last_text = text
    except Exception:
        logger.exception("Download poll loop failed for job %s", job_id)
        await _safe_edit_text(message, texts.unexpected_error_caption(ctx))
    finally:
        ctx.finish(action_key)


async def _poll_separate(message: Message, ctx: VideoContext, job_id: str, action_key: str) -> None:
    try:
        last_text = None
        while True:
            await asyncio.sleep(1.5)
            progress = separator.get_progress(job_id)
            if not progress:
                return
            status = progress.get("status")
            pct = progress.get("percent", 0)
            if status in ("installing_ai", "downloading", "separating"):
                text = texts.separate_progress_caption(ctx, status, pct, progress.get("ai_stage"))
            elif status == "finished":
                await _safe_edit_text(message, texts.uploading_caption(ctx))
                await _send_result_file(message, progress["speech_file"], caption="🗣 Nutq (speech)")
                separator.cleanup_file(job_id, "speech")
                await _send_result_file(message, progress["background_file"], caption="🎼 Fon (background)")
                separator.cleanup_file(job_id, "background")
                return
            elif status == "error":
                await _safe_edit_text(message, texts.error_caption(ctx, progress.get("error")))
                return
            else:
                continue
            if text != last_text:
                await _safe_edit_text(message, text)
                last_text = text
    except Exception:
        logger.exception("Separate poll loop failed for job %s", job_id)
        await _safe_edit_text(message, texts.unexpected_error_caption(ctx))
    finally:
        ctx.finish(action_key)


# ---------------------------------------------------------------------------
# Ish (job) boshlash
# ---------------------------------------------------------------------------

@router.callback_query(DownloadVideoCB.filter())
async def on_download_video(callback: CallbackQuery, callback_data: DownloadVideoCB) -> None:
    ctx = _ctx_or_none(callback_data.token)
    if not ctx:
        await callback.answer(texts.EXPIRED_ALERT, show_alert=True)
        return
    action_key = f"dv:{callback_data.format_id}"
    if not ctx.try_start(action_key):
        await callback.answer(texts.BUSY_ALERT, show_alert=True)
        return
    await callback.answer()
    job_id = downloader.start_download(
        ctx.url, callback_data.format_id, ctx.audio_format_id, False, ctx.title
    )
    chosen = next((r for r in ctx.resolutions if r["format_id"] == callback_data.format_id), None)
    # Kartochka (thumbnail + menyu) o'z holicha qoladi — foydalanuvchi shu
    # video uchun darhol boshqa xizmatni ham tanlay oladi. Progress alohida
    # xabarda kuzatiladi.
    await _edit_card(callback.message, texts.card_header(ctx), kb.main_menu(ctx, callback_data.token))
    status = await callback.message.answer(texts.starting_caption(ctx))
    asyncio.create_task(_poll_download(
        status, ctx, job_id, action_key,
        width=chosen.get("width") if chosen else None,
        height=chosen.get("height") if chosen else None,
    ))


@router.callback_query(DownloadAudioCB.filter())
async def on_download_audio(callback: CallbackQuery, callback_data: DownloadAudioCB) -> None:
    ctx = _ctx_or_none(callback_data.token)
    if not ctx:
        await callback.answer(texts.EXPIRED_ALERT, show_alert=True)
        return
    action_key = "da"
    if not ctx.try_start(action_key):
        await callback.answer(texts.BUSY_ALERT, show_alert=True)
        return
    await callback.answer()
    job_id = downloader.start_download(ctx.url, None, ctx.audio_format_id, True, ctx.title)
    await _edit_card(callback.message, texts.card_header(ctx), kb.main_menu(ctx, callback_data.token))
    status = await callback.message.answer(texts.starting_caption(ctx))
    asyncio.create_task(_poll_download(status, ctx, job_id, action_key))


@router.callback_query(DownloadSubtitleCB.filter())
async def on_download_subtitle(callback: CallbackQuery, callback_data: DownloadSubtitleCB) -> None:
    ctx = _ctx_or_none(callback_data.token)
    if not ctx:
        await callback.answer(texts.EXPIRED_ALERT, show_alert=True)
        return
    if not (0 <= callback_data.index < len(ctx.subtitles)):
        await callback.answer(texts.EXPIRED_ALERT, show_alert=True)
        return
    sub = ctx.subtitles[callback_data.index]
    action_key = f"st:{sub['lang_code']}:{int(sub['auto'])}"
    if not ctx.try_start(action_key):
        await callback.answer(texts.BUSY_ALERT, show_alert=True)
        return
    await callback.answer()
    job_id = downloader.start_subtitle_download(ctx.url, sub["lang_code"], sub["auto"], ctx.title)
    await _edit_card(callback.message, texts.card_header(ctx), kb.main_menu(ctx, callback_data.token))
    status = await callback.message.answer(texts.starting_caption(ctx))
    asyncio.create_task(_poll_download(status, ctx, job_id, action_key))


@router.callback_query(SeparateCB.filter())
async def on_separate(callback: CallbackQuery, callback_data: SeparateCB) -> None:
    ctx = _ctx_or_none(callback_data.token)
    if not ctx:
        await callback.answer(texts.EXPIRED_ALERT, show_alert=True)
        return
    if not ctx.audio_format_id:
        await callback.answer(texts.NO_AUDIO_ALERT, show_alert=True)
        return
    action_key = f"se:{callback_data.engine}"
    if not ctx.try_start(action_key):
        await callback.answer(texts.BUSY_ALERT, show_alert=True)
        return
    await callback.answer()
    job_id = separator.start_separation(ctx.url, ctx.audio_format_id, ctx.title, callback_data.engine)
    await _edit_card(callback.message, texts.card_header(ctx), kb.main_menu(ctx, callback_data.token))
    status = await callback.message.answer(texts.starting_caption(ctx))
    asyncio.create_task(_poll_separate(status, ctx, job_id, action_key))


@router.errors()
async def on_error(event, exception: Exception) -> bool:
    logger.exception("Unhandled error while processing update: %s", exception)
    return True


def build(token: str) -> tuple[Bot, Dispatcher]:
    """Bot/Dispatcher juftligini yaratadi (ishga tushirmasdan) — chaqiruvchi
    tomon `dp`ni saqlab qolsa, keyinchalik `dp.stop_polling()` orqali
    boshqa thread'dan ham botni to'xtata oladi (masalan tray ilovasidan)."""
    session = None
    if LOCAL_API_BASE_URL:
        session = AiohttpSession(api=TelegramAPIServer.from_base(LOCAL_API_BASE_URL, is_local=True))
    bot = Bot(token, session=session, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)
    return bot, dp


async def main(token: str) -> None:
    bot, dp = build(token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    _token = os.environ.get("BOT_TOKEN")
    if not _token:
        print("XATO: BOT_TOKEN muhit o'zgaruvchisi topilmadi (backend/.env ichida BOT_TOKEN=... bo'lishi kerak).")
        sys.exit(1)
    asyncio.run(main(_token))
