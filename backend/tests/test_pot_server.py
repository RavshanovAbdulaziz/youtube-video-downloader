"""pot_server.py: node.exe jarayonining umri shu Python jarayoniga
bog'langanini tekshirish (Windows Job Object)."""
import ctypes
import os
import subprocess
import sys
import time

import pytest

import pot_server

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Job Object faqat Windows'da")


def _spawn_dummy() -> subprocess.Popen:
    """Uzoq ishlaydigan, zararsiz bola jarayon."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


class TestJobObject:
    def test_assign_succeeds_and_sets_handle(self, monkeypatch):
        monkeypatch.setattr(pot_server, "_job_handle", None)
        process = _spawn_dummy()
        try:
            pot_server._assign_to_job_object(process)
            assert pot_server._job_handle, "Job Object yaratilmadi"
        finally:
            process.kill()
            process.wait(timeout=10)

    def test_closing_job_handle_kills_child(self, monkeypatch):
        """Asosiy da'vo: dastur MAJBURAN yopilganda (Task Manager → End Task)
        Windows uning handle'larini yopadi, va shu handle yopilishi
        node.exe'ni ham o'ldiradi — ya'ni egasiz (orphan) jarayon qolmaydi.

        Bu yerda handle'ni qo'lda yopib, xuddi shu mexanizmni sinaymiz
        (atexit bunday holatda umuman chaqirilmaydi)."""
        monkeypatch.setattr(pot_server, "_job_handle", None)
        process = _spawn_dummy()
        killed = False
        try:
            pot_server._assign_to_job_object(process)
            job = pot_server._job_handle
            assert job, "Job Object yaratilmadi — test ma'nosiz"
            assert process.poll() is None, "bola jarayon allaqachon tugagan"

            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(job)

            deadline = time.time() + 10
            while time.time() < deadline:
                if process.poll() is not None:
                    killed = True
                    break
                time.sleep(0.1)

            assert killed, "job handle yopilgach bola jarayon o'lmadi (orphan qoladi)"
        finally:
            if not killed:
                process.kill()
                process.wait(timeout=10)

    def test_assign_never_raises_on_bad_input(self):
        """Job Object qo'llab-quvvatlanmasa ham, PO token IXTIYORIY —
        bu yerdagi xato butun yuklashni to'xtatmasligi kerak."""
        class _Bogus:
            _handle = 0

        pot_server._assign_to_job_object(_Bogus())  # xato ko'tarmasligi kerak


class TestStop:
    def test_stop_is_safe_when_nothing_running(self, monkeypatch):
        monkeypatch.setattr(pot_server, "_process", None)
        pot_server._stop()

    def test_stop_terminates_running_process(self, monkeypatch):
        process = _spawn_dummy()
        monkeypatch.setattr(pot_server, "_process", process)
        try:
            pot_server._stop()
            deadline = time.time() + 10
            while time.time() < deadline and process.poll() is None:
                time.sleep(0.1)
            assert process.poll() is not None, "_stop() jarayonni to'xtatmadi"
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


class TestEnsureRunning:
    def test_returns_none_when_server_not_available(self, monkeypatch):
        # bgutil serveri o'rnatilmagan bo'lsa — None qaytarib, yuklash
        # PO token'siz davom etishi kerak (xato ko'tarmasdan).
        monkeypatch.setattr(pot_server, "_is_up", lambda: False)
        monkeypatch.setattr(pot_server.paths, "bundled_bgutil_server_dir", lambda: None)
        assert pot_server.ensure_running() is None
