import contextlib
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import yt_dlp
from yt_dlp.cookies import extract_cookies_from_browser
from yt_dlp.networking.common import Request

import paths
import pot_server

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

DOWNLOADS_DIR = paths.DOWNLOADS_DIR

# Datacenter IP'lardan (masalan, bulutli serverlardan) kelayotgan so'rovlarni,
# va tobora ko'proq holatlarda hatto rezidensial IP'lardan kelgan so'rovlarni
# ham, YouTube "sign in to confirm you're not a bot" deb bloklashi mumkin.
# Asosiy yechim: PO token provider (bgutil) — hisobga bog'liq bo'lmagan,
# cookie kabi "bekor qilinish"ga moyil bo'lmagan usul
# (https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide). Server/Docker
# joylashtirishda YTDLP_POT_BASE_URL alohida konteynerga ishora qiladi; lokal
# Windows ishga tushirishda esa (bu env var berilmagan bo'lsa) pot_server.py
# lokal bgutil serverini o'zi avtomatik topib, fon jarayoni sifatida ishga
# tushiradi — foydalanuvchi hech narsa sozlamaydi. cookies.txt (agar
# backend/ papkasiga qo'yilgan bo'lsa) qo'shimcha himoya, shart emas.
COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE", "") or paths.default_cookies_file() or ""
POT_BASE_URL = os.environ.get("YTDLP_POT_BASE_URL", "")

# Cookie'larni fayldan emas, BRAUZERDAN to'g'ridan-to'g'ri o'qish. Bu yagona
# haqiqiy "avtomatik" usul: har safar brauzerdagi joriy cookie olinadi, ya'ni
# YouTube ularni yangilaganda ham hech narsa qo'lda eksport qilinmaydi.
# Format: "firefox", "chrome", "edge:Profile 1" va h.k.
#
# DIQQAT — Windows'da cheklov bor: Chrome 127+ (va uning asosidagi Edge,
# Brave, Opera) cookie bazasini "App-Bound Encryption" bilan shifrlaydi va
# yt-dlp uni ocha olmaydi ("Failed to decrypt with DPAPI",
# https://github.com/yt-dlp/yt-dlp/issues/10927). Ya'ni bu sozlama amalda
# faqat FIREFOX bilan ishonchli ishlaydi.
#
# Sozlama yoqilgani bilan brauzer o'qilmasligi mumkin (profil yo'q, brauzer
# o'rnatilmagan, shifrlash ochilmadi). Bunday holat XATO EMAS: _browser_
# cookies_usable() buni oldindan bir marta tekshiradi va ishlamasa, jim
# ravishda cookie fayliga (u ham bo'lmasa — cookie'siz rejimga) qaytadi.
COOKIES_FROM_BROWSER = (
    os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "")
    or (paths.read_config().get("cookies_from_browser") or "")
).strip()

# YouTube brauzerdan eksport qilingan hisob cookie'larini vaqti-vaqti bilan
# "rotate" qiladi (xavfsizlik chorasi) — shundan keyin eksport fayli o'lik
# bo'lib qoladi. yt-dlp buni har bir so'rovdan keyin o'zi sezadi va
# ogohlantiradi; biz o'sha ogohlantirishni ushlab, faylni shu jarayon
# davomida chetlab o'tamiz va foydalanuvchiga bir marta aniq xabar beramiz.
# Aks holda dastur "jim" ravishda o'lik cookie yuboraverar edi va nima uchun
# qayta eksport kerakligi umuman bilinmasdi.
_COOKIES_INVALID_MARKER = "account cookies are no longer valid"
_cookies_invalid = False
_cookies_lock = threading.Lock()


def _cookies_file_usable() -> bool:
    return bool(COOKIES_FILE) and os.path.isfile(COOKIES_FILE) and not _cookies_invalid


def _mark_cookies_invalid() -> None:
    global _cookies_invalid
    with _cookies_lock:
        if _cookies_invalid:
            return
        _cookies_invalid = True
    print(
        f"DIQQAT: cookie fayli eskirgan, YouTube uni bekor qilgan:\n"
        f"  {COOKIES_FILE}\n"
        "  Yuklash cookie'siz davom etadi (ko'p hollarda bu yetarli).\n"
        "  Yosh cheklovli yoki yopiq videolar uchun brauzerdan yangi cookie\n"
        "  eksport qilib, shu papkaga qo'ying. Nomi muhim emas: eng yangi\n"
        "  *cookies*.txt fayli avtomatik tanlanadi.",
        file=sys.stderr,
    )


def _parse_cookies_from_browser(spec: str) -> tuple:
    """yt-dlp'ning `cookiesfrombrowser` parametri uchun: "chrome:Profile 1" ->
    ("chrome", "Profile 1", None, None)."""
    browser, _, profile = spec.partition(":")
    return (browser.strip().lower(), profile.strip() or None, None, None)


_browser_probe_lock = threading.Lock()
_browser_probe_done = False
_browser_cookies_ok = False


