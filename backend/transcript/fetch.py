"""YouTube'dan video ro'yxati (Data API v3) va transkript matnini (yt-dlp)
olish.

Ikkita mustaqil manba ishlatiladi:
  - **Data API v3** (`google-api-python-client`) — kanal/video METADATA'si
    uchun (sarlavha, kanal nomi, video ro'yxati). Kunlik kvota: 10,000 unit.
    `search.list` boshqa chaqiruvlardan ~100x qimmat, shuning uchun faqat
    global (kanalsiz) qidiruv rejimida, bitta so'rovga bitta marta ishlatiladi.
  - **yt-dlp** (`downloader.ydl_opts_ctx` orqali, `downloader.py`dagi
    yuklash funksiyalari bilan BIR XIL PO token/mijoz sozlamalari) —
    subtitr/transkript matni uchun. Avval `youtube-transcript-api`
    ishlatilgan edi, lekin u xom HTTP so'rovlari yuboradi (PO token/session
    dalili yo'q) va YouTube tomonidan tez-tez `RequestBlocked` bilan
    bloklanib qolardi — hatto avval muvaffaqiyatli o'qilgan videolarda ham
    (2026-09-03, haqiqiy tekshiruvda takror reproduktsiya qilindi). yt-dlp
    esa xuddi shu jarayonni (tv_simply mijozi + bgutil PO token provideri)
    ishlatib, video yuklashda ishlagani kabi subtitr ro'yxatini ham
    ishonchli oladi — alohida infratuzilma qo'shilmadi, faqat mavjudi
    qayta ishlatildi.
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import date, datetime
from functools import lru_cache

import yt_dlp
from googleapiclient.discovery import build

import downloader

# Har bir Data API chaqiruvining taxminiy kvota narxi — kunlik 10,000 unit
# limitiga nisbatan rejalashtirish uchun (README/ .env.example'da ham eslatiladi).
QUOTA_COST = {"channels.list": 1, "playlistItems.list": 1, "search.list": 100}

# INGLIZ TILI BIRINCHI (2026-09-03 da o'zgartirildi, avval "uz" birinchi edi).
# Sabab: YouTube o'zbekcha subtitrni asl ASR ustidan AVTOMATIK TARJIMA qilib
# beradi — ya'ni ikki qavatli xatolik (ASR + mashina tarjimasi) va natija
# beqaror: bir xil audio uchun ham har xil so'zlar chiqadi. Bu, ayniqsa,
# `find_source.py` (klipni manba streamdan topish) uchun halokatli edi —
# klip va streamning tarjimalari mos kelmasdi. Asl inglizcha ASR esa barqaror
# va aniqroq, IShowSpeed kabi kanallar kontenti ham inglizcha.
DEFAULT_TRANSCRIPT_LANGUAGES = ["en", "uz"]

_CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")
_URL_REF_RE = re.compile(r"youtube\.com/(?:channel/|c/|user/|@)?([^/?&#]+)", re.I)


class ConfigError(RuntimeError):
    """YOUTUBE_API_KEY muhit o'zgaruvchisi o'rnatilmagan."""


class TranscriptFetchBlocked(RuntimeError):
    """Transkriptni olishga urinish YouTube tomonidan bloklandi (IP limiti,
    PO token talabi, tarmoq xatosi va h.k.) — bu VAQTINCHALIK holat va shu
    video haqida hech narsa demaydi (uni "subtitr yo'q" deb doimiy
    belgilash noto'g'ri bo'lardi — ``search.py``dagi chaqiruvchilar buni
    ushlab, o'sha videoni "tekshirilgan" deb belgilamasdan o'tkazib
    yuborishi, keyingi safar qayta urinishi kerak)."""


# Bular — video HAQIQATDA doimiy sabab bilan mavjud emasligini bildiruvchi,
# yt-dlp xato xabarlarida uchraydigan iboralar (kichik harflarda solishtiriladi).
# ATAYLAB tor ro'yxat: yosh cheklovi ("sign in to confirm your age") kabi
# holatlar bu yerga KIRITILMAGAN — cookie sozlansa keyinroq ochilishi mumkin,
# shuning uchun ular ham VAQTINCHALIK (`TranscriptFetchBlocked`) deb
# hisoblanadi. Ro'yxatga kirmagan HAR QANDAY boshqa xato (tarmoq, "sign in
# to confirm you're not a bot", PO token muammosi va h.k.) ham shu tarzda
# vaqtinchalik deb qayta ko'tariladi — noto'g'ri "doimiy" deb belgilash
# xavfliroq (video abadiy "tekshirilgan, subtitri yo'q" bo'lib qolardi).
_PERMANENT_ERROR_MARKERS = (
    "video unavailable",
    "private video",
    "this video has been removed",
    "video is no longer available",
    "account associated with this video has been terminated",
    "this video is not available",
    "content isn't available",
    # Hali boshlanmagan/rejalashtirilgan jonli efir — HOZIRCHA transkript
    # uchun hech qanday kontent yo'q (real IShowSpeed kanaliga qarshi
    # tekshiruvda topildi: kanal ro'yxatida "12 soatdan keyin boshlanadi"
    # kabi efir bo'lsa). Bu marker bo'lmasa, shu bitta video butun kanalni
    # "blocked" deb belgilab, `mark_channel_indexed` hech qachon
    # chaqirilmasdi — efir tugab, subtitr paydo bo'lgandan keyin ham force
    # reindex qilinmaguncha qayta tekshirilmasdi.
    "this live event will begin",
    "premieres in",
)


def _is_permanently_unavailable(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _PERMANENT_ERROR_MARKERS)


_BACKEND_ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


def _read_backend_env_fallback(key: str, env_path: str) -> str:
    """``backend/.env`` hech qachon avtomatik process env'ga yuklanmaydi —
    loyihada bunday umumiy mexanizm yo'q (``start_bot.bat`` buni o'zi,
    batch darajasida, faqat BOT_TOKEN uchun qiladi; web UI/tray ishga
    tushirgichlari esa umuman o'qimaydi). Shu sababli ``main:app`` odatiy
    tray/`start_dev.bat` orqali ishga tushirilganda ``YOUTUBE_API_KEY``
    ``os.environ``da yo'q bo'lib qoladi — shuning uchun faqat shu bitta
    kalit uchun, zaxira sifatida, faylni to'g'ridan-to'g'ri o'qiymiz.
    Boshqa hech qanday modulning env o'qish tartibiga ta'sir qilmaydi."""
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


@lru_cache(maxsize=1)
def _client():
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip() or _read_backend_env_fallback("YOUTUBE_API_KEY", _BACKEND_ENV_FILE)
    if not api_key:
        raise ConfigError(
            "YOUTUBE_API_KEY o'rnatilmagan (backend/.env). Namuna uchun "
            ".env.example'ga qarang."
        )
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def _parse_channel_ref(ref: str) -> tuple[str, str]:
    """Kanal identifikatorini turlicha kiritilgan shakllardan ajratib oladi.

    Qabul qilinadi: xom ``channel_id`` (``UCxxxxxxxxxxxxxxxxxxxxxx``),
    ``@handle``, handle nomi (``@``siz), yoki to'liq kanal URL'i
    (``/@handle``, ``/channel/UC...``, ``/c/nom``, ``/user/nom``).

    Qaytaradi: ``(kind, value)`` — ``kind`` ``"id" | "handle" | "username"``.
    """
    ref = ref.strip()
    m = _URL_REF_RE.search(ref)
    value = m.group(1) if m else ref

    if "/user/" in ref:
        return "username", value
    if "/c/" in ref:
        return "handle", value
    if value.startswith("@") or "/@" in ref:
        return "handle", value.lstrip("@")
    if _CHANNEL_ID_RE.match(value):
        return "id", value
    return "handle", value.lstrip("@")


def resolve_channel(channel_ref: str) -> dict:
    """Kanal ma'ntiqiy identifikatorini (ID/handle/URL) to'liq ma'lumotga
    aylantiradi.

    Qaytaradi: ``{"channel_id", "title", "uploads_playlist_id"}``.

    Har doim ``channels.list`` (1 unit) bilan boshlanadi; faqat u bo'sh
    natija bersa (masalan eskirgan ``/c/nom`` qisqa havolasi haqiqiy
    username emas) ``search.list``ga (100 unit) tushadi — shuning uchun
    chaqiruvchi tomonidan xom ``channel_id`` yoki ``@handle`` berish
    tavsiya etiladi, kvota jihatidan eng arzoni shu.
    """
    kind, value = _parse_channel_ref(channel_ref)
    if not value:
        raise ValueError(f"Kanal aniqlanmadi: {channel_ref!r}")

    client = _client()
    params = {"part": "snippet,contentDetails"}
    if kind == "id":
        params["id"] = value
    elif kind == "handle":
        params["forHandle"] = value if value.startswith("@") else f"@{value}"
    else:
        params["forUsername"] = value

    items = client.channels().list(**params).execute().get("items", [])

    if not items and kind != "id":
        search_res = (
            client.search()
            .list(part="snippet", type="channel", q=value, maxResults=1)
            .execute()
            .get("items", [])
        )
        if not search_res:
            raise ValueError(f"Kanal topilmadi: {channel_ref}")
        found_id = search_res[0]["snippet"]["channelId"]
        items = (
            client.channels()
            .list(part="snippet,contentDetails", id=found_id)
            .execute()
            .get("items", [])
        )

    if not items:
        raise ValueError(f"Kanal topilmadi: {channel_ref}")

    item = items[0]
    return {
        "channel_id": item["id"],
        # Data API sarlavha/kanal nomlarini HTML-entity qilib qaytaradi
        # (masalan "Guetta &amp; Bebe Rexha") — shu yerda hamma joyda
        # unescape qilinadi, aks holda frontendda xom "&amp;" ko'rinadi.
        "title": html.unescape(item["snippet"]["title"]),
        "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def _parse_video_published_date(item: dict) -> date | None:
    """``playlistItems.list`` elementidan videoning haqiqiy e'lon qilingan
    sanasini oladi. ``contentDetails.videoPublishedAt`` afzal — bu VIDEO
    o'zi ommaga ochilgan payt (masalan premyera/rejalashtirilgan chiqarilish
    holatlarida ``snippet.publishedAt``, ya'ni playlist'ga QO'SHILGAN payt,
    bundan farq qilishi mumkin). Ikkalasi ham yo'q bo'lsa ``None``."""
    raw = item.get("contentDetails", {}).get("videoPublishedAt") or item["snippet"].get("publishedAt")
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()


def list_channel_videos(
    uploads_playlist_id: str,
    max_results: int | None = None,
    published_after: str | None = None,
    published_before: str | None = None,
) -> list[dict]:
    """Kanal yuklagan videolar ro'yxati (eng yangisidan) —
    ``[{video_id, title, published_at}, ...]`` (``published_at`` —
    ``"YYYY-MM-DD"`` yoki topilmasa ``None``).

    ``playlistItems.list`` sahifalab (50 tadan) chaqiriladi. ``max_results``
    berilmasa, butun kanal oxirigacha (minglab video bo'lishi mumkin)
    o'qiladi — katta kanallarda albatta chegara bering.

    ``published_after``/``published_before`` (``"YYYY-MM-DD"``) berilsa,
    faqat shu oraliqda e'lon qilingan videolar qaytadi va ``max_results``
    KO'RIB CHIQILGAN emas, MOS KELGAN videolar soniga chegara bo'ladi —
    kerakli oraliqqa yetish uchun ko'proq sahifa ko'rib chiqilishi mumkin.
    "Uploads" playlist'i har doim eng yangi-birinchi tartibda bo'lgani
    uchun, ``published_after``dan eskiroq videoga yetilganda sahifalash
    DARHOL to'xtatiladi (qolgan hammasi undan ham eskiroq bo'ladi — qidirib
    o'tirishning hojati yo'q, kvota tejaladi)."""
    after_date = date.fromisoformat(published_after) if published_after else None
    before_date = date.fromisoformat(published_before) if published_before else None
    date_ranged = after_date is not None or before_date is not None

    client = _client()
    videos: list[dict] = []
    page_token = None
    while True:
        remaining = None if max_results is None else max_results - len(videos)
        if remaining is not None and remaining <= 0:
            break
        # Sana oralig'i berilganda sahifa hajmini KAM QILMAYMIZ: ko'rib
        # chiqilgan elementlarning hammasi mos kelmasligi mumkin (masalan
        # oraliqqa hali yetilmagan), shuning uchun `remaining`ga qarab
        # kichraytirish noto'g'ri bo'lardi.
        page_size = 50 if (date_ranged or remaining is None) else min(50, remaining)
        res = (
            client.playlistItems()
            .list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=page_size,
                pageToken=page_token,
            )
            .execute()
        )
        items = res.get("items", [])
        if not items:
            break

        reached_older_than_range = False
        for item in items:
            snippet = item["snippet"]
            resource = snippet.get("resourceId", {})
            if resource.get("kind") != "youtube#video":
                continue

            video_date = _parse_video_published_date(item)
            if after_date is not None and video_date is not None and video_date < after_date:
                # Bu va undan keyingi HAMMA video (playlist eng yangi-birinchi
                # tartibda) so'ralgan oraliqdan eskiroq — sahifalashni butunlay
                # to'xtatamiz.
                reached_older_than_range = True
                break
            if before_date is not None and video_date is not None and video_date > before_date:
                # Hali oraliqqa yetilmagan (juda yangi) — o'tkazib yuboramiz,
                # lekin sahifalashni davom ettiramiz (eskiroqlari hali oldinda).
                continue

            videos.append({
                "video_id": resource["videoId"],
                "title": html.unescape(snippet.get("title", "")),
                "published_at": video_date.isoformat() if video_date else None,
            })
            if max_results is not None and len(videos) >= max_results:
                break

        if reached_older_than_range or (max_results is not None and len(videos) >= max_results):
            break
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return videos


def search_videos(
    query: str,
    max_results: int = 25,
    published_after: str | None = None,
    published_before: str | None = None,
) -> list[dict]:
    """Butun YouTube bo'yicha kalit so'z asosida nomzod videolarni topadi.

    ``search.list`` — 100 unit/chaqiruv, shuning uchun bitta qidiruv bitta
    chaqiruv bilan cheklanadi (sahifalanmaydi), natija ko'pi bilan 50 ta.

    ``published_after``/``published_before`` (``"YYYY-MM-DD"``) berilsa,
    to'g'ridan-to'g'ri ``search.list``ning shu nomdagi (RFC 3339) parametrlariga
    o'tkaziladi — Data API o'zi filtrlaydi, qo'shimcha so'rov shart emas.
    """
    client = _client()
    params = {"part": "snippet", "type": "video", "q": query, "maxResults": min(max(max_results, 1), 50)}
    if published_after:
        params["publishedAfter"] = f"{published_after}T00:00:00Z"
    if published_before:
        params["publishedBefore"] = f"{published_before}T23:59:59Z"
    res = client.search().list(**params).execute()
    videos = []
    for item in res.get("items", []):
        snippet = item["snippet"]
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        videos.append({
            "video_id": video_id,
            "title": html.unescape(snippet.get("title", "")),
            "channel_id": snippet.get("channelId", ""),
            "channel_name": html.unescape(snippet.get("channelTitle", "")),
        })
    return videos


def _pick_caption_track(info: dict, languages: list[str]) -> list[dict] | None:
    """``languages`` ro'yxatidagi BIRINCHI mos keluvchi subtitr formatlar
    ro'yxatini qaytaradi — har bir til uchun qo'lda yozilgan subtitr
    (``subtitles``) avtomatikdan (``automatic_captions``) afzal ko'riladi,
    chunki odatda aniqroq. Hech biri topilmasa ``None``."""
    subtitles = info.get("subtitles") or {}
    auto_captions = info.get("automatic_captions") or {}
    for lang in languages:
        if lang in subtitles:
            return subtitles[lang]
        if lang in auto_captions:
            return auto_captions[lang]
    return None


def _parse_json3(raw: bytes) -> list[dict]:
    """YouTube'ning ``json3`` subtitr formatini (``{"events": [...]}``)
    ``youtube-transcript-api``ning xom natijasi bilan bir xil shaklga
    (``{text, start, duration}``, soniyalarda) keltiradi — ``search.py``
    boshqa hech narsani bilishi shart emas."""
    events = json.loads(raw).get("events", [])
    segments = []
    for event in events:
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs)
        if not text.strip():
            continue
        segments.append({
            "text": text,
            "start": event.get("tStartMs", 0) / 1000.0,
            "duration": event.get("dDurationMs", 0) / 1000.0,
        })
    return segments


def fetch_transcript(video_id: str, languages: list[str] | None = None) -> list[dict] | None:
    """Bitta videoning transkriptini qaytaradi: ``[{text, start, duration}, ...]``.

    ``downloader.ydl_opts_ctx`` orqali yt-dlp bilan olinadi (video
    yuklashda ishlatilgan bilan bir xil PO token/mijoz sozlamalari) —
    ``json3`` formatidagi subtitr URL'i o'qilib, qatorlarga bo'linadi.

    Ikki xil muvaffaqiyatsizlik farqlanadi (aralashtirib yuborilsa, IP
    bloklanganda butun kanal "subtitri yo'q" deb DOIMIY belgilanib qolardi
    — bu haqiqatda sodir bo'lgan edi, jonli IShowSpeed tekshiruvida topildi):

      - Videoning O'ZIDA transkript yo'q (talab qilingan tillarda subtitr
        yo'q, video mavjud emas/o'chirilgan) — doimiy holat, ``None``
        qaytaradi.
      - YouTube so'rovni bloklagan (IP limiti, PO token va h.k.) — bu video
        haqida hech narsa demaydi, ``TranscriptFetchBlocked`` ko'taradi.

    Boshqa hech qachon exception ko'tarmaydi (kutilmagan xatolar ham
    ``TranscriptFetchBlocked``ga o'raladi) — chaqiruvchi (``search.py``) buni
    ko'plab videolar ustidan loop ichida chaqiradi, bitta video muammosi
    butun qidiruvni to'xtatib qo'ymasligi kerak.
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with downloader.ydl_opts_ctx({"quiet": True, "no_warnings": True, "skip_download": True}) as opts:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                track = _pick_caption_track(info, languages or DEFAULT_TRANSCRIPT_LANGUAGES)
                if track is None:
                    return None
                fmt = next((f for f in track if f.get("ext") == "json3"), None)
                if fmt is None:
                    return None
                raw = ydl.urlopen(fmt["url"]).read()
    except Exception as e:
        if _is_permanently_unavailable(e):
            return None
        raise TranscriptFetchBlocked(str(e)) from e
    return _parse_json3(raw)
