"""Server test fixtures, including a self-contained integration environment.

The TCP control server and the SCPI peer both listen on ephemeral loopback ports.
Only the serial transport is replaced: the real driver still performs *IDN?,
command writes, reads, locking, timeouts and response-recovery bookkeeping.
"""
import asyncio
import json
import shutil
from types import SimpleNamespace

import pytest
import pytest_asyncio
from construct import Bytes, Int32ub, Struct, this

import device.scpi_power_supply as scpi_module
from device.device_simulator import SCPISimulator
from device.scpi_power_supply import SCPI_PowerSupply

from . import registry as registry_mod
from .protocal.protocal import LoginRequest, OpenDeviceRequest
from .registry import ClientRegistry, clients_file_path, use_registry
from .socket_server import SocketServer

CLIENT_ID = "test-client"
SIMULATED_SERIAL = "COM-SIM"

MessageProtocol = Struct(
    "length" / Int32ub,
    "payload" / Bytes(this.length),
)


class JsonSocketClient:
    """Length-prefixed UTF-8 JSON client used by the wire-level tests."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0,
                 client_id: str = CLIENT_ID, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout = timeout
        self._reader = None
        self._writer = None

    async def connect(self):
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        return self._reader, self._writer

    async def close(self):
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()

    async def request(self, req) -> dict:
        if self._reader is None or self._writer is None:
            raise RuntimeError("call connect() before request()")
        payload = req.model_dump_json().encode("utf-8")
        self._writer.write(MessageProtocol.build({"length": len(payload), "payload": payload}))
        await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)
        length = Int32ub.parse(
            await asyncio.wait_for(self._reader.readexactly(4), timeout=self.timeout)
        )
        raw = await asyncio.wait_for(self._reader.readexactly(length), timeout=self.timeout)
        return json.loads(raw.decode("utf-8"))

    async def login(self, tier: str = "L2") -> dict:
        return await self.request(LoginRequest(client_id=self.client_id, tier=tier))


@pytest.fixture(autouse=True)
def isolated_access_state():
    """Process-wide session and lease state must not leak between tests."""
    from . import access as access_mod
    from . import session as session_mod
    from .session import lease as shared_lease

    access_mod.admission_rate_limiter.reset()
    # 测试需要强制归零；生产 release/revoke 会刻意拒绝在途或隔离中的预留。
    shared_lease._clear()
    for session in list(session_mod.hub):
        session_mod.hub.close(session)
    yield
    access_mod.admission_rate_limiter.reset()
    shared_lease._clear()


def _tracked(handler):
    tasks: set[asyncio.Task] = set()

    async def wrapped(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            await handler(reader, writer)
        finally:
            tasks.discard(task)

    return wrapped, tasks


async def _start(handler, host: str = "127.0.0.1"):
    wrapped, tasks = _tracked(handler)
    server = await asyncio.start_server(wrapped, host, 0)
    return server, server.sockets[0].getsockname()[1], tasks


async def _stop(server, tasks) -> None:
    server.close()
    for task in list(tasks):
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await server.wait_closed()


@pytest_asyncio.fixture
async def simulated_scpi_peer(monkeypatch):
    """Replace pyserial-asyncio with a local TCP transport speaking SCPI lines."""
    simulator = SCPISimulator()
    calls: list[str] = []

    async def serve(reader, writer):
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                command = line.decode("utf-8").strip()
                if not command:
                    continue
                calls.append(command)
                response = await simulator.execute_scpi_command(command)
                if response:
                    writer.write(f"{response}\n".encode("utf-8"))
                    await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    peer, peer_port, peer_tasks = await _start(serve)

    async def open_sim_serial(*, url, baudrate):
        return await asyncio.open_connection("127.0.0.1", peer_port)

    psu = SCPI_PowerSupply()
    # The singleton's lock must belong to this test's event loop, not an earlier test's.
    monkeypatch.setattr(psu, "_locker", asyncio.Lock())
    monkeypatch.setattr(scpi_module.serial_asyncio, "open_serial_connection", open_sim_serial)

    try:
        yield SimpleNamespace(port=peer_port, calls=calls, simulator=simulator,
                              serial_number=SIMULATED_SERIAL)
    finally:
        if psu.is_connected:
            await psu.disconnect()
        await _stop(peer, peer_tasks)


@pytest.fixture
def integration_registry(tmp_path):
    """Load a temporary copy of the shipped allow-list, never mutate config/."""
    source = clients_file_path()
    if not source.is_file():
        pytest.fail(f"client registry not found: {source}", pytrace=False)
    path = tmp_path / "clients.json"
    shutil.copyfile(source, path)

    previous = registry_mod._registry
    use_registry(ClientRegistry.load(path))
    try:
        yield registry_mod._registry
    finally:
        use_registry(previous)


@pytest_asyncio.fixture
async def control_server(integration_registry):
    """Start SocketServer on an ephemeral port; no external 18888 process is needed."""
    server, port, tasks = await _start(SocketServer(host="127.0.0.1").handle_client)
    try:
        yield port
    finally:
        await _stop(server, tasks)


@pytest_asyncio.fixture
async def control_client(control_server):
    client = JsonSocketClient(port=control_server)
    await client.connect()
    try:
        yield client
    finally:
        await client.close()


@pytest_asyncio.fixture
async def opened_device(control_client, simulated_scpi_peer):
    assert (await control_client.login(tier="L2"))["status"] == "success"
    response = await control_client.request(
        OpenDeviceRequest(serial_number=simulated_scpi_peer.serial_number)
    )
    assert response["status"] == "success", response
    yield control_client