def _browser_cookies_usable() -> bool:
    """Brauzerdan cookie o'qish sozlangan bo'lsa, u AMALDA ishlashini bir
    marta tekshiradi; natija jarayon davomida eslab qolinadi.

    Tekshiruv ataylab shu yerda bajariladi, yt-dlp ichida emas: agar
    `cookiesfrombrowser` berilib, brauzer bazasi ochilmasa, yt-dlp BUTUN
    yuklashni xato bilan to'xtatadi. Bu yerda esa muvaffaqiyatsizlik oddiy
    "cookie yo'q" holatiga aylanadi va yuklash davom etaveradi — cookie
    faqat yosh cheklovli/yopiq videolar uchun kerak, oddiy videolar ularsiz
    ham yuklanadi.
    """
    global _browser_probe_done, _browser_cookies_ok
    if not COOKIES_FROM_BROWSER:
        return False
    if _browser_probe_done:
        return _browser_cookies_ok

    with _browser_probe_lock:
        if _browser_probe_done:
            return _browser_cookies_ok
        browser, profile, keyring, container = _parse_cookies_from_browser(COOKIES_FROM_BROWSER)
        try:
            jar = extract_cookies_from_browser(
                browser, profile, _LOGGER, keyring=keyring, container=container,
            )
        except Exception as e:
            reason = str(e).splitlines()[0] if str(e) else e.__class__.__name__
            print(
                f"DIQQAT: '{browser}' brauzeridan cookie o'qib bo'lmadi: {reason}\n"
                "  Cookie fayli (yoki cookie'siz rejim) ishlatiladi.",
                file=sys.stderr,
            )
        else:
            _browser_cookies_ok = any("youtube.com" in (c.domain or "") for c in jar)
            if not _browser_cookies_ok:
                print(
                    f"DIQQAT: '{browser}' brauzerida YouTube cookie'lari topilmadi.\n"
                    "  Unda YouTube'ga bir marta kiring va dasturni qayta ishga tushiring.\n"
                    "  Hozircha cookie fayli (yoki cookie'siz rejim) ishlatiladi.",
                    file=sys.stderr,
                )
        _browser_probe_done = True
    return _browser_cookies_ok


class _YdlLogger:
    """yt-dlp uchun logger — `no_warnings=True` bo'lganda ham ogohlantirishlar
    loggerga baribir uzatiladi, cookie eskirganini aynan shu yerda ushlaymiz.
    Xatolar avvalgidek stderr'ga chiqadi (va yt-dlp ularni `DownloadError`
    sifatida ko'taradi, ya'ni job holati o'zgarmaydi)."""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg, only_once=False):
        # `only_once` — yt-dlp'ning cookies.py moduli loggerni aynan shu
        # imzo bilan chaqiradi; parametrsiz qolsa, brauzerdan cookie o'qishda
        # TypeError bo'lardi.
        if _COOKIES_INVALID_MARKER in msg:
            _mark_cookies_invalid()

    def error(self, msg):
        print(msg, file=sys.stderr)


_LOGGER = _YdlLogger()


@contextlib.contextmanager
def ydl_opts_ctx(extra: dict):
    """yt-dlp uchun umumiy sozlamalar. Har bir chaqiruv cookies faylining
    o'z vaqtinchalik nusxasini oladi — chunki yt-dlp foydalanilgan
    cookie'larni faylga qayta yozadi, va bir nechta jarayon (api + bot,
    yoki bir nechta parallel so'rov) bitta faylni bir vaqtda yozsa, u
    asta-sekin buzilib boradi. Asosiy fayl hech qachon o'zgarmaydi.
    """
    opts = {"js_runtimes": {"node": {}}, "logger": _LOGGER, **extra}
    # "web"/"web_safari" mijozlari cookie (login) bilan so'ralganda YouTube
    # SABR streamingni majburlaydi va ko'pchilik DASH formatlarini (jumladan
    # audio-only treklarni) URL'siz qoldiradi — natijada audio_tracks bo'sh
    # chiqadi va segment (start/end) yuklab olish uchun kerakli byte-range
    # so'rovlar ishlamay qoladi. "web_embedded" bunday emas — cookie bilan
    # ham to'liq DASH formatlarni beradi. MUHIM: avval "mweb" tanlangan edi,
    # lekin u ARXIVLANGAN JONLI EFIR (tugagan livestream) yozuvlarida taxminan
    # 32-38 MB'dan keyin har doim 403 qaytaradi (butunlay yangi URL/sessiya
    # bilan ham) — "web_embedded" esa xuddi shu formatni (~1 GB'dan ko'proq
    # tekshirildi) devorsiz beradi. "mweb" ikkinchi variant sifatida
    # qoldirilgan — ba'zi videolarda joylashtirish (embedding) o'chirilgan
    # bo'lsa, "web_embedded" butunlay ishlamay qoladi, "mweb" esa ishlaydi.
    opts["extractor_args"] = {"youtube": {"player_client": ["web_embedded", "mweb"]}}
    pot_base_url = POT_BASE_URL or pot_server.ensure_running()
    if pot_base_url:
        opts["extractor_args"]["youtubepot-bgutilhttp"] = {"base_url": [pot_base_url]}
    # Paketlangan (plug-and-play) versiyada ffmpeg va Node.js tizim PATH'ida
    # emas, dastur bilan birga keladi — shu holatda ularning aniq yo'lini
    # ko'rsatamiz. Manba koddan ishga tushirilganda (APP_RUNTIME_DIR yo'q)
    # ikkalasi ham None qaytadi va avvalgidek tizim PATH'iga tayaniladi.
    ffmpeg_dir = paths.bundled_ffmpeg_dir()
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir
    node_exe = paths.bundled_node_exe()
    if node_exe:
        opts["js_runtimes"] = {"node": {"path": node_exe}}
    tmp_cookie = None
    if _browser_cookies_usable():
        # Brauzerdan o'qilganda vaqtinchalik nusxa kerak emas — yt-dlp
        # brauzer bazasiga hech narsa yozmaydi, va cookie har safar yangi.
        opts["cookiesfrombrowser"] = _parse_cookies_from_browser(COOKIES_FROM_BROWSER)
    elif _cookies_file_usable():
        fd, tmp_cookie = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        shutil.copyfile(COOKIES_FILE, tmp_cookie)
        opts["cookiefile"] = tmp_cookie
    try:
        yield opts
    finally:
        if tmp_cookie:
            try:
                os.remove(tmp_cookie)
            except OSError:
                pass

