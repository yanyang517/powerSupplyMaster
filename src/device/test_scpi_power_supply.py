"""Windows 串口轮询间隔回归：qasync 不会把亚毫秒延时截断成 0ms。"""
import asyncio
from types import SimpleNamespace

import pytest

from device import scpi_power_supply as scpi


class FakeReader:
    async def readline(self):
        return b"FAKE,IDN\n"


class FakeWriter:
    def __init__(self, poll_interval):
        self.transport = SimpleNamespace(_poll_wait_time=poll_interval)
        self.writes = []

    def write(self, data):
        self.writes.append(data)

    async def drain(self):
        pass


@pytest.fixture
def psu():
    instance = scpi.SCPI_PowerSupply()
    instance._reader = None
    instance._writer = None
    instance.is_connected = False
    instance.identifier = ""
    instance.last_error = ""
    yield instance
    instance._reader = None
    instance._writer = None
    instance.is_connected = False


@pytest.mark.parametrize(("initial_interval", "expected_interval"), [
    (0.0005, scpi.MIN_SERIAL_POLL_INTERVAL_SECONDS),
    (0.0, scpi.MIN_SERIAL_POLL_INTERVAL_SECONDS),
    (0.005, 0.005),
])
def test_connect_enforces_nonzero_minimum_poll_interval(
        monkeypatch, psu, initial_interval, expected_interval):
    writer = FakeWriter(initial_interval)
    calls = []

    async def fake_open_serial_connection(*, url, baudrate):
        calls.append((url, baudrate))
        return FakeReader(), writer

    monkeypatch.setattr(scpi.serial_asyncio, "open_serial_connection",
                        fake_open_serial_connection)

    assert asyncio.run(psu.connect(serial_number="COM8", baudrate=115200)) is True
    assert calls == [("COM8", 115200)]
    assert writer.transport._poll_wait_time == expected_interval
    assert writer.writes == [b"*IDN?\n"]
    assert psu.identifier == "FAKE,IDN"


def test_minimum_interval_survives_qasync_millisecond_conversion():
    # qasync 使用 int(delay * 1000) 创建 Qt 定时器；低于 1ms 会得到 0ms。
    assert int(scpi.MIN_SERIAL_POLL_INTERVAL_SECONDS * 1000) >= 1
