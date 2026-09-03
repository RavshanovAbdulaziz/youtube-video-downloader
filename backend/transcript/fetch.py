"""YouTube'dan video ro'yxati (Data API v3) va transkript matnini
(`youtube-transcript-api`) olish.

Ikkita mustaqil manba ishlatiladi:
  - **Data API v3** (`google-api-python-client`) — kanal/video METADATA'si
    uchun (sarlavha, kanal nomi, video ro'yxati). Kunlik kvota: 10,000 unit.
    `search.list` boshqa chaqiruvlardan ~100x qimmat, shuning uchun faqat
    global (kanalsiz) qidiruv rejimida, bitta so'rovga bitta marta ishlatiladi.
  - **youtube-transcript-api** — subtitr/transkript matni uchun (Data API bu
    ma'lumotni umuman bermaydi). Rasmiy kvotaga bog'liq emas, lekin YouTube
    tomonidan IP darajasida cheklanishi mumkin (`IpBlocked`/`RequestBlocked`).
"""
from __future__ import annotations

import html
import os
import re
from functools import lru_cache

from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    AgeRestricted,
    InvalidVideoId,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
)

# Har bir Data API chaqiruvining taxminiy kvota narxi — kunlik 10,000 unit
# limitiga nisbatan rejalashtirish uchun (README/ .env.example'da ham eslatiladi).
QUOTA_COST = {"channels.list": 1, "playlistItems.list": 1, "search.list": 100}

DEFAULT_TRANSCRIPT_LANGUAGES = ["uz", "en"]

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


# Bular — VIDEONING O'ZIGA xos, doimiy holatlar (subtitr yo'q/o'chirilgan/
# video mavjud emas): `None` qaytariladi, video "tekshirilgan" deb
# belgilanishi xavfsiz. Boshqa har qanday xato (IpBlocked, RequestBlocked,
# PoTokenRequired, tarmoq xatosi va h.k.) — VAQTINCHALIK, `TranscriptFetchBlocked`
# sifatida qayta ko'tariladi.
_PERMANENTLY_UNAVAILABLE = (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable, VideoUnplayable, AgeRestricted, InvalidVideoId)


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


def list_channel_videos(uploads_playlist_id: str, max_results: int | None = None) -> list[dict]:
    """Kanal yuklagan videolar ro'yxati (eng yangisidan) — ``[{video_id, title}]``.

    ``playlistItems.list`` sahifalab (50 tadan) chaqiriladi. ``max_results``
    berilmasa, butun kanal oxirigacha (minglab video bo'lishi mumkin)
    o'qiladi — katta kanallarda albatta chegara bering.
    """
    client = _client()
    videos: list[dict] = []
    page_token = None
    while True:
        remaining = None if max_results is None else max_results - len(videos)
        if remaining is not None and remaining <= 0:
            break
        page_size = 50 if remaining is None else min(50, remaining)
        res = (
            client.playlistItems()
            .list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=page_size,
                pageToken=page_token,
            )
            .execute()
        )
        for item in res.get("items", []):
            snippet = item["snippet"]
            resource = snippet.get("resourceId", {})
            if resource.get("kind") != "youtube#video":
                continue
            videos.append({"video_id": resource["videoId"], "title": html.unescape(snippet.get("title", ""))})

        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return videos


def search_videos(query: str, max_results: int = 25) -> list[dict]:
    """Butun YouTube bo'yicha kalit so'z asosida nomzod videolarni topadi.

    ``search.list`` — 100 unit/chaqiruv, shuning uchun bitta qidiruv bitta
    chaqiruv bilan cheklanadi (sahifalanmaydi), natija ko'pi bilan 50 ta.
    """
    client = _client()
    res = (
        client.search()
        .list(part="snippet", type="video", q=query, maxResults=min(max(max_results, 1), 50))
        .execute()
    )
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


def fetch_transcript(video_id: str, languages: list[str] | None = None) -> list[dict] | None:
    """Bitta videoning transkriptini qaytaradi: ``[{text, start, duration}, ...]``.

    Ikki xil muvaffaqiyatsizlik farqlanadi (aralashtirib yuborilsa, IP
    bloklanganda butun kanal "subtitri yo'q" deb DOIMIY belgilanib qolardi
    — bu haqiqatda sodir bo'lgan edi, jonli IShowSpeed tekshiruvida topildi):

      - Videoning O'ZIDA transkript yo'q (subtitr o'chirilgan/topilmadi/
        video mavjud emas) — doimiy holat, ``None`` qaytaradi.
      - YouTube so'rovni bloklagan (IP limiti, PO token va h.k.) — bu video
        haqida hech narsa demaydi, ``TranscriptFetchBlocked`` ko'taradi.

    Boshqa hech qachon exception ko'tarmaydi (kutilmagan xatolar ham
    ``TranscriptFetchBlocked``ga o'raladi) — chaqiruvchi (``search.py``) buni
    ko'plab videolar ustidan loop ichida chaqiradi, bitta video muammosi
    butun qidiruvni to'xtatib qo'ymasligi kerak.
    """
    try:
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=languages or DEFAULT_TRANSCRIPT_LANGUAGES)
        return transcript.to_raw_data()
    except _PERMANENTLY_UNAVAILABLE:
        return None
    except Exception as e:
        raise TranscriptFetchBlocked(str(e)) from e
