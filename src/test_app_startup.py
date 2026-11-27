"""启动引导测试：客户端登记表缺失或损坏时拒绝启动（任务 2.3）。

运行方式（在仓库根目录）：python -m pytest src/test_app_startup.py
"""
import json
from types import SimpleNamespace

import pytest

import app as app_module
import version as version_module

from server.registry import get_registry
from server.runtime_config import runtime_config
from server.session import lease_config


@pytest.fixture
def registry_file(tmp_path):
    path = tmp_path / "clients.json"
    path.write_text(json.dumps(
        {"schema_version": 1, "clients": {"probe": {"tier": "L2", "name": "Probe"}}}
    ), encoding="utf-8")
    return path


class TestBootstrapAccess:
    def test_explicit_clients_path_is_honoured(self, registry_file, monkeypatch):
        monkeypatch.setattr(app_module, "use_registry", lambda reg: None)
        loaded = app_module.bootstrap_access(str(registry_file), 45.0)
        assert [p.client_id for p in loaded] == ["probe"]
        assert lease_config.ttl_seconds == 45.0

    def test_missing_registry_exits_with_code_2(self, tmp_path):
        with pytest.raises(SystemExit) as e:
            app_module.bootstrap_access(str(tmp_path / "absent.json"), 120.0)
        assert e.value.code == 2

    def test_broken_registry_exits_with_code_2(self, tmp_path):
        bad = tmp_path / "clients.json"
        bad.write_text("{oops", encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            app_module.bootstrap_access(str(bad), 120.0)
        assert e.value.code == 2

    def test_injected_registry_is_reachable_by_get_registry(self, registry_file):
        app_module.bootstrap_access(str(registry_file), 120.0)
        assert get_registry().get("probe") is not None

    @pytest.mark.parametrize("ttl", [0.0, -1.0, float("nan"), float("inf"), float("-inf")])
    def test_invalid_lease_ttl_is_rejected_before_mutating_config(self, monkeypatch, ttl):
        monkeypatch.setattr(lease_config, "ttl_seconds", 120.0)
        monkeypatch.setattr(app_module, "report_startup_failure", lambda message: None)

        with pytest.raises(SystemExit) as caught:
            app_module.bootstrap_access("not-read.json", ttl)

        assert caught.value.code == 2
        assert lease_config.ttl_seconds == 120.0

    def test_default_arg_loads_shipped_registry(self):
        """仓库自带的 config/clients.json 必须可用，否则全新检出无法启动。"""
        registry = app_module.bootstrap_access(None, 120.0)
        assert len(registry) >= 1


class TestParseArgs:
    def test_new_flags_present_with_defaults(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["app"])
        args = app_module.parse_args()
        assert args.clients is None
        assert args.lease_ttl == pytest.approx(120.0)
        assert args.no_update_check is False

    def test_new_flags_accept_values(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["app", "--clients", "c.json", "--lease-ttl", "30"])
        args = app_module.parse_args()
        assert args.clients == "c.json" and args.lease_ttl == 30.0

    def test_update_check_can_be_disabled(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["app", "--no-update-check"])
        assert app_module.parse_args().no_update_check is True

    @pytest.mark.parametrize("flag", ["--max-voltage", "--max-current"])
    @pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-1"])
    def test_invalid_control_limits_are_rejected(self, monkeypatch, flag, value):
        monkeypatch.setattr("sys.argv", ["app", flag, value])

        with pytest.raises(SystemExit) as caught:
            app_module.parse_args()

        assert caught.value.code == 2

    def test_zero_control_limits_are_valid(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["app", "--max-voltage", "0", "--max-current", "0"])
        args = app_module.parse_args()
        assert args.max_voltage == 0.0
        assert args.max_current == 0.0

    @pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
    def test_invalid_lease_ttl_is_rejected(self, monkeypatch, value):
        monkeypatch.setattr("sys.argv", ["app", "--lease-ttl", value])

        with pytest.raises(SystemExit) as caught:
            app_module.parse_args()

        assert caught.value.code == 2


@pytest.mark.parametrize("field,value", [
    ("max_voltage", float("nan")),
    ("max_voltage", float("inf")),
    ("max_current", float("-inf")),
    ("max_current", -1.0),
])
def test_startup_revalidates_limits_before_bootstrapping(monkeypatch, field, value):
    monkeypatch.setattr(runtime_config, "max_voltage", 30.0)
    monkeypatch.setattr(runtime_config, "max_current", 5.0)
    monkeypatch.setattr(app_module, "configure_logging", lambda: None)
    monkeypatch.setattr(app_module, "install_excepthook", lambda: None)
    monkeypatch.setattr(app_module, "report_startup_failure", lambda message: None)
    values = {"max_voltage": 30.0, "max_current": 5.0, field: value}
    monkeypatch.setattr(app_module, "parse_args", lambda: SimpleNamespace(**values))
    monkeypatch.setattr(
        app_module, "bootstrap_access",
        lambda *args, **kwargs: pytest.fail("invalid limits must stop startup"),
    )

    with pytest.raises(SystemExit) as caught:
        app_module.main()

    assert caught.value.code == 2
    assert runtime_config.max_voltage == 30.0
    assert runtime_config.max_current == 5.0


class TestVersionLogging:
    def test_startup_log_contains_the_version(self, caplog):
        """启动日志必须能看到版本，否则用户报障时无从判断跑的是哪一版。"""
        import logging

        with caplog.at_level(logging.INFO, logger="app"):
            app_module.logger.info(version_module.summary())
        assert version_module.__version__ in caplog.text


class TestIconDegradation:
    """图标资源缺失不得影响启动（design.md D4）。

    失败形态必须只是"没有图标"：打包后资源路径一变，最坏可以是难看，不能是不能用。
    """

    @pytest.fixture
    def qapp(self):
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    @pytest.fixture
    def empty_resources(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module.icons, "resources_dir", lambda: tmp_path / "resources")
        monkeypatch.setattr("views.window_geometry.geometry_file_path",
                            lambda: tmp_path / "window_positions.json")
        return tmp_path

    def test_missing_mark_yields_null_but_usable_window_icon(self, empty_resources, qapp):
        icon = app_module.icons.app_icon()
        assert icon.isNull()
        qapp.setWindowIcon(icon)  # 与 app.main() 里同一句调用，不得抛

    def test_floating_window_still_builds_without_resources(self, empty_resources, qapp):
        """设图标不得改变悬浮窗的窗口属性：它必须还是无边框 + 置顶。"""
        from PySide6.QtCore import Qt

        from views.floating_window import FloatingWindow

        window = FloatingWindow()
        assert window.windowIcon().isNull()
        flags = window.windowFlags()
        assert flags & Qt.WindowType.FramelessWindowHint
        assert flags & Qt.WindowType.WindowStaysOnTopHint
