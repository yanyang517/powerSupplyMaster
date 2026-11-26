"""Socket lifecycle messages must use logging and report real bind addresses."""
import logging
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