# job_id -> progress/state dict, shared across threads
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()

# YouTube CDN yuklash o'rtasida ulanishni tez-tez uzadi. Odatda yt-dlp buni
# sezmasdan hal qiladi: uzilgan joydan `Range` so'rovi bilan davom etadi.
# Lekin ba'zan aynan o'sha "davom ettirish" so'roviga CDN 403 qaytaradi va
# yuklash butunlay to'xtaydi:
#
#     ERROR: unable to download video data: HTTP Error 403: Forbidden
#
# yt-dlp bunda o'zi qayta urinmaydi, chunki 403 — "qat'iy" HTTP xatosi (403
# odatda "ruxsat yo'q" degani, ya'ni qayta urinish befoyda).
#
# 2026-08-17 da o'lchanganlari (aqz-KE-bpKQ, ketma-ket o'nlab urinish):
#   * Xato TASODIFIY. Ayni bir video/format/sozlama bilan urinishlarning bir
#     qismi 100% tugadi, bir qismi 403 berdi.
#   * Sababi cookies.txt EMAS, format tanlovi (faqat video / video+audio)
#     EMAS, `http_chunk_size` (10M ham, 1M ham) ham EMAS — uchalasi ham
#     alohida sinaldi va farq bermadi.
#   * Xato ehtimoli fayl hajmiga qarab keskin oshadi: CDN ulanishni har
#     ~10 MB'da uzadi, va har bir "davom ettirish" 403 olish uchun yangi
#     imkoniyat. 360p/480p/audio muammosiz tugadi, 1080p60 (~245 MB) va
#     2160p60 (~1.3 GB) esa muntazam yiqildi.
#
# MUHIM: shunchaki qayta urinish YETARLI EMAS. Yarim yuklangan `.part` fayli
# joyida qolsa, yt-dlp o'sha joydan `Range` bilan davom ettirishga uringani
# uchun CDN yana o'sha 403'ni qaytaradi — o'lchovda 11 tadan 11 urinish shu
# tarzda yiqildi. Faqat noldan boshlangan yuklashning o'tish imkoniyati bor.
# Shuning uchun har bir qayta urinishdan oldin shu job'ning tugallanmagan
# `.part` fayllarini o'chiramiz. Tugagan oqimlar (masalan video tayyor bo'lib,
# audio yiqilgan bo'lsa) `.part`siz saqlanadi va qayta yuklanmaydi.
#
# Bu muammoni butunlay YO'QOTMAYDI — imkoniyatni oshiradi xolos. Har bir
# urinish noldan boshlanadi, shuning uchun urinishlar soni ataylab kichik:
# yiqilgan katta faylni 5 marta qayta tortish trafikni behuda sarflaydi.
DOWNLOAD_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2


def _discard_partials(job_id: str) -> None:
    """Shu job'ning tugallanmagan `.part` fayllarini o'chiradi, keyingi
    urinish noldan (va yangi URL bilan) boshlansin."""
    for name in os.listdir(DOWNLOADS_DIR):
        if name.startswith(job_id) and name.endswith(".part"):
            try:
                os.remove(os.path.join(DOWNLOADS_DIR, name))
            except OSError:
                pass

# Vaqtinchalik (qayta urinishga arziydigan) xatolar. "Video unavailable",
# "Private video" kabi doimiy sabablar bu ro'yxatga kirmaydi — ular darhol
# foydalanuvchiga qaytadi.
_TRANSIENT_ERROR_MARKERS = (
    "403", "forbidden", "unable to download video data",
    "connection", "timed out", "timeout", "incomplete",
)


def _is_transient(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_ERROR_MARKERS)


