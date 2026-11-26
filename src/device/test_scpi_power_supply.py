"""Windows 串口轮询间隔与输出状态查询回归。"""
import asyncio
import inspect
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
    instance._response_recovery_pending = False
    yield instance
    instance._reader = None
    instance._writer = None
    instance.is_connected = False
    instance._response_recovery_pending = False


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


@pytest.mark.parametrize(("response", "expected"), [
    (b"ON\n", True),
    (b" off \r\n", False),
])
def test_get_on_off_accepts_only_valid_states(monkeypatch, psu, response, expected):
    calls = []

    async def fake_send(command, wait_response=True, timeout=1.0):
        calls.append((command, wait_response, timeout))
        return response

    monkeypatch.setattr(psu, "_send_cmd", fake_send)

    assert asyncio.run(psu.get_on_off(timeout=0.25)) is expected
    assert calls == [(b"OUTP?\n", True, 0.25)]


@pytest.mark.parametrize("response", [b"ERROR\n", b"1\n", b"\n"])
def test_get_on_off_rejects_unparseable_responses(monkeypatch, psu, response):
    async def fake_send(command, wait_response=True, timeout=1.0):
        return response

    monkeypatch.setattr(psu, "_send_cmd", fake_send)

    with pytest.raises(ValueError, match="invalid OUTP\\? response"):
        asyncio.run(psu.get_on_off())


def test_command_timeout_defaults_remain_one_second():
    instance = scpi.SCPI_PowerSupply()
    send_params = inspect.signature(instance._send_cmd).parameters
    query_params = inspect.signature(instance.get_on_off).parameters
    assert send_params["timeout"].default == 1.0
    assert query_params["timeout"].default == 1.0


def test_output_query_honours_short_timeout(psu):
    class SlowReader:
        async def readline(self):
            await asyncio.sleep(1)
            return b"ON\n"

    psu._reader = SlowReader()
    psu._writer = FakeWriter(0.001)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(psu._send_cmd(b"OUTP?\n", timeout=0.01))


class QueuedReader:
    def __init__(self):
        self.responses = asyncio.Queue()

    async def readline(self):
        return await self.responses.get()


class RespondingWriter(FakeWriter):
    def __init__(self, reader, poll_interval=0.001):
        super().__init__(poll_interval)
        self.reader = reader

    def write(self, data):
        super().write(data)
        if data == b"MEASure:VOLTage?\n":
            self.reader.responses.put_nowait(b"5.00\n")


def test_next_command_discards_late_response_before_sending(psu):
    reader = QueuedReader()
    writer = RespondingWriter(reader)
    psu._reader = reader
    psu._writer = writer

    async def scenario():
        with pytest.raises(asyncio.TimeoutError):
            await psu._send_cmd(b"OUTP?\n", timeout=0.01)
        assert psu._response_recovery_pending is True

        # 模拟设备在超时之后才把 ON 送到串口。
        reader.responses.put_nowait(b"ON\n")
        response = await psu._send_cmd(b"MEASure:VOLTage?\n", timeout=0.1)

        assert response == b"5.00\n"
        assert writer.writes == [b"OUTP?\n", b"MEASure:VOLTage?\n"]
        assert psu._response_recovery_pending is False

    asyncio.run(scenario())


def test_recovery_timeout_does_not_send_another_command(psu):
    reader = QueuedReader()
    writer = FakeWriter(0.001)
    psu._reader = reader
    psu._writer = writer

    async def scenario():
        with pytest.raises(asyncio.TimeoutError):
            await psu._send_cmd(b"OUTP?\n", timeout=0.01)
        with pytest.raises(asyncio.TimeoutError):
            await psu._send_cmd(b"MEASure:VOLTage?\n", timeout=0.01)

        # 恢复读取也超时：不能继续堆命令，只保留唯一一条迟到响应待消费。
        assert writer.writes == [b"OUTP?\n"]
        assert psu._response_recovery_pending is True

    asyncio.run(scenario())


def test_cancelled_query_also_requires_late_response_recovery(psu):
    reader = QueuedReader()
    writer = RespondingWriter(reader)
    psu._reader = reader
    psu._writer = writer

    async def scenario():
        query = asyncio.create_task(psu._send_cmd(b"OUTP?\n", timeout=1.0))
        await asyncio.sleep(0)
        query.cancel()
        with pytest.raises(asyncio.CancelledError):
            await query
        assert psu._response_recovery_pending is True

        reader.responses.put_nowait(b"OFF\n")
        response = await psu._send_cmd(b"MEASure:VOLTage?\n", timeout=0.1)
        assert response == b"5.00\n"
        assert writer.writes == [b"OUTP?\n", b"MEASure:VOLTage?\n"]

    asyncio.run(scenario())


class DrainFailureWriter(RespondingWriter):
    def __init__(self, reader, failure_type):
        super().__init__(reader)
        self.failure_type = failure_type
        self.fail_next = True

    async def drain(self):
        if self.fail_next:
            self.fail_next = False
            raise self.failure_type()
        await super().drain()


@pytest.mark.parametrize("failure_type", [asyncio.TimeoutError, asyncio.CancelledError])
def test_drain_failure_also_requires_late_response_recovery(psu, failure_type):
    reader = QueuedReader()
    writer = DrainFailureWriter(reader, failure_type)
    psu._reader = reader
    psu._writer = writer

    async def scenario():
        with pytest.raises(failure_type):
            await psu._send_cmd(b"OUTP?\n", timeout=0.1)
        assert psu._response_recovery_pending is True

        reader.responses.put_nowait(b"ON\n")
        response = await psu._send_cmd(b"MEASure:VOLTage?\n", timeout=0.1)
        assert response == b"5.00\n"
        assert writer.writes == [b"OUTP?\n", b"MEASure:VOLTage?\n"]
        assert psu._response_recovery_pending is False

    asyncio.run(scenario())


def test_write_only_drain_failure_does_not_wait_for_nonexistent_response(psu):
    reader = QueuedReader()
    writer = DrainFailureWriter(reader, asyncio.TimeoutError)
    psu._reader = reader
    psu._writer = writer

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(psu._send_cmd(b"OUTP ON\n", wait_response=False, timeout=0.1))

    assert psu._response_recovery_pending is False


def test_write_only_command_does_not_wait_for_response_recovery(psu):
    reader = QueuedReader()
    writer = FakeWriter(0.001)
    psu._reader = reader
    psu._writer = writer

    assert asyncio.run(psu._send_cmd(
        b"OUTP ON\n", wait_response=False, timeout=0.01)) == b""
    assert writer.writes == [b"OUTP ON\n"]
    assert psu._response_recovery_pending is False
