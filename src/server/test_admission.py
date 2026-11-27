"""登录准入与控制权命令测试：降格、首次准入、超时、双清单与交还。

运行方式（在仓库根目录）：python -m pytest src/server/test_admission.py
"""
import asyncio
import json

import pytest
from pydantic import ValidationError

from . import access
from .access import set_approval_handler
from .dispatcher import dispatcher
from .protocal.protocal import LoginRequest
from .registry import ClientRegistry, Principal, Tier, use_registry
from .runtime_config import (
    ADMISSION_RATE_WINDOW_SECONDS,
    MAX_ADMISSION_ATTEMPTS,
    MAX_CLIENT_ID_LENGTH,
    MAX_REGISTRY_CLIENTS,
)
from .request_handles import *  # noqa: F401,F403  确保 handler 完成注册
from .session import access_config, hub, lease, pending_approvals
from device.scpi_power_supply import SCPI_PowerSupply


@pytest.fixture(autouse=True)
def fake_device(monkeypatch):
    """本文件关心的是权限而非设备：把单例设备假装成已连接。"""
    psu = SCPI_PowerSupply()
    calls = []

    async def _set_voltage(value):
        calls.append(value)

    monkeypatch.setattr(psu, "is_connected", True)
    monkeypatch.setattr(psu, "set_voltage", _set_voltage)
    monkeypatch.setattr(psu, "get_voltage", lambda: asyncio.sleep(0, result=12.0))
    yield calls


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / "clients.json"
    path.write_text(json.dumps({"schema_version": 1, "clients": {
        "known-l0": {"tier": "L0", "name": "Known L0"},
        "known-l2": {"tier": "L2", "name": "Known L2"},
        "rival-l2": {"tier": "L2", "name": "Rival L2"},
    }}), encoding="utf-8")
    reg = ClientRegistry.load(path)
    use_registry(reg)
    return reg


@pytest.fixture
def anon():
    s = hub.open("127.0.0.1:52000")
    lease.revoke()
    yield s
    lease.revoke()
    set_approval_handler(None)


def run(coro):
    return asyncio.run(coro)


async def send(request_type, session, **fields):
    raw = json.dumps({"type": request_type, "request_id": "c1", **fields})
    return await dispatcher.dispatch(raw, session)


def login(session, client_id, tier="L0"):
    return run(send("login", session, client_id=client_id, tier=tier))


def call(session, request_type, **fields):
    return run(send(request_type, session, **fields))


class TestLoginGate:
    def test_business_before_login_is_rejected(self, registry, anon):
        resp = call(anon, "setting_query")
        assert resp.status == "error" and "not_authenticated" in resp.message

    def test_echo_works_before_login(self, registry, anon):
        assert call(anon, "echo", message="ping").status == "success"

    def test_registered_client_gets_recorded_tier(self, registry, anon):
        resp = login(anon, "known-l2", "L2")
        assert resp.status == "success" and resp.tier == "L2" and resp.client_id == "known-l2"

    def test_request_above_recorded_is_downgraded_not_escalated(self, registry, anon):
        resp = login(anon, "known-l0", "L2")
        assert resp.status == "success"
        assert resp.tier == "L0"
        assert "granted L0 as registered" in resp.message
        assert anon.tier is Tier.L0

    def test_downgraded_client_still_cannot_write(self, registry, anon):
        login(anon, "known-l0", "L2")
        resp = call(anon, "set_voltage", value=12.0)
        assert resp.status == "error" and "insufficient_tier" in resp.message

    def test_login_response_carries_no_reusable_token(self, registry, anon):
        resp = login(anon, "known-l0", "L0")
        assert "token" not in resp.model_dump()
        assert "session" not in resp.model_dump()

    def test_logout_clears_identity_but_not_lease(self, registry, anon):
        login(anon, "known-l2", "L2")
        call(anon, "set_voltage", value=12.0)
        held = lease.holder
        call(anon, "logout")
        assert not anon.is_authenticated
        assert lease.holder == held


