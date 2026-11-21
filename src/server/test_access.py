"""server/client-access-control 判定测试：三道门、默认拒绝与审计留痕。

运行方式（在仓库根目录）：python -m pytest src/server/test_access.py
"""
import asyncio
import json
import logging

import pytest

from . import access
from .dispatcher import dispatcher
from .protocal.protocal import BaseRequest
from .registry import Principal, Tier
from .request_handles import *  # noqa: F401,F403  确保 handler 完成注册
from .runtime_config import runtime_config
from .session import Session, lease
from device.scpi_power_supply import SCPI_PowerSupply


def make_session(client_id="tester", tier=Tier.L0, authenticated=True) -> Session:
    s = Session(peer="unit-test")
    if authenticated:
        s.authenticate(Principal(client_id, tier, client_id))
    return s


def dispatch(request_type: str, session=None, **fields):
    raw = json.dumps({"type": request_type, **fields})
    return asyncio.run(dispatcher.dispatch(raw, session if session is not None else make_session()))


@pytest.fixture
def fake_device(monkeypatch):
    """让写操作在无串口时也能成功，以便观察控制权效果。"""
    psu = SCPI_PowerSupply()
    calls = []

    for method in ("set_voltage", "set_current", "set_on_off", "get_voltage", "get_current", "get_on_off"):
        async def impl(*a, _m=method):
            calls.append(_m)
            return 12.0
        monkeypatch.setattr(psu, method, impl)
    monkeypatch.setattr(psu, "is_connected", True)
    monkeypatch.setattr(runtime_config, "max_voltage", 30.0)
    monkeypatch.setattr(runtime_config, "max_current", 5.0)
    lease.revoke()
    yield calls
    lease.revoke()


class TestTierDeclaration:
    def test_register_without_tier_is_a_type_error(self):
        with pytest.raises(TypeError):
            @dispatcher.register("ungraded_probe", BaseRequest)
            async def _handler(req):  # pragma: no cover - 注册即失败
                return None

    def test_command_absent_from_registry_is_rejected(self):
        # output_query 在协议里有模型，但从未注册处理器
        with pytest.raises(ValueError, match="Unknown request type"):
            dispatch("output_query")

    def test_every_registered_command_carries_a_tier(self):
        assert set(dispatcher._tiers) == set(dispatcher._handlers)
        assert all(isinstance(t, Tier) for t in dispatcher._tiers.values())

    def test_query_commands_are_l0_and_write_commands_are_gated(self):
        assert dispatcher.tier_of("voltage_query") is Tier.L0
        assert dispatcher.tier_of("setting_query") is Tier.L0
        assert dispatcher.tier_of("set_voltage") is Tier.L1
        assert dispatcher.tier_of("set_on_off") is Tier.L2
        assert dispatcher.tier_of("open_device") is Tier.L2
        assert dispatcher.tier_of("close_device") is Tier.L2


class TestAuthenticationGate:
    def test_anonymous_write_is_denied_before_device(self, fake_device):
        resp = dispatch("set_voltage", make_session(authenticated=False), value=12.0)
        assert resp.status == "error"
        assert "not_authenticated" in resp.message
        assert "set_voltage" not in fake_device

    def test_anonymous_query_is_denied(self, fake_device):
        resp = dispatch("voltage_query", make_session(authenticated=False))
        assert resp.status == "error"
        assert "not_authenticated" in resp.message

    def test_anonymous_echo_still_works(self):
        resp = dispatch("echo", make_session(authenticated=False), message="ping")
        assert resp.status == "success" and resp.message == "ping"

    def test_denial_keeps_request_id(self):
        s = make_session(authenticated=False)
        resp = dispatch("voltage_query", s, request_id="abc123")
        assert resp.request_id == "abc123"