def _with_retries(job_id: str, action):
    """`action`ni bajaradi; vaqtinchalik tarmoq xatosida qayta uriniladi."""
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            return action()
        except Exception as e:
            if attempt == DOWNLOAD_ATTEMPTS or not _is_transient(e):
                raise
            _discard_partials(job_id)
            # Holatni "downloading"da qoldiramiz — frontend faqat ma'lum
            # holatlarni biladi va qayta urinish foydalanuvchi uchun oddiy
            # yuklashning davomi bo'lib ko'rinishi kerak.
            with jobs_lock:
                jobs.setdefault(job_id, {})["status"] = "downloading"
                jobs[job_id]["percent"] = 0
            time.sleep(RETRY_DELAY_SECONDS)

LANGUAGE_NAMES = {
    "en": "English", "en-US": "English (US)", "en-GB": "English (UK)",
    "es": "Spanish", "es-419": "Spanish (Latin America)", "es-ES": "Spanish (Spain)",
    "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
    "pt-BR": "Portuguese (Brazil)", "ru": "Russian", "ja": "Japanese",
    "ko": "Korean", "zh": "Chinese", "zh-Hans": "Chinese (Simplified)",
    "hi": "Hindi", "ar": "Arabic", "tr": "Turkish", "id": "Indonesian",
    "vi": "Vietnamese", "th": "Thai", "uz": "Uzbek", "ru-RU": "Russian",
    "uk": "Ukrainian", "pl": "Polish", "nl": "Dutch",
}


def _lang_label(code: str, is_original: bool) -> str:
    if code == "und":
        return "Original audio"
    name = LANGUAGE_NAMES.get(code, code)
    return f"{name} (original)" if is_original else f"{name} (dubbed)"


def _subtitle_label(code: str, auto: bool) -> str:
    name = LANGUAGE_NAMES.get(code, code)
    return f"{name} (avtomatik)" if auto else name


def _build_subtitles(info: dict) -> list[dict]:
    """Qo'lda yuklangan subtitrlar + avtomatik (ASR) subtitrlar ro'yxati.
    Avtomatik subtitrlar YouTube'da yuzlab tilga tarjima qilingan bo'lishi
    mumkin — ro'yxatni cheksiz shishirmaslik uchun faqat LANGUAGE_NAMES'da
    tanilgan (keng tarqalgan) tillarni ko'rsatamiz. Qo'lda yuklangan
    subtitrlar esa (muallif tomonidan qo'shilgan haqiqiy tarjimalar)
    kodidan qat'i nazar har doim ko'rsatiladi."""
    subs = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}

    result = [
        {"lang_code": code, "label": _subtitle_label(code, False), "auto": False}
        for code, tracks in subs.items() if tracks
    ]
    seen = {s["lang_code"] for s in result}
    for code, tracks in auto_subs.items():
        if not tracks or code in seen or code not in LANGUAGE_NAMES:
            continue
        result.append({"lang_code": code, "label": _subtitle_label(code, True), "auto": True})

    result.sort(key=lambda s: (s["auto"], s["label"]))
    return result


def _video_codec_rank(vcodec: str | None) -> int:
    # H.264 (avc1) mp4 konteynerida deyarli har qanday player/muharrirda
    # ochiladi; VP9/AV1 ko'proq joyda (ayniqsa eski video muharrirlarda)
    # muammo qiladi — shuning uchun bir xil balandlikda avc1'ga ustunlik
    # beramiz, u yo'q bo'lsagina VP9/AV1'ga tushamiz.
    vcodec = vcodec or ""
    if vcodec.startswith("avc1") or vcodec.startswith("h264"):
        return 0
    if vcodec.startswith("vp9") or vcodec.startswith("vp09"):
        return 1
    if vcodec.startswith("av01"):
        return 2
    return 3


def _audio_codec_rank(acodec: str | None) -> int:
    # AAC (mp4a) mp4 konteynerida Opus'dan ancha kengroq qo'llab-quvvatlanadi.
    acodec = acodec or ""
    return 0 if acodec.startswith("mp4a") else 1


