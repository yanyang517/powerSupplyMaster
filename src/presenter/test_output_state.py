"""Presenter 输出三态：成功回读发布设备事实，失败降为未知。"""
import asyncio

import pytest

from presenter import presenter as presenter_mod
from presenter.presenter import Presenter


class StubCombo:
    def __init__(self, text):
        self._text = text

    def currentText(self):
        return self._text


class OutputView:
    def __init__(self, presenter=None):
        self.presenter = presenter
        self.ui = type("StubUI", (), {
            "com_num_comboBox": StubCombo("COM8"),
            "baudrate_comboBox": StubCombo("115200"),
        })()
        self.output_states = []

    def show(self):
        pass

    def update_output_state(self, value):
        self.output_states.append(value)

    def update_connection_state(self, connected, port=None):
        pass

    def update_device_id(self, value):
        pass

    def update_voltage(self, value):
        pass

    def update_current(self, value):
        pass

    def update_recording_state(self):
        pass


class OutputModel:
    def __init__(self, value=True, error=None):
        self.value = value
        self.error = error
        self.calls = []

    async def open(self, port=None, **kwargs):
        return True

    async def close(self):
        pass

    async def get_device_id(self):
        return "FAKE-PSU"

    async def get_voltage(self):
        return 12.0

    async def get_current(self):
        return 1.0

    async def get_on_off(self, *, timeout):
        self.calls.append(timeout)
        if self.error is not None:
            raise self.error
        return self.value


def make_presenter(model):
    return Presenter(OutputView, lambda: model)


def test_output_starts_unknown_without_guessing():
    presenter = make_presenter(OutputModel(value=True))

    assert presenter._output_state is None
    assert presenter.view.output_states == []


async def wait_until(predicate, timeout=1.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise AssertionError("condition was not reached")
        await asyncio.sleep(0)


def test_connect_calibrates_immediately_and_every_second(monkeypatch):
    monkeypatch.setattr(presenter_mod, "OUTPUT_CALIBRATION_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(presenter_mod, "SAMPLE_INTERVAL_SECONDS", 0)
    model = OutputModel(value=False)
    presenter = make_presenter(model)

    async def scenario():
        try:
            await Presenter.open_device.__wrapped__(presenter)
            await wait_until(lambda: len(model.calls) == 3)
            assert presenter._output_state is False
            assert presenter.view.output_states == [None, False, False, False]
            assert presenter._output_calibration_task is not None
        finally:
            await Presenter.close_device.__wrapped__(presenter)

    asyncio.run(scenario())
    assert presenter._output_calibration_task is None
    assert presenter._output_state is None


def test_repeated_connect_does_not_stack_calibration_tasks(monkeypatch):
    monkeypatch.setattr(presenter_mod, "OUTPUT_CALIBRATION_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(presenter_mod, "SAMPLE_INTERVAL_SECONDS", 0)
    model = OutputModel()
    presenter = make_presenter(model)

    async def scenario():
        try:
            await Presenter.open_device.__wrapped__(presenter)
            first_task = presenter._output_calibration_task
            await Presenter.open_device.__wrapped__(presenter)
            assert presenter._output_calibration_task is first_task
            await wait_until(lambda: len(model.calls) >= 2)
        finally:
            await Presenter.close_device.__wrapped__(presenter)

    asyncio.run(scenario())


def test_disconnect_cancels_inflight_query_without_late_update():
    model = OutputModel()
    presenter = make_presenter(model)
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_query(*, timeout):
        started.set()
        await release.wait()
        return True

    model.get_on_off = blocked_query

    async def scenario():
        try:
            await Presenter.open_device.__wrapped__(presenter)
            await started.wait()
            await Presenter.close_device.__wrapped__(presenter)
            release.set()
            await asyncio.sleep(0)
            assert presenter._output_calibration_task is None
            assert presenter._output_state is None
            assert presenter.view.output_states == [None, None]
            assert True not in presenter.view.output_states
        finally:
            release.set()
            await Presenter.close_device.__wrapped__(presenter)

    asyncio.run(scenario())


@pytest.mark.parametrize(("value", "expected"), [(True, True), (False, False)])
def test_successful_readback_publishes_confirmed_state(value, expected):
    presenter = make_presenter(OutputModel(value=value))

    assert asyncio.run(presenter.refresh_output_state()) is expected
    assert presenter._output_state is expected
    assert presenter.view.output_states == [expected]
    assert presenter.model.calls == [presenter_mod.OUTPUT_CALIBRATION_TIMEOUT_SECONDS]


def test_failed_readback_publishes_unknown_instead_of_stale_state():
    presenter = make_presenter(OutputModel(error=asyncio.TimeoutError()))
    presenter._publish_output_state(True)

    assert asyncio.run(presenter.refresh_output_state()) is None
    assert presenter._output_state is None
    assert presenter.view.output_states == [True, None]


def test_unparseable_readback_publishes_unknown():
    presenter = make_presenter(OutputModel(error=ValueError("invalid OUTP? response")))

    assert asyncio.run(presenter.refresh_output_state()) is None
    assert presenter.view.output_states == [None]


def test_cancelled_readback_does_not_publish_a_late_state():
    presenter = make_presenter(OutputModel())

    async def cancelled(*, timeout):
        raise asyncio.CancelledError()

    presenter.model.get_on_off = cancelled
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(presenter.refresh_output_state())

    assert presenter._output_state is None
    assert presenter.view.output_states == []