class TestFirstContactAdmission:
    def test_unknown_l0_is_auto_admitted_and_persisted(self, registry, anon):
        resp = login(anon, "probe-script", "L0")
        assert resp.status == "success" and resp.tier == "L0"
        assert resp.reason == "auto_admitted_l0"
        assert registry.get("probe-script").tier is Tier.L0

    def test_unknown_l1_without_approver_is_refused(self, registry, anon):
        set_approval_handler(None)
        resp = login(anon, "new-tool", "L1")
        assert resp.status == "error"
        assert "no_approver" in resp.message
        assert registry.get("new-tool") is None

    def test_unknown_l1_approved_by_user_is_admitted(self, registry, anon):
        seen = []

        def approve(approval):
            seen.append(approval)
            assert pending_approvals.decide(approval.request_id, True)

        set_approval_handler(approve)
        resp = login(anon, "new-tool", "L1")
        assert resp.status == "success" and resp.tier == "L1"
        assert resp.reason == "approved_by_user"
        assert seen[0].client_id == "new-tool" and seen[0].tier is Tier.L1
        assert registry.get("new-tool").tier is Tier.L1

    def test_unknown_l2_refused_closes_connection_and_keeps_registry(self, registry, anon):
        set_approval_handler(lambda a: pending_approvals.decide(a.request_id, False))
        resp = login(anon, "wanted-l2", "L2")
        assert resp.status == "error" and "refused_by_user" in resp.message
        assert anon.close_after_response is True
        assert registry.get("wanted-l2") is None
        assert len(registry) == 3

    def test_no_answer_times_out_as_refusal(self, registry, anon, monkeypatch):
        monkeypatch.setattr(access_config, "approval_timeout_seconds", 0.05)
        set_approval_handler(lambda a: None)  # 用户不在，无人应答
        resp = login(anon, "silent-requester", "L1")
        assert resp.status == "error" and "approval_timeout" in resp.message
        assert anon.close_after_response is True
        assert len(pending_approvals) == 0

    def test_pending_approval_does_not_block_other_clients(self, registry, anon, monkeypatch):
        """确认弹窗挂起期间，事件循环照常服务其他连接，准入等待不是全局阻塞。"""
        monkeypatch.setattr(access_config, "approval_timeout_seconds", 5.0)
        set_approval_handler(lambda a: None)

        async def scenario():
            waiting = asyncio.ensure_future(send("login", anon, client_id="slowpoke", tier="L1"))
            await asyncio.sleep(0.01)
            other = hub.open("127.0.0.1:52006")
            await send("login", other, client_id="known-l2", tier="L2")
            resp = await asyncio.wait_for(send("set_voltage", other, value=12.0), timeout=1.0)
            assert resp.status == "success"
            assert len(pending_approvals) == 1
            waiting.cancel()

        asyncio.run(scenario())

    def test_pending_queue_is_visible_while_awaiting_answer(self, registry, anon, monkeypatch):
        monkeypatch.setattr(access_config, "approval_timeout_seconds", 0.2)
        snapshots = []
        set_approval_handler(lambda a: snapshots.append(a.describe()))
        login(anon, "watched", "L1")
        assert snapshots[0]["client_id"] == "watched" and snapshots[0]["tier"] == "L1"