def get_info(url: str) -> dict:
    with ydl_opts_ctx({"quiet": True, "no_warnings": True, "skip_download": True}) as opts:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

    formats = info.get("formats", [])

    # Video streams: prefer video-only (DASH) so "no audio" downloads are clean.
    video_only = [f for f in formats if f.get("vcodec") != "none" and f.get("acodec") == "none"]
    progressive = [f for f in formats if f.get("vcodec") != "none" and f.get("acodec") != "none"]
    video_candidates = video_only if video_only else progressive

    best_by_height: dict[int, dict] = {}
    for f in video_candidates:
        height = f.get("height") or 0
        if height == 0:
            continue
        current = best_by_height.get(height)
        if current is None:
            best_by_height[height] = f
            continue
        f_rank = _video_codec_rank(f.get("vcodec"))
        cur_rank = _video_codec_rank(current.get("vcodec"))
        if f_rank < cur_rank or (f_rank == cur_rank and (f.get("tbr") or 0) > (current.get("tbr") or 0)):
            best_by_height[height] = f

    resolutions = []
    for height, f in sorted(best_by_height.items(), key=lambda kv: kv[0], reverse=True):
        fps = f.get("fps") or 0
        label = f"{height}p" + (f"{int(fps)}" if fps and fps > 30 else "")
        resolutions.append({
            "format_id": f["format_id"],
            "label": label,
            "height": height,
            "width": f.get("width"),
            "fps": fps,
            "ext": f.get("ext"),
            "has_audio": f.get("acodec") != "none",
            "filesize": f.get("filesize") or f.get("filesize_approx"),
        })

    # Audio streams, grouped by language (includes YouTube auto-dubbed tracks).
    audio_only = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]
    max_pref = max((f.get("language_preference") or 0) for f in audio_only) if audio_only else 0

    single_track = len({f.get("language") or "und" for f in audio_only}) <= 1
    seen_langs: dict[str, dict] = {}
    for f in audio_only:
        code = f.get("language") or "und"
        pref = f.get("language_preference") or 0
        is_original = single_track or (max_pref > 0 and pref == max_pref)
        current = seen_langs.get(code)
        is_better = current is None
        if current is not None:
            f_rank = _audio_codec_rank(f.get("acodec"))
            cur_rank = _audio_codec_rank(current.get("_acodec"))
            is_better = f_rank < cur_rank or (f_rank == cur_rank and (f.get("abr") or 0) > (current.get("abr") or 0))
        if is_better:
            seen_langs[code] = {
                "format_id": f["format_id"],
                "lang_code": code,
                "label": _lang_label(code, is_original),
                "abr": f.get("abr"),
                "ext": f.get("ext"),
                "is_original": is_original,
                "_acodec": f.get("acodec"),
            }

    audio_tracks = [
        {k: v for k, v in track.items() if k != "_acodec"}
        for track in sorted(seen_langs.values(), key=lambda a: (not a["is_original"], a["label"]))
    ]

    return {
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "resolutions": resolutions,
        "audio_tracks": audio_tracks,
        "subtitles": _build_subtitles(info),
        "has_video_only_streams": bool(video_only),
    }


def _sanitize_filename(name: str, max_len: int = 150) -> str:
    name = _INVALID_FILENAME_CHARS.sub("", name).strip(" .")
    return name[:max_len] if name else "video"


def _unique_path(directory: str, base: str, ext: str) -> str:
    candidate = os.path.join(directory, f"{base}{ext}")
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{base} ({counter}){ext}")
        counter += 1
    return candidate


FFMPEG_RANGE_MARGIN = 3_000_000  # bayt — bitrate taxminidagi noaniqlik uchun zaxira (sidx topilmasa)
FFMPEG_RANGE_CHUNK = 8 * 1024 * 1024  # 8 MB — native so'rov o'lchami
SIDX_PROBE_SIZE = 5 * 1024 * 1024  # ftyp+moov+sidx odatda bundan ancha kichik


def _select_format(info: dict, format_id: str) -> dict:
    for f in info.get("formats", []):
        if f.get("format_id") == format_id:
            return f
    raise RuntimeError(f"Format topilmadi: {format_id}")


def _iter_top_boxes(data: bytes):
    """(box_type, header_boshi, tarkib_boshi, tarkib_oxiri) larni beradi —
    ISO-BMFF (MP4) faylining eng yuqori darajadagi box'lari bo'yicha."""
    pos, n = 0, len(data)
    while pos + 8 <= n:
        size = int.from_bytes(data[pos:pos + 4], "big")
        box_type = data[pos + 4:pos + 8]
        header_len = 8
        if size == 1:
            if pos + 16 > n:
                break
            size = int.from_bytes(data[pos + 8:pos + 16], "big")
            header_len = 16
        elif size == 0:
            size = n - pos
        if size < header_len or pos + size > n:
            break
        yield box_type, pos, pos + header_len, pos + size
        pos += size


def _parse_sidx(content: bytes) -> tuple[int, list[tuple[int, int]]] | None:
    """`sidx` (segment index) box tarkibidan (timescale, [(davomiylik, bayt
    hajmi), ...]) segmentlar ro'yxatini o'qiydi. Kutilmagan tuzilma (masalan
    ichma-ich sidx'ga ishora) uchraса — xavfsizlik uchun None qaytaradi."""
    if len(content) < 12:
        return None
    version = content[0]
    pos = 8  # version(1)+flags(3) + reference_ID(4)
    timescale = int.from_bytes(content[pos:pos + 4], "big"); pos += 4
    pos += 8 if version == 0 else 16  # earliest_presentation_time + first_offset
    pos += 2  # reserved
    if pos + 2 > len(content):
        return None
    ref_count = int.from_bytes(content[pos:pos + 2], "big"); pos += 2
    segments = []
    for _ in range(ref_count):
        if pos + 12 > len(content):
            return None
        chunk = int.from_bytes(content[pos:pos + 4], "big"); pos += 4
        if chunk >> 31:  # reference_type=1 -> ichma-ich sidx'ga ishora, qo'llab-quvvatlanmaydi
            return None
        referenced_size = chunk & 0x7FFFFFFF
        duration = int.from_bytes(content[pos:pos + 4], "big"); pos += 4
        pos += 4  # SAP ma'lumoti
        segments.append((duration, referenced_size))
    return timescale, segments


