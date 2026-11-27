"""GUI/TCP 安全限值共用校验的回归测试。"""
import asyncio
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from device.scpi_power_supply import SCPI_PowerSupply
from presenter.model import PowerSupplyModel
from presenter.presenter import Presenter
from server.dispatcher import dispatcher
from server.registry import Principal, Tier
from server.request_handles import *  # noqa: F401,F403  注册 handler
from server.runtime_config import SetpointLimitError, runtime_config, validate_power_setting
from server.session import Session, hub, lease


class StubCombo:
    def __init__(self, text):
        self._text = text

    def currentText(self):
        return self._text


class FakeView:
    def __init__(self, presenter=None):
        self.presenter = presenter
        self.ui = type("StubUI", (), {
            "com_num_comboBox": StubCombo("COM8"),
            "baudrate_comboBox": StubCombo("115200"),
        })()
        self.voltage_updates = []
        self.current_updates = []
        self.errors = []

    def show(self):
        pass

    def update_voltage_setting(self, value):
        self.voltage_updates.append(value)

    def update_current_setting(self, value):
        self.current_updates.append(value)

    def update_setting_error(self, error):
        self.errors.append(error)

    def update_voltage(self, value):
        pass

    def update_current(self, value):
        pass

    def update_connection_state(self, connected, port=None):
        pass

    def update_device_id(self, value):
        pass

    def update_output_state(self, value):
        pass

    def update_recording_state(self):
        pass


class FakeDevice:
    def __init__(self):
        self.calls = []
        self.write_started = None
        self.release_write = None
        self.write_error = None

    async def set_voltage(self, value):
        self.calls.append(("voltage", value))
        await self._write()

    async def set_current(self, value):
        self.calls.append(("current", value))
        await self._write()

    async def _write(self):
        if self.write_started is not None:
            self.write_started.set()
        if self.release_write is not None:
            await self.release_write.wait()
        if self.write_error is not None:
            raise self.write_error


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(monkeypatch):
    lease.revoke()
    for session in list(hub):
        hub.close(session)
    monkeypatch.setattr(runtime_config, "max_voltage", 30.0)
    monkeypatch.setattr(runtime_config, "max_current", 5.0)
    device = FakeDevice()
    psu = SCPI_PowerSupply()
    monkeypatch.setattr(psu, "is_connected", True)
    monkeypatch.setattr(psu, "set_voltage", device.set_voltage)
    monkeypatch.setattr(psu, "set_current", device.set_current)
    model = PowerSupplyModel()
    model.device = device
    presenter = Presenter(FakeView, lambda: model)
    yield presenter, device
    lease.revoke()
    for session in list(hub):
        hub.close(session)


def run_write(presenter, setting, value):
    coro = getattr(Presenter, f"set_{setting}").__wrapped__(presenter, value)
    return asyncio.run(coro)


def dispatch(setting, value):
    session = Session(peer="unit-test")
    session.authenticate(Principal("tester", Tier.L2, "tester"))
    raw = json.dumps({"type": f"set_{setting}", "value": value})
    return asyncio.run(dispatcher.dispatch(raw, session))


INVALID_VALUES = [
    ("voltage", 30.01, "over_limit"),
    ("current", 5.001, "over_limit"),
    ("voltage", -0.01, "negative"),
    ("current", -0.001, "negative"),
    ("voltage", float("nan"), "non_finite"),
    ("current", float("nan"), "non_finite"),
    ("voltage", float("inf"), "non_finite"),
    ("current", float("inf"), "non_finite"),
    ("voltage", float("-inf"), "non_finite"),
    ("current", float("-inf"), "non_finite"),
]


@pytest.mark.parametrize("setting,value,code", INVALID_VALUES)
def test_gui_and_server_reject_with_identical_structured_error(panel, setting, value, code):
    presenter, device = panel

    run_write(presenter, setting, value)
    response = dispatch(setting, value)

    assert response.status == "error"
    assert response.error.code == code
    assert response.error.model_dump() == presenter.view.errors[-1]
    assert response.message == presenter.view.errors[-1]["message"]
    assert "0~" in response.message
    assert device.calls == []


@pytest.mark.parametrize("setting,value,code", INVALID_VALUES)
def test_model_itself_rejects_without_device_write(panel, setting, value, code):
    presenter, device = panel

    with pytest.raises(SetpointLimitError) as caught:
        asyncio.run(getattr(presenter.model, f"set_{setting}")(value))

    assert caught.value.code == code
    assert device.calls == []


@pytest.mark.parametrize("setting,limit", [("voltage", 30.0), ("current", 5.0)])
@pytest.mark.parametrize("value_kind", ["zero", "boundary"])
def test_gui_and_server_accept_zero_and_exact_boundary(panel, setting, limit, value_kind):
    presenter, device = panel
    value = 0.0 if value_kind == "zero" else limit

    run_write(presenter, setting, value)
    response = dispatch(setting, value)

    assert response.status == "success"
    assert response.value == value
    assert device.calls == [(setting, value), (setting, value)]
    if setting == "voltage":
        assert presenter.view.voltage_updates == [value]
    else:
        assert presenter.view.current_updates == [value]
    assert presenter.view.errors == []


