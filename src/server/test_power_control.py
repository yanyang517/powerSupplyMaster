"""power-supply-control 能力测试：限值校验、连接状态错误语义、setting_query。

运行方式（仓库根目录或 src 目录都可，见根 pytest.ini）：
    python -m pytest src/server/test_power_control.py
"""
import asyncio
import json

import pytest

import device.scpi_power_supply as scpi_module

from .dispatcher import dispatcher
from .request_handles import *  # noqa: F401,F403  确保 handler 完成注册
from .registry import Principal, Tier
from .runtime_config import runtime_config
from .session import Session
from device.scpi_power_supply import SCPI_PowerSupply
import version


def make_session(client_id: str = "tester", tier: Tier = Tier.L2) -> Session:
    s = Session(peer="unit-test")
    s.authenticate(Principal(client_id, tier, client_id))
    return s


def dispatch(request_type: str, session: Session | None = None, **fields):
    """默认以已登录 L2 身份调用，使本文件专注于设备行为而非权限。"""
    raw = json.dumps({"type": request_type, **fields})
    return asyncio.run(dispatcher.dispatch(raw, session or make_session()))


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
        assert resp.error.code == "over_limit"
        assert resp.error.setting == "voltage"
        assert resp.error.maximum == 30.0
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
        assert resp.error.code == "negative"
        assert not any(c[0] == "set_voltage" for c in calls)


class TestSetCurrentLimits:
    def test_over_limit_rejected(self, fake_device):
        psu, calls = fake_device
        resp = dispatch("set_current", value=7.0)
        assert resp.status == "error"
        assert resp.error.code == "over_limit"
        assert resp.error.setting == "current"
        assert resp.error.maximum == 5.0
        assert "0~5" in resp.message
        assert not any(c[0] == "set_current" for c in calls)

    def test_boundary_allowed(self, fake_device):
        psu, calls = fake_device
        resp = dispatch("set_current", value=5.0)
        assert resp.status == "success"
        assert ("set_current", 5.0) in calls

    def test_zero_allowed(self, fake_device):
        psu, calls = fake_device
        resp = dispatch("set_current", value=0.0)
        assert resp.status == "success"
        assert ("set_current", 0.0) in calls

    def test_in_range_allowed(self, fake_device):
        psu, calls = fake_device
        resp = dispatch("set_current", value=2.0)
        assert resp.status == "success"
        assert ("set_current", 2.0) in calls

    def test_negative_rejected(self, fake_device):
        psu, calls = fake_device
        resp = dispatch("set_current", value=-1.0)
        assert resp.status == "error"
        assert resp.error.code == "negative"
        assert not any(c[0] == "set_current" for c in calls)


@pytest.mark.parametrize("request_type,setting", [
    ("set_voltage", "voltage"),
    ("set_current", "current"),
])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_values_rejected_with_json_safe_details(fake_device, request_type,
                                                            setting, value):
    psu, calls = fake_device
    resp = dispatch(request_type, value=value)

    assert resp.status == "error"
    assert resp.error.code == "non_finite"
    assert resp.error.setting == setting
    assert calls == []
    payload = json.loads(resp.model_dump_json())
    assert payload["error"]["value"] == repr(value)
    assert payload["message"] == resp.message


@pytest.mark.parametrize("request_type,setting,scaled_unit,default_unit,value,expected", [
    ("set_voltage", "voltage", "mV", "V", 25000.0, 25.0),
    ("set_current", "current", "mA", "A", 2500.0, 2.5),
])
def test_scaled_units_are_normalized_before_validation_and_write(
        fake_device, request_type, setting, scaled_unit, default_unit, value, expected):
    psu, calls = fake_device

    resp = dispatch(request_type, value=value, unit=scaled_unit)

    assert resp.status == "success"
    assert resp.value == expected
    assert calls == [(f"set_{setting}", expected)]

    # 同一个数字若按默认单位解释必须超限；旧实现忽略 unit，会错误下发 1000 倍值。
    rejected = dispatch(request_type, value=value, unit=default_unit)
    assert rejected.status == "error"
    assert rejected.error.code == "over_limit"
    assert calls == [(f"set_{setting}", expected)]


@pytest.mark.parametrize("request_type,setting,unit,boundary,over_limit", [
    ("set_voltage", "voltage", "mV", 30000.0, 30001.0),
    ("set_current", "current", "mA", 5000.0, 5001.0),
])
def test_scaled_unit_boundaries_use_canonical_limits(
        fake_device, request_type, setting, unit, boundary, over_limit):
    psu, calls = fake_device

    allowed = dispatch(request_type, value=boundary, unit=unit)
    rejected = dispatch(request_type, value=over_limit, unit=unit)

    assert allowed.status == "success"
    assert allowed.value == boundary / 1000.0
    assert rejected.status == "error"
    assert rejected.error.code == "over_limit"
    assert rejected.error.value == pytest.approx(over_limit / 1000.0)
    assert calls == [(f"set_{setting}", boundary / 1000.0)]


def test_unknown_unit_is_rejected_before_device_write(fake_device):
    psu, calls = fake_device

    with pytest.raises(ValueError, match="Invalid request format"):
        dispatch("set_voltage", value=1000.0, unit="kV")

    assert calls == []


@pytest.mark.parametrize("request_type,setting", [
    ("set_voltage", "voltage"),
    ("set_current", "current"),
])
@pytest.mark.parametrize("limit", [float("nan"), float("inf"), float("-inf"), -1.0,
                                   "invalid", None])
def test_invalid_runtime_limit_fails_closed(fake_device, monkeypatch, request_type,
                                           setting, limit):
    psu, calls = fake_device
    monkeypatch.setattr(runtime_config, f"max_{setting}", limit)

    resp = dispatch(request_type, value=1.0)

    assert resp.status == "error"
    assert resp.error.code == "invalid_limit"
    assert resp.error.setting == setting
    assert calls == []
    # 非有限配置值不能污染 JSON 响应。
    json.loads(resp.model_dump_json())


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

    def test_response_carries_the_running_version(self, fake_device):
        """客户端要靠这一个字段判断连的是哪一版上位机，报障时才不用猜。"""
        resp = dispatch("setting_query")
        assert resp.version == version.__version__

    def test_version_follows_the_single_source(self, fake_device, monkeypatch):
        """版本必须现场取自真源，而不是 handler 里抄的一份。"""
        monkeypatch.setattr(version, "__version__", "9.9.9")
        resp = dispatch("setting_query")
        assert resp.version == "9.9.9"

    def test_works_without_a_connected_device(self, fake_device):
        """限值与版本都来自本进程：串口没连上也必须答得出，且是 success。"""
        psu, calls = fake_device
        psu.is_connected = False
        resp = dispatch("setting_query")
        assert resp.status == "success"
        assert resp.max_voltage == 30.0
        assert resp.version == version.__version__
        assert calls == []


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
    def test_bad_serial_reports_error(self, fake_device, monkeypatch):
        # Inject a transport failure rather than assuming a particular COM port is absent.
        psu, _ = fake_device
        psu.is_connected = False
        attempted = []

        async def fail_open(*, url, baudrate):
            attempted.append((url, baudrate))
            raise OSError("serial port unavailable")

        monkeypatch.setattr(scpi_module.serial_asyncio, "open_serial_connection", fail_open)
        resp = dispatch("open_device", serial_number="SIMULATED-ABSENT")
        assert resp.status == "error"
        assert "connect failed" in resp.message
        assert "serial port unavailable" in resp.message
        assert attempted == [("SIMULATED-ABSENT", 115200)]
