"""Persist serial port selection and automatic connection preferences.

The file lives beside the executable when frozen and in the repository's config
directory when running from source. A remembered port is only a selection hint:
it is used at startup only when the current port enumeration still contains it.
"""

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
CONFIG_DIR_NAME = "config"
SETTINGS_FILE_NAME = "serial_port.json"


@dataclass(frozen=True)
class ConnectionSettings:
    port: str | None = None
    auto_connect: bool = False


def settings_file_path(module_file: str = __file__) -> Path:
    """Return the absolute settings path, independent of the process cwd."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_DIR_NAME / SETTINGS_FILE_NAME
    return Path(module_file).resolve().parents[1] / CONFIG_DIR_NAME / SETTINGS_FILE_NAME


def _clean_port(port) -> str | None:
    if not isinstance(port, str) or not port.strip():
        return None
    return port.strip()


def load_settings(path: Path | None = None) -> ConnectionSettings:
    """Read connection preferences; unusable history falls back to safe defaults."""
    path = Path(path) if path is not None else settings_file_path()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ConnectionSettings()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("serial port settings unreadable, using defaults: %s (%s)", path, exc)
        return ConnectionSettings()

    if not isinstance(document, dict):
        logger.warning("serial port settings is not an object, using defaults: %s", path)
        return ConnectionSettings()
    if document.get("version") != SCHEMA_VERSION:
        logger.warning("serial port settings version %r unsupported, using defaults: %s",
                       document.get("version"), path)
        return ConnectionSettings()

    raw_port = document.get("port")
    port = _clean_port(raw_port)
    if raw_port is not None and port is None:
        logger.warning("serial port settings 'port' is not a non-empty string: %r", raw_port)

    auto_connect = document.get("auto_connect", False)
    if not isinstance(auto_connect, bool):
        logger.warning("serial port settings 'auto_connect' is not a bool: %r", auto_connect)
        auto_connect = False
    return ConnectionSettings(port=port, auto_connect=auto_connect)


def save_settings(settings: ConnectionSettings, path: Path | None = None) -> bool:
    """Atomically write connection preferences; failures are logged, never raised."""
    path = Path(path) if path is not None else settings_file_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump({
                "version": SCHEMA_VERSION,
                "port": _clean_port(settings.port),
                "auto_connect": bool(settings.auto_connect),
            }, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("failed to write serial port settings to %s (%s)", path, exc)
        try:
            if tmp.exists():
                os.remove(tmp)
        except OSError as cleanup_exc:
            logger.warning("failed to remove temporary serial port settings %s (%s)", tmp, cleanup_exc)
        return False
    return True


def load_last_port(path: Path | None = None) -> str | None:
    """Backward-compatible helper for callers that only need the remembered port."""
    return load_settings(path).port


def save_last_port(port: str, path: Path | None = None) -> bool:
    """Remember a port without discarding the existing automatic connection choice."""
    port = _clean_port(port)
    if port is None:
        logger.warning("refusing to remember an empty serial port")
        return False
    current = load_settings(path)
    return save_settings(ConnectionSettings(port=port, auto_connect=current.auto_connect), path)


def choose_port_index(available_ports: list[str], last_port: str | None,
                      usb_index: int | None = None) -> int | None:
    """Prefer an available remembered port, then a USB port, else the first item."""
    if last_port:
        target = last_port.casefold()
        for index, port in enumerate(available_ports):
            if port.casefold() == target:
                return index
    if (isinstance(usb_index, int) and not isinstance(usb_index, bool)
            and 0 <= usb_index < len(available_ports)):
        return usb_index
    return None
