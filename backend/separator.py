import glob
import os
import re
import shutil
import subprocess
import threading
import time
import uuid

import yt_dlp
from yt_dlp.utils import download_range_func

import ai_setup
import paths
from downloader import DOWNLOADS_DIR, _is_transient, _sanitize_filename, _unique_path, ydl_opts_ctx

SEPARATE_TMP_DIR = paths.SEPARATE_TMP_DIR

# numba standart holatda keshni site-packages ichiga yozadi — admin bo'lmagan
# jarayon u yerga yoza olmay, tempfile abadiy qayta urinish tsikliga tushib qoladi.
NUMBA_CACHE_DIR = paths.NUMBA_CACHE_DIR

UVR_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
_PERCENT_RE = re.compile(r"(\d{1,3})%\|")

jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def _set_percent(job_id: str, percent: int) -> None:
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["percent"] = percent


def _set_ai_progress(job_id: str, stage: str, percent: int) -> None:
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["ai_stage"] = stage
            jobs[job_id]["percent"] = percent


def _subprocess_env() -> dict:
    env = {**os.environ, "NUMBA_CACHE_DIR": NUMBA_CACHE_DIR, "PYTHONUNBUFFERED": "1"}
    # demucs/audio-separator shell out to ffmpeg themselves (no equivalent of
    # yt-dlp's ffmpeg_location option) — in a packaged build there's no
    # system-wide ffmpeg, so we prepend the bundled copy's folder to this
    # subprocess's PATH only (doesn't touch the real system PATH).
    ffmpeg_dir = paths.bundled_ffmpeg_dir()
    if ffmpeg_dir:
        env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")
    return env


def _run_with_progress(cmd: list[str], job_id: str) -> None:
    """Run a subprocess, parsing tqdm-style 'NN%|' output to report live progress."""
    env = _subprocess_env()
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        env=env,
    )
    tail_chars: list[str] = []
    buf = ""
    while True:
        ch = process.stdout.read(1)
        if ch == "" and process.poll() is not None:
            break
        if not ch:
            continue
        tail_chars.append(ch)
        if len(tail_chars) > 4000:
            del tail_chars[:2000]
        if ch in ("\r", "\n"):
            match = _PERCENT_RE.search(buf)
            if match:
                _set_percent(job_id, int(match.group(1)))
            buf = ""
        else:
            buf += ch

    returncode = process.wait()
    if returncode != 0:
        raise RuntimeError("".join(tail_chars)[-2000:] or f"process exited with code {returncode}")


def _script_exe(name: str) -> str:
    """AI kutubxonalari bilan birga o'rnatilgan konsol skript (masalan
    demucs.exe) yo'li. PATH'ga tayanmaydi — paketlangan runtime'da bu papka
    tizim PATH'ida bo'lmasligi mumkin."""
    return os.path.join(paths.runtime_scripts_dir(), f"{name}.exe")


def _run_demucs(source_file: str, work_dir: str, job_id: str) -> tuple[str, str]:
    _run_with_progress(
        [_script_exe("demucs"), "--two-stems", "vocals", "--mp3", "-n", "htdemucs",
         "-d", ai_setup.current_device(), "-o", work_dir, source_file],
        job_id,
    )
    stem_name = os.path.splitext(os.path.basename(source_file))[0]
    stem_dir = os.path.join(work_dir, "htdemucs", stem_name)
    return os.path.join(stem_dir, "vocals.mp3"), os.path.join(stem_dir, "no_vocals.mp3")


def _run_uvr(source_file: str, work_dir: str, job_id: str) -> tuple[str, str]:
    _run_with_progress(
        [_script_exe("audio-separator"), source_file, "--model_filename", UVR_MODEL,
         "--output_dir", work_dir, "--output_format", "mp3"],
        job_id,
    )
    vocals_matches = glob.glob(os.path.join(work_dir, "*(Vocals)*.mp3"))
    instrumental_matches = glob.glob(os.path.join(work_dir, "*(Instrumental)*.mp3"))
    if not vocals_matches or not instrumental_matches:
        raise RuntimeError("audio-separator natija fayllarini topa olmadi")
    return vocals_matches[0], instrumental_matches[0]


ENGINES = {
    "demucs": _run_demucs,
    "uvr": _run_uvr,
}


def _download_progress_hook(job_id: str):
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes") or 0
            if total:
                _set_percent(job_id, round(downloaded / total * 100))
    return hook


_DOWNLOAD_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 2


def _discard_source_files(work_dir: str) -> None:
    for f in os.listdir(work_dir):
        if f.startswith("source."):
            try:
                os.remove(os.path.join(work_dir, f))
            except OSError:
                pass


