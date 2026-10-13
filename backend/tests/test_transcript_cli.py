"""transcript/cli.py: CLI kirish nuqtasining muhitga bog'liq qismlari —
chiqish kodlashi va paket konteksti. Tarmoqqa chiqilmaydi: qidiruv
funksiyalari umuman chaqirilmaydi, faqat `--help` va yordamchi
funksiyalar tekshiriladi."""
import io
import os
import subprocess
import sys

import pytest

from transcript import cli

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLI_PATH = os.path.join(_BACKEND_DIR, "transcript", "cli.py")
# Bayroq va emoji — aynan shunday sarlavha (IShowSpeed stream'i) cp1252
# quvurida natija topilganidan KEYIN butun buyruqni yiqitgan edi.
_NON_ASCII = "Portugal \U0001F1F5\U0001F1F9 Vs Colombia \U0001F1E8\U0001F1F4 \u26BD"


class TestUseUtf8Output:
    def test_switches_streams_to_utf8(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
        monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
        cli._use_utf8_output()
        assert sys.stdout.encoding == "utf-8"
        assert sys.stderr.encoding == "utf-8"

    def test_tolerates_streams_without_reconfigure(self, monkeypatch):
        # Almashtirilgan oqimlarda (test o'ramlari, pythonw'dagi `None`)
        # `reconfigure` bo'lmasligi mumkin — bu CLI'ni yiqitmasligi kerak.
        monkeypatch.setattr(sys, "stdout", object())
        monkeypatch.setattr(sys, "stderr", None)
        cli._use_utf8_output()

    def test_tolerates_reconfigure_failure(self, monkeypatch):
        class Stubborn:
            encoding = "cp1252"

            def reconfigure(self, **kwargs):
                raise OSError("konsol kodlashini o'zgartirib bo'lmadi")

        monkeypatch.setattr(sys, "stdout", Stubborn())
        monkeypatch.setattr(sys, "stderr", Stubborn())
        cli._use_utf8_output()

    def test_non_ascii_survives_a_cp1252_pipe(self):
        """Asl nosozlikning to'g'ridan-to'g'ri qaytarilishi: lokal kodlash
        cp1252 bo'lganda emoji chiqarish `UnicodeEncodeError` berardi."""
        script = (
            f"import sys; sys.path.insert(0, {_BACKEND_DIR!r});"
            "from transcript import cli; cli._use_utf8_output();"
            f"print({_NON_ASCII!r})"
        )
        env = dict(os.environ, PYTHONIOENCODING="cp1252")
        env.pop("PYTHONUTF8", None)
        proc = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, timeout=120, env=env,
        )
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
        assert proc.stdout.decode("utf-8").strip() == _NON_ASCII


class TestRunsWithoutPackageContext:
    """`py cli.py` — `-m transcript.cli` emas, oddiy skript sifatida
    chaqiruv (`_bootstrap_package`). Avval `ImportError` berardi."""

    @pytest.mark.parametrize("where", ["backend", "transcript", "elsewhere"])
    def test_help_works_from_any_directory(self, where, tmp_path):
        cwd = {
            "backend": _BACKEND_DIR,
            "transcript": os.path.join(_BACKEND_DIR, "transcript"),
            "elsewhere": str(tmp_path),
        }[where]
        proc = subprocess.run(
            [sys.executable, _CLI_PATH, "--help"],
            cwd=cwd, capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        assert "--find-source" in proc.stdout

    def test_module_invocation_still_works(self):
        proc = subprocess.run(
            [sys.executable, "-m", "transcript.cli", "--help"],
            cwd=_BACKEND_DIR, capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        assert "--find-source" in proc.stdout
