"""Lokal "bgutil" PO (Proof-of-Origin) token HTTP serverini avtomatik
boshqaradi — https://github.com/Brainicism/bgutil-ytdlp-pot-provider

YouTube tobora ko'proq holatlarda (hatto rezidensial IP'larda ham) so'rovlar
bilan birga haqiqiy PO token talab qiladi, aks holda "Sign in to confirm
you're not a bot" xatosi beradi. Cookie bilan ham chetlab o'tish mumkin
(downloader.py'dagi COOKIES_FILE), lekin PO token cookie'ga bog'liq
bo'lmagan, barqarorroq muqobil/qo'shimcha.

Docker orqali serverga joylashtirilganda (Dockerfile/docker-compose.yml)
bu server alohida konteyner sifatida ishlaydi va YTDLP_POT_BASE_URL orqali
ko'rsatiladi — bu modul faqat o'sha env var berilmagan holatda (lokal
Windows ishga tushirish) ishga tushadi.
"""
import atexit
import ctypes
import os
import subprocess
import threading
import time
import urllib.request

import paths

PORT = 4416
BASE_URL = f"http://127.0.0.1:{PORT}"

_lock = threading.Lock()
_process: subprocess.Popen | None = None
_job_handle = None  # Windows Job Object — pastdagi _assign_to_job_object'ga qarang


def _assign_to_job_object(process: subprocess.Popen) -> None:
    """Windows'da node.exe'ni "Job Object"ga biriktiradi, shu bilan uning
    umrini shu Python jarayoniga bog'laydi: `atexit.register(_stop)` FAQAT
    "toza" chiqishda ishlaydi — Task Manager'dan "End Task", jarayonni
    majburan o'ldirish yoki qulash paytida chaqirilmaydi, va node.exe
    egasiz (orphan) qolib, portni band qilib qoladi. JOB_OBJECT_LIMIT_
    KILL_ON_JOB_CLOSE bilan esa: bu jarayon QANDAY tugasa ham (hatto
    majburan), Windows uning barcha handle'larini (job handle ham shular
    ichida) avtomatik yopadi — shu handle yopilishi node.exe'ni ham darhol
    tugatadi. Muvaffaqiyatsiz bo'lsa (masalan eski Windows) jim o'tkazib
    yuboriladi — atexit hamon zaxira sifatida ishlayveradi."""
    if os.name != "nt":
        return
    global _job_handle
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        JobObjectExtendedLimitInformation = 9

        class _IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]

        class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", _IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not ok or not kernel32.AssignProcessToJobObject(job, int(process._handle)):
            kernel32.CloseHandle(job)
            return
        _job_handle = job  # dastur umri davomida ochiq turishi shart (yopilsa — kill ishga tushadi)
    except Exception:
        pass


def _is_up() -> bool:
    try:
        urllib.request.urlopen(f"{BASE_URL}/ping", timeout=0.5)
        return True
    except Exception:
        return False


def _stop() -> None:
    global _process
    if _process is not None and _process.poll() is None:
        _process.terminate()
    _process = None


def ensure_running() -> str | None:
    """Lokal bgutil serveri topilsa (paths.bundled_bgutil_server_dir()),
    uni bir martalik fon jarayoni sifatida ishga tushiradi (allaqachon
    ishlab turgan bo'lsa — qayta ishga tushirmaydi) va bazaviy URL'ni
    qaytaradi. Server topilmasa yoki ishga tushmasa, None qaytaradi — bunda
    chaqiruvchi (downloader.py) PO token'siz, faqat cookie/JS runtime bilan
    davom etadi."""
    if _is_up():
        return BASE_URL

    server_dir = paths.bundled_bgutil_server_dir()
    if not server_dir:
        return None
    main_js = os.path.join(server_dir, "build", "main.js")
    if not os.path.isfile(main_js):
        return None

    with _lock:
        global _process
        if _process is None or _process.poll() is not None:
            if _is_up():  # boshqa thread/jarayon shu orada ishga tushirgan bo'lishi mumkin
                return BASE_URL
            node_exe = paths.bundled_node_exe() or "node"
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                _process = subprocess.Popen(
                    [node_exe, main_js, "--port", str(PORT)],
                    cwd=server_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
            except OSError:
                # node_exe topilmadi (masalan, paketlangan qurilmada Node
                # bundle qilinmagan, tizimda ham o'rnatilmagan) — PO token
                # ixtiyoriy, shuning uchun shu yerda yutib, None qaytaramiz.
                return None
            _assign_to_job_object(_process)
            atexit.register(_stop)

    for _ in range(40):  # ~4s gacha startup kutamiz
        if _is_up():
            return BASE_URL
        time.sleep(0.1)
    return BASE_URL if _is_up() else None
