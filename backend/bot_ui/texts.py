import html

START_TEXT = (
    "👋 <b>Salom!</b>\n\n"
    "YouTube havolasini shu yerga yuboring — men taklif qilaman:\n"
    "🎬 Video (istalgan sifatda)\n"
    "🎵 Faqat audio (mp3)\n"
    "🎤 Ovozni ajratish (AI: nutq / fon)\n"
    "📝 Subtitr (matn, .srt)\n\n"
    "Yordam uchun: /help"
)

EXPIRED_ALERT = "⏳ Muddati tugagan, havolani qayta yuboring."
BUSY_ALERT = "⌛ Joriy vazifa hali tugamadi, biroz kuting."
NO_AUDIO_ALERT = "Bu video uchun audio trek topilmadi."
BACK_LABEL = "🔙 Orqaga"


def help_text(max_telegram_mb: int) -> str:
    return (
        "ℹ️ <b>Qanday ishlatiladi</b>\n\n"
        "1️⃣ YouTube havolasini yuboring\n"
        "2️⃣ Kerakli amalni tugmalar orqali tanlang\n"
        "3️⃣ Kutib turing — tayyor bo'lgach fayl avtomatik keladi\n\n"
        f"📦 Fayl hajmi chegarasi: {max_telegram_mb} MB"
    )


def fmt_duration(seconds) -> str:
    if not seconds:
        return ""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_size(size_bytes) -> str:
    if not size_bytes:
        return ""
    mb = size_bytes / 1024 / 1024
    return f"{mb:.0f} MB" if mb < 1024 else f"{mb / 1024:.1f} GB"


def progress_bar(percent, width: int = 14) -> str:
    percent = max(0, min(100, percent or 0))
    filled = round(width * percent / 100)
    return "█" * filled + "░" * (width - filled)


def card_header(ctx) -> str:
    title = html.escape(ctx.title or ctx.url)
    duration = fmt_duration(ctx.duration)
    header = f"🎬 <b>{title}</b>"
    if duration:
        header += f"\n⏱ {duration}"
    if ctx.audio_label:
        header += f"\n🌐 {html.escape(ctx.audio_label)}"
    return header


def resolution_submenu_caption(ctx) -> str:
    return card_header(ctx) + "\n\n📐 Sifatni tanlang:"


def separate_submenu_caption(ctx) -> str:
    return (
        card_header(ctx) + "\n\n"
        "🎤 <b>Ovozni ajratish</b> — audio ikkiga bo'linadi: nutq va fon.\n"
        "⚡ <i>Demucs</i> — tezroq\n"
        "💎 <i>UVR</i> — sifatliroq, sekinroq"
    )


def language_submenu_caption(ctx) -> str:
    return card_header(ctx) + "\n\n🌐 Audio tilini tanlang:"


def subtitle_submenu_caption(ctx) -> str:
    return card_header(ctx) + "\n\n📝 Subtitr tilini tanlang:"


def resolution_button_text(r: dict) -> str:
    size = fmt_size(r.get("filesize"))
    audio_mark = "" if r.get("has_audio") else " 🔇"
    return r["label"] + audio_mark + (f" · {size}" if size else "")


def starting_caption(ctx) -> str:
    return card_header(ctx) + "\n\n⏳ Boshlanmoqda..."


def download_progress_caption(ctx, percent, speed) -> str:
    pct = percent or 0
    speed_txt = f" · {speed / 1024 / 1024:.1f} MB/s" if speed else ""
    return (
        card_header(ctx) + "\n\n"
        f"📥 Yuklanmoqda\n<code>{progress_bar(pct)}</code> {pct:.0f}%{speed_txt}"
    )


def merging_caption(ctx) -> str:
    return card_header(ctx) + "\n\n🔧 Video va audio birlashtirilmoqda..."


_AI_STAGE_LABELS = {
    "torch": "PyTorch", "demucs": "Demucs", "separator": "UVR/audio-separator",
    "compat": "moslashtirish",
}


def separate_progress_caption(ctx, status: str, percent, ai_stage: str | None = None) -> str:
    pct = percent or 0
    if status == "installing_ai":
        stage_label = _AI_STAGE_LABELS.get(ai_stage, "")
        return (
            card_header(ctx) + "\n\n"
            f"⚙️ AI komponentlari o'rnatilmoqda{f' ({stage_label})' if stage_label else ''}\n"
            f"<code>{progress_bar(pct)}</code> {pct}%\n"
            "<i>(bir martalik jarayon, internetga bog'liq)</i>"
        )
    if status == "downloading":
        return (
            card_header(ctx) + "\n\n"
            f"📥 Audio yuklanmoqda\n<code>{progress_bar(pct)}</code> {pct}%"
        )
    return (
        card_header(ctx) + "\n\n"
        f"🧠 Ajratilmoqda\n<code>{progress_bar(pct)}</code> {pct}%\n"
        "<i>(bir necha daqiqa vaqt olishi mumkin)</i>"
    )


def uploading_caption(ctx) -> str:
    return card_header(ctx) + "\n\n✅ Tayyor! Yuborilmoqda..."


def error_caption(ctx, message) -> str:
    return card_header(ctx) + f"\n\n❌ Xatolik: {html.escape(str(message))}"


def unexpected_error_caption(ctx) -> str:
    return card_header(ctx) + "\n\n❌ Kutilmagan xatolik yuz berdi."


def too_large_text(size_mb: float, web_ui_url: str) -> str:
    text = f"⚠️ Fayl juda katta ({size_mb:.0f} MB), Telegram orqali yuborib bo'lmaydi."
    if web_ui_url:
        text += f"\n🔗 Web UI orqali qayta urinib ko'ring: {web_ui_url}"
    return text
