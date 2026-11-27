"""psu_client 单元测试：假 TCP 对端（长度前缀 + JSON）验证线上协议行为。

不依赖 powerSupplyMaster 仓库任何模块。运行：在包目录下 python -m pytest tests
"""
import asyncio
import json
import struct

import pytest

from psu_mcp import psu_client
from psu_mcp.psu_client import (
    PsuAccessDeniedError,
    PsuClient,
    PsuProtocolError,
    PsuUnavailableError,
)

HOST = "127.0.0.1"


class FakeServer:
    """可控协议对端：记录收到的帧，handler 返回 dict 应答、返回 None 表示掐断连接。"""

    def __init__(self, handler):
        self.handler = handler
        self.received = []
        self.connections = 0
        self._server = None
        self._writers = []

    async def start(self):
        self._server = await asyncio.start_server(self._serve, HOST, 0)
        return self._server.sockets[0].getsockname()[1]

    async def stop(self):
        writers = list(self._writers)
        for writer in writers:
            writer.close()
        self._server.close()
        await self._server.wait_closed()
        for writer in writers:
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def _serve(self, reader, writer):
        self.connections += 1
        self._writers.append(writer)
        state = {"count": 0}
        try:
            while True:
                header = await reader.readexactly(4)
                (length,) = struct.unpack(">I", header)
                frame = json.loads((await reader.readexactly(length)).decode("utf-8"))
                self.received.append(frame)
                state["count"] += 1
                reply = self.handler(frame, state)
                if reply is None:
                    writer.close()
                    return
                body = json.dumps(reply).encode("utf-8")
                writer.write(struct.pack(">I", len(body)) + body)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            if writer in self._writers:
                self._writers.remove(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass


def login_ok(business_handler):
    """login 帧恒应答 success，其余交给 business_handler。"""

    def handler(frame, state):
        if frame["type"] == "login":
            return {"request_id": frame["request_id"], "status": "success"}
        return business_handler(frame, state)

    return handler


def echo_ok(frame, state):
    return {"request_id": frame["request_id"], "status": "success", "value": 12.3}


def test_login_handshake_before_business_frame():
    async def scenario():
        srv = FakeServer(login_ok(echo_ok))
        port = await srv.start()
        client = PsuClient(HOST, port, timeout=2.0)
        try:
            response = await client.request("voltage_query")
        finally:
            await client._drop_connection()
            await srv.stop()
        return srv, response

    srv, response = asyncio.run(scenario())
    assert response["value"] == 12.3
    types = [f["type"] for f in srv.received]
    assert types == ["login", "voltage_query"]
    login = srv.received[0]
    assert login["client_id"] == "mcp-bridge" and login["tier"] == "L2"


def test_request_id_mismatch_retries_once_then_unavailable():
    def wrong_id(frame, state):
        return {"request_id": "deadbeef", "status": "success"}

    async def scenario():
        srv = FakeServer(login_ok(wrong_id))
        port = await srv.start()
        client = PsuClient(HOST, port, timeout=2.0)
        try:
            with pytest.raises(PsuUnavailableError):
                await client.request("voltage_query")
        finally:
            await client._drop_connection()
            await srv.stop()
        return srv

    srv = asyncio.run(scenario())
    business = [f for f in srv.received if f["type"] != "login"]
    assert len(business) == 2  # 透明重试一次后放弃


def test_error_frame_without_request_id_passes_through():
    def err_frame(frame, state):
        return {"error": "dispatcher blew up"}

    async def scenario():
        srv = FakeServer(login_ok(err_frame))
        port = await srv.start()
        client = PsuClient(HOST, port, timeout=2.0)
        try:
            response = await client.request("voltage_query")
        finally:
            await client._drop_connection()
            await srv.stop()
        return response

    response = asyncio.run(scenario())
    assert response == {"error": "dispatcher blew up"}


def test_login_refused_raises_access_denied():
    def refused_login(frame, state):
        if frame["type"] == "login":
            return {"request_id": frame["request_id"], "status": "error",
                    "message": "tier not approved"}
        return echo_ok(frame, state)

    async def scenario():
        srv = FakeServer(refused_login)
        port = await srv.start()
        client = PsuClient(HOST, port, timeout=2.0)
        try:
            with pytest.raises(PsuAccessDeniedError, match="tier not approved"):
                await client.request("voltage_query")
        finally:
            await client._drop_connection()
            await srv.stop()

    asyncio.run(scenario())


def test_peer_disconnect_triggers_transparent_reconnect():
    calls = {"business": 0}

    def handler(frame, state):
        if frame["type"] == "login":
            return {"request_id": frame["request_id"], "status": "success"}
        calls["business"] += 1
        if calls["business"] == 1:
            return None  # 首个业务请求：对端掐断
        return echo_ok(frame, state)

    async def scenario():
        srv = FakeServer(handler)
        port = await srv.start()
        client = PsuClient(HOST, port, timeout=2.0)
        try:
            response = await client.request("voltage_query")
        finally:
            await client._drop_connection()
            await srv.stop()
        return srv, response

    srv, response = asyncio.run(scenario())
    assert response["value"] == 12.3
    assert srv.connections == 2  # 断连后新连接并重走 login


@pytest.mark.parametrize("request_type", ["set_voltage", "set_current", "set_on_off"])
@pytest.mark.parametrize("failure", [asyncio.TimeoutError("timeout"), PsuProtocolError("bad frame")])
def test_write_commands_are_never_retried_after_transport_failure(request_type, failure):
    calls = []

    async def roundtrip(payload):
        calls.append(payload)
        raise failure

    async def scenario():
        client = PsuClient(timeout=0.01)
        client._roundtrip = roundtrip
        with pytest.raises(PsuUnavailableError):
            await client.request(request_type, value=1.0)
        return calls

    calls = asyncio.run(scenario())
    assert len(calls) == 1


def test_unknown_command_is_not_assumed_safe_to_retry():
    calls = []

    async def roundtrip(payload):
        calls.append(payload)
        raise PsuProtocolError("bad frame")

    async def scenario():
        client = PsuClient()
        client._roundtrip = roundtrip
        with pytest.raises(PsuUnavailableError):
            await client.request("future_write")

    asyncio.run(scenario())
    assert len(calls) == 1


def test_response_size_limit_rejects_header_before_payload_read():
    class Reader:
        def __init__(self):
            self.read_sizes = []

        async def readexactly(self, size):
            self.read_sizes.append(size)
            if size == 4:
                return struct.pack(">I", 129)
            raise AssertionError("oversized response payload must not be read")

    class Writer:
        def write(self, data):
            pass

        async def drain(self):
            pass

    async def scenario():
        reader = Reader()
        client = PsuClient(max_response_bytes=128)
        client._reader = reader
        client._writer = Writer()
        with pytest.raises(PsuProtocolError, match="exceeds limit 128"):
            await client._exchange({"request_id": "r1"})
        return reader.read_sizes

    assert asyncio.run(scenario()) == [4]


def test_connection_timeout_is_bounded_and_read_may_retry(monkeypatch):
    calls = []

    async def hanging_connect(host, port):
        calls.append((host, port))
        await asyncio.Event().wait()

    monkeypatch.setattr(psu_client.asyncio, "open_connection", hanging_connect)

    async def scenario():
        client = PsuClient(connection_timeout=0.01, timeout=1.0)
        with pytest.raises(PsuUnavailableError, match="timed out"):
            await client.request("voltage_query")
        assert client._reader is None and client._writer is None

    asyncio.run(scenario())
    assert len(calls) == 2


@pytest.mark.parametrize("request_type, expected_attempts", [
    ("voltage_query", 2),
    ("set_voltage", 1),
    ("set_on_off", 1),
])
def test_response_timeout_retry_policy(request_type, expected_attempts):
    class Reader:
        def __init__(self):
            self.headers = 0

        async def readexactly(self, size):
            if size == 4:
                self.headers += 1
                return struct.pack(">I", 2)
            await asyncio.Event().wait()

    class Writer:
        def write(self, data):
            pass

        async def drain(self):
            pass

    async def scenario():
        reader = Reader()
        client = PsuClient(timeout=0.01)
        client._reader = reader
        client._writer = Writer()

        async def already_connected():
            pass

        async def keep_test_reader():
            pass

        client._ensure_connection = already_connected
        client._drop_connection = keep_test_reader
        with pytest.raises(PsuUnavailableError, match="timed out"):
            await client.request(request_type, value=1.0)
        return reader.headers

    assert asyncio.run(scenario()) == expected_attempts


def test_write_protocol_failure_is_not_retried_on_wire():
    def wrong_id(frame, state):
        return {"request_id": "deadbeef", "status": "success"}

    async def scenario():
        srv = FakeServer(login_ok(wrong_id))
        port = await srv.start()
        client = PsuClient(HOST, port, timeout=2.0)
        try:
            with pytest.raises(PsuUnavailableError, match="request_id mismatch"):
                await client.request("set_voltage", value=5.0)
        finally:
            await client._drop_connection()
            await srv.stop()
        return srv

    srv = asyncio.run(scenario())
    business = [f for f in srv.received if f["type"] != "login"]
    assert len(business) == 1
    assert srv.connections == 1


@pytest.mark.parametrize("cancel_during_login", [False, True])
def test_request_cancellation_closes_and_clears_connection(monkeypatch, cancel_during_login):
    started = asyncio.Event()

    class Writer:
        def __init__(self):
            self.closed = False

        def write(self, data):
            pass

        async def drain(self):
            started.set()
            await asyncio.Event().wait()

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    async def scenario():
        writer = Writer()
        reader = object()
        client = PsuClient(timeout=1.0, close_timeout=1.0)
        if cancel_during_login:
            async def open_connection(host, port):
                return reader, writer

            async def hanging_login():
                started.set()
                await asyncio.Event().wait()

            monkeypatch.setattr(psu_client.asyncio, "open_connection", open_connection)
            client._login = hanging_login
        else:
            client._reader = reader
            client._writer = writer

        task = asyncio.create_task(client.request("set_voltage", value=5.0))
        await asyncio.wait_for(started.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return client, writer

    client, writer = asyncio.run(scenario())
    assert writer.closed
    assert client._reader is None and client._writer is None


def test_drop_connection_close_wait_is_bounded_and_clears_references():
    class Writer:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        async def wait_closed(self):
            await asyncio.Event().wait()

    async def scenario():
        writer = Writer()
        client = PsuClient(close_timeout=0.01)
        client._reader = object()
        client._writer = writer
        await asyncio.wait_for(client._drop_connection(), timeout=0.5)
        return client, writer

    client, writer = asyncio.run(scenario())
    assert writer.closed
    assert client._reader is None and client._writer is None


def test_drop_connection_clears_references_when_close_raises():
    class Writer:
        def close(self):
            raise ConnectionResetError("peer reset")

        async def wait_closed(self):
            raise AssertionError("wait_closed must not run after close fails")

    async def scenario():
        client = PsuClient()
        client._reader = object()
        client._writer = Writer()
        await client._drop_connection()
        return client

    client = asyncio.run(scenario())
    assert client._reader is None and client._writer is None
