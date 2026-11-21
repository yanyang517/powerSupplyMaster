"""psu_client 单元测试：假 TCP 对端（长度前缀 + JSON）验证线上协议行为。

不依赖 powerSupplyMaster 仓库任何模块。运行：在包目录下 python -m pytest tests
"""
import asyncio
import json
import struct

import pytest

from psu_mcp.psu_client import (
    PsuAccessDeniedError,
    PsuClient,
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
        for w in list(self._writers):
            w.close()
        self._server.close()

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
