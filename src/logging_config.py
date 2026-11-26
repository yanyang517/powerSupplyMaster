"""Application-wide logging and uncaught-exception reporting.

Importing this module has no side effects.  The application entry point calls
``configure_logging`` once; runtime modules only obtain their own loggers.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO


LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "powerSupplyMaster.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
ROOT_LEVEL = logging.DEBUG
CONSOLE_LEVEL = logging.INFO
FILE_LEVEL = logging.DEBUG
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

_HANDLER_MARKER = "_powerSupplyMaster_logging_handler"
_EXCEPTHOOK_MARKER = "_powerSupplyMaster_excepthook"
_ASYNC_HANDLER_MARKER = "_powerSupplyMaster_asyncio_exception_handler"
_unwritable_directories: set[Path] = set()

logger = logging.getLogger(__name__)


def logs_dir() -> Path:
    """Return the source-tree or frozen-application log directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / LOG_DIR_NAME
    return Path(__file__).resolve().parents[1] / LOG_DIR_NAME


def log_file_path() -> Path:
    return logs_dir() / LOG_FILE_NAME


def _owned_handlers(root: logging.Logger) -> list[logging.Handler]:
    return [handler for handler in root.handlers if getattr(handler, _HANDLER_MARKER, False)]


def _remove_owned_handlers(root: logging.Logger) -> None:
    for handler in _owned_handlers(root):
        root.removeHandler(handler)
        handler.close()


def _warn_file_logging_unavailable(path: Path, error: OSError) -> None:
    """Warn once per unusable directory, without making startup fail."""
    if path in _unwritable_directories:
        return
    _unwritable_directories.add(path)
    logger.warning(
        "File logging disabled: cannot write %s: %s; console logging remains active",
        path,
        error,
    )


def configure_logging(
    *,
    log_dir: Path | None = None,
    stream: TextIO | None = None,
) -> logging.Logger:
    """Install the console and rotating-file handlers exactly once.

    Handlers owned by this module are replaced on reinitialization, while
    handlers installed by a host or test framework are preserved.  An
    unwritable log directory degrades to console-only logging.
    """
    root = logging.getLogger()
    _remove_owned_handlers(root)

    formatter = logging.Formatter(LOG_FORMAT)
    console_handler = logging.StreamHandler(stream)
    console_handler.setLevel(CONSOLE_LEVEL)
    console_handler.setFormatter(formatter)
    setattr(console_handler, _HANDLER_MARKER, True)
    root.addHandler(console_handler)
    root.setLevel(ROOT_LEVEL)

    directory = Path(log_dir) if log_dir is not None else logs_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            directory / LOG_FILE_NAME,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as error:
        _warn_file_logging_unavailable(directory, error)
    else:
        file_handler.setLevel(FILE_LEVEL)
        file_handler.setFormatter(formatter)
        setattr(file_handler, _HANDLER_MARKER, True)
        root.addHandler(file_handler)
        _unwritable_directories.discard(directory)

    return root


def install_excepthook():
    """Log uncaught exceptions, then delegate to the previous stderr hook."""
    current = sys.excepthook
    if getattr(current, _EXCEPTHOOK_MARKER, False):
        return current

    previous = current if callable(current) else sys.__excepthook__

    def excepthook(exc_type, exc_value, exc_traceback) -> None:
        try:
            logger.critical(
                "Uncaught exception",
                exc_info=(exc_type, exc_value, exc_traceback),
            )
        except Exception:
            # Reporting must never replace the original exception or prevent
            # the previous hook from preserving stderr/exit behaviour.
            pass
        previous(exc_type, exc_value, exc_traceback)

    setattr(excepthook, _EXCEPTHOOK_MARKER, True)
    sys.excepthook = excepthook
    return excepthook


def _log_asyncio_context(context: dict) -> None:
    message = context.get("message") or "Unhandled exception in event loop"
    exception = context.get("exception")
    if exception is None:
        logger.critical("Unhandled asyncio event loop error: %s (%r)", message, context)
        return
    logger.critical(
        "Unhandled asyncio exception: %s",
        message,
        exc_info=(type(exception), exception, exception.__traceback__),
    )


def install_asyncio_exception_handler(loop: asyncio.AbstractEventLoop):
    """Log unhandled task/loop errors and retain the loop's previous handler."""
    current = loop.get_exception_handler()
    if getattr(current, _ASYNC_HANDLER_MARKER, False):
        return current

    def exception_handler(active_loop: asyncio.AbstractEventLoop, context: dict) -> None:
        try:
            _log_asyncio_context(context)
        except Exception:
            # A logging failure must not suppress the loop's normal reporting.
            pass
        if previous is None:
            active_loop.default_exception_handler(context)
        else:
            previous(active_loop, context)

    previous = current
    setattr(exception_handler, _ASYNC_HANDLER_MARKER, True)
    loop.set_exception_handler(exception_handler)
    return exception_handler
