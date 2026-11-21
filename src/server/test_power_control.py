"""power-supply-control 能力测试：限值校验、连接状态错误语义、setting_query。

运行方式（在 src 目录下）：python -m pytest server/test_power_control.py
"""
import asyncio
import json

import pytest

from .dispatcher import dispatcher
from .request_handles import *  # noqa: F401,F403  确保 handler 完成注册
from .runtime_config import runtime_config
from device.scpi_power_supply import SCPI_PowerSupply


def dispatch(request_type: str, **fields):
    raw = json.dumps({"type": request_type, **fields})
    return asyncio.run(dispatcher.dispatch(raw))


@pytest.fixture
def fake_device(monkeypatch):
    '''把单例设备替换成无串口的假设备，记录 SCPI 下发调用'''
    psu = SCPI_PowerSupply()
    calls = []

    for method in ("set_voltage", "set_current", "set_on_off", "get_voltage", "get_current", "get_on_off", "get_identifier"):
        async def impl(*a, _m=method):
            calls.append((_m, *a))
            if _m == "get_voltage":
                return 12.0
            if _m == "get_current":
                return 0.5
            if _m == "get_on_off":
                return False
            if _m == "get_identifier":
                return "FAKE,IDN"
            return None
        monkeypatch.setattr(psu, method, impl)

    monkeypatch.setattr(psu, "is_connected", True)
    monkeypatch.setattr(runtime_config, "max_voltage", 30.0)
    monkeypatch.setattr(runtime_config, "max_current", 5.0)
    yield psu, calls


class TestSetVoltageLimits:
    def test_over_limit_rejected(self, fake_device):
        psu, calls = fake_device
        resp = dispatch("set_voltage", value=36.0)
        assert resp.status == "error"
        assert "0~30" in resp.message
        assert not any(c[0] == "set_voltage" for c in calls)

    def test_boundary_allowed(self, fake_device):
        psu, calls = fake_device
        resp = dispatch("set_voltage", value=30.0)
        assert resp.status == "success"
        assert ("set_voltage", 30.0) in calls

    def test_in_range_allowed(self, fake_device):
        psu, calls = fake_device
        resp = dispatch("set_voltage", value=12.5)
        assert resp.status == "success"
        assert resp.value == 12.5

    def test_negative_rejected(self, fake_device):
        psu, calls = fake_device
        resp = dispatch("set_voltage", value=-1.0)
        assert resp.status == "error"


class TestSetCurrentLimits:
    def test_over_limit_rejected(self, fake_device):
        psu, calls = fake_device
        resp = dispatch("set_current", value=7.0)
        assert resp.status == "error"
        assert "0~5" in resp.message
        assert not any(c[0] == "set_current" for c in calls)

    def test_in_range_allowed(self, fake_device):
        psu, calls = fake_device
        resp = dispatch("set_current", value=2.0)
        assert resp.status == "success"
        assert ("set_current", 2.0) in calls


class TestSettingQuery:
    def test_returns_limits(self, fake_device):
        resp = dispatch("setting_query")
        assert resp.status == "success"
        assert resp.max_voltage == 30.0
        assert resp.max_current == 5.0

    def test_limits_follow_runtime_config(self, fake_device, monkeypatch):
        monkeypatch.setattr(runtime_config, "max_voltage", 24.0)
        resp = dispatch("setting_query")
        assert resp.max_voltage == 24.0


class TestNotConnected:
    @pytest.mark.parametrize("request_type,fields", [
        ("voltage_query", {}),
        ("current_query", {}),
        ("on_off_query", {}),
        ("device_id_query", {}),
        ("set_voltage", {"value": 5.0}),
        ("set_current", {"value": 1.0}),
        ("set_on_off", {"value": True}),
    ])
    def test_device_dependent_requests_error(self, request_type, fields, fake_device):
        psu, calls = fake_device
        psu.is_connected = False
        resp = dispatch(request_type, **fields)
        assert resp.status == "error"
        assert "device not connected" in resp.message
        assert calls == []


class TestOpenDevice:
    def test_bad_serial_reports_error(self, fake_device):
        # psu.connect 保持真实实现：打开不存在的串口应如实报告失败
        psu, _ = fake_device
        psu.is_connected = False
        resp = dispatch("open_device", serial_number="COM255")
        assert resp.status == "error"
        assert "connect failed" in resp.message
