"""Focused regressions for application logging and crash fallback."""
import asyncio
import gc
import importlib
import io
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

import app as app_module
import logging_config as logging_module


@pytest.fixture(autouse=True)
def isolate_global_logging():
    """Keep process-wide logging and excepthook changes inside each test."""
    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level
    previous_excepthook = sys.excepthook
    previous_unwritable = set(logging_module._unwritable_directories)
    yield
    for handler in logging_module._owned_handlers(root):
        root.removeHandler(handler)
        handler.close()
    root.handlers[:] = previous_handlers
    root.setLevel(previous_level)
    sys.excepthook = previous_excepthook
    logging_module._unwritable_directories.clear()
    logging_module._unwritable_directories.update(previous_unwritable)


def _file_handler(root: logging.Logger) -> RotatingFileHandler:
    handlers = [
        handler for handler in logging_module._owned_handlers(root)
        if isinstance(handler, RotatingFileHandler)
    ]
    assert len(handlers) == 1
    return handlers[0]


def _flush(root: logging.Logger) -> None:
    for handler in root.handlers:
        handler.flush()


def test_source_logs_are_relative_to_repo_not_working_directory(tmp_path, monkeypatch):
    source_root = tmp_path / "source-tree"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(
        logging_module, "__file__", str(source_root / "src" / "logging_config.py")
    )
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(elsewhere)

    root = logging_module.configure_logging(stream=io.StringIO())

    expected = source_root / "logs" / logging_module.LOG_FILE_NAME
    assert logging_module.log_file_path() == expected
    assert Path(_file_handler(root).baseFilename) == expected
    assert expected.parent.is_dir()
    assert not (elsewhere / "logs").exists()


def test_frozen_logs_are_next_to_executable(tmp_path, monkeypatch):
    app_dir = tmp_path / "dist" / "powerSupplyMaster"
    app_dir.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app_dir / "powerSupplyMaster.exe"))

    root = logging_module.configure_logging(stream=io.StringIO())

    expected = app_dir / "logs" / logging_module.LOG_FILE_NAME
    assert logging_module.log_file_path() == expected
    assert Path(_file_handler(root).baseFilename) == expected


