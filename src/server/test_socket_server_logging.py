"""Socket lifecycle, transport boundaries and admission tests."""
import asyncio
import json
import logging
import struct
from types import SimpleNamespace

import pytest

from server import socket_server
from server.socket_server import SocketServer


class _StopServing(Exception):
    pass


class _FakeServer:
    def __init__(self, addresses):
        self.sockets = [
            SimpleNamespace(getsockname=lambda address=address: address)
            for address in addresses
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def serve_forever(self):
        raise _StopServing


@pytest.mark.asyncio
async def test_start_logs_actual_bound_address_without_print(monkeypatch, caplog, capsys):
    fake_server = _FakeServer([("127.0.0.1", 43123)])

    async def fake_start_server(handler, host, port):
        assert (host, port) == ("0.0.0.0", 0)
        return fake_server

    monkeypatch.setattr(socket_server.asyncio, "start_server", fake_start_server)
    server = SocketServer(host="0.0.0.0", port=0)

    with caplog.at_level(logging.INFO, logger="server.socket_server"):
        with pytest.raises(_StopServing):
            await server.start()

    assert "Server started on 127.0.0.1:43123" in caplog.text
    assert "0.0.0.0:0" not in caplog.text
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.asyncio
async def test_client_disconnect_uses_logger_without_print(monkeypatch, caplog, capsys):
    class FakeReader:
        async def read(self, size):
            return b""

    class FakeWriter:
        def get_extra_info(self, name):
            assert name == "peername"
            return ("127.0.0.1", 43210)

        def close(self):
            pass

        async def wait_closed(self):
            pass

    class FakeHub:
        def __init__(self):
            self.closed = []

        def open(self, peer):
            return SimpleNamespace(session_id="session-1", close_after_response=False)

        def close(self, session):
            self.closed.append(session.session_id)

    hub = FakeHub()
    monkeypatch.setattr(socket_server, "hub", hub)
    server = SocketServer()

    with caplog.at_level(logging.INFO, logger="server.socket_server"):
        await server.handle_client(FakeReader(), FakeWriter())

    assert hub.closed == ["session-1"]
    assert "Client disconnected" in caplog.text
    assert "Connection closed while reading" in caplog.text
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_ipv6_bound_address_is_unambiguous():
    server = _FakeServer([("::1", 18888)])
    assert socket_server._bound_addresses(server) == ["[::1]:18888"]


def _frame(payload):
    body = json.dumps(payload).encode("utf-8")
    return struct.pack(">I", len(body)) + body


class _PrefixReader:
    def __init__(self, prefix):
        self.prefix = prefix
        self.read_sizes = []

    async def read(self, size):
        self.read_sizes.append(size)
        if self.prefix:
            prefix, self.prefix = self.prefix[:size], self.prefix[size:]
            return prefix
        raise AssertionError("oversized payload must not be read")


@pytest.mark.asyncio
async def test_oversize_length_is_rejected_before_payload_read():
    limit = 128
    reader = _PrefixReader(struct.pack(">I", limit + 1))
    server = SocketServer(max_frame_bytes=limit)

    with pytest.raises(socket_server.FrameTooLargeError, match="exceeds limit 128"):
        await server.parse_message(reader)

    assert reader.read_sizes == [4]


@pytest.mark.asyncio
async def test_frame_at_limit_is_accepted():
    payload = '{"type":"echo"}'
    body = payload.encode("utf-8")
    reader = _PrefixReader(struct.pack(">I", len(body)) + body)

    assert await SocketServer(max_frame_bytes=len(body)).parse_message(reader) == payload


@pytest.mark.asyncio
async def test_slow_peer_times_out_without_occupying_connection_slot():
    class SlowReader:
        async def read(self, size):
            await asyncio.Event().wait()

    class Writer:
        closed = False

        def get_extra_info(self, name):
            return ("127.0.0.1", 55000)

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    writer = Writer()
    server = SocketServer(read_timeout=0.01, idle_timeout=1.0)
    await server.handle_client(SlowReader(), writer)

    assert writer.closed
    assert server._active_connections == 0


@pytest.mark.asyncio
async def test_idle_timeout_bounds_trickled_incomplete_frame():
    class TrickleReader:
        async def read(self, size):
            await asyncio.sleep(0.005)
            return b"\x00"

    server = SocketServer(read_timeout=1.0, idle_timeout=0.015)
    with pytest.raises(TimeoutError, match="idle read timed out"):
        await server._timed(server.parse_message(TrickleReader()), server.idle_timeout, "idle read")


@pytest.mark.asyncio
async def test_dispatch_timeout_returns_error_and_closes_poisoned_session(caplog):
    calls = []
    sessions = []

    class Dispatcher:
        async def dispatch(self, data, session):
            calls.append(data)
            sessions.append(session)
            if len(calls) == 1:
                await asyncio.Event().wait()
            return SimpleNamespace(model_dump_json=lambda: '{"status":"success"}')

    class Writer:
        def __init__(self):
            self.data = b""
            self.closed = False

        def get_extra_info(self, name):
            return ("127.0.0.1", 55001)

        def write(self, data):
            self.data += data

        async def drain(self):
            pass

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    writer = Writer()
    server = SocketServer(dispatch_timeout=0.01)
    server.dispatcher = Dispatcher()
    request = _frame({"type": "echo", "request_id": "r1", "message": "ping"})

    class Reader:
        def __init__(self):
            # A poisoned session would dispatch this second request if the
            # timeout handler accidentally continued the read loop.
            self.data = request + request

        async def read(self, size):
            data, self.data = self.data[:size], self.data[size:]
            return data

    with caplog.at_level(logging.WARNING, logger="server.socket_server"):
        await server.handle_client(Reader(), writer)

    length = struct.unpack(">I", writer.data[:4])[0]
    assert json.loads(writer.data[4:4 + length])["error"] == "dispatch_timeout"
    assert len(writer.data) == 4 + length  # no response to the queued second request
    assert len(calls) == 1
    assert len(socket_server.hub) == 0
    assert socket_server.hub.get(sessions[0].session_id) is None
    assert "Request dispatch timed out" in caplog.text
    assert "Closing session" in caplog.text
    assert writer.closed and server._active_connections == 0


@pytest.mark.asyncio
async def test_handler_cancellation_during_dispatch_closes_socket_and_session():
    started = asyncio.Event()

    class Dispatcher:
        async def dispatch(self, data, session):
            started.set()
            await asyncio.Event().wait()

    class Writer:
        def __init__(self):
            self.closed = False

        def get_extra_info(self, name):
            return ("127.0.0.1", 55004)

        def write(self, data):
            pass

        async def drain(self):
            pass

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    class Reader:
        def __init__(self):
            self.data = _frame({"type": "echo", "request_id": "r1", "message": "ping"})

        async def read(self, size):
            data, self.data = self.data[:size], self.data[size:]
            return data

    writer = Writer()
    server = SocketServer(dispatch_timeout=10.0)
    server.dispatcher = Dispatcher()
    task = asyncio.create_task(server.handle_client(Reader(), writer))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert writer.closed
    assert server._active_connections == 0
    assert len(socket_server.hub) == 0


@pytest.mark.asyncio
async def test_write_timeout_closes_connection_and_releases_slot():
    class Dispatcher:
        async def dispatch(self, data, session):
            return SimpleNamespace(model_dump_json=lambda: '{"status":"success"}')

    class Writer:
        def __init__(self):
            self.closed = False

        def get_extra_info(self, name):
            return ("127.0.0.1", 55002)

        def write(self, data):
            pass

        async def drain(self):
            await asyncio.Event().wait()

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    writer = Writer()
    server = SocketServer(write_timeout=0.01)
    server.dispatcher = Dispatcher()
    request = _frame({"type": "echo", "request_id": "r1", "message": "ping"})

    class Reader:
        def __init__(self):
            self.data = request

        async def read(self, size):
            data, self.data = self.data[:size], self.data[size:]
            return data

    await server.handle_client(Reader(), writer)
    assert writer.closed and server._active_connections == 0


@pytest.mark.asyncio
async def test_close_timeout_is_bounded():
    class Writer:
        closed = False

        def get_extra_info(self, name):
            return ("127.0.0.1", 55003)

        def close(self):
            self.closed = True

        async def wait_closed(self):
            await asyncio.Event().wait()

    class Reader:
        async def read(self, size):
            return b""

    writer = Writer()
    server = SocketServer(close_timeout=0.01)
    await asyncio.wait_for(server.handle_client(Reader(), writer), timeout=0.5)
    assert writer.closed and server._active_connections == 0


@pytest.mark.asyncio
async def test_connection_cap_rejects_without_opening_session_then_recovers(caplog):
    server = SocketServer(host="127.0.0.1", port=0, max_connections=1, idle_timeout=5.0)
    listener = await asyncio.start_server(server.handle_client, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    first_reader = first_writer = second_reader = second_writer = None
    try:
        first_reader, first_writer = await asyncio.open_connection("127.0.0.1", port)
        for _ in range(20):
            if server._active_connections == 1:
                break
            await asyncio.sleep(0)
        assert len(socket_server.hub) == 1

        second_reader, second_writer = await asyncio.open_connection("127.0.0.1", port)
        header = await asyncio.wait_for(second_reader.readexactly(4), 1.0)
        length = struct.unpack(">I", header)[0]
        rejection = json.loads(await second_reader.readexactly(length))
        assert rejection == {"error": "connection_limit_exceeded"}
        assert await asyncio.wait_for(second_reader.read(), 1.0) == b""
        assert len(socket_server.hub) == 1
        assert "connection limit reached" in caplog.text

        first_writer.close()
        await first_writer.wait_closed()
        assert await asyncio.wait_for(first_reader.read(), 1.0) == b""
        for _ in range(20):
            if server._active_connections == 0:
                break
            await asyncio.sleep(0)
        assert server._active_connections == 0

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            writer.write(_frame({"type": "echo", "request_id": "ok", "message": "ping"}))
            await writer.drain()
            header = await asyncio.wait_for(reader.readexactly(4), 1.0)
            length = struct.unpack(">I", header)[0]
            response = json.loads(await reader.readexactly(length))
            assert response["status"] == "success"
        finally:
            writer.close()
            await writer.wait_closed()
            for _ in range(20):
                if server._active_connections == 0:
                    break
                await asyncio.sleep(0)
            assert server._active_connections == 0
    finally:
        for writer in (first_writer, second_writer):
            if writer is not None:
                writer.close()
        listener.close()
        await listener.wait_closed()
