"""Wire-level integration tests with an in-process server and simulated SCPI device.

Run from the repository root:
    python -m pytest src
    python -m pytest src/server/test_client.py
    python -m pytest src -m "integration and not hardware"
"""
import asyncio

import pytest

from .conftest import CLIENT_ID, JsonSocketClient, _start, _stop
from .protocal.protocal import (
    BaseRequest,
    CloseDeviceRequest,
    EchoRequest,
    ListClientsRequest,
    LoginRequest,
    LogoutRequest,
    OpenDeviceRequest,
    SettingQueryRequest,
    SetVoltageRequest,
    VoltageQueryRequest,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestSocketServer:
    async def test_echo_command(self, control_client):
        response = await control_client.request(EchoRequest(message="Hello, Server!"))

        assert response["status"] == "success"
        assert response["message"] == "Hello, Server!"

    async def test_business_command_requires_login(self, control_client):
        response = await control_client.request(SetVoltageRequest(value=5.0))

        assert response["status"] == "error"
        assert "not_authenticated" in response["message"]

    async def test_login_command(self, control_client):
        response = await control_client.request(LoginRequest(client_id=CLIENT_ID, tier="L1"))

        assert response["status"] == "success"
        assert response["client_id"] == CLIENT_ID and response["tier"] == "L2"
        # The registry is an allow-list, not a reusable credential store.
        assert not {"token", "secret", "password"} & set(response)

    async def test_logout_command(self, control_client):
        assert (await control_client.login(tier="L2"))["status"] == "success"
        assert (await control_client.request(LogoutRequest()))["status"] == "success"

        after = await control_client.request(SetVoltageRequest(value=5.0))
        assert after["status"] == "error" and "not_authenticated" in after["message"]

    async def test_open_device_command(self, control_client, simulated_scpi_peer):
        assert (await control_client.login(tier="L2"))["status"] == "success"

        response = await control_client.request(
            OpenDeviceRequest(serial_number=simulated_scpi_peer.serial_number)
        )

        assert response["status"] == "success"
        assert "FAKE" in response["message"]
        assert "*IDN?" in simulated_scpi_peer.calls

    async def test_close_device_command(self, opened_device):
        response = await opened_device.request(CloseDeviceRequest(device_id="device_id_123"))
        assert response["status"] == "success"

        after = await opened_device.request(VoltageQueryRequest())
        assert after["status"] == "error" and "device not connected" in after["message"]

    async def test_set_voltage_command(self, opened_device, simulated_scpi_peer):
        response = await opened_device.request(SetVoltageRequest(value=5.0))

        assert response["status"] == "success"
        assert response["value"] == 5.0
        # Prove the real driver sent bytes through the transport, rather than mocking it.
        assert "VOLTage 5.00" in simulated_scpi_peer.calls

    async def test_setting_query_over_the_wire(self, control_client):
        assert (await control_client.login())["status"] == "success"

        response = await control_client.request(SettingQueryRequest())

        assert response["status"] == "success"
        assert response["max_voltage"] == 30.0
        assert response["version"]

    @pytest.mark.skip(reason="Unknown-command response contract is not yet defined")
    async def test_unknown_command(self, control_client):
        from typing import Literal

        class UnknownRequest(BaseRequest):
            type: Literal["unknown_cmd"] = "unknown_cmd"
            data: str = "test"

        response = await control_client.request(UnknownRequest(data="test data"))
        assert response["status"] == "error"
        assert "Unknown command" in response.get("message", "")


class TestConnectionManagement:
    async def test_connection_establishment(self, control_server):
        assert control_server > 0
        reader, writer = await asyncio.open_connection("127.0.0.1", control_server)
        try:
            assert writer.is_closing() is False
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_multiple_connections(self, control_server, control_client):
        """Three unauthenticated sockets coexist with one authenticated client."""
        clients = [JsonSocketClient(port=control_server) for _ in range(3)]
        try:
            for client in clients:
                await client.connect()
            # A completed round-trip proves each server handler has opened its session.
            ready = await asyncio.gather(*(
                client.request(EchoRequest(message="ready")) for client in clients
            ))
            assert all(response["status"] == "success" for response in ready)
            assert (await control_client.login(tier="L2"))["status"] == "success"

            listed = await control_client.request(ListClientsRequest())
            assert listed["status"] == "success"
            assert len(listed["clients"]) == 4
            assert {c["client_id"] for c in listed["clients"]} == {None, CLIENT_ID}
            assert {c["tier"] for c in listed["clients"] if c["authenticated"]} == {"L2"}
        finally:
            for client in clients:
                await client.close()

    @pytest.mark.parametrize(
        "response_prefix", [b"", b"\x00\x00\x00\x40"], ids=["header", "body"]
    )
    async def test_request_read_times_out(self, response_prefix):
        """A peer that stalls before the header or body cannot hang the test client."""
        async def silent_peer(reader, writer):
            try:
                header = await reader.readexactly(4)
                await reader.readexactly(int.from_bytes(header, "big"))
                if response_prefix:
                    writer.write(response_prefix)
                    await writer.drain()
                await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()

        server, port, tasks = await _start(silent_peer)
        client = JsonSocketClient(port=port, timeout=0.1)
        try:
            await client.connect()
            with pytest.raises(asyncio.TimeoutError):
                await client.request(EchoRequest(message="timeout"))
        finally:
            await client.close()
            await _stop(server, tasks)


class TestDevice:
    async def test_set_voltage_command(self, opened_device):
        response = await opened_device.request(SetVoltageRequest(value=5.0))

        assert response["status"] == "success"
        assert response["value"] == 5.0

    async def test_voltage_query_command(self, opened_device):
        # Simulator state is per-test; establish the value instead of relying on test order.
        assert (await opened_device.request(SetVoltageRequest(value=5.0)))["status"] == "success"

        response = await opened_device.request(VoltageQueryRequest())

        assert response["status"] == "success"
        assert abs(response["value"] - 5.0) < 0.11


class TestVoltageDevice:
    _target_voltage = 5.0

    async def test_set_voltage_command(self, opened_device):
        response = await opened_device.request(SetVoltageRequest(value=self._target_voltage))

        assert response["status"] == "success"
        assert response["value"] == self._target_voltage

    # pytest-repeat is not a dependency. Parametrization makes all five executions real.
    @pytest.mark.parametrize("attempt", range(5))
    async def test_repeat_voltage_query_command(self, opened_device, attempt):
        assert (await opened_device.request(
            SetVoltageRequest(value=self._target_voltage)))["status"] == "success"

        response = await opened_device.request(VoltageQueryRequest())

        assert response["status"] == "success"
        assert abs(response["value"] - self._target_voltage) < 0.11
