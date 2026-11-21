import json
import logging
import os
from pathlib import Path

import pytest

from . import window_geometry as wg

logging.basicConfig(level=logging.DEBUG)

MAIN_RECT = (320, 180, 1000, 700)
FLOATING_POS = (1450, 980)
AVAIL = (0, 0, 1920, 1040)


def _valid_document():
    return {
        "version": 1,
        "windows": {
            "main": {"x": 10, "y": 20, "width": 30, "height": 40, "screen": "MONITOR-A"},
            "floating": {"x": 50, "y": 60, "screen": "MONITOR-B"},
        },
    }


def _write(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")


class TestGeometryFilePath:
    def test_path_is_independent_of_cwd(self, monkeypatch):
        expected = wg.geometry_file_path()
        src_dir = Path(wg.__file__).resolve().parents[2] / "src"
        drive_root = os.path.splitdrive(str(src_dir))[0] + os.sep
        for cwd in (drive_root, str(src_dir)):
            monkeypatch.chdir(cwd)
            assert wg.geometry_file_path() == expected

    def test_path_layout(self):
        path = wg.geometry_file_path()
        assert path.name == "window_geometry.json"
        assert path.parent.name == "config"
        assert path.parent == Path(wg.__file__).resolve().parents[2] / "config"
        assert path.is_absolute()


class TestLoadEntries:
    def test_missing_file_returns_none(self, tmp_path):
        assert wg.load_entries(tmp_path / "window_geometry.json") is None

    def test_invalid_json_returns_none(self, tmp_path):
        path = tmp_path / "window_geometry.json"
        path.write_text("{not json", encoding="utf-8")
        assert wg.load_entries(path) is None

    @pytest.mark.parametrize("version", [0, 2, "1", None])
    def test_unsupported_version_returns_none(self, tmp_path, version):
        path = tmp_path / "window_geometry.json"
        document = _valid_document()
        document["version"] = version
        _write(path, document)
        assert wg.load_entries(path) is None

    def test_missing_window_returns_none(self, tmp_path):
        path = tmp_path / "window_geometry.json"
        document = _valid_document()
        del document["windows"]["floating"]
        _write(path, document)
        assert wg.load_entries(path) is None

    def test_missing_required_field_returns_none(self, tmp_path):
        path = tmp_path / "window_geometry.json"
        document = _valid_document()
        del document["windows"]["main"]["height"]
        _write(path, document)
        assert wg.load_entries(path) is None

    @pytest.mark.parametrize("value", [30.5, "30", None, [30]])
    def test_non_integer_field_returns_none(self, tmp_path, value):
        path = tmp_path / "window_geometry.json"
        document = _valid_document()
        document["windows"]["main"]["width"] = value
        _write(path, document)
        assert wg.load_entries(path) is None

    def test_bool_field_returns_none(self, tmp_path):
        path = tmp_path / "window_geometry.json"
        document = _valid_document()
        document["windows"]["main"]["width"] = True
        _write(path, document)
        assert wg.load_entries(path) is None

    def test_non_positive_size_returns_none(self, tmp_path):
        path = tmp_path / "window_geometry.json"
        document = _valid_document()
        document["windows"]["main"]["height"] = 0
        _write(path, document)
        assert wg.load_entries(path) is None

    def test_negative_position_is_accepted(self, tmp_path):
        path = tmp_path / "window_geometry.json"
        document = _valid_document()
        document["windows"]["main"]["x"] = -1280
        _write(path, document)
        assert wg.load_entries(path)["main"]["x"] == -1280

    def test_valid_document_returns_both_windows(self, tmp_path):
        path = tmp_path / "window_geometry.json"
        _write(path, _valid_document())
        entries = wg.load_entries(path)
        assert entries == {
            "main": {"x": 10, "y": 20, "width": 30, "height": 40, "screen": "MONITOR-A"},
            "floating": {"x": 50, "y": 60, "screen": "MONITOR-B"},
        }


class TestIsRectUsable:
    def test_fully_inside_is_usable(self):
        assert wg.is_rect_usable((100, 100, 100, 100), [AVAIL]) is True

    def test_40_percent_outside_is_usable(self):
        assert wg.is_rect_usable((1860, 300, 100, 100), [AVAIL]) is True

    def test_60_percent_outside_is_unusable(self):
        assert wg.is_rect_usable((1880, 300, 100, 100), [AVAIL]) is False

    def test_second_screen_counts(self):
        screens = [AVAIL, (1920, 0, 1920, 1040)]
        assert wg.is_rect_usable((2000, 300, 100, 100), screens) is True

    def test_no_screen_is_unusable(self):
        assert wg.is_rect_usable(MAIN_RECT, []) is False


class TestClampInto:
    def test_partly_offscreen_moves_together_with_screen(self):
        assert wg.clamp_into((1860, 1000, 100, 100), AVAIL) == (1820, 940, 100, 100)

    def test_inside_rect_is_untouched(self):
        assert wg.clamp_into((100, 100, 50, 50), AVAIL) == (100, 100, 50, 50)

    def test_rect_larger_than_screen_keeps_top_left_reachable(self):
        assert wg.clamp_into((500, 500, 3000, 2000), AVAIL) == (0, 0, 3000, 2000)


class TestDefaultLayout:
    def test_main_is_centered(self):
        width, height = 591, 622
        assert wg.default_main_rect(AVAIL, width, height) == (
            AVAIL[0] + (AVAIL[2] - width) // 2,
            AVAIL[1] + (AVAIL[3] - height) // 2,
            width,
            height,
        )

    def test_floating_is_bottom_right_with_margin(self):
        width, height = 407, 81
        pos = wg.default_floating_pos(AVAIL, width, height)
        assert pos == (AVAIL[0] + AVAIL[2] - width - wg.FLOATING_MARGIN,
                       AVAIL[1] + AVAIL[3] - height - wg.FLOATING_MARGIN)

    def test_floating_top_left_stays_reachable_when_screen_is_smaller(self):
        small = (0, 0, 300, 60)
        assert wg.default_floating_pos(small, 407, 81) == (0, 0)

    def test_floating_bottom_edge_stays_inside_available_area(self):
        avail = (0, 0, 300, 200)
        x, y = wg.default_floating_pos(avail, 407, 81)
        assert x == avail[0]
        assert y + 81 <= avail[1] + avail[3]

    def test_choose_available_rect_picks_overlapping_screen(self):
        screens = [AVAIL, (1920, 0, 1920, 1040)]
        assert wg.choose_available_rect((2000, 300, 100, 100), screens) == (1920, 0, 1920, 1040)

    def test_choose_available_rect_falls_back_to_first(self):
        screens = [AVAIL, (1920, 0, 1920, 1040)]
        assert wg.choose_available_rect((-5000, 0, 100, 100), screens) == AVAIL


class TestRestoredRect:
    _ENTRIES = {
        "main": {"x": 100, "y": 100, "width": 800, "height": 600, "screen": "A"},
        "floating": {"x": 1500, "y": 900, "screen": "A"},
    }

    def test_no_history_returns_none(self):
        assert wg.restored_rect(None, "main", screen_rects=[AVAIL]) is None

    def test_resizable_window_keeps_stored_size(self):
        assert wg.restored_rect(self._ENTRIES, "main", 591, 622, [AVAIL]) == (100, 100, 800, 600)

    def test_history_ignores_stored_size_for_fixed_size_window(self):
        assert wg.restored_rect(self._ENTRIES, "floating", 407, 81, [AVAIL]) == (1500, 900, 407, 81)

    def test_offscreen_history_returns_none(self):
        entries = {"main": {"x": 9000, "y": 9000, "width": 800, "height": 600, "screen": "A"},
                   "floating": {"x": 0, "y": 0, "screen": "A"}}
        assert wg.restored_rect(entries, "main", 800, 600, [AVAIL]) is None

    def test_partly_offscreen_history_is_clamped(self):
        entries = {"main": {"x": 1860, "y": 300, "width": 100, "height": 100, "screen": "A"},
                   "floating": {"x": 0, "y": 0, "screen": "A"}}
        assert wg.restored_rect(entries, "main", 100, 100, [AVAIL]) == (1820, 300, 100, 100)


class TestSaveGeometry:
    def test_saved_file_reads_back(self, tmp_path):
        path = tmp_path / "config" / "window_geometry.json"
        assert wg.save_geometry(path, MAIN_RECT, FLOATING_POS, "MONITOR-A", "MONITOR-B") is True
        entries = wg.load_entries(path)
        assert entries["main"] == {"x": 320, "y": 180, "width": 1000, "height": 700, "screen": "MONITOR-A"}
        assert entries["floating"] == {"x": 1450, "y": 980, "screen": "MONITOR-B"}

    def test_saved_file_is_readable_json(self, tmp_path):
        path = tmp_path / "window_geometry.json"
        wg.save_geometry(path, MAIN_RECT, FLOATING_POS)
        text = path.read_text(encoding="utf-8")
        assert "\n  \"windows\"" in text
        assert json.loads(text)["version"] == wg.SCHEMA_VERSION

    def test_uncreatable_directory_returns_false_without_raising(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        assert wg.save_geometry(blocker / "sub" / "window_geometry.json", MAIN_RECT, FLOATING_POS) is False

    def test_replace_failure_keeps_original_content(self, tmp_path, monkeypatch):
        path = tmp_path / "window_geometry.json"
        wg.save_geometry(path, MAIN_RECT, FLOATING_POS)
        before = path.read_text(encoding="utf-8")

        def raise_oserror(*args):
            raise OSError("device busy")

        monkeypatch.setattr(wg.os, "replace", raise_oserror)
        assert wg.save_geometry(path, (1, 2, 300, 400), (5, 6)) is False
        assert path.read_text(encoding="utf-8") == before
        assert not (tmp_path / (path.name + ".tmp")).exists()
