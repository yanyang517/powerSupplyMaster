"""P0-5 regressions for loopback-by-default, intranet-only TCP exposure.

The admission allow-list is not authentication: client_id is self-declared.
These tests pin the default bind, explicit wildcard opt-in, exposure warning,
fail-closed host classification, real-address logging, and CLI propagation.

Run from the repository root:
python -m pytest src/server/test_listen_address.py
"""
import logging
from types import SimpleNamespace

import pytest

import app as app_module
from server import socket_server as socket_server_module
from server.runtime_config import SERVER_HOST, is_loopback_host
from server.socket_server import SocketServer, server_main

MODULE_LOGGER = "server.socket_server"


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

    async def __aexit__(self, *exc):
        return False

    async def serve_forever(self):
        raise _StopServing


@pytest.fixture
def captured_bind(monkeypatch):
    """Capture bind arguments without opening a real network listener."""
    seen = {"addresses": [("127.0.0.1", 43123)]}

    async def fake_start_server(client_cb, host, port, *args, **kwargs):
        seen["host"] = host
        seen["port"] = port
        return _FakeServer(seen["addresses"])

    monkeypatch.setattr(socket_server_module.asyncio, "start_server", fake_start_server)
    return seen


def test_default_host_is_loopback():
    assert SERVER_HOST == "127.0.0.1"
    assert SocketServer().host == SERVER_HOST
    assert is_loopback_host(SocketServer().host)


@pytest.mark.parametrize("host,expected", [
    ("127.0.0.1", True),
    ("127.1.2.3", True),
    ("::1", True),
    ("0:0:0:0:0:0:0:1", True),
    ("localhost", True),
    ("LOCALHOST", True),
    ("0.0.0.0", False),
    ("::", False),
    ("192.168.1.10", False),
    ("", False),
    ("   ", False),
    (None, False),
    ("bench-pc", False),
    ("definitely.invalid", False),
    ("999.999.999.999", False),
    ("127.0.0.1.example.com", False),
])
def test_loopback_detection_fails_closed(host, expected):
    assert is_loopback_host(host) is expected


