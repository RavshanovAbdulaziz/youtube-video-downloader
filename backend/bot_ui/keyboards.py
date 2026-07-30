from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .callbacks import (
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
from .texts import BACK_LABEL, resolution_button_text

EMPTY = InlineKeyboardMarkup(inline_keyboard=[])


def main_menu(ctx, token: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🎬 Video yuklab olish", callback_data=MenuVideoCB(token=token).pack())]]
    if ctx.audio_format_id:
        rows.append([InlineKeyboardButton(text="🎵 Faqat audio (mp3)", callback_data=DownloadAudioCB(token=token).pack())])
        rows.append([InlineKeyboardButton(text="🎤 Ovozni ajratish (AI)", callback_data=MenuSeparateCB(token=token).pack())])
        if len(ctx.audio_tracks) > 1:
            rows.append([InlineKeyboardButton(text="🌐 Audio tilini o'zgartirish", callback_data=PickLanguageCB(token=token).pack())])
    if ctx.subtitles:
        rows.append([InlineKeyboardButton(text="📝 Subtitr (matn)", callback_data=MenuSubtitleCB(token=token).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def resolutions_menu(token: str, resolutions: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for r in resolutions[:8]:
        row.append(InlineKeyboardButton(
            text=resolution_button_text(r),
            callback_data=DownloadVideoCB(token=token, format_id=r["format_id"]).pack(),
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=BACK_LABEL, callback_data=MenuBackCB(token=token).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def separate_menu(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Demucs (tezroq)", callback_data=SeparateCB(token=token, engine="demucs").pack())],
        [InlineKeyboardButton(text="💎 UVR (sifatliroq)", callback_data=SeparateCB(token=token, engine="uvr").pack())],
        [InlineKeyboardButton(text=BACK_LABEL, callback_data=MenuBackCB(token=token).pack())],
    ])


def language_menu(token: str, audio_tracks: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for i, track in enumerate(audio_tracks):
        mark = "✅ " if track.get("is_original") else ""
        rows.append([InlineKeyboardButton(
            text=f"{mark}{track.get('label', track.get('lang_code', '?'))}",
            callback_data=SetLanguageCB(token=token, index=i).pack(),
        )])
    rows.append([InlineKeyboardButton(text=BACK_LABEL, callback_data=MenuBackCB(token=token).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subtitle_menu(token: str, subtitles: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for i, sub in enumerate(subtitles[:30]):
        rows.append([InlineKeyboardButton(
            text=sub["label"],
            callback_data=DownloadSubtitleCB(token=token, index=i).pack(),
        )])
    rows.append([InlineKeyboardButton(text=BACK_LABEL, callback_data=MenuBackCB(token=token).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def web_ui_link(web_ui_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Web UI'ni ochish", url=web_ui_url)]
    ])