def _sidx_plan(ydl, fmt: dict, start_time: float, end_time: float | None) -> dict | None:
    """Format uchun `sidx` box asosida ANIQ bayt rejasini tuzadi — YouTube'ning
    fragmentlangan MP4 formatlarida (moov'dan keyin sidx bo'ladi) har bir
    segmentning bayt/vaqt joylashuvini bildiradi, shu orqali `start_time`ga ham
    to'g'ridan-to'g'ri "sakrash" mumkin bo'ladi (faqat `end_time`gacha emas).
    Muvaffaqiyatsiz bo'lsa (sidx topilmadi/tushunarsiz) None — chaqiruvchi
    xavfsiz "0-baytdan" usuliga tushishi kerak."""
    url = fmt["url"]
    headers = fmt.get("http_headers") or {}
    req = Request(url, headers={**headers, "Range": f"bytes=0-{SIDX_PROBE_SIZE - 1}"})
    probe = ydl.urlopen(req).read()

    moov_end = sidx_range = None
    for box_type, _start, cstart, cend in _iter_top_boxes(probe):
        if box_type == b"moov":
            moov_end = cend
        elif box_type == b"sidx":
            sidx_range = (cstart, cend)
        if moov_end is not None and sidx_range is not None:
            break
    if moov_end is None or sidx_range is None:
        return None

    parsed = _parse_sidx(probe[sidx_range[0]:sidx_range[1]])
    if not parsed:
        return None
    timescale, segments = parsed
    if not timescale or not segments:
        return None

    seg_start_byte = sidx_range[1]  # sidx tugagan joy — birinchi segment shu yerda boshlanadi
    cur_byte, cur_time = seg_start_byte, 0.0
    byte_start, byte_end = seg_start_byte, None
    for duration, size in segments:
        seg_time = duration / timescale
        if cur_time + seg_time <= start_time:
            byte_start = cur_byte + size
        cur_byte += size
        cur_time += seg_time
        if end_time is not None and byte_end is None and cur_time >= end_time:
            byte_end = cur_byte
    if end_time is not None and byte_end is None:
        byte_end = cur_byte

    return {"header": probe[:moov_end], "byte_start": byte_start, "byte_end": byte_end}


def _fetch_range(ydl, fmt: dict, byte_start: int, byte_end: int | None, out, on_bytes) -> None:
    """`byte_start`dan (`byte_end` berilmagan bo'lsa — fayl oxirigacha) `out`
    (ochiq fayl) ga yt-dlp'ning o'z (autentifikatsiyalangan) HTTP mijozi bilan,
    kichik Range so'rovlarida yozib oladi. Buni ffmpeg'ga topshirish (yt-dlp'ning
    odatiy `download_ranges` mexanizmi) YouTube CDN tomonidan qattiq
    sekinlashtiriladi — ffmpeg bitta uzluksiz so'rov yuboradi va CDN buni
    "throttle" qiladi (kuzatilgan: bir xil bayt oralig'i 113 soniya o'rniga
    0.17 soniyada tugadi). yt-dlp'ning oddiy to'liq yuklashi buni sezmaydi,
    chunki u ham kichik bo'laklarga bo'lib so'raydi — shu bo'lish naqshini
    shu yerda qo'lda takrorlaymiz."""
    url = fmt["url"]
    headers = fmt.get("http_headers") or {}
    pos = byte_start
    while byte_end is None or pos < byte_end:
        chunk_end = (min(pos + FFMPEG_RANGE_CHUNK, byte_end) - 1) if byte_end is not None \
            else (pos + FFMPEG_RANGE_CHUNK - 1)
        req = Request(url, headers={**headers, "Range": f"bytes={pos}-{chunk_end}"})
        data = ydl.urlopen(req).read()
        if not data:
            break
        out.write(data)
        pos += len(data)
        on_bytes(len(data))
        if byte_end is None and len(data) < FFMPEG_RANGE_CHUNK:
            break  # server so'ralgandan kamroq qaytardi — fayl shu yerda tugadi


