"""Persist and restore main/floating window geometry in a project-local JSON file.

The pure functions take explicit (x, y, w, h) tuples so they can be unit tested
without a QApplication; only available_rects()/screen_name() touch Qt.
"""

import json
import logging
import os
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QScreen

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
CONFIG_DIR_NAME = "config"
GEOMETRY_FILE_NAME = "window_geometry.json"
FLOATING_MARGIN = 24
USABLE_INTERSECT_RATIO = 0.5

_REQUIRED_FIELDS = {
    "main": ("x", "y", "width", "height"),
    "floating": ("x", "y"),
}
_MIN_SIZE_FIELDS = ("width", "height")


def geometry_file_path(module_file: str = __file__) -> Path:
    """Absolute path of the geometry file, independent of the process cwd.

    This module lives in <repo>/src/views, so two levels up is the repo root.
    When frozen by PyInstaller the module path points inside the bundle, so the
    config sits next to the executable instead (writable, survives upgrades).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_DIR_NAME / GEOMETRY_FILE_NAME
    return Path(module_file).resolve().parents[2] / CONFIG_DIR_NAME / GEOMETRY_FILE_NAME


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_window(name: str, entry) -> dict | None:
    if not isinstance(entry, dict):
        logger.warning("window geometry %r is not an object: %r", name, entry)
        return None
    fields = _REQUIRED_FIELDS[name]
    for field in fields:
        if not _is_int(entry.get(field)):
            logger.warning("window geometry %r field %r is not an int: %r", name, field, entry.get(field))
            return None
    for field in _MIN_SIZE_FIELDS:
        if field in fields and entry[field] <= 0:
            logger.warning("window geometry %r field %r must be positive: %r", name, field, entry[field])
            return None
    screen = entry.get("screen")
    if screen is not None and not isinstance(screen, str):
        logger.warning("window geometry %r field 'screen' is not a string: %r", name, screen)
        return None
    return {field: entry[field] for field in fields} | {"screen": screen}


def load_entries(path) -> dict | None:
    """Return {"main": {...}, "floating": {...}} or None when history is unusable."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("window geometry file missing, using default layout: %s", path)
        return None
    except OSError as exc:
        logger.warning("window geometry file unreadable, using default layout: %s (%s)", path, exc)
        return None

    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("window geometry file is not valid JSON, using default layout: %s (%s)", path, exc)
        return None

    if not isinstance(document, dict):
        logger.warning("window geometry file is not an object, using default layout: %s", path)
        return None
    if document.get("version") != SCHEMA_VERSION:
        logger.warning("window geometry file version %r unsupported, using default layout: %s",
                       document.get("version"), path)
        return None

    windows = document.get("windows")
    if not isinstance(windows, dict):
        logger.warning("window geometry file has no 'windows' object, using default layout: %s", path)
        return None

    entries = {}
    for name in _REQUIRED_FIELDS:
        entry = _validate_window(name, windows.get(name))
        if entry is None:
            return None
        entries[name] = entry
    return entries


def _intersect_area(left: tuple, right: tuple) -> int:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    x0, y0 = max(lx, rx), max(ly, ry)
    x1, y1 = min(lx + lw, rx + rw), min(ly + lh, ry + rh)
    if x1 <= x0 or y1 <= y0:
        return 0
    return (x1 - x0) * (y1 - y0)


def is_rect_usable(rect: tuple, available_rects: list) -> bool:
    if not available_rects:
        return False
    area = rect[2] * rect[3]
    if area <= 0:
        return False
    return any(_intersect_area(rect, avail) / area >= USABLE_INTERSECT_RATIO for avail in available_rects)


def clamp_into(rect: tuple, available_rect: tuple) -> tuple:
    """Move rect's top-left so it is reachable inside available_rect."""
    x, y, w, h = rect
    ax, ay, aw, ah = available_rect
    nx = min(max(x, ax), ax + max(0, aw - w))
    ny = min(max(y, ay), ay + max(0, ah - h))
    return (nx, ny, w, h)


def default_main_rect(available_rect: tuple, width: int, height: int) -> tuple:
    ax, ay, aw, ah = available_rect
    return (ax + max(0, (aw - width) // 2), ay + max(0, (ah - height) // 2), width, height)


def default_floating_pos(available_rect: tuple, width: int, height: int,
                         margin: int = FLOATING_MARGIN) -> tuple:
    ax, ay, aw, ah = available_rect
    bottom_right = (ax + aw - width - margin, ay + ah - height - margin, width, height)
    return clamp_into(bottom_right, available_rect)[:2]


def choose_available_rect(rect: tuple, available_rects: list):
    """The screen available area overlapping rect most, else the first candidate."""
    if not available_rects:
        return None
    return max(available_rects, key=lambda avail: _intersect_area(rect, avail))


def restored_rect(entries, name: str, width: int = None, height: int = None,
                  screen_rects: list | None = None):
    """Clamped rect from history, or None when that window has no usable history.

    A window whose size is fixed by the UI (the floating window) has no stored
    size, so width/height supply it; a stored size wins for resizable windows.
    """
    if not entries:
        return None
    entry = entries[name]
    rect = (entry["x"], entry["y"], entry.get("width", width), entry.get("height", height))
    rects = available_rects(entry["screen"]) if screen_rects is None else screen_rects
    if not is_rect_usable(rect, rects):
        logger.warning("stored %s geometry %r is off every screen, using default layout", name, rect)
        return None
    return clamp_into(rect, choose_available_rect(rect, rects))


def available_rects(preferred_name: str | None = None) -> list:
    """Qt-facing: available areas ranked preferred screen, primary, others."""
    screens = list(QGuiApplication.screens())
    if not screens:
        return []
    primary = QGuiApplication.primaryScreen()

    def rank(screen) -> int:
        if preferred_name is not None and screen.name() == preferred_name:
            return 0
        if primary is not None and screen is primary:
            return 1
        return 2

    screens.sort(key=rank)
    return [s.availableGeometry().getRect() for s in screens]


def primary_available_rect():
    """Available area the default layout is computed against, or None without screens."""
    rects = available_rects()
    return rects[0] if rects else None


def screen_name(widget):
    screen = widget.screen()
    if not isinstance(screen, QScreen):
        return None
    return screen.name()


def save_geometry(path, main_rect: tuple, floating_pos: tuple,
                  main_screen: str | None = None, floating_screen: str | None = None) -> bool:
    """Atomically write the geometry history; failures are logged, never raised."""
    path = Path(path)
    document = {
        "version": SCHEMA_VERSION,
        "windows": {
            "main": {
                "x": int(main_rect[0]),
                "y": int(main_rect[1]),
                "width": int(main_rect[2]),
                "height": int(main_rect[3]),
                "screen": main_screen,
            },
            "floating": {
                "x": int(floating_pos[0]),
                "y": int(floating_pos[1]),
                "screen": floating_screen,
            },
        },
    }
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("failed to save window geometry to %s (%s)", path, exc)
        try:
            if tmp.exists():
                os.remove(tmp)
        except OSError as cleanup_exc:
            logger.warning("failed to remove temporary window geometry file %s (%s)", tmp, cleanup_exc)
        return False
    return True