def test_validation_uses_current_runtime_limits(panel, monkeypatch):
    presenter, device = panel
    monkeypatch.setattr(runtime_config, "max_voltage", 24.0)
    monkeypatch.setattr(runtime_config, "max_current", 3.0)

    run_write(presenter, "voltage", 24.0)
    run_write(presenter, "current", 3.0)
    assert dispatch("voltage", 24.0).status == "success"
    assert dispatch("current", 3.0).status == "success"
    assert dispatch("voltage", 24.01).error.maximum == 24.0
    assert dispatch("current", 3.001).error.maximum == 3.0
    assert device.calls == [("voltage", 24.0), ("current", 3.0),
                            ("voltage", 24.0), ("current", 3.0)]


@pytest.mark.parametrize("setting", ["voltage", "current"])
@pytest.mark.parametrize("limit", [float("nan"), float("inf"), float("-inf"), -1.0])
def test_invalid_limit_fails_closed_in_gui_model_and_server(panel, monkeypatch,
                                                            setting, limit):
    presenter, device = panel
    monkeypatch.setattr(runtime_config, f"max_{setting}", limit)

    run_write(presenter, setting, 1.0)
    response = dispatch(setting, 1.0)
    with pytest.raises(SetpointLimitError) as caught:
        asyncio.run(getattr(presenter.model, f"set_{setting}")(1.0))

    assert response.status == "error"
    assert response.error.code == "invalid_limit"
    assert response.error.model_dump() == presenter.view.errors[-1]
    assert caught.value.code == "invalid_limit"
    assert device.calls == []


def test_gui_waits_for_device_success_before_publishing(panel):
    presenter, device = panel
    device.write_started = asyncio.Event()
    device.release_write = asyncio.Event()

    async def scenario():
        task = asyncio.create_task(
            Presenter.set_voltage.__wrapped__(presenter, 15.0))
        try:
            await device.write_started.wait()
            assert presenter.view.voltage_updates == []
            device.release_write.set()
            await task
            assert presenter.view.voltage_updates == [15.0]
        finally:
            device.release_write.set()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_gui_does_not_publish_after_device_failure(panel):
    presenter, device = panel
    device.write_error = asyncio.TimeoutError("write timed out")

    with pytest.raises(asyncio.TimeoutError):
        run_write(presenter, "voltage", 15.0)

    assert presenter.view.voltage_updates == []


class WindowPresenter:
    def __init__(self):
        self.voltages = []

    def get_available_ports(self):
        return [], None

    def auto_connect_enabled(self):
        return False

    def open_device(self):
        pass

    def close_device(self):
        pass

    def toggle_output(self):
        pass

    def set_voltage(self, value):
        self.voltages.append(value)

    def set_recording_enabled(self, enabled):
        return True

    def stop_recording(self):
        pass


@pytest.fixture
def window(qapp, tmp_path, monkeypatch, request):
    from views.main_window import MainWindow

    max_voltage, max_current = getattr(request, "param", (30.0, 5.0))
    monkeypatch.setattr(runtime_config, "max_voltage", max_voltage)
    monkeypatch.setattr(runtime_config, "max_current", max_current)
    monkeypatch.setattr(
        "views.window_geometry.geometry_file_path",
        lambda *a, **k: tmp_path / "window_geometry.json",
    )
    win = MainWindow(WindowPresenter())
    yield win
    win.floating_window.close()
    win.close()


def test_window_dial_tracks_only_confirmed_voltage(window):
    window.ui.voltage_spinBox.setValue(15.0)

    assert window.presenter.voltages == [15.0]
    assert window.ui.voltage_dial.value() == 1200

    window.update_voltage_setting(15.0)

    assert window.ui.voltage_dial.value() == 1500


@pytest.mark.parametrize("window", [(36.0, 7.5)], indirect=True)
def test_window_limit_displays_use_effective_runtime_limits(window):
    assert window.ui.max_voltage_spinbox.value() == 36.0
    assert window.ui.max_voltage_spinbox.isReadOnly()
    assert window.ui.voltage_spinBox.maximum() == 36.0
    assert window.ui.voltage_dial.maximum() == 3600
    assert window.ui.max_current_spinBox.value() == 7.5
    assert window.ui.max_current_spinBox.isReadOnly()

    window.ui.voltage_spinBox.setValue(25.0)
    assert window.presenter.voltages == [25.0]
    window.update_voltage_setting(25.0)
    assert window.ui.voltage_dial.value() == 2500

    # 显示框不能二次覆盖真实运行时限值。
    window.ui.max_voltage_spinbox.setValue(10.0)
    window.ui.max_current_spinBox.setValue(1.0)
    assert window.ui.voltage_spinBox.maximum() == 36.0
    assert window.ui.voltage_dial.maximum() == 3600
    assert window.ui.max_current_spinBox.value() == 7.5


def test_window_restores_confirmed_voltage_on_limit_error(window):
    window.update_voltage_setting(10.0)
    window.on_voltage_spinbox_value_changed(31.0)
    assert window.ui.voltage_dial.value() == 1000

    try:
        validate_power_setting("voltage", 31.0)
    except SetpointLimitError as exc:
        window.update_setting_error(exc.as_dict())

    assert window.ui.voltage_spinBox.value() == 10.0
    assert window.ui.voltage_dial.value() == 1000
    assert "0~30.00V" in window.ui.statusbar.currentMessage()
    assert window.presenter.voltages == [31.0]  # 恢复值不能再次下发