class TestAdmissionLimits:
    def test_login_request_rejects_overlong_client_id(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            LoginRequest(client_id="x" * (MAX_CLIENT_ID_LENGTH + 1))

    def test_login_request_trims_before_applying_length_limit(self):
        client_id = "x" * MAX_CLIENT_ID_LENGTH
        request = LoginRequest(client_id=f"  {client_id}  ")
        assert request.client_id == client_id

    def test_direct_admission_rejects_overlong_client_id(self, registry, anon):
        admission = run(access.admit(
            anon, "x" * (MAX_CLIENT_ID_LENGTH + 1), Tier.L0
        ))
        assert not admission.granted
        assert admission.reason == "invalid_client_id"
        assert len(registry) == 3

    def test_login_normalizes_client_id(self, registry, anon):
        resp = login(anon, "  probe-script  ", "L0")
        assert resp.status == "success"
        assert resp.client_id == "probe-script"
        assert registry.get("probe-script") is not None

    def test_sequential_unique_l0_admissions_are_rate_limited(
        self, registry, anon, monkeypatch
    ):
        now = [1000.0]
        monkeypatch.setattr(access.time, "monotonic", lambda: now[0])
        initial_count = len(registry)

        for index in range(MAX_ADMISSION_ATTEMPTS):
            fresh = hub.open(f"127.0.0.1:{54000 + index}")
            try:
                resp = login(fresh, f"probe-{index}", "L0")
                assert resp.status == "success"
            finally:
                hub.close(fresh)

        assert len(registry) == initial_count + MAX_ADMISSION_ATTEMPTS
        before = registry.path.read_bytes()
        resp = login(anon, "blocked-probe", "L0")
        assert resp.status == "error" and "[rate_limited]" in resp.message
        assert registry.get("blocked-probe") is None
        assert registry.path.read_bytes() == before

        # Registered identities do not consume the first-contact allowance.
        assert login(anon, "known-l0", "L0").status == "success"

        now[0] += ADMISSION_RATE_WINDOW_SECONDS
        recovered = hub.open("127.0.0.1:54999")
        try:
            assert login(recovered, "after-window", "L0").status == "success"
        finally:
            hub.close(recovered)
        assert registry.get("after-window") is not None

    def test_rate_limited_l1_does_not_create_pending_approval(self, registry, anon):
        for index in range(MAX_ADMISSION_ATTEMPTS):
            assert login(anon, f"unapproved-{index}", "L1").status == "error"

        seen = []
        set_approval_handler(seen.append)
        resp = login(anon, "blocked-l1", "L1")
        assert resp.status == "error" and "[rate_limited]" in resp.message
        assert seen == []
        assert len(pending_approvals) == 0
        assert len(registry) == 3

    def test_full_registry_refuses_new_identity_without_rewrite(self, registry, anon):
        full = ClientRegistry(registry.path, {
            f"client-{index}": Principal(f"client-{index}", Tier.L0, f"Client {index}")
            for index in range(MAX_REGISTRY_CLIENTS)
        })
        use_registry(full)
        before = registry.path.read_bytes()

        resp = login(anon, "one-too-many", "L0")

        assert resp.status == "error" and "[registry_full]" in resp.message
        assert len(full) == MAX_REGISTRY_CLIENTS
        assert full.get("one-too-many") is None
        assert registry.path.read_bytes() == before


class TestLeaseCommands:
    def _holder(self, registry, anon, client_id="known-l2"):
        login(anon, client_id, "L2")
        return anon

    def test_write_claims_and_lease_status_reports_it(self, registry, anon):
        s = self._holder(registry, anon)
        call(s, "set_voltage", value=12.0)
        resp = call(s, "lease_status")
        assert resp.status == "success"
        assert resp.holder == "known-l2" and resp.tier == "L2"
        assert resp.holder_connected is True
        assert resp.remaining_seconds > 0

    def test_lease_status_when_free(self, registry, anon):
        s = self._holder(registry, anon)
        resp = call(s, "lease_status")
        assert resp.holder is None and resp.holder_connected is False

    def test_list_clients_separates_sessions_from_lease(self, registry, anon):
        holder = self._holder(registry, anon)
        watcher = hub.open("127.0.0.1:52001")
        login(watcher, "known-l0", "L0")
        call(holder, "set_voltage", value=12.0)

        resp = call(watcher, "list_clients")
        assert resp.lease["holder"] == "known-l2"
        ids = {c["client_id"] for c in resp.clients}
        assert ids == {"known-l2", "known-l0"}
        assert all(c["authenticated"] for c in resp.clients)

    def test_list_clients_shows_unauthenticated_connections(self, registry, anon):
        fresh = hub.open("127.0.0.1:52002")
        resp = call(self._holder(registry, anon), "list_clients")
        entry = [c for c in resp.clients if c["peer"] == fresh.peer][0]
        assert entry["authenticated"] is False and entry["client_id"] is None

    def test_holder_releases(self, registry, anon):
        s = self._holder(registry, anon)
        call(s, "set_voltage", value=12.0)
        resp = call(s, "release_lease")
        assert resp.status == "success"
        assert lease.is_free()

    def test_non_holder_cannot_release(self, registry, anon):
        s = self._holder(registry, anon)
        call(s, "set_voltage", value=12.0)
        other = hub.open("127.0.0.1:52003")
        login(other, "rival-l2", "L2")
        resp = call(other, "release_lease")
        assert resp.status == "error" and "not_holder" in resp.message
        assert lease.holder == "known-l2"

    def test_rival_write_names_holder_and_remaining_time(self, registry, anon):
        s = self._holder(registry, anon)
        call(s, "set_voltage", value=12.0)
        other = hub.open("127.0.0.1:52004")
        login(other, "rival-l2", "L2")
        resp = call(other, "set_voltage", value=13.0)
        assert resp.status == "error" and "controlled_by_other" in resp.message
        assert "known-l2" in resp.message

    def test_panel_revoke_frees_lease_without_touching_the_device(self, registry, anon,
                                                                  fake_device):
        s = self._holder(registry, anon)
        call(s, "set_voltage", value=12.0)
        assert access.panel_revoke() == "known-l2"
        assert fake_device == [12.0]
        assert lease.holder is None
        assert call(s, "set_voltage", value=13.0).status == "success"


class TestLeaseSurvivesDisconnect:
    def test_holder_without_connection_is_still_reported(self, registry, anon, monkeypatch):
        login(anon, "known-l2", "L2")
        call(anon, "set_voltage", value=12.0)
        hub.close(anon)
        assert lease.holder == "known-l2"
        watcher = hub.open("127.0.0.1:52005")
        login(watcher, "known-l0", "L0")
        resp = call(watcher, "lease_status")
        assert resp.holder == "known-l2" and resp.holder_connected is False