def _run_ffmpeg(args: list[str]) -> None:
    ffmpeg_dir = paths.bundled_ffmpeg_dir()
    exe = os.path.join(ffmpeg_dir, "ffmpeg.exe") if ffmpeg_dir else "ffmpeg"
    result = subprocess.run([exe, *args], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg xatosi: {result.stderr.decode(errors='ignore')[-800:]}")


def _download_clip(job_id: str, url: str, video_format_id: str | None, audio_format_id: str | None,
                    audio_only: bool, start_time: float, end_time: float | None) -> str:
    """start_time/end_time berilganda ishlatiladi — yuqoridagi `_fetch_range`
    izohiga qarang. Har bir kerakli oqim uchun avval `sidx`-asosli ANIQ bayt
    rejasi sinaladi (topilsa — `start_time`ga ham to'g'ridan-to'g'ri "sakraladi",
    videoning istalgan joyidagi klip uchun bir xil tezlikda ishlaydi); topilmasa
    — 0-baytdan taxminiy oxirgi baytgacha (yoki to'liq) yuklashga tushiladi.
    Aniq kesish va birlashtirish MAHALLIY (tarmoqsiz, bir zumda) ffmpeg bilan
    bajariladi — katta `-analyzeduration`/`-probesize` va `-seek_timestamp 1`
    kerak, chunki bu fayllar odatiy to'liq indeksga ega emas (faqat kerakli
    segment saqlangan)."""
    with ydl_opts_ctx({"quiet": True, "no_warnings": True, "skip_download": True}) as opts:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration") or 0

            needed_ids = [fid for fid in (video_format_id, audio_format_id) if fid]
            plans: dict[str, dict] = {}
            total_expected = 0
            for fid in needed_ids:
                fmt = _select_format(info, fid)
                sidx = None
                if start_time > 1:  # boshlanish deyarli 0 bo'lsa, sidx qidirish foyda bermaydi
                    try:
                        sidx = _sidx_plan(ydl, fmt, start_time, end_time)
                    except Exception:
                        sidx = None
                if sidx:
                    span = (sidx["byte_end"] - sidx["byte_start"]) if sidx["byte_end"] is not None else None
                    plans[fid] = {"fmt": fmt, "mode": "sidx", **sidx}
                    total_expected += len(sidx["header"]) + (span or 0)
                else:
                    filesize = fmt.get("filesize") or fmt.get("filesize_approx")
                    if end_time is not None and duration and filesize and end_time < duration * 0.97:
                        byte_end = min(filesize, int(math.ceil(end_time / duration * filesize)) + FFMPEG_RANGE_MARGIN)
                    else:
                        byte_end = filesize  # None bo'lsa ham pastda to'liq yt-dlp yuklovchisiga tushadi
                    plans[fid] = {"fmt": fmt, "mode": "prefix", "byte_end": byte_end}
                    total_expected += byte_end or 0

            tmp_dir = tempfile.mkdtemp(prefix=f"{job_id}_clip_")
            bytes_so_far = 0

            def on_bytes(n: int) -> None:
                nonlocal bytes_so_far
                bytes_so_far += n
                pct = round(bytes_so_far / total_expected * 100, 1) if total_expected else 0
                with jobs_lock:
                    jobs[job_id]["status"] = "downloading"
                    jobs[job_id]["percent"] = min(pct, 99.0)

            try:
                fetched_paths: dict[str, str] = {}
                for fid, plan in plans.items():
                    fmt = plan["fmt"]
                    dest = os.path.join(tmp_dir, f"{fid}.{fmt.get('ext', 'bin')}")
                    if plan["mode"] == "sidx":
                        with open(dest, "wb") as out:
                            out.write(plan["header"])
                            on_bytes(len(plan["header"]))
                            _fetch_range(ydl, fmt, plan["byte_start"], plan["byte_end"], out, on_bytes)
                    elif plan["byte_end"] is None:
                        # Filesize noma'lum — yt-dlp'ning odatiy (throttle
                        # qilinmaydigan) to'liq yuklovchisiga tayanamiz.
                        single_opts = {"format": fid, "outtmpl": dest, "quiet": True, "no_warnings": True}
                        with ydl_opts_ctx(single_opts) as sopts, yt_dlp.YoutubeDL(sopts) as sydl:
                            sydl.download([url])
                    else:
                        with open(dest, "wb") as out:
                            _fetch_range(ydl, fmt, 0, plan["byte_end"], out, on_bytes)
                    fetched_paths[fid] = dest

                with jobs_lock:
                    jobs[job_id]["status"] = "merging"

                clip_duration = (end_time - start_time) if end_time is not None else None
                # Bu fayllar (ayniqsa "sidx" rejimida) to'liq/odatiy indeksga
                # ega emas — katta analyzeduration/probesize va PTS-asosli
                # (bayt taxminiga emas) seek majburlanmasa, ffmpeg noto'g'ri
                # joydan kesadi yoki bo'sh natija beradi.
                trim_args = [
                    "-analyzeduration", "200M", "-probesize", "200M", "-seek_timestamp", "1",
                    "-ss", str(start_time),
                ] + (["-t", str(clip_duration)] if clip_duration else [])
                out_ext = "mp3" if audio_only else "mp4"
                out_path = os.path.join(DOWNLOADS_DIR, f"{job_id}.{out_ext}")

                if audio_only:
                    args = [*trim_args, "-i", fetched_paths[audio_format_id],
                            "-codec:a", "libmp3lame", "-q:a", "2", "-y", out_path]
                elif video_format_id and audio_format_id:
                    args = [*trim_args, "-i", fetched_paths[video_format_id],
                            *trim_args, "-i", fetched_paths[audio_format_id],
                            "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
                            "-movflags", "+faststart", "-y", out_path]
                else:
                    src_id = video_format_id or audio_format_id
                    args = [*trim_args, "-i", fetched_paths[src_id],
                            "-c", "copy", "-movflags", "+faststart", "-y", out_path]

                _run_ffmpeg(args)
                return out_path
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)


