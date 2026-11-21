"""tools 层单元测试：错误话术映射与 get_status 聚合，不触网。"""
import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from psu_mcp import tools
from psu_mcp.psu_client import PsuAccessDeniedError, PsuUnavailableError


class FakeClient:
    def __init__(self, responses):
        self.responses = responses  # request_type -> dict | Exception | callable(**fields)
        self.calls = []

    async def request(self, request_type, **fields):
        self.calls.append((request_type, fields))
        value = self.responses[request_type]
        if callable(value):
            value = value(**fields)
        if isinstance(value, Exception):
            raise value
        return value


def status_responses(**overrides):
    base = {
        "device_id_query": {"status": "success", "value": "FAKE,RIGOL"},
        "voltage_query": {"status": "success", "value": 12.0},
        "current_query": {"status": "success", "value": 1.0},
        "on_off_query": {"status": "success", "value": True},
        "setting_query": {"status": "success", "max_voltage": 24.0, "max_current": 3.0,
                          "version": "1.2.3"},
    }
    base.update(overrides)
    return base


def run(coro):
    return asyncio.run(coro)


def test_get_status_aggregates_five_queries(monkeypatch):
    fake = FakeClient(status_responses())
    monkeypatch.setattr(tools, "client", fake)
    result = run(tools.get_status())
    assert result == {
        "identifier": "FAKE,RIGOL",
        "voltage_v": 12.0,
        "current_a": 1.0,
        "output_on": True,
        "limits": {"max_voltage_v": 24.0, "max_current_a": 3.0, "server_version": "1.2.3"},
    }
    assert [c[0] for c in fake.calls] == [
        "device_id_query", "voltage_query", "current_query", "on_off_query", "setting_query",
    ]


def test_get_status_degrades_when_setting_query_unavailable(monkeypatch):
    fake = FakeClient(status_responses(setting_query=PsuUnavailableError("app too old")))
    monkeypatch.setattr(tools, "client", fake)
    result = run(tools.get_status())
    assert result["limits"] is None
    assert result["voltage_v"] == 12.0  # 核心读数不受影响


def test_app_not_running_mapped_to_friendly_error(monkeypatch):
    fake = FakeClient({"set_voltage": PsuUnavailableError("conn refused")})
    monkeypatch.setattr(tools, "client", fake)
    with pytest.raises(ToolError) as exc:
        run(tools.set_voltage(12.0))
    assert "电源控制应用未运行" in str(exc.value)


def test_login_refused_mapped_to_admission_hint(monkeypatch):
    fake = FakeClient({"set_voltage": PsuAccessDeniedError("login refused")})
    monkeypatch.setattr(tools, "client", fake)
    with pytest.raises(ToolError) as exc:
        run(tools.set_voltage(12.0))
    assert "拒绝了本桥的登录" in str(exc.value)


def test_device_not_connected_mapped_to_ui_hint(monkeypatch):
    fake = FakeClient({
        "set_voltage": {"status": "error", "message": "device not connected"},
        "voltage_query": {"status": "error", "message": "device not connected"},
    })
    monkeypatch.setattr(tools, "client", fake)
    with pytest.raises(ToolError) as exc:
        run(tools.set_voltage(12.0))
    assert "设备未连接" in str(exc.value)


def test_limit_rejection_message_passes_through(monkeypatch):
    fake = FakeClient({
        "set_voltage": {"status": "error", "message": "voltage out of allowed range 0~24.00V"},
    })
    monkeypatch.setattr(tools, "client", fake)
    with pytest.raises(ToolError) as exc:
        run(tools.set_voltage(30.0))
    assert "0~24.00V" in str(exc.value)


def test_server_error_frame_mapped(monkeypatch):
    fake = FakeClient({"set_current": {"error": "dispatcher failed"}})
    monkeypatch.setattr(tools, "client", fake)
    with pytest.raises(ToolError) as exc:
        run(tools.set_current(1.0))
    assert "server 处理失败" in str(exc.value)


def test_setters_return_applied_values(monkeypatch):
    fake = FakeClient({
        "set_voltage": {"status": "success", "value": 5.5},
        "set_current": {"status": "success", "value": 2.5},
    })
    monkeypatch.setattr(tools, "client", fake)
    assert run(tools.set_voltage(5.5)) == {"set_voltage_v": 5.5}
    assert run(tools.set_current(2.5)) == {"set_current_a": 2.5}


def test_set_output_reads_back_state(monkeypatch):
    fake = FakeClient({
        "set_on_off": {"status": "success"},
        "on_off_query": {"status": "success", "value": True},
    })
    monkeypatch.setattr(tools, "client", fake)
    assert run(tools.set_output(True)) == {"output_on": True}
    assert fake.calls[0] == ("set_on_off", {"value": True})
