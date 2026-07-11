import os
import re
import threading
import uuid

import yt_dlp

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Datacenter IP'lardan (masalan, bulutli serverlardan) kelayotgan so'rovlarni
# YouTube ko'pincha "sign in to confirm you're not a bot" deb bloklaydi.
# Brauzerdan eksport qilingan cookies.txt fayli (Netscape format) ko'rsatilsa,
# bu muammoni chetlab o'tadi.
COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE", "")


def _ydl_base_opts() -> dict:
    opts = {}
    if COOKIES_FILE and os.path.isfile(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    return opts

# job_id -> progress/state dict, shared across threads
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()

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


def get_info(url: str) -> dict:
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True, **_ydl_base_opts()}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
        fps = f.get("fps") or 0
        key = height
        current = best_by_height.get(key)
        if current is None or (f.get("tbr") or 0) > (current.get("tbr") or 0):
            best_by_height[key] = f

    resolutions = []
    for height, f in sorted(best_by_height.items(), key=lambda kv: kv[0], reverse=True):
        fps = f.get("fps") or 0
        label = f"{height}p" + (f"{int(fps)}" if fps and fps > 30 else "")
        resolutions.append({
            "format_id": f["format_id"],
            "label": label,
            "height": height,
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
        if current is None or (f.get("abr") or 0) > (current.get("abr") or 0):
            seen_langs[code] = {
                "format_id": f["format_id"],
                "lang_code": code,
                "label": _lang_label(code, is_original),
                "abr": f.get("abr"),
                "ext": f.get("ext"),
                "is_original": is_original,
            }

    audio_tracks = sorted(seen_langs.values(), key=lambda a: (not a["is_original"], a["label"]))

    return {
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "resolutions": resolutions,
        "audio_tracks": audio_tracks,
        "has_video_only_streams": bool(video_only),
    }


def _progress_hook(job_id: str):
    def hook(d):
        with jobs_lock:
            job = jobs.setdefault(job_id, {})
            if d["status"] == "downloading":
                job["status"] = "downloading"
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes") or 0
                job["percent"] = round(downloaded / total * 100, 1) if total else None
                job["speed"] = d.get("speed")
                job["eta"] = d.get("eta")
            elif d["status"] == "finished":
                job["status"] = "merging"
    return hook


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


def start_download(url: str, video_format_id: str | None, audio_format_id: str | None,
                    audio_only: bool, title: str | None = None) -> str:
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"status": "queued", "percent": 0}

    if audio_only:
        fmt = audio_format_id
    elif video_format_id and audio_format_id:
        fmt = f"{video_format_id}+{audio_format_id}"
    else:
        fmt = video_format_id

    outtmpl = os.path.join(DOWNLOADS_DIR, f"{job_id}.%(ext)s")
    ydl_opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_progress_hook(job_id)],
        **_ydl_base_opts(),
    }
    if not audio_only:
        ydl_opts["merge_output_format"] = "mp4"
    if audio_only:
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
        }]

    def run():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            raw_path = _find_output_file(job_id)
            final_path = raw_path
            if raw_path and title:
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