def start_download(url: str, video_format_id: str | None, audio_format_id: str | None,
                    audio_only: bool, title: str | None = None,
                    start_time: float | None = None, end_time: float | None = None) -> str:
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"status": "queued", "percent": 0, "created_at": time.time()}

    def run():
        try:
            # Klipsiz (butun video) yuklashlar ham `_download_clip` orqali
            # o'tadi (start_time=0, end_time=None bilan) — yt-dlp'ning
            # o'z yuklovchisi EMAS. Sabab: yt-dlp'ning odatiy yuklovchisi
            # katta (~100+ MB) formatlarda uzilgan ulanishni "davom ettirish"
            # uchun Range so'rov yuboradi, va aynan shu so'rovga YouTube CDN
            # tasodifiy 403 qaytaradi (o'lchandi: 360p/480p muammosiz, 1080p60
            # va 2160p60 muntazam yiqiladi — quyidagi _TRANSIENT_ERROR_MARKERS
            # izohiga qarang). `_download_clip` filesize ma'lum bo'lgan har
            # bir formatni 8 MB'lik mustaqil (davom ettirilmaydigan) Range
            # so'rovlar bilan yuklaydi, shu bilan aynan shu 403 xavfini
            # kamaytiradi.
            final_path = _with_retries(job_id, lambda: _download_clip(
                job_id, url, video_format_id, audio_format_id, audio_only,
                start_time or 0, end_time,
            ))
            if title:
                ext = os.path.splitext(final_path)[1]
                desired_path = _unique_path(DOWNLOADS_DIR, _sanitize_filename(title), ext)
                os.replace(final_path, desired_path)
                final_path = desired_path
            with jobs_lock:
                jobs[job_id]["status"] = "finished"
                jobs[job_id]["percent"] = 100
                jobs[job_id]["file"] = final_path
        except Exception as e:
            with jobs_lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = str(e)

    threading.Thread(target=run, daemon=True).start()
    return job_id


def start_subtitle_download(url: str, lang_code: str, auto: bool, title: str | None = None) -> str:
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"status": "queued", "percent": 0, "created_at": time.time()}

    outtmpl = os.path.join(DOWNLOADS_DIR, f"{job_id}.%(ext)s")
    base_opts = {
        "outtmpl": outtmpl,
        "skip_download": True,
        "writesubtitles": not auto,
        "writeautomaticsub": auto,
        "subtitleslangs": [lang_code],
        "quiet": True,
        "no_warnings": True,
        # YouTube (va ko'pchilik saytlar) subtitrni vtt/ttml/json3 kabi
        # formatlarda beradi — srt'ga ffmpeg orqali aylantiramiz, chunki
        # u eng keng qo'llab-quvvatlanadigan format.
        "postprocessors": [{"key": "FFmpegSubtitlesConvertor", "format": "srt", "when": "before_dl"}],
    }

    def run():
        try:
            def download_once():
                with ydl_opts_ctx(base_opts) as opts, yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])

            _with_retries(job_id, download_once)
            raw_path = _find_output_file(job_id)
            if not raw_path:
                raise RuntimeError("Bu til uchun subtitr topilmadi")
            final_path = raw_path
            if title:
                ext = os.path.splitext(raw_path)[1]
                desired_path = _unique_path(DOWNLOADS_DIR, _sanitize_filename(title), ext)
                os.replace(raw_path, desired_path)
                final_path = desired_path
            with jobs_lock:
                jobs[job_id]["status"] = "finished"
                jobs[job_id]["percent"] = 100
                jobs[job_id]["file"] = final_path
        except Exception as e:
            with jobs_lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = str(e)

    threading.Thread(target=run, daemon=True).start()
    return job_id


def cleanup_job(job_id: str) -> None:
    with jobs_lock:
        job = jobs.pop(job_id, None)
    if job and job.get("file"):
        try:
            os.remove(job["file"])
        except OSError:
            pass


def _find_output_file(job_id: str) -> str | None:
    for name in os.listdir(DOWNLOADS_DIR):
        if name.startswith(job_id):
            return os.path.join(DOWNLOADS_DIR, name)
    return None


def get_progress(job_id: str) -> dict | None:
    with jobs_lock:
        return jobs.get(job_id)


# `cleanup_job` faqat mijoz `/api/file/{job_id}`ni SO'RASA chaqiriladi — agar
# job xato bilan tugasa, yoki mijoz sahifani yopib/qayta yuklab faylni hech
# qachon so'ramasa, `jobs` yozuvi (va tugagan bo'lsa — DOWNLOADS_DIR'dagi
# fayli) abadiy xotira/diskda qolib ketardi. Bu fon "tozalovchi" (reaper)
# shuni oldini oladi: yaratilganidan beri _JOB_TTL_SECONDS'dan ko'p vaqt
# o'tgan har qanday job (holatidan qat'i nazar) muntazam tozalanadi.
_JOB_TTL_SECONDS = 3 * 3600  # 3 soat


def _reap_stale_jobs() -> None:
    while True:
        time.sleep(600)
        now = time.time()
        with jobs_lock:
            stale_ids = [
                jid for jid, job in jobs.items()
                if now - job.get("created_at", now) > _JOB_TTL_SECONDS
            ]
        for jid in stale_ids:
            cleanup_job(jid)


threading.Thread(target=_reap_stale_jobs, daemon=True).start()
