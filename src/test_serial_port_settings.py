"""Last-successful serial port persistence and startup selection policy."""

import json
import os
from pathlib import Path

import pytest

import serial_port_settings as settings


class TestSettingsFilePath:
    def test_path_is_independent_of_cwd(self, monkeypatch):
        expected = settings.settings_file_path()
        drive_root = os.path.splitdrive(str(Path(settings.__file__).resolve()))[0] + os.sep
        for cwd in (drive_root, str(Path(settings.__file__).resolve().parent)):
            monkeypatch.chdir(cwd)
            assert settings.settings_file_path() == expected

    def test_source_path_layout(self):
        path = settings.settings_file_path()
        assert path == Path(settings.__file__).resolve().parents[1] / "config" / "serial_port.json"
        assert path.is_absolute()

    def test_frozen_path_follows_executable(self, monkeypatch, tmp_path):
        exe = tmp_path / "dist" / "powerSupplyMaster.exe"
        monkeypatch.setattr(settings.sys, "frozen", True, raising=False)
        monkeypatch.setattr(settings.sys, "executable", str(exe))
        assert settings.settings_file_path() == exe.resolve().parent / "config" / "serial_port.json"


class TestLoadLastPort:
    def test_missing_file_means_no_preference(self, tmp_path):
        assert settings.load_last_port(tmp_path / "missing.json") is None

    def test_valid_file_returns_port(self, tmp_path):
        path = tmp_path / "serial_port.json"
        path.write_text(json.dumps({"version": 1, "port": " COM9 "}), encoding="utf-8")
        assert settings.load_last_port(path) == "COM9"

    def test_invalid_json_means_no_preference(self, tmp_path):
        path = tmp_path / "serial_port.json"
        path.write_text("{not json", encoding="utf-8")
        assert settings.load_last_port(path) is None

    def test_unreadable_file_means_no_preference(self, tmp_path):
        assert settings.load_last_port(tmp_path) is None

    @pytest.mark.parametrize("document", [
        [],
        {"version": 2, "port": "COM9"},
        {"version": "1", "port": "COM9"},
        {"version": 1},
        {"version": 1, "port": None},
        {"version": 1, "port": 9},
        {"version": 1, "port": "   "},
    ])
    def test_unusable_document_means_no_preference(self, tmp_path, document):
        path = tmp_path / "serial_port.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        assert settings.load_last_port(path) is None


class TestSaveLastPort:
    def test_saved_file_reads_back(self, tmp_path):
        path = tmp_path / "config" / "serial_port.json"
        assert settings.save_last_port("COM9", path) is True
        assert settings.load_last_port(path) == "COM9"
        assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1, "port": "COM9"}

    @pytest.mark.parametrize("port", [None, 9, "", "   "])
    def test_invalid_port_is_not_written(self, tmp_path, port):
        path = tmp_path / "serial_port.json"
        assert settings.save_last_port(port, path) is False
        assert not path.exists()

    def test_uncreatable_directory_returns_false_without_raising(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        assert settings.save_last_port("COM9", blocker / "config" / "serial_port.json") is False

    def test_replace_failure_keeps_original_and_removes_temporary_file(self, tmp_path, monkeypatch):
        path = tmp_path / "serial_port.json"
        settings.save_last_port("COM8", path)
        before = path.read_text(encoding="utf-8")

        def fail_replace(*args):
            raise OSError("device busy")

        monkeypatch.setattr(settings.os, "replace", fail_replace)
        assert settings.save_last_port("COM9", path) is False
        assert path.read_text(encoding="utf-8") == before
        assert not path.with_name(path.name + ".tmp").exists()


class TestChoosePortIndex:
    PORTS = ["COM3", "COM8", "COM9"]

    def test_available_remembered_port_wins_over_usb(self):
        assert settings.choose_port_index(self.PORTS, "COM9", 1) == 2

    def test_remembered_port_matching_ignores_case(self):
        assert settings.choose_port_index(self.PORTS, "com8", 2) == 1

    def test_missing_remembered_port_falls_back_to_usb(self):
        assert settings.choose_port_index(self.PORTS, "COM7", 1) == 1

    def test_no_remembered_or_usb_port_leaves_first_item_selected(self):
        assert settings.choose_port_index(self.PORTS, None, None) is None

    def test_empty_enumeration_has_no_selection(self):
        assert settings.choose_port_index([], "COM8", 0) is None

    @pytest.mark.parametrize("usb_index", [-1, 3, True, "1"])
    def test_invalid_usb_index_leaves_first_item_selected(self, usb_index):
        assert settings.choose_port_index(self.PORTS, None, usb_index) is None
