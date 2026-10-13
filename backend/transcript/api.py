"""FastAPI marshrutlari — `backend/main.py`ga `include_router` orqali ulanadi."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import fetch
from . import find_source as find_source_module
from . import search as search_module

router = APIRouter(prefix="/api/transcript", tags=["transcript"])


class TranscriptSearchRequest(BaseModel):
    query: str
    channel_id: str | None = None
    max_videos: int | None = None
    # "YYYY-MM-DD", ikkalasi ham qamrovga kiradi. Format tekshiruvi
    # `search.search()` ichida (`date.fromisoformat`) bajariladi va
    # noto'g'ri bo'lsa `ValueError` -> pastdagi 400ga aylanadi.
    published_after: str | None = None
    published_before: str | None = None


@router.post("/search")
def api_transcript_search(req: TranscriptSearchRequest):
    """``{query, channel_id?, max_videos?, published_after?, published_before?}``
    qabul qiladi, moslik ro'yxatini JSON qilib qaytaradi (``search.search``ga
    qarang)."""
    max_videos = req.max_videos
    if max_videos is not None:
        date_ranged = bool(req.published_after or req.published_before)
        # Sana oralig'i berilganda ``max_videos`` "oraliqqa mos N video"
        # chegarasi (25/50 kabi kichik son juda faol kanalda oraliqning
        # atigi bir necha haftasini qamrab olardi — ``search.py``dagi
        # ``DEFAULT_DATE_RANGE_MAX_VIDEOS``ga qarang), shuning uchun bu
        # holatda ancha yuqoriroq chegara qo'yiladi.
        max_videos = max(1, min(max_videos, 500 if date_ranged else 50))

    try:
        data = search_module.search(
            req.query, channel_id=req.channel_id, max_videos=max_videos,
            published_after=req.published_after, published_before=req.published_before,
        )
    except fetch.ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Qidirishda xatolik: {e}")

    return {
        "query": req.query,
        "mode": "channel" if req.channel_id else "global",
        "count": len(data["results"]),
        "results": data["results"],
        # True bo'lsa, YouTube ba'zi videolarni tekshirishni bloklagan —
        # natija bo'sh/to'liqsiz bo'lishi so'z transkriptlarda umuman
        # yo'qligini emas, vaqtinchalik cheklovni bildirishi mumkin.
        "blocked": data["blocked"],
    }


class FindSourceRequest(BaseModel):
    clip_url: str
    channel_id: str | None = None


@router.post("/find-source")
def api_transcript_find_source(req: FindSourceRequest):
    """Klip (Shorts) havolasini qabul qiladi va uni qaysi INDEKSLANGAN
    streamdan olinganini, aniq vaqt belgisi bilan qaytaradi
    (``find_source.find_source``ga qarang).

    Qidirishdan oldin indeks AVTOMATIK yangilanadi (``search.catch_up``):
    aks holda kecha chiqqan streamdan olingan klip hech qachon topilmasdi
    va foydalanuvchi kanalni qo'lda qayta indexlashi kerak bo'lardi.
    Yangilash muvaffaqiyatsiz bo'lsa (API kaliti yo'q, YouTube bloklagan
    va h.k.) qidiruv baribir mavjud indeks ustida davom etadi — yangilash
    qulaylik, majburiy shart emas."""
    catch_up: dict = {"indexed": 0, "pending": 0, "blocked": False, "error": None}
    try:
        catch_up.update(search_module.catch_up(req.channel_id))
    except Exception as e:
        catch_up["error"] = str(e)

    try:
        data = find_source_module.find_source(req.clip_url, channel_id=req.channel_id)
    except fetch.TranscriptFetchBlocked as e:
        raise HTTPException(
            status_code=503,
            detail=f"Klip transkriptini olishda YouTube bloklandi, birozdan keyin urinib ko'ring: {e}",
        )
    except fetch.ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Manbani aniqlashda xatolik: {e}")

    return {**data, "catch_up": catch_up}
