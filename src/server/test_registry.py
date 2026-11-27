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
from .runtime_config import MAX_CLIENT_ID_LENGTH, MAX_REGISTRY_CLIENTS


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

    def test_registry_keys_are_normalized_before_lookup(self, registry_path):
        reg = make_registry(registry_path, {"  mcp-bridge  ": {"tier": "L1", "name": "AI 助手"}})
        assert reg.get("mcp-bridge") == Principal("mcp-bridge", Tier.L1, "AI 助手")
        assert [p.client_id for p in reg] == ["mcp-bridge"]

    def test_normalized_key_collisions_are_rejected(self, registry_path):
        with pytest.raises(RegistryError, match="duplicate normalized client id"):
            make_registry(registry_path, {
                "probe": {"tier": "L0", "name": "one"},
                " probe ": {"tier": "L1", "name": "two"},
            })

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


class TestLimits:
    def test_client_id_at_length_limit_is_accepted(self, registry_path):
        client_id = "x" * MAX_CLIENT_ID_LENGTH
        reg = make_registry(registry_path, {client_id: {"tier": "L0", "name": "Boundary"}})
        assert reg.get(client_id) == Principal(client_id, Tier.L0, "Boundary")

    def test_client_id_over_length_limit_is_rejected_on_load(self, registry_path):
        with pytest.raises(RegistryError, match=f"at most {MAX_CLIENT_ID_LENGTH}"):
            make_registry(registry_path, {
                "x" * (MAX_CLIENT_ID_LENGTH + 1): {"tier": "L0", "name": "Too long"}
            })

    def test_client_id_over_length_limit_is_rejected_on_add(self, registry_path):
        reg = make_registry(registry_path, {})
        with pytest.raises(RegistryError, match=f"at most {MAX_CLIENT_ID_LENGTH}"):
            reg.add(Principal("x" * (MAX_CLIENT_ID_LENGTH + 1), Tier.L0, "Too long"))
        assert len(reg) == 0

    def test_registry_at_capacity_loads(self, registry_path):
        clients = {
            f"client-{index}": {"tier": "L0", "name": f"Client {index}"}
            for index in range(MAX_REGISTRY_CLIENTS)
        }
        reg = make_registry(registry_path, clients)
        assert len(reg) == MAX_REGISTRY_CLIENTS

    def test_registry_over_capacity_fails_closed(self, registry_path):
        clients = {
            f"client-{index}": {"tier": "L0", "name": f"Client {index}"}
            for index in range(MAX_REGISTRY_CLIENTS + 1)
        }
        with pytest.raises(RegistryError, match=f"maximum of {MAX_REGISTRY_CLIENTS}"):
            make_registry(registry_path, clients)

    def test_add_at_capacity_does_not_mutate_or_rewrite(self, registry_path):
        clients = {
            f"client-{index}": {"tier": "L0", "name": f"Client {index}"}
            for index in range(MAX_REGISTRY_CLIENTS)
        }
        reg = make_registry(registry_path, clients)
        before = registry_path.read_bytes()

        with pytest.raises(RegistryError, match="registry is full"):
            reg.add(Principal("one-too-many", Tier.L0, "One too many"))

        assert len(reg) == MAX_REGISTRY_CLIENTS
        assert reg.get("one-too-many") is None
        assert registry_path.read_bytes() == before

    def test_existing_entry_can_be_updated_at_capacity(self, registry_path):
        clients = {
            f"client-{index}": {"tier": "L0", "name": f"Client {index}"}
            for index in range(MAX_REGISTRY_CLIENTS)
        }
        reg = make_registry(registry_path, clients)
        assert reg.add(Principal("client-0", Tier.L2, "Updated")) is True
        assert len(reg) == MAX_REGISTRY_CLIENTS
        assert reg.get("client-0").tier is Tier.L2

    def test_add_normalizes_client_id_before_lookup(self, registry_path):
        reg = make_registry(registry_path, {})
        assert reg.add(Principal("  probe  ", Tier.L0, "Probe")) is True
        assert reg.get("probe") == Principal("probe", Tier.L0, "Probe")
        assert reg.add(Principal("probe", Tier.L0, "Probe")) is False


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
        assert reg.get("new") is None

    def test_failed_update_restores_previous_in_memory_entry(self, registry_path, monkeypatch):
        reg = make_registry(registry_path, {"keep": {"tier": "L0", "name": "keep"}})
        monkeypatch.setattr("os.replace", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
        with pytest.raises(OSError):
            reg.add(Principal("keep", Tier.L2, "updated"))
        assert reg.get("keep") == Principal("keep", Tier.L0, "keep")


class TestPathResolution:
    def test_default_path_is_project_config_dir(self):
        path = clients_file_path()
        assert path.name == CLIENTS_FILE_NAME
        assert path.parent.name == "config"
        assert path.is_absolute()
