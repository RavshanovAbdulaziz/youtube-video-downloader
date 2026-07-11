import glob
import os
import re
import shutil
import subprocess
import threading
import uuid

import yt_dlp

from downloader import DOWNLOADS_DIR, _sanitize_filename, _unique_path

SEPARATE_TMP_DIR = os.path.join(os.path.dirname(__file__), "downloads", "_separate_tmp")
os.makedirs(SEPARATE_TMP_DIR, exist_ok=True)

# numba standart holatda keshni site-packages ichiga yozadi — admin bo'lmagan
# jarayon u yerga yoza olmay, tempfile abadiy qayta urinish tsikliga tushib qoladi.
NUMBA_CACHE_DIR = os.path.join(os.path.dirname(__file__), "_numba_cache")
os.makedirs(NUMBA_CACHE_DIR, exist_ok=True)

UVR_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
_PERCENT_RE = re.compile(r"(\d{1,3})%\|")


def _detect_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            print(f"[separator] GPU topildi: {torch.cuda.get_device_name(0)} — CUDA ishlatiladi")
            return "cuda"
    except ImportError:
        pass
    print("[separator] GPU topilmadi (yoki torch o'rnatilmagan) — CPU ishlatiladi")
    return "cpu"


DEVICE = _detect_device()

jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def _set_percent(job_id: str, percent: int) -> None:
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["percent"] = percent


def _run_with_progress(cmd: list[str], job_id: str) -> None:
    """Run a subprocess, parsing tqdm-style 'NN%|' output to report live progress."""
    env = {**os.environ, "NUMBA_CACHE_DIR": NUMBA_CACHE_DIR, "PYTHONUNBUFFERED": "1"}
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


def _run_demucs(source_file: str, work_dir: str, job_id: str) -> tuple[str, str]:
    _run_with_progress(
        ["demucs", "--two-stems", "vocals", "--mp3", "-n", "htdemucs",
         "-d", DEVICE, "-o", work_dir, source_file],
        job_id,
    )
    stem_name = os.path.splitext(os.path.basename(source_file))[0]
    stem_dir = os.path.join(work_dir, "htdemucs", stem_name)
    return os.path.join(stem_dir, "vocals.mp3"), os.path.join(stem_dir, "no_vocals.mp3")


def _run_uvr(source_file: str, work_dir: str, job_id: str) -> tuple[str, str]:
    _run_with_progress(
        ["audio-separator", source_file, "--model_filename", UVR_MODEL,
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


def start_separation(url: str, audio_format_id: str, title: str | None = None,
                      engine: str = "demucs") -> str:
    if engine not in ENGINES:
        raise ValueError(f"Noma'lum dvigatel: {engine}")

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"status": "downloading", "percent": 0}

    def run():
        work_dir = os.path.join(SEPARATE_TMP_DIR, job_id)
        os.makedirs(work_dir, exist_ok=True)
        try:
            ydl_opts = {
                "format": audio_format_id,
                "outtmpl": os.path.join(work_dir, "source.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [_download_progress_hook(job_id)],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            source_file = next(
                os.path.join(work_dir, f) for f in os.listdir(work_dir) if f.startswith("source.")
            )

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
