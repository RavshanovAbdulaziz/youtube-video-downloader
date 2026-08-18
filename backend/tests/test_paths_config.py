"""paths.py: config o'qish/yozish, va parallel yozuvda yo'qolgan-yangilanish
(lost update) muammosi tuzatilganini tekshirish."""
import json
import os
import threading

import paths


class TestConfigBasics:
    def test_read_returns_defaults_when_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(paths, "CONFIG_FILE", str(tmp_path / "nope.json"))
        cfg = paths.read_config()
        assert cfg["bot_token"] is None
        assert cfg["ai_installed"] is False

    def test_read_survives_corrupt_json(self, monkeypatch, tmp_path):
        bad = tmp_path / "config.json"
        bad.write_text("{ this is not valid json", encoding="utf-8")
        monkeypatch.setattr(paths, "CONFIG_FILE", str(bad))
        # Buzilgan fayl dasturni yiqitmasligi, standart qiymatlarga
        # qaytishi kerak.
        assert paths.read_config()["bot_token"] is None

    def test_write_then_read_roundtrip(self, monkeypatch, tmp_path):
        monkeypatch.setattr(paths, "CONFIG_FILE", str(tmp_path / "config.json"))
        paths.write_config(bot_token="secret123", gpu=True)
        cfg = paths.read_config()
        assert cfg["bot_token"] == "secret123"
        assert cfg["gpu"] is True

    def test_write_merges_instead_of_replacing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(paths, "CONFIG_FILE", str(tmp_path / "config.json"))
        paths.write_config(bot_token="tok")
        paths.write_config(gpu=True)
        cfg = paths.read_config()
        # Ikkinchi yozuv birinchisini o'chirib yubormasligi kerak.
        assert cfg["bot_token"] == "tok"
        assert cfg["gpu"] is True

    def test_write_leaves_no_temp_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(paths, "CONFIG_FILE", str(tmp_path / "config.json"))
        paths.write_config(bot_token="tok")
        assert not os.path.exists(str(tmp_path / "config.json.tmp"))


class TestConcurrentConfigWrites:
    def test_no_lost_updates_under_thread_contention(self, monkeypatch, tmp_path):
        """Har bir thread o'z kalitini yozadi; lock bo'lmasa ba'zilari
        yo'qolardi (read-modify-write poygasi)."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(paths, "CONFIG_FILE", str(config_file))
        paths.write_config(bot_token="initial")

        thread_count = 12
        barrier = threading.Barrier(thread_count)
        errors = []

        def writer(index):
            try:
                barrier.wait()  # hammasini bir vaqtda ishga tushiramiz
                for _ in range(8):
                    paths.write_config(**{f"key_{index}": index})
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"parallel yozuvda xato: {errors}"

        with open(config_file, "r", encoding="utf-8") as f:
            final = json.load(f)  # buzilmagan JSON bo'lishi shart

        assert final["bot_token"] == "initial", "boshlang'ich qiymat yo'qoldi"
        for i in range(thread_count):
            assert final.get(f"key_{i}") == i, f"key_{i} yozuvi yo'qoldi (lost update)"


class TestRuntimeHelpers:
    def test_runtime_root_none_without_env(self, monkeypatch):
        monkeypatch.delenv("APP_RUNTIME_DIR", raising=False)
        assert paths._runtime_root() is None
        assert paths.bundled_ffmpeg_dir() is None
        assert paths.bundled_node_exe() is None

    def test_runtime_root_ignores_nonexistent_dir(self, monkeypatch):
        monkeypatch.setenv("APP_RUNTIME_DIR", r"C:\definitely\not\a\real\path")
        assert paths._runtime_root() is None

    def test_python_exe_falls_back_to_current_interpreter(self, monkeypatch):
        import sys
        monkeypatch.delenv("APP_RUNTIME_DIR", raising=False)
        assert paths.runtime_python_exe() == sys.executable

    def test_default_cookies_file_picks_newest(self, monkeypatch, tmp_path):
        import time
        older = tmp_path / "cookies.txt"
        newer = tmp_path / "www.youtube.com_cookies.txt"
        older.write_text("old", encoding="utf-8")
        time.sleep(0.05)
        newer.write_text("new", encoding="utf-8")
        os.utime(str(older), (1, 1))  # eskini aniq eski qilamiz

        monkeypatch.setattr(paths, "_base_dir", lambda: str(tmp_path))
        monkeypatch.setattr(paths, "_BACKEND_DIR", str(tmp_path))

        assert paths.default_cookies_file() == str(newer)

    def test_default_cookies_file_none_when_absent(self, monkeypatch, tmp_path):
        monkeypatch.setattr(paths, "_base_dir", lambda: str(tmp_path))
        monkeypatch.setattr(paths, "_BACKEND_DIR", str(tmp_path))
        assert paths.default_cookies_file() is None
