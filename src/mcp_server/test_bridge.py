"""MCP 桥线上协议回归：psu_mcp 包对真实 SocketServer 的互操作。

本文件留在主仓库，专职验证包与 app 的协议契约（准入、租约、限值文案、版本上报）；
psu_client/tools 的纯客户端行为在 packages/psu-mcp/tests 内自测。
运行方式（在 src 目录下，需先 pip install -e packages/psu-mcp）：
python -m pytest mcp_server/test_bridge.py
"""
import asyncio
import json
import socket

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import version
from device.scpi_power_supply import SCPI_PowerSupply
from psu_mcp import tools
from psu_mcp.psu_client import PsuAccessDeniedError, PsuClient, PsuUnavailableError
from server.access import set_approval_handler
from server.registry import ClientRegistry, use_registry
from server.runtime_config import runtime_config
from server.session import hub, lease, lease_config
from server.socket_server import SocketServer

HOST = "127.0.0.1"


@pytest.fixture
def unavailable_port():
    """Reserve a loopback port without listening so connection refusal is deterministic."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved:
        reserved.bind((HOST, 0))
        yield reserved.getsockname()[1]


@pytest.fixture(autouse=True)
def bridge_is_registered(tmp_path):
    """桥默认以 mcp-bridge/L2 身份登录：给每个用例一份干净的临时登记表与会话状态。"""
    path = tmp_path / "clients.json"
    path.write_text(json.dumps({"schema_version": 1, "clients": {
        "mcp-bridge": {"tier": "L2", "name": "AI 助手 (MCP 桥)"}
    }}), encoding="utf-8")
    use_registry(ClientRegistry.load(path))
    lease.revoke()
    for s in list(hub):
        hub.close(s)
    set_approval_handler(None)
    yield
    lease.revoke()
    set_approval_handler(None)


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


async def start_psu_server(port: int = 0):
    server = SocketServer(host=HOST, port=port)
    srv = await asyncio.start_server(server.handle_client, HOST, port)
    server.port = srv.sockets[0].getsockname()[1]
    return srv, server.port


class TestProtocolClient:
    def test_default_port_tracks_app(self):
        """包内 DEFAULT_PORT 与应用侧 SERVER_PORT 不允许悄悄漂移（design D3）。"""
        from psu_mcp.psu_client import DEFAULT_PORT
        from server.runtime_config import SERVER_PORT
        assert DEFAULT_PORT == SERVER_PORT

    def test_roundtrip_against_real_server(self, monkeypatch):
        make_fake_device(monkeypatch)

        async def scenario():
            srv, port = await start_psu_server()
            try:
                client = PsuClient(host=HOST, port=port, timeout=2.0)
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

    def test_default_identity_covers_every_bridge_command(self, monkeypatch):
        """桥的四个工具必须全部落地：默认身份低于 L2 时 set_on_off 会被门控拒掉。"""
        make_fake_device(monkeypatch)

        async def scenario():
            srv, port = await start_psu_server()
            try:
                client = PsuClient(host=HOST, port=port, timeout=2.0)
                assert client.tier == "L2", "默认身份应与 set_output 所需的等级一致"
                for request_type, fields in (("set_voltage", {"value": 12.0}),
                                             ("set_current", {"value": 1.0}),
                                             ("set_on_off", {"value": True})):
                    resp = await client.request(request_type, **fields)
                    assert resp["status"] == "success", f"{request_type}: {resp.get('message')}"
                await client._drop_connection()
            finally:
                srv.close()
                await srv.wait_closed()

        asyncio.run(scenario())

    def test_lazy_reconnect_after_server_restart(self, monkeypatch):
        make_fake_device(monkeypatch)

        async def scenario():
            srv1, port = await start_psu_server()
            client = PsuClient(host=HOST, port=port, timeout=2.0)
            resp = await client.request("voltage_query")
            assert resp["status"] == "success"
            # 模拟 server 进程突然消失：监听关闭 + 现有连接被硬切断
            # （不 await srv1.wait_closed()，它会等待仍在保活的 handle_client）
            srv1.close()
            client._writer.transport.abort()
            await asyncio.sleep(0.1)

            # server 恢复后，下一次调用应透明重连并成功
            srv2, _ = await start_psu_server(port)
            try:
                resp = await client.request("voltage_query")
                assert resp["status"] == "success"
            finally:
                await client._drop_connection()
                srv2.close()
                await srv2.wait_closed()

        asyncio.run(scenario())

    def test_server_down_raises_unavailable(self, unavailable_port):
        async def scenario():
            client = PsuClient(host=HOST, port=unavailable_port, timeout=0.5)
            with pytest.raises(PsuUnavailableError):
                await client.request("voltage_query")

        asyncio.run(scenario())

    def test_lease_survives_lazy_reconnect(self, monkeypatch, tmp_path):
        """控制权按 client_id 存续：桥透明重连后不必重新认领，争用方依旧被拒。"""
        make_fake_device(monkeypatch)
        path = tmp_path / "clients.json"
        path.write_text(json.dumps({"schema_version": 1, "clients": {
            "mcp-bridge": {"tier": "L1", "name": "AI 助手 (MCP 桥)"},
            "rival": {"tier": "L1", "name": "争用的另一端"},
        }}), encoding="utf-8")
        use_registry(ClientRegistry.load(path))

        async def scenario():
            srv1, port = await start_psu_server()
            client = PsuClient(host=HOST, port=port, timeout=2.0)
            assert (await client.request("set_voltage", value=12.0))["status"] == "success"
            srv1.close()
            client._writer.transport.abort()
            await asyncio.sleep(0.1)

            srv2, _ = await start_psu_server(port)
            rival = PsuClient(host=HOST, port=port, timeout=2.0, client_id="rival")
            try:
                status = await client.request("lease_status")
                assert status["holder"] == "mcp-bridge" and status["holder_connected"] is True
                assert (await client.request("set_voltage", value=13.0))["status"] == "success"
                denied = await rival.request("set_voltage", value=14.0)
                assert denied["status"] == "error" and "controlled_by_other" in denied["message"]
            finally:
                await client._drop_connection()
                await rival._drop_connection()
                srv2.close()
                await srv2.wait_closed()

        asyncio.run(scenario())

    def test_lease_expires_while_bridge_is_idle(self, monkeypatch):
        """超过时限后控制权自动释放：重连的桥不再被认作持有者，需要重新认领。"""
        make_fake_device(monkeypatch)
        monkeypatch.setattr(lease_config, "ttl_seconds", 0.2)

        async def scenario():
            srv, port = await start_psu_server()
            client = PsuClient(host=HOST, port=port, timeout=2.0)
            try:
                assert (await client.request("set_voltage", value=12.0))["status"] == "success"
                assert (await client.request("lease_status"))["holder"] == "mcp-bridge"
                await asyncio.sleep(0.3)
                assert (await client.request("lease_status"))["holder"] is None
                assert (await client.request("set_voltage", value=13.0))["status"] == "success"
                assert (await client.request("lease_status"))["holder"] == "mcp-bridge"
            finally:
                await client._drop_connection()
                srv.close()
                await srv.wait_closed()

        asyncio.run(scenario())

    def test_unregistered_client_id_fails_with_server_reason(self, monkeypatch, tmp_path):
        """无界面模式下未登记的桥身份应直接给出拒绝原因，而不是被传输层重试掩盖。"""
        make_fake_device(monkeypatch)
        path = tmp_path / "empty-clients.json"
        path.write_text(json.dumps({"schema_version": 1, "clients": {}}), encoding="utf-8")
        use_registry(ClientRegistry.load(path))

        async def scenario():
            srv, port = await start_psu_server()
            try:
                client = PsuClient(host=HOST, port=port, timeout=2.0)
                with pytest.raises(PsuAccessDeniedError) as ei:
                    await client.request("voltage_query")
                assert "no_approver" in str(ei.value)
            finally:
                await client._drop_connection()
                srv.close()
                await srv.wait_closed()

        asyncio.run(scenario())

    def test_client_id_and_tier_are_configurable(self, monkeypatch, tmp_path):
        """只读场景可用更低身份登录，验证 client_id/tier 不是硬编码在请求里。"""
        make_fake_device(monkeypatch)
        path = tmp_path / "clients.json"
        path.write_text(json.dumps({"schema_version": 1, "clients": {
            "observer": {"tier": "L0", "name": "只读观察端"}
        }}), encoding="utf-8")
        use_registry(ClientRegistry.load(path))

        async def scenario():
            srv, port = await start_psu_server()
            try:
                client = PsuClient(host=HOST, port=port, timeout=2.0,
                                   client_id="observer", tier="L0")
                assert (await client.request("voltage_query"))["status"] == "success"
                denied = await client.request("set_voltage", value=12.0)
                assert denied["status"] == "error" and "insufficient_tier" in denied["message"]
            finally:
                await client._drop_connection()
                srv.close()
                await srv.wait_closed()

        asyncio.run(scenario())


class TestToolErrorMapping:
    def _scenario(self, monkeypatch, connected, body):
        make_fake_device(monkeypatch, connected=connected)

        async def scenario():
            srv, port = await start_psu_server()
            tools.client = PsuClient(host=HOST, port=port, timeout=2.0)
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

    def test_app_not_running_maps_to_start_hint(self, monkeypatch, unavailable_port):
        make_fake_device(monkeypatch)

        async def body():
            with pytest.raises(ToolError) as ei:
                await tools.set_current(1.0)
            assert "powerSupplyMaster" in str(ei.value)

        async def scenario_no_server():
            tools.client = PsuClient(host=HOST, port=unavailable_port, timeout=0.5)
            await body()

        asyncio.run(scenario_no_server())


class TestGetStatus:
    def test_aggregates_all_fields(self, monkeypatch):
        make_fake_device(monkeypatch)

        async def body():
            return await tools.get_status()

        async def scenario():
            srv, port = await start_psu_server()
            tools.client = PsuClient(host=HOST, port=port, timeout=2.0)
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
            "limits": {
                "max_voltage_v": 30.0,
                "max_current_a": 5.0,
                "server_version": version.__version__,
            },
        }

    def test_server_version_follows_the_running_app(self, monkeypatch):
        """版本号必须现场取自上位机真源，不是桥里抄的一份。"""
        make_fake_device(monkeypatch)

        async def scenario():
            srv, port = await start_psu_server()
            tools.client = PsuClient(host=HOST, port=port, timeout=2.0)
            try:
                return await tools.get_status()
            finally:
                await tools.client._drop_connection()
                srv.close()
                await srv.wait_closed()

        monkeypatch.setattr(version, "__version__", "9.9.9")
        assert asyncio.run(scenario())["limits"]["server_version"] == "9.9.9"
