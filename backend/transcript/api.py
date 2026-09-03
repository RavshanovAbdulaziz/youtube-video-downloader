"""FastAPI marshrutlari — `backend/main.py`ga `include_router` orqali ulanadi."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import fetch
from . import search as search_module

router = APIRouter(prefix="/api/transcript", tags=["transcript"])


class TranscriptSearchRequest(BaseModel):
    query: str
    channel_id: str | None = None
    max_videos: int | None = None


@router.post("/search")
def api_transcript_search(req: TranscriptSearchRequest):
    """``{query, channel_id?, max_videos?}`` qabul qiladi, moslik
    ro'yxatini JSON qilib qaytaradi (``search.search``ga qarang)."""
    max_videos = req.max_videos
    if max_videos is not None:
        max_videos = max(1, min(max_videos, 50))

    try:
        results = search_module.search(req.query, channel_id=req.channel_id, max_videos=max_videos)
    except fetch.ConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Qidirishda xatolik: {e}")

    return {
        "query": req.query,
        "mode": "channel" if req.channel_id else "global",
        "count": len(results),
        "results": results,
    }
