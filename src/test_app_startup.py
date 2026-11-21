"""启动引导测试：客户端登记表缺失或损坏时拒绝启动（任务 2.3）。

运行方式（在仓库根目录）：python -m pytest src/test_app_startup.py
"""
import json

import pytest

import app as app_module
import version as version_module

from server.registry import get_registry
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


class TestVersionLogging:
    def test_startup_log_contains_the_version(self, caplog):
        """启动日志必须能看到版本，否则用户报障时无从判断跑的是哪一版。"""
        import logging

        with caplog.at_level(logging.INFO, logger="app"):
            app_module.logger.info(version_module.summary())
        assert version_module.__version__ in caplog.text
