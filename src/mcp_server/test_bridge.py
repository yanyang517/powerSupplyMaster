"""MCP 桥集成测试：对真实 SocketServer 的协议客户端与错误映射。

运行方式（在 src 目录下）：python -m pytest mcp_server/test_bridge.py
"""
import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from device.scpi_power_supply import SCPI_PowerSupply
from server.runtime_config import runtime_config
from server.socket_server import SocketServer

from . import tools
from .psu_client import PsuClient, PsuUnavailableError

HOST = "127.0.0.1"
PORT = 18899  # 测试专用端口，避开默认 8888


def make_fake_device(monkeypatch, connected=True):
    psu = SCPI_PowerSupply()

    async def get_voltage():
        return 12.0

    async def get_current():
        return 0.5

    async def get_on_off():
        return True

    async def get_identifier():
        return "FAKE,RIGOL DP832"

    async def noop(*args):
        return None

    monkeypatch.setattr(psu, "is_connected", connected)
    monkeypatch.setattr(psu, "get_voltage", get_voltage)
    monkeypatch.setattr(psu, "get_current", get_current)
    monkeypatch.setattr(psu, "get_on_off", get_on_off)
    monkeypatch.setattr(psu, "get_identifier", get_identifier)
    monkeypatch.setattr(psu, "set_voltage", noop)
    monkeypatch.setattr(psu, "set_current", noop)
    monkeypatch.setattr(psu, "set_on_off", noop)
    monkeypatch.setattr(runtime_config, "max_voltage", 30.0)
    monkeypatch.setattr(runtime_config, "max_current", 5.0)
    return psu


async def start_psu_server():
    server = SocketServer(host=HOST, port=PORT)
    srv = await asyncio.start_server(server.handle_client, HOST, PORT)
    return srv


class TestProtocolClient:
    def test_roundtrip_against_real_server(self, monkeypatch):
        make_fake_device(monkeypatch)

        async def scenario():
            srv = await start_psu_server()
            try:
                client = PsuClient(host=HOST, port=PORT, timeout=2.0)
                resp = await client.request("voltage_query")
                assert resp["status"] == "success"
                assert resp["value"] == 12.0

                setting = await client.request("setting_query")
                assert setting["max_voltage"] == 30.0
                assert setting["max_current"] == 5.0
                await client._drop_connection()
            finally:
                srv.close()
                await srv.wait_closed()

        asyncio.run(scenario())

    def test_lazy_reconnect_after_server_restart(self, monkeypatch):
        make_fake_device(monkeypatch)

        async def scenario():
            client = PsuClient(host=HOST, port=PORT, timeout=2.0)

            srv1 = await start_psu_server()
            resp = await client.request("voltage_query")
            assert resp["status"] == "success"
            # 模拟 server 进程突然消失：监听关闭 + 现有连接被硬切断
            # （不 await srv1.wait_closed()，它会等待仍在保活的 handle_client）
            srv1.close()
            client._writer.transport.abort()
            await asyncio.sleep(0.1)

            # server 恢复后，下一次调用应透明重连并成功
            srv2 = await start_psu_server()
            try:
                resp = await client.request("voltage_query")
                assert resp["status"] == "success"
            finally:
                await client._drop_connection()
                srv2.close()
                await srv2.wait_closed()

        asyncio.run(scenario())

    def test_server_down_raises_unavailable(self):
        async def scenario():
            client = PsuClient(host=HOST, port=PORT, timeout=0.5)
            with pytest.raises(PsuUnavailableError):
                await client.request("voltage_query")

        asyncio.run(scenario())


class TestToolErrorMapping:
    def _scenario(self, monkeypatch, connected, body):
        make_fake_device(monkeypatch, connected=connected)

        async def scenario():
            srv = await start_psu_server()
            tools.client = PsuClient(host=HOST, port=PORT, timeout=2.0)
            try:
                await body()
            finally:
                await tools.client._drop_connection()
                srv.close()
                await srv.wait_closed()

        asyncio.run(scenario())

    def test_device_not_connected_maps_to_ui_hint(self, monkeypatch):
        async def body():
            with pytest.raises(ToolError) as ei:
                await tools.get_status()
            assert "UI" in str(ei.value) and "未连接" in str(ei.value)

        self._scenario(monkeypatch, connected=False, body=body)

    def test_over_limit_message_passes_through(self, monkeypatch):
        async def body():
            with pytest.raises(ToolError) as ei:
                await tools.set_voltage(36.0)
            assert "0~30" in str(ei.value)

        self._scenario(monkeypatch, connected=True, body=body)

    def test_app_not_running_maps_to_start_hint(self, monkeypatch):
        make_fake_device(monkeypatch)

        async def body():
            with pytest.raises(ToolError) as ei:
                await tools.set_current(1.0)
            assert "powerSupplyMaster" in str(ei.value)

        async def scenario_no_server():
            tools.client = PsuClient(host=HOST, port=PORT, timeout=0.5)
            await body()

        asyncio.run(scenario_no_server())


class TestGetStatus:
    def test_aggregates_all_fields(self, monkeypatch):
        make_fake_device(monkeypatch)

        async def body():
            return await tools.get_status()

        async def scenario():
            srv = await start_psu_server()
            tools.client = PsuClient(host=HOST, port=PORT, timeout=2.0)
            try:
                return await body()
            finally:
                await tools.client._drop_connection()
                srv.close()
                await srv.wait_closed()

        result = asyncio.run(scenario())
        assert result == {
            "identifier": "FAKE,RIGOL DP832",
            "voltage_v": 12.0,
            "current_a": 0.5,
            "output_on": True,
            "limits": {"max_voltage_v": 30.0, "max_current_a": 5.0},
        }
