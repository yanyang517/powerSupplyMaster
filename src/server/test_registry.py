"""server/client-access-control 登记表测试：加载、校验与原子写回。

运行方式（在仓库根目录）：python -m pytest src/server/test_registry.py
"""
import json

import pytest

from .registry import (
    CLIENTS_FILE_NAME,
    SCHEMA_VERSION,
    ClientRegistry,
    Principal,
    RegistryError,
    Tier,
    clients_file_path,
    parse_registry,
)


@pytest.fixture
def registry_path(tmp_path):
    return tmp_path / "config" / CLIENTS_FILE_NAME


def make_registry(registry_path, clients: dict) -> ClientRegistry:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "clients": clients}, ensure_ascii=False),
        encoding="utf-8",
    )
    return ClientRegistry.load(registry_path)


class TestTier:
    def test_ordering_and_lease(self):
        assert Tier.L0 < Tier.L1 < Tier.L2
        assert not Tier.L0.needs_lease
        assert Tier.L1.needs_lease and Tier.L2.needs_lease

    def test_parse_accepts_case_insensitive_names(self):
        assert Tier.parse("l1") is Tier.L1
        assert Tier.parse("L2") is Tier.L2

    def test_parse_rejects_unknown(self):
        with pytest.raises(RegistryError):
            Tier.parse("L3")
        with pytest.raises(RegistryError):
            Tier.parse(1)


class TestLoad:
    def test_valid_registry_loads(self, registry_path):
        reg = make_registry(registry_path, {"mcp-bridge": {"tier": "L1", "name": "AI 助手"}})
        principal = reg.get("mcp-bridge")
        assert principal == Principal("mcp-bridge", Tier.L1, "AI 助手")
        assert len(reg) == 1

    def test_missing_file_raises_not_empty_table(self, registry_path):
        with pytest.raises(RegistryError, match="not found"):
            ClientRegistry.load(registry_path)

    def test_broken_json_raises(self, registry_path):
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text("{not json", encoding="utf-8")
        with pytest.raises(RegistryError, match="not valid JSON"):
            ClientRegistry.load(registry_path)

    def test_empty_clients_is_valid(self, registry_path):
        reg = make_registry(registry_path, {})
        assert len(reg) == 0
        assert reg.get("anyone") is None

    def test_unknown_tier_rejected(self, registry_path):
        with pytest.raises(RegistryError, match="unknown tier"):
            make_registry(registry_path, {"x": {"tier": "L9", "name": "n"}})

    def test_missing_name_rejected(self, registry_path):
        with pytest.raises(RegistryError, match="'name'"):
            make_registry(registry_path, {"x": {"tier": "L0"}})

    def test_credential_fields_rejected(self, registry_path):
        with pytest.raises(RegistryError, match="allow-list"):
            make_registry(registry_path, {"x": {"tier": "L0", "name": "n", "password": "hunter2"}})

    def test_wrong_schema_version_rejected(self, registry_path):
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(json.dumps({"schema_version": 99, "clients": {}}), encoding="utf-8")
        with pytest.raises(RegistryError, match="schema_version"):
            ClientRegistry.load(registry_path)

    def test_clients_must_be_object(self):
        with pytest.raises(RegistryError, match="keyed by client_id"):
            parse_registry('{"clients": []}', "<test>")


class TestPersistence:
    def test_add_survives_reload(self, registry_path):
        reg = make_registry(registry_path, {})
        assert reg.add(Principal("probe", Tier.L0, "probe")) is True
        reloaded = ClientRegistry.load(registry_path)
        assert reloaded.get("probe") == Principal("probe", Tier.L0, "probe")

    def test_add_idempotent_without_rewrite(self, registry_path):
        reg = make_registry(registry_path, {"probe": {"tier": "L0", "name": "probe"}})
        assert reg.add(Principal("probe", Tier.L0, "probe")) is False

    def test_save_leaves_no_temp_file(self, registry_path):
        reg = make_registry(registry_path, {})
        reg.add(Principal("a", Tier.L1, "A"))
        assert list(registry_path.parent.glob("*.tmp")) == []

    def test_entries_are_stably_ordered(self, registry_path):
        reg = make_registry(registry_path, {"b": {"tier": "L0", "name": "B"}, "a": {"tier": "L0", "name": "A"}})
        reg.add(Principal("c", Tier.L2, "C"))
        assert [p.client_id for p in reg] == ["a", "b", "c"]

    def test_existing_file_untouched_on_failed_write(self, registry_path, monkeypatch):
        reg = make_registry(registry_path, {"keep": {"tier": "L0", "name": "keep"}})
        monkeypatch.setattr("os.replace", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
        with pytest.raises(OSError):
            reg.add(Principal("new", Tier.L1, "new"))
        assert "keep" in registry_path.read_text(encoding="utf-8")


class TestPathResolution:
    def test_default_path_is_project_config_dir(self):
        path = clients_file_path()
        assert path.name == CLIENTS_FILE_NAME
        assert path.parent.name == "config"
        assert path.is_absolute()
