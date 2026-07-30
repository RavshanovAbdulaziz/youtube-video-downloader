import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.middleware.cors import CORSMiddleware

import downloader
import separator

app = FastAPI(title="YouTube Downloader")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("PUBLIC_ORIGIN", "*")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Paketlangan (PyInstaller) qurilmada `frontend/` haqiqiy fayllar sifatida
# `sys._MEIPASS` ostida joylashadi — manba koddan ishga tushirilganda esa bu
# atribut mavjud emas va oddiy nisbiy yo'l ishlatiladi.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    FRONTEND_DIR = os.path.join(sys._MEIPASS, "frontend")
else:
    FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


class InfoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    video_format_id: str | None = None
    audio_format_id: str | None = None
    audio_only: bool = False
    title: str | None = None
    # Ikkalasi ham ixtiyoriy — berilsa, faqat shu oraliq (soniyalarda) yuklab
    # olinadi, butun video emas (downloader.start_download'ga qarang).
    start_time: float | None = None
    end_time: float | None = None


class SeparateRequest(BaseModel):
    url: str
    audio_format_id: str
    title: str | None = None
    engine: str = "demucs"
    start_time: float | None = None
    end_time: float | None = None


def _validate_clip_range(start_time: float | None, end_time: float | None) -> None:
    if start_time is not None and start_time < 0:
        raise HTTPException(status_code=400, detail="Boshlanish vaqti manfiy bo'lishi mumkin emas")
    if end_time is not None and end_time < 0:
        raise HTTPException(status_code=400, detail="Tugash vaqti manfiy bo'lishi mumkin emas")
    if start_time is not None and end_time is not None and end_time <= start_time:
        raise HTTPException(status_code=400, detail="Tugash vaqti boshlanish vaqtidan katta bo'lishi kerak")


class SubtitleRequest(BaseModel):
    url: str
    lang_code: str
    auto: bool = False
    title: str | None = None


@app.get("/api/health")
def api_health():
    return {"status": "ok"}


@app.post("/api/info")
def api_info(req: InfoRequest):
    try:
        return downloader.get_info(req.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Video ma'lumotlarini olishda xatolik: {e}")


@app.post("/api/download")
def api_download(req: DownloadRequest):
    if not req.audio_only and not req.video_format_id:
        raise HTTPException(status_code=400, detail="video_format_id kerak (audio_only=false bo'lsa)")
    _validate_clip_range(req.start_time, req.end_time)
    job_id = downloader.start_download(
        req.url, req.video_format_id, req.audio_format_id, req.audio_only, req.title,
        req.start_time, req.end_time,
    )
    return {"job_id": job_id}


@app.post("/api/download/subtitle")
def api_download_subtitle(req: SubtitleRequest):
    job_id = downloader.start_subtitle_download(req.url, req.lang_code, req.auto, req.title)
    return {"job_id": job_id}


@app.get("/api/progress/{job_id}")
def api_progress(job_id: str):
    progress = downloader.get_progress(job_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="job topilmadi")
    return progress


@app.get("/api/file/{job_id}")
def api_file(job_id: str):
    progress = downloader.get_progress(job_id)
    if not progress or progress.get("status") != "finished" or not progress.get("file"):
        raise HTTPException(status_code=400, detail="fayl hali tayyor emas")
    path = progress["file"]
    return FileResponse(
        path,
        filename=os.path.basename(path),
        background=BackgroundTask(downloader.cleanup_job, job_id),
    )


@app.post("/api/separate")
def api_separate(req: SeparateRequest):
    if req.engine not in separator.ENGINES:
        raise HTTPException(status_code=400, detail=f"Noma'lum dvigatel: {req.engine}")
    _validate_clip_range(req.start_time, req.end_time)
    job_id = separator.start_separation(
        req.url, req.audio_format_id, req.title, req.engine, req.start_time, req.end_time
    )
    return {"job_id": job_id}


@app.get("/api/separate/progress/{job_id}")
def api_separate_progress(job_id: str):
    progress = separator.get_progress(job_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="job topilmadi")
    return progress


@app.get("/api/separate/file/{job_id}/{which}")
def api_separate_file(job_id: str, which: str):
    if which not in ("speech", "background"):
        raise HTTPException(status_code=400, detail="which speech yoki background bo'lishi kerak")
    progress = separator.get_progress(job_id)
    if not progress or progress.get("status") != "finished":
        raise HTTPException(status_code=400, detail="fayl hali tayyor emas")
    key = "speech_file" if which == "speech" else "background_file"
    path = progress.get(key)
    if not path:
        raise HTTPException(status_code=404, detail="fayl allaqachon yuklab olingan")
    return FileResponse(
        path,
        filename=os.path.basename(path),
        background=BackgroundTask(separator.cleanup_file, job_id, which),
    )


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
