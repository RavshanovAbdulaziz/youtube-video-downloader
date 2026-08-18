"""Lazy, automatic installer for the optional "Ovozni ajratish" AI stack
(PyTorch + Demucs + audio-separator).

Mirrors install_ai.bat's exact, already-proven command sequence, but fully
automatic: GPU vs CPU is auto-detected (no y/n prompt), and progress is
reported through the same job-progress dict pattern separator.py already
uses for downloads/separation, via a caller-supplied ``progress_cb(stage,
percent)``.

Packages are installed straight into paths.runtime_python_exe()'s own
site-packages — under a packaged build that's the bundled portable Python
that's *already running this process*, so console scripts (demucs.exe,
audio-separator.exe) appear in its Scripts folder immediately, with no
restart needed. From source, that's just the current interpreter, matching
today's install_ai.bat behavior exactly.
"""
import os
import shutil
import subprocess
import threading

import paths

# (stage key, label, relative weight) — torch is by far the largest download,
# so it dominates the reported percentage.
_STAGES = [
    ("torch", "PyTorch", 60),
    ("demucs", "Demucs", 15),
    ("separator", "UVR/audio-separator", 15),
    ("compat", "Moslashtirish", 10),
]
_TOTAL_WEIGHT = sum(w for _, _, w in _STAGES)

_install_lock = threading.Lock()


def _python() -> str:
    return paths.runtime_python_exe()


def is_ai_installed() -> bool:
    scripts_dir = paths.runtime_scripts_dir()
    return (
        os.path.isfile(os.path.join(scripts_dir, "demucs.exe"))
        and os.path.isfile(os.path.join(scripts_dir, "audio-separator.exe"))
    )


def _detect_gpu() -> bool:
    cfg = paths.read_config()
    if cfg.get("gpu") is not None:
        return cfg["gpu"]
    has_gpu = shutil.which("nvidia-smi") is not None
    paths.write_config(gpu=has_gpu)
    return has_gpu


def current_device() -> str:
    """"cuda" yoki "cpu" — demucs'ga -d flagi va audio-separator uchun GPU
    paketini tanlashda ishlatiladi. AI kutubxonalari o'rnatilgan-yo'qligidan
    mustaqil — faqat uskuna (va o'rnatish paytidagi tanlov)ni aks ettiradi."""
    return "cuda" if paths.read_config().get("gpu") else "cpu"


_PIP_TIMEOUT_SECONDS = 1800  # 30 daqiqa — torch (~2-3 GB) kabi katta yuklamalar uchun


def _run_pip(args: list[str]) -> None:
    cmd = [_python(), "-m", "pip", "install", "--no-warn-script-location", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_PIP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        # Timeout'siz bu yerda abadiy osilib qolishi mumkin edi (uzilgan/juda
        # sekin internet) — `ensure_installed`dagi `_install_lock` global
        # bo'lgani uchun bu BUTUN AI ajratish funksiyasini barcha
        # foydalanuvchilar uchun dastur qayta ishga tushirilguncha bloklab
        # qo'yardi.
        raise RuntimeError(
            f"pip install {_PIP_TIMEOUT_SECONDS // 60} daqiqada tugamadi "
            "(internet sekin yoki uzilgan bo'lishi mumkin) — qayta urinib ko'ring"
        )
    if result.returncode != 0:
        raise RuntimeError((result.stdout + result.stderr)[-2000:])


def _install(progress_cb) -> None:
    gpu = _detect_gpu()

    def report(stage_idx: int) -> None:
        done_weight = sum(w for _, _, w in _STAGES[:stage_idx])
        progress_cb(_STAGES[stage_idx][0], round(done_weight * 100 / _TOTAL_WEIGHT))

    report(0)
    if gpu:
        _run_pip(["torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu128"])
    else:
        _run_pip(["torch", "torchvision", "torchaudio"])

    report(1)
    _run_pip(["demucs"])

    report(2)
    _run_pip([("audio-separator[gpu]" if gpu else "audio-separator"), "--no-deps"])
    _run_pip([
        "audioop-lts", "beartype", "einops", "julius", "librosa", "ml_collections",
        "numpy", "onnx-weekly", "onnx2torch-py313",
        "onnxruntime-gpu" if gpu else "onnxruntime",
        "pydub", "pyyaml", "requests", "resampy", "rotary-embedding-torch",
        "samplerate", "scipy", "six", "soundfile", "tqdm",
    ])

    report(3)
    _run_pip(["--upgrade", "beartype"])
    _run_pip(["numpy<2.5"])

    if gpu:
        # nvidia-smi bor degani haydovchi CUDA build bilan mos keladi degani
        # emas — tekshirib ko'ramiz, mos kelmasa "cpu"ga tushamiz (aks holda
        # demucs'ga -d cuda berilib, u ishlay olmaydigan build bilan qulaydi).
        check = subprocess.run(
            [_python(), "-c", "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)"],
            capture_output=True,
        )
        if check.returncode != 0:
            paths.write_config(gpu=False)

    progress_cb("compat", 100)
    paths.write_config(ai_installed=True)


def ensure_installed(progress_cb) -> None:
    """AI kutubxonalari hali o'rnatilmagan bo'lsa, o'rnatadi (bloklovchi
    chaqiruv — alohida thread'da chaqirish chaqiruvchi tomonning ishi).
    Bir vaqtning o'zida bir nechta so'rov kelsa (masalan Web UI va bot bir
    paytda), faqat bittasi haqiqiy o'rnatishni bajaradi — qolganlari lock
    bo'shashini kutib, keyin darhol davom etadi (chunki shu paytda AI
    allaqachon o'rnatilgan bo'ladi)."""
    if is_ai_installed():
        return
    with _install_lock:
        if is_ai_installed():
            return
        _install(progress_cb)