@pytest.mark.asyncio
async def test_explicit_wildcard_reaches_bind_call(captured_bind):
    with pytest.raises(_StopServing):
        await SocketServer(host="0.0.0.0", port=0).start()

    assert captured_bind["host"] == "0.0.0.0"
    assert captured_bind["port"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("host,bound_address,should_warn", [
    ("127.0.0.1", ("127.0.0.1", 43123), False),
    ("::1", ("::1", 43123), False),
    ("localhost", ("127.0.0.1", 43123), False),
    ("localhost", ("192.168.1.10", 43123), True),
    ("0.0.0.0", ("0.0.0.0", 43123), True),
    ("0.0.0.0", ("127.0.0.1", 43123), False),
    ("192.168.1.10", ("192.168.1.10", 43123), True),
    ("bench-pc", ("192.168.1.10", 43123), True),
    ("bench-pc", ("127.0.0.1", 43123), False),
    ("127.0.0.1", ("unverified-host", 43123), True),
])
async def test_warning_tracks_exposure(
    host, bound_address, should_warn, captured_bind, caplog
):
    captured_bind["addresses"] = [bound_address]

    with caplog.at_level(logging.INFO, logger=MODULE_LOGGER):
        with pytest.raises(_StopServing):
            await SocketServer(host, port=0).start()

    assert captured_bind["host"] == host
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert bool(warnings) is should_warn, caplog.text
    if should_warn:
        text = " ".join(record.getMessage() for record in warnings).lower()
        assert "no authentication" in text
        assert "token" in text and "mtls" in text
        assert "isolated, trusted intranet/experimental network" in text
        assert "--listen 127.0.0.1" in text
        assert socket_server_module._bound_addresses(_FakeServer([bound_address]))[0] in text


@pytest.mark.asyncio
async def test_startup_log_reports_actual_bound_address(captured_bind, caplog):
    captured_bind["addresses"] = [("127.0.0.1", 43123), ("::1", 43123)]

    with caplog.at_level(logging.INFO, logger=MODULE_LOGGER):
        with pytest.raises(_StopServing):
            await SocketServer(port=18888).start()

    assert "Server started on 127.0.0.1:43123, [::1]:43123" in caplog.text
    assert "127.0.0.1:18888" not in caplog.text


@pytest.mark.asyncio
async def test_warning_if_any_actual_address_is_non_loopback(captured_bind, caplog):
    captured_bind["addresses"] = [
        ("127.0.0.1", 43123),
        ("192.168.1.10", 43123),
        ("::1", 43123),
    ]

    with caplog.at_level(logging.INFO, logger=MODULE_LOGGER):
        with pytest.raises(_StopServing):
            await SocketServer(host="localhost", port=0).start()

    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "192.168.1.10:43123" in warnings[0]
    assert "127.0.0.1:43123" in warnings[0]
    assert "[::1]:43123" in warnings[0]


@pytest.mark.asyncio
async def test_unreadable_actual_address_warns_even_for_localhost(
    captured_bind, caplog, monkeypatch
):
    class BrokenSocket:
        def getsockname(self):
            raise OSError("address unavailable")

    fake_server = _FakeServer([("127.0.0.1", 43123)])
    fake_server.sockets = [BrokenSocket()]

    async def fake_start_server(client_cb, host, port, *args, **kwargs):
        return fake_server

    monkeypatch.setattr(socket_server_module.asyncio, "start_server", fake_start_server)
    with caplog.at_level(logging.INFO, logger=MODULE_LOGGER):
        with pytest.raises(_StopServing):
            await SocketServer(host="localhost", port=0).start()

    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "<unverifiable>" in warnings[0]


@pytest.mark.asyncio
async def test_no_actual_addresses_fails_closed(captured_bind, caplog):
    captured_bind["addresses"] = []

    with caplog.at_level(logging.INFO, logger=MODULE_LOGGER):
        with pytest.raises(_StopServing):
            await SocketServer(host="localhost", port=0).start()

    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert any("without bound socket addresses" in text for text in warnings)
    assert any("not all known to be loopback-only" in text for text in warnings)


@pytest.mark.asyncio
async def test_server_main_defaults_to_loopback(captured_bind):
    with pytest.raises(_StopServing):
        await server_main()

    assert is_loopback_host(captured_bind["host"])


@pytest.mark.asyncio
async def test_server_main_forwards_explicit_host(captured_bind):
    with pytest.raises(_StopServing):
        await server_main("0.0.0.0")

    assert captured_bind["host"] == "0.0.0.0"


def test_cli_listen_default_and_explicit_wildcard(monkeypatch):
    monkeypatch.setattr("sys.argv", ["app.py"])
    args = app_module.parse_args()
    assert args.listen == SERVER_HOST
    assert is_loopback_host(args.listen)

    monkeypatch.setattr("sys.argv", ["app.py", "--listen", "0.0.0.0"])
    assert app_module.parse_args().listen == "0.0.0.0"


@pytest.mark.asyncio
async def test_headless_runner_forwards_host(monkeypatch):
    seen = []

    async def fake_server_main(host):
        seen.append(host)

    monkeypatch.setattr(app_module, "server_main", fake_server_main)
    await app_module.run_server("0.0.0.0")

    assert seen == ["0.0.0.0"]


def test_headless_cli_propagates_listen(monkeypatch):
    seen = []

    async def fake_server_main(host):
        seen.append(host)

    monkeypatch.setattr("sys.argv", [
        "app.py", "--no-gui", "--no-update-check", "--listen", "0.0.0.0"
    ])
    monkeypatch.setattr(app_module, "configure_logging", lambda: None)
    monkeypatch.setattr(app_module, "install_excepthook", lambda: None)
    monkeypatch.setattr(app_module, "bootstrap_access", lambda *args: None)
    monkeypatch.setattr(app_module, "server_main", fake_server_main)

    app_module.main()

    assert seen == ["0.0.0.0"]