def _download_source(job_id: str, url: str, base_opts: dict, work_dir: str) -> None:
    """downloader.py'dagi CDN 403 muammosiga (o'sha fayldagi izohga qarang)
    audio-only yuklashda ham duch kelinadi — bu yerda ham xuddi shu
    "vaqtinchalik xatoda noldan qayta urinish" strategiyasi qo'llanadi."""
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            with ydl_opts_ctx(base_opts) as opts, yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            return
        except Exception as e:
            if attempt == _DOWNLOAD_ATTEMPTS or not _is_transient(e):
                raise
            _discard_source_files(work_dir)
            with jobs_lock:
                jobs[job_id]["status"] = "downloading"
                jobs[job_id]["percent"] = 0
            time.sleep(_RETRY_DELAY_SECONDS)


def start_separation(url: str, audio_format_id: str, title: str | None = None,
                      engine: str = "demucs",
                      start_time: float | None = None, end_time: float | None = None) -> str:
    if engine not in ENGINES:
        raise ValueError(f"Noma'lum dvigatel: {engine}")

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"status": "queued", "percent": 0, "created_at": time.time()}

    def run():
        work_dir = os.path.join(SEPARATE_TMP_DIR, job_id)
        os.makedirs(work_dir, exist_ok=True)
        try:
            if not ai_setup.is_ai_installed():
                # Bir martalik, birinchi ishlatishda: AI kutubxonalari (torch/
                # demucs/audio-separator) fonda avtomatik o'rnatiladi. Foydalanuvchi
                # hech qanday buyruq yozmaydi — progress shu jobning o'zida
                # ko'rsatiladi (installing_ai -> downloading -> separating).
                with jobs_lock:
                    jobs[job_id].update(status="installing_ai", percent=0, ai_stage="torch")
                ai_setup.ensure_installed(lambda stage, pct: _set_ai_progress(job_id, stage, pct))

            with jobs_lock:
                jobs[job_id].update(status="downloading", percent=0)

            base_opts = {
                "format": audio_format_id,
                "outtmpl": os.path.join(work_dir, "source.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [_download_progress_hook(job_id)],
            }
            if start_time is not None or end_time is not None:
                # downloader.start_download'dagi izohga qarang: butun audioni
                # yuklab olmasdan, faqat tanlangan oraliqni manba serveridan
                # o'qiydi (tezroq, va AI ajratish ham kamroq vaqt oladi).
                base_opts["download_ranges"] = download_range_func(
                    None, [(start_time or 0, end_time if end_time is not None else float("inf"))]
                )
            _download_source(job_id, url, base_opts, work_dir)

            source_file = next(
                (os.path.join(work_dir, f) for f in os.listdir(work_dir) if f.startswith("source.")),
                None,
            )
            if not source_file:
                raise RuntimeError("Audio yuklab olinmadi (source fayl topilmadi)")

            with jobs_lock:
                jobs[job_id]["status"] = "separating"
                jobs[job_id]["percent"] = 0

            vocals_src, background_src = ENGINES[engine](source_file, work_dir, job_id)

            base_name = _sanitize_filename(title) if title else job_id
            speech_path = _unique_path(DOWNLOADS_DIR, f"{base_name} - Speech", ".mp3")
            background_path = _unique_path(DOWNLOADS_DIR, f"{base_name} - Background", ".mp3")
            shutil.move(vocals_src, speech_path)
            shutil.move(background_src, background_path)

            with jobs_lock:
                jobs[job_id]["status"] = "finished"
                jobs[job_id]["percent"] = 100
                jobs[job_id]["speech_file"] = speech_path
                jobs[job_id]["background_file"] = background_path
        except Exception as e:
            with jobs_lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = str(e)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    threading.Thread(target=run, daemon=True).start()
    return job_id


def get_progress(job_id: str) -> dict | None:
    with jobs_lock:
        return jobs.get(job_id)


def cleanup_file(job_id: str, which: str) -> None:
    key = "speech_file" if which == "speech" else "background_file"
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        path = job.get(key)
        job[key] = None
        if not job.get("speech_file") and not job.get("background_file"):
            jobs.pop(job_id, None)
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


# `cleanup_file` faqat mijoz uni SO'RASA (har ikkala fayl uchun alohida)
# chaqiriladi — mijoz sahifani yopib ketsa yoki faqat bittasini yuklab olsa,
# `jobs` yozuvi va (tugagan bo'lsa) qolgan mp3 fayl abadiy qolib ketardi. Bu
# fon "tozalovchi" (reaper) shuni oldini oladi.
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
            stale_jobs = [(jid, jobs.pop(jid)) for jid in stale_ids]
        for _jid, job in stale_jobs:
            for key in ("speech_file", "background_file"):
                path = job.get(key)
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass


threading.Thread(target=_reap_stale_jobs, daemon=True).start()