def test_missing_stderr_does_not_break_file_logging(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    root = logging_module.configure_logging(log_dir=tmp_path)

    root.info("windowed marker")
    _flush(root)

    text = Path(_file_handler(root).baseFilename).read_text(encoding="utf-8")
    assert "windowed marker" in text


def test_reinitialization_and_reload_do_not_duplicate_handlers(tmp_path, monkeypatch):
    root = logging.getLogger()
    foreign_handler = logging.NullHandler()
    root.addHandler(foreign_handler)
    monkeypatch.setattr(logging_module, "LOG_MAX_BYTES", 256)
    monkeypatch.setattr(logging_module, "LOG_BACKUP_COUNT", 2)
    stream = io.StringIO()

    logging_module.configure_logging(log_dir=tmp_path, stream=stream)
    first_handlers = logging_module._owned_handlers(root)
    importlib.reload(logging_module)
    # Reload restores defaults; set the small rotation limits again.
    monkeypatch.setattr(logging_module, "LOG_MAX_BYTES", 256)
    monkeypatch.setattr(logging_module, "LOG_BACKUP_COUNT", 2)
    logging_module.configure_logging(log_dir=tmp_path, stream=stream)

    owned = logging_module._owned_handlers(root)
    assert len(owned) == 2
    assert foreign_handler in root.handlers
    assert all(handler._closed for handler in first_handlers)
    file_handler = _file_handler(root)
    assert file_handler.maxBytes == 256
    assert file_handler.backupCount == 2
    assert file_handler.level == logging_module.FILE_LEVEL
    console_handler = next(
        handler for handler in owned if not isinstance(handler, RotatingFileHandler)
    )
    assert console_handler.level == logging_module.CONSOLE_LEVEL
    assert root.level == logging_module.ROOT_LEVEL

    root.debug("debug marker")
    root.info("info marker")
    _flush(root)
    text = Path(file_handler.baseFilename).read_text(encoding="utf-8")
    assert "debug marker" in text
    assert "info marker" in text
    assert "debug marker" not in stream.getvalue()
    assert "info marker" in stream.getvalue()

    file_path = Path(file_handler.baseFilename)
    for index in range(12):
        root.info("rotation payload %d %s", index, "x" * 160)
    _flush(root)
    assert list(file_path.parent.glob(f"{file_path.name}.*"))
    assert len(list(file_path.parent.glob(f"{file_path.name}.*"))) <= 2


def test_unwritable_log_directory_degrades_to_console_once(tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("blocked", encoding="utf-8")
    log_dir = blocker / "logs"
    stream = io.StringIO()
    root = logging.getLogger()

    logging_module.configure_logging(log_dir=log_dir, stream=stream)
    logging_module.configure_logging(log_dir=log_dir, stream=stream)
    root.info("application still runs")
    _flush(root)

    owned = logging_module._owned_handlers(root)
    assert len(owned) == 1
    assert isinstance(owned[0], logging.StreamHandler)
    assert not isinstance(owned[0], RotatingFileHandler)
    assert stream.getvalue().count("File logging disabled") == 1
    assert "application still runs" in stream.getvalue()
    assert not log_dir.exists()


def test_excepthook_logs_full_traceback_and_preserves_stderr(tmp_path, monkeypatch, capsys):
    root = logging_module.configure_logging(log_dir=tmp_path, stream=io.StringIO())
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    hook = logging_module.install_excepthook()
    assert logging_module.install_excepthook() is hook

    try:
        raise ValueError("uncaught boom")
    except ValueError:
        exc_info = sys.exc_info()
    sys.excepthook(*exc_info)
    _flush(root)

    text = Path(_file_handler(root).baseFilename).read_text(encoding="utf-8")
    assert text.count("Uncaught exception") == 1
    assert "Traceback (most recent call last)" in text
    assert "test_excepthook_logs_full_traceback_and_preserves_stderr" in text
    assert "ValueError: uncaught boom" in text
    stderr = capsys.readouterr().err
    assert "Traceback (most recent call last)" in stderr
    assert "ValueError: uncaught boom" in stderr


def test_asyncio_handler_logs_unretrieved_task_and_preserves_previous_handler(tmp_path):
    root = logging_module.configure_logging(log_dir=tmp_path, stream=io.StringIO())
    loop = asyncio.new_event_loop()
    contexts = []

    def previous_handler(active_loop, context):
        assert active_loop is loop
        contexts.append(context)

    try:
        loop.set_exception_handler(previous_handler)
        handler = logging_module.install_asyncio_exception_handler(loop)
        assert loop.get_exception_handler() is handler
        assert logging_module.install_asyncio_exception_handler(loop) is handler

        async def fail():
            raise RuntimeError("task boom")

        async def scenario():
            asyncio.create_task(fail())
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        loop.run_until_complete(scenario())
        gc.collect()

        assert len(contexts) == 1
        assert contexts[0]["message"] == "Task exception was never retrieved"
        _flush(root)
        text = Path(_file_handler(root).baseFilename).read_text(encoding="utf-8")
        assert "Unhandled asyncio exception" in text
        assert "Traceback (most recent call last)" in text
        assert "RuntimeError: task boom" in text
    finally:
        loop.close()


def test_headless_runner_installs_handler_on_running_loop(monkeypatch):
    seen = []

    async def fake_server_main(host):
        seen.append(asyncio.get_running_loop().get_exception_handler())

    monkeypatch.setattr(app_module, "server_main", fake_server_main)
    asyncio.run(app_module.run_server())

    assert len(seen) == 1
    assert getattr(seen[0], logging_module._ASYNC_HANDLER_MARKER, False)


def test_logging_initialization_failure_is_reported_and_reraised(monkeypatch):
    reports = []

    def fail_logging(**kwargs):
        raise OSError("logging unavailable")

    monkeypatch.setattr(app_module, "configure_logging", fail_logging)
    monkeypatch.setattr(app_module, "report_startup_failure", reports.append)

    with pytest.raises(OSError, match="logging unavailable"):
        app_module.main([])

    assert reports == ["logging initialization failed: logging unavailable"]