class TestTierGate:
    def test_l0_session_cannot_write(self, fake_device):
        resp = dispatch("set_voltage", make_session(tier=Tier.L0), value=12.0)
        assert resp.status == "error"
        assert "insufficient_tier" in resp.message
        assert "needs L1" in resp.message and "is L0" in resp.message
        assert "set_voltage" not in fake_device

    def test_l1_session_cannot_switch_output(self, fake_device):
        resp = dispatch("set_on_off", make_session(tier=Tier.L1), value=True)
        assert resp.status == "error"
        assert "insufficient_tier" in resp.message and "needs L2" in resp.message
        assert "set_on_off" not in fake_device

    def test_l1_session_can_set_and_not_output(self, fake_device):
        assert dispatch("set_voltage", make_session(tier=Tier.L1), value=12.0).status == "success"
        assert dispatch("set_on_off", make_session(tier=Tier.L1), value=True).status == "error"

    def test_l2_session_can_do_both(self, fake_device):
        assert dispatch("set_voltage", make_session(tier=Tier.L2), value=12.0).status == "success"
        assert dispatch("set_on_off", make_session(tier=Tier.L2), value=True).status == "success"

    def test_tier_denial_is_reported_before_lease_denial(self, fake_device):
        lease.claim("other", Tier.L2)
        lease.record_write("other")
        resp = dispatch("set_on_off", make_session(client_id="me", tier=Tier.L1), value=True)
        assert "insufficient_tier" in resp.message


class TestLeaseGate:
    def test_write_claims_lease_and_renews(self, fake_device):
        s = make_session(client_id="a", tier=Tier.L1)
        assert dispatch("set_voltage", s, value=12.0).status == "success"
        assert lease.holder == "a"

    def test_second_client_write_is_denied_with_holder_named(self, fake_device):
        dispatch("set_voltage", make_session(client_id="a", tier=Tier.L1), value=12.0)
        resp = dispatch("set_voltage", make_session(client_id="b", tier=Tier.L2), value=13.0)
        assert resp.status == "error"
        assert "controlled_by_other" in resp.message and "'a'" in resp.message
        assert "set_voltage" not in fake_device[1:]

    def test_queries_work_while_another_holds_lease(self, fake_device):
        dispatch("set_voltage", make_session(client_id="a", tier=Tier.L1), value=12.0)
        watcher = make_session(client_id="watch", tier=Tier.L0)
        assert dispatch("voltage_query", watcher).status == "success"

    def test_failed_write_does_not_renew(self, fake_device):
        s = make_session(client_id="a", tier=Tier.L1)
        dispatch("set_voltage", s, value=12.0)
        remaining_after_success = lease.seconds_remaining()
        resp = dispatch("set_voltage", s, value=99.0)
        assert resp.status == "error"
        assert lease.seconds_remaining() <= remaining_after_success


class TestAudit:
    def test_allowed_decision_is_logged(self, fake_device, caplog):
        with caplog.at_level(logging.INFO, logger="server.audit"):
            dispatch("set_voltage", make_session(client_id="a", tier=Tier.L1), value=12.0)
        lines = [r.getMessage() for r in caplog.records if r.name == "server.audit"]
        assert any("client=a" in l and "cmd=set_voltage" in l and "allowed" in l for l in lines)

    def test_denied_decision_is_logged_with_reason(self, fake_device, caplog):
        with caplog.at_level(logging.WARNING, logger="server.audit"):
            dispatch("set_on_off", make_session(client_id="l0guy", tier=Tier.L0), value=True)
        lines = [r.getMessage() for r in caplog.records if r.name == "server.audit"]
        assert any("client=l0guy" in l and "denied" in l and "insufficient_tier" in l for l in lines)

    def test_lease_denial_logs_current_holder(self, fake_device, caplog):
        dispatch("set_voltage", make_session(client_id="owner", tier=Tier.L1), value=12.0)
        with caplog.at_level(logging.WARNING, logger="server.audit"):
            dispatch("set_voltage", make_session(client_id="intruder", tier=Tier.L2), value=13.0)
        lines = [r.getMessage() for r in caplog.records if r.name == "server.audit"]
        assert any("controlled_by_other" in l and "holder='owner'" in l for l in lines)

    def test_unauthenticated_denial_is_logged(self, caplog):
        with caplog.at_level(logging.WARNING, logger="server.audit"):
            dispatch("voltage_query", make_session(authenticated=False))
        lines = [r.getMessage() for r in caplog.records if r.name == "server.audit"]
        assert any("not_authenticated" in l for l in lines)
