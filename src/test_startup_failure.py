"""P0-1 回归：产物落点、缺登记表的退出码，以及 windowed 下启动失败是否可见。

这些用例覆盖两条契约：
1. 冻结运行时从「exe 同级 config/clients.json」读登记表（build_exe.ps1 就是按这个落点打包的）；
2. 登记表缺失时 MUST 仍以退出码 2 拒绝启动（openspec server/client-access-control），
   且错误在没有控制台的情况下也必须被用户看到。

运行方式（在仓库根目录）：python -m pytest src/test_startup_failure.py
"""
import json
import logging
import shutil
import sys
from pathlib import Path

import pytest

import app as app_module

from server import registry as registry_module
from server.registry import ClientRegistry, clients_file_path
from server.session import lease_config

REPO_ROOT = Path(app_module.__file__).resolve().parents[1]
SHIPPED_REGISTRY = REPO_ROOT / "config" / "clients.json"


@pytest.fixture(autouse=True)
def isolate_process_state():
    """登记表与租约是进程级单例：进出用例都归零，免得污染同进程的其他测试文件。"""
    previous_registry = registry_module._registry
    previous_ttl = lease_config.ttl_seconds
    registry_module._registry = None
    yield
    registry_module._registry = previous_registry
    lease_config.ttl_seconds = previous_ttl


@pytest.fixture
def artifact_dir(tmp_path, monkeypatch):
    """把运行时伪装成 PyInstaller onedir 产物：exe 在 dist 下，config/ 与它同级。"""
    app_dir = (tmp_path / "dist" / "powerSupplyMaster").resolve()
    app_dir.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app_dir / "powerSupplyMaster.exe"))
    return app_dir


@pytest.fixture
def dialogs(monkeypatch):
    """打桩弹窗：测试里绝不能真的弹出模态框。"""
    calls = []
    monkeypatch.setattr(app_module, "show_startup_error_dialog",
                        lambda title, text: (calls.append((title, text)), True)[1])
    return calls


def disable_console(monkeypatch):
    """双击 --windowed 产物时的实测状态：sys.stderr 是 None。

    只能在测试函数体内调用：pytest 在 call 阶段开始前会再次接管 sys.stderr，
    放在 fixture 里打的桩会被它覆盖掉（实测）。
    """
    monkeypatch.setattr(sys, "stderr", None)


class TestFrozenArtifactLayout:
    def test_clients_file_path_follows_the_executable(self, artifact_dir):
        assert clients_file_path() == artifact_dir / "config" / "clients.json"

    def test_shipped_registry_loads_from_next_to_the_exe(self, artifact_dir):
        """产物目录内的 config/clients.json 就是冻结运行时实际加载的那一份。"""
        target = artifact_dir / "config" / "clients.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SHIPPED_REGISTRY, target)

        registry = ClientRegistry.load()

        assert registry.path == target
        assert len(registry) >= 1

    def test_repo_ships_a_registry_for_the_artifact(self):
        """build_exe.ps1 的种子来源必须存在，否则产物永远起不来。"""
        assert SHIPPED_REGISTRY.is_file()
        assert json.loads(SHIPPED_REGISTRY.read_text(encoding="utf-8"))["clients"]


class TestMissingRegistryStaysFatal:
    def test_exit_code_2_and_the_error_names_the_path(self, tmp_path, caplog):
        missing = tmp_path / "absent.json"

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit) as excinfo:
                app_module.bootstrap_access(str(missing), 120.0)

        assert excinfo.value.code == 2
        assert "refusing to start" in caplog.text
        assert missing.name in caplog.text
        assert registry_module._registry is None, "拒绝启动后不能留下半初始化的登记表"


class TestStartupFailureIsVisibleWithoutAConsole:
    def test_frozen_and_headless_writes_a_log_then_pops_once(self, artifact_dir, dialogs, monkeypatch):
        disable_console(monkeypatch)
        missing = artifact_dir / "config" / "clients.json"

        with pytest.raises(SystemExit) as excinfo:
            app_module.bootstrap_access(str(missing), 120.0)

        assert excinfo.value.code == 2
        log_path = artifact_dir / "logs" / "startup_error.log"
        text = log_path.read_text(encoding="utf-8")
        assert "client registry not found" in text
        assert str(missing) in text
        assert len(dialogs) == 1
        assert str(log_path) in dialogs[0][1], "弹窗要告诉用户去哪儿找详情"

    def test_frozen_with_a_console_logs_but_stays_quiet(self, artifact_dir, dialogs):
        """CI/命令行里跑 exe：stderr 已经看得见，不该被模态框卡住。"""
        app_module.report_startup_failure("boom")

        assert (artifact_dir / "logs" / "startup_error.log").is_file()
        assert dialogs == []

    def test_dev_run_without_console_only_pops(self, dialogs, tmp_path, monkeypatch):
        disable_console(monkeypatch)
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.chdir(tmp_path)
        app_module.report_startup_failure("boom")

        assert len(dialogs) == 1
        assert not (tmp_path / "logs").exists(), "非冻结运行不该往工作目录扔日志"

    def test_repeated_failures_append(self, artifact_dir, dialogs, monkeypatch):
        disable_console(monkeypatch)
        app_module.report_startup_failure("first")
        app_module.report_startup_failure("second")

        lines = (artifact_dir / "logs" / "startup_error.log").read_text(encoding="utf-8").splitlines()
        assert [line.split("] ", 1)[1] for line in lines] == ["first", "second"]

    def test_unwritable_log_dir_does_not_silence_the_dialog(self, tmp_path, dialogs, monkeypatch):
        """装在只读位置时文件写不了：弹窗必须补位，否则又退回「双击没反应」。"""
        disable_console(monkeypatch)
        blocker = tmp_path / "blocker.txt"
        blocker.write_text("not a directory", encoding="utf-8")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(blocker / "powerSupplyMaster.exe"))

        app_module.report_startup_failure("still reported")

        assert len(dialogs) == 1
        assert "still reported" in dialogs[0][1]
        assert "详情已记录到" not in dialogs[0][1], "没写成的日志不能在弹窗里空头承诺"

    def test_dialog_helper_is_inert_off_windows(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.setattr(sys, "platform", "linux")
        assert app_module.show_startup_error_dialog("t", "text") is False


class TestLoggingSurvivesMissingStderr:
    def test_logger_error_does_not_raise_without_stderr(self, monkeypatch, caplog):
        """windowed 下 logging 只丢输出、不崩（实测 CPython 3.13），这条兜底防它变成崩。"""
        disable_console(monkeypatch)
        with caplog.at_level(logging.ERROR):
            app_module.logger.error("dropped, but must not raise")
        assert "must not raise" in caplog.text
