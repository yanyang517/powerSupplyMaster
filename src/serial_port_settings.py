"""Remember the last successfully opened serial port.

The file lives beside the executable when frozen and in the repository's config
directory when running from source. A remembered port is only a selection hint:
it is used at startup only when the current port enumeration still contains it.
"""

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
CONFIG_DIR_NAME = "config"
SETTINGS_FILE_NAME = "serial_port.json"


def settings_file_path(module_file: str = __file__) -> Path:
    """Return the absolute settings path, independent of the process cwd."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_DIR_NAME / SETTINGS_FILE_NAME
    return Path(module_file).resolve().parents[1] / CONFIG_DIR_NAME / SETTINGS_FILE_NAME


def load_last_port(path: Path | None = None) -> str | None:
    """Read the remembered port; missing or unusable history means no preference."""
    path = Path(path) if path is not None else settings_file_path()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("serial port settings unreadable, using default selection: %s (%s)", path, exc)
        return None

    if not isinstance(document, dict):
        logger.warning("serial port settings is not an object, using default selection: %s", path)
        return None
    if document.get("version") != SCHEMA_VERSION:
        logger.warning("serial port settings version %r unsupported, using default selection: %s",
                       document.get("version"), path)
        return None

    port = document.get("port")
    if not isinstance(port, str) or not port.strip():
        logger.warning("serial port settings 'port' is not a non-empty string: %r", port)
        return None
    return port.strip()


def save_last_port(port: str, path: Path | None = None) -> bool:
    """Atomically remember a successfully opened port; never block connection."""
    if not isinstance(port, str) or not port.strip():
        logger.warning("refusing to remember an empty serial port")
        return False

    path = Path(path) if path is not None else settings_file_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump({"version": SCHEMA_VERSION, "port": port.strip()},
                      handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("failed to remember serial port %r in %s (%s)", port, path, exc)
        try:
            if tmp.exists():
                os.remove(tmp)
        except OSError as cleanup_exc:
            logger.warning("failed to remove temporary serial port settings %s (%s)", tmp, cleanup_exc)
        return False
    logger.info("remembered serial port %s", port.strip())
    return True


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
