"""记录器与采样循环的接线：会话边界、零额外串口往返、故障不外溢。

对应 specs/recording/data-capture 的"记录以连接会话为切分单位""记录不改变采样时序"
"记录故障不伤及控制与显示""异常退出后已落盘数据仍可复看"。假 model 与假视图都是
手写的：这一段要验的正是 presenter 这个中间层，不该被真实控件或串口拖住。
"""
import asyncio
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import serial
import pytest

from recording.recorder import INDEX_FILE_NAME
from recording.settings import RecordSettings

from . import presenter as presenter_mod
from .presenter import Presenter


class StubCombo:
    def __init__(self, text):
        self._text = text

    def currentText(self):
        return self._text


class StubUI:
    def __init__(self, port="COM8"):
        self.com_num_comboBox = StubCombo(port)
        self.baudrate_comboBox = StubCombo("9600")


class RecordingView:
    """只记账不画控件：本文件关心的是会话边界，不是外观。"""

    def __init__(self, presenter=None, port="COM8"):
        self.presenter = presenter
        self.ui = StubUI(port)
        self.voltages = []
        self.currents = []
        self.recording_states = []
        self.error_messages = []
        self.connection_states = []
        self.output_states = []

    def show(self):
        pass

    def update_voltage(self, value):
        self.voltages.append(value)

    def update_current(self, value):
        self.currents.append(value)

    def update_device_id(self, value):
        pass

    def update_connection_state(self, connected, port=None):
        self.connection_states.append((connected, port))

    def update_sampling_error(self, message):
        self.error_messages.append(message)

    def update_output_state(self, value):
        self.output_states.append(value)

    def update_recording_state(self):
        self.recording_states.append(self.presenter.recording_status())


class CountingModel:
    """数得清调用次数的假设备：记录是否多问一句串口，只能这么验。"""

    def __init__(self, fail_voltage_on=(), fail_current_on=(), open_ok=True,
                 output_error=None, voltage_error=None, open_results=()):
        self.fail_voltage_on = set(fail_voltage_on)
        self.fail_current_on = set(fail_current_on)
        self.output_error = output_error
        self.voltage_error = voltage_error
        self.open_results = list(open_results)
        self.opened_ports = []
        self.output_calls = 0
        self.voltage_calls = 0
        self.current_calls = 0
        self.opened = 0
        self.closed = 0
        # 连接被拒（串口占用等）时的按钮复位行为只有这条路能验。
        self.open_ok = open_ok

    async def open(self, port=None, **kwargs):
        self.opened += 1
        self.opened_ports.append(port)
        if self.open_results:
            return self.open_results.pop(0)
        return self.open_ok

    async def close(self):
        self.closed += 1
        return True

    async def get_device_id(self):
        return "FAKE-PSU"

    async def get_on_off(self, *, timeout=1.0):
        self.output_calls += 1
        if self.output_error is not None:
            raise self.output_error
        return True

    async def get_voltage(self):
        self.voltage_calls += 1
        if self.voltage_error is not None:
            raise self.voltage_error
        if self.voltage_calls in self.fail_voltage_on:
            raise asyncio.TimeoutError()
        return 12.0

    async def get_current(self):
        self.current_calls += 1
        if self.current_calls in self.fail_current_on:
            raise asyncio.TimeoutError()
        return 1.0


def make(tmp_path, monkeypatch, model=None, enabled=False, port="COM8",
         auto_connect=False, save_connection=True):
    """造一个记录目录落在 tmp_path、且不真睡觉的 presenter。"""
    settings = RecordSettings(enabled=enabled, dir=str(tmp_path / "records"))
    connection_settings = presenter_mod.ConnectionSettings(
        port=port, auto_connect=auto_connect)
    monkeypatch.setattr(presenter_mod, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(presenter_mod, "save_settings", lambda _s: True)
    monkeypatch.setattr(presenter_mod, "load_connection_settings",
                        lambda *a, **k: connection_settings)
    monkeypatch.setattr(presenter_mod, "save_connection_settings",
                        lambda _s: save_connection)
    monkeypatch.setattr(presenter_mod, "SAMPLE_INTERVAL_SECONDS", 0)
    return Presenter(lambda presenter=None: RecordingView(presenter, port),
                     lambda: model or CountingModel())


def connect(presenter, cycles=0):
    """连接并等够 cycles 个成功周期；不等任务，直接跑原协程。"""

    async def scenario():
        await Presenter.open_device.__wrapped__(presenter)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5.0
        while len(presenter.view.voltages) < cycles:
            if loop.time() > deadline:
                raise AssertionError(f"采样未按预期产出：{presenter.view.voltages}")
            await asyncio.sleep(0)

    asyncio.run(scenario())


def disconnect(presenter):
    asyncio.run(Presenter.close_device.__wrapped__(presenter))


def read_index(tmp_path):
    path = tmp_path / "records" / INDEX_FILE_NAME
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["sessions"]


def read_rows(tmp_path, name):
    with open(tmp_path / "records" / name, "r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def only_csv(tmp_path):
    files = list((tmp_path / "records").glob("*.csv"))
    assert len(files) == 1, f"期望一份数据文件，实际 {[f.name for f in files]}"
    return files[0].name


class TestStandbyBeforeConnect:
    def test_enabled_but_disconnected_writes_nothing(self, tmp_path, monkeypatch):
        make(tmp_path, monkeypatch, enabled=True)

        assert not (tmp_path / "records").exists()

    def test_disabled_never_creates_the_directory(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch, enabled=False)
        connect(presenter, cycles=3)
        disconnect(presenter)

        assert not (tmp_path / "records").exists()

    def test_enabling_while_disconnected_only_stands_by(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch, enabled=False)

        assert presenter.set_recording_enabled(True) is True
        assert presenter.recording_status()["enabled"] is True
        assert presenter.recording_status()["recording"] is False
        assert not (tmp_path / "records").exists()


class TestSessionBoundaries:
    def test_the_file_appears_at_connect_not_at_enable(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch, enabled=False)
        presenter.set_recording_enabled(True)

        connect(presenter, cycles=2)

        entry = read_index(tmp_path)[0]
        assert entry["status"] == "recording"
        assert entry["port"] == "COM8"
        assert (tmp_path / "records" / entry["file"]).is_file()
        disconnect(presenter)

    def test_disconnect_closes_the_session_with_real_counts(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch, enabled=True)
        connect(presenter, cycles=4)

        disconnect(presenter)

        entry = read_index(tmp_path)[0]
        assert entry["status"] == "closed"
        assert entry["rows"] == len(read_rows(tmp_path, entry["file"])) - 1
        assert entry["ended_at"]
        assert entry["bytes"] > 0

    def test_reconnect_is_a_second_independent_session(self, tmp_path, monkeypatch):
        model = CountingModel()
        presenter = make(tmp_path, monkeypatch, model=model, enabled=True)
        connect(presenter, cycles=2)
        disconnect(presenter)
        connect(presenter, cycles=4)
        disconnect(presenter)

        entries = read_index(tmp_path)
        assert [entry["status"] for entry in entries] == ["closed", "closed"]
        assert len({entry["file"] for entry in entries}) == 2

    def test_disabling_mid_run_ends_the_session(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch, enabled=True)
        connect(presenter, cycles=2)
        rows_written = presenter._recorder.rows

        assert presenter.set_recording_enabled(False) is True

        entry = read_index(tmp_path)[0]
        assert entry["status"] == "closed"
        assert entry["rows"] == rows_written
        assert len(read_rows(tmp_path, entry["file"])) - 1 == rows_written

    def test_disabling_then_sampling_adds_no_rows(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch, enabled=True)
        connect(presenter, cycles=2)
        name = read_index(tmp_path)[0]["file"]
        rows_at_disable = presenter._recorder.rows   # 盘上此时可能还压着没 flush 的几行

        presenter.set_recording_enabled(False)
        connect(presenter, cycles=5)
        disconnect(presenter)

        # 关使能时 stop 会 flush+close，盘上内容定格在关闭那一刻的行数；
        # 之后那段采样一条都不许再进来。
        assert len(read_rows(tmp_path, name)) - 1 == rows_at_disable
        assert read_index(tmp_path)[0]["rows"] == rows_at_disable

    def test_a_session_that_recorded_nothing_leaves_no_trace(self, tmp_path, monkeypatch):
        model = CountingModel(fail_voltage_on=set(range(1, 50)))
        presenter = make(tmp_path, monkeypatch, model=model, enabled=True)
        connect(presenter)          # 一次都没采到

        disconnect(presenter)

        assert read_index(tmp_path) == []
        assert list((tmp_path / "records").glob("*.csv")) == []

    def test_stop_recording_without_a_session_is_harmless(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch, enabled=True)

        assert presenter.stop_recording() is None


class TestSamplingIsUntouched:
    def test_recording_adds_no_extra_device_reads(self, tmp_path, monkeypatch):
        """使能与否，每周期都恰好一次电压一次电流查询。"""
        off_model = CountingModel()
        off = make(tmp_path, monkeypatch, model=off_model, enabled=False)
        connect(off, cycles=5)
        disconnect(off)

        on_model = CountingModel()
        on = make(tmp_path / "second", monkeypatch, model=on_model, enabled=True)
        connect(on, cycles=5)
        disconnect(on)

        assert off_model.voltage_calls == off_model.current_calls == on_model.voltage_calls
        assert on_model.voltage_calls == on_model.current_calls

    def test_only_fully_paired_cycles_are_written(self, tmp_path, monkeypatch):
        """视图只在成对成功时刷新，文件行数与它一致即证明没有半条入账。"""
        model = CountingModel(fail_current_on={3})
        presenter = make(tmp_path, monkeypatch, model=model, enabled=True)
        connect(presenter, cycles=4)

        disconnect(presenter)

        rows = read_rows(tmp_path, only_csv(tmp_path))
        pairs = len(presenter.view.voltages)
        assert len(rows) - 1 == pairs
        # 第 3 轮的电流查询失败：电压已经取到却整轮作废，所以成对数比查询次数少一。
        assert pairs == model.current_calls - 1
        assert model.voltage_calls == model.current_calls
        assert all(len(row) == 4 and all(field.strip() for field in row) for row in rows[1:])

    def test_a_failed_cycle_is_absent_from_the_file(self, tmp_path, monkeypatch):
        """失败的那一轮不留行：文件里相邻两条的时间差是缺口的唯一凭据。"""
        model = CountingModel(fail_voltage_on={2})
        presenter = make(tmp_path, monkeypatch, model=model, enabled=True)
        connect(presenter, cycles=3)

        disconnect(presenter)

        rows = read_rows(tmp_path, only_csv(tmp_path))
        assert len(rows) - 1 == len(presenter.view.voltages)
        assert model.voltage_calls == len(presenter.view.voltages) + 1


class TestOutputFailureDoesNotSpillOver:
    def test_output_timeout_keeps_sampling_and_paired_records(self, tmp_path, monkeypatch):
        model = CountingModel(output_error=asyncio.TimeoutError())
        presenter = make(tmp_path, monkeypatch, model=model, enabled=True)

        connect(presenter, cycles=3)

        assert model.output_calls >= 1
        assert presenter._output_state is None
        assert presenter.view.error_messages == []
        assert model.voltage_calls == model.current_calls >= 3
        assert len(presenter.view.voltages) >= 3
        displayed_pairs = len(presenter.view.voltages)
        disconnect(presenter)
        rows = read_rows(tmp_path, only_csv(tmp_path))
        assert len(rows) - 1 == displayed_pairs
        assert all(len(row) == 4 for row in rows[1:])


class TestFailureDoesNotSpillOver:
    def test_unwritable_dir_stops_recording_but_keeps_sampling(self, tmp_path, monkeypatch):
        (tmp_path / "records").write_text("我不是目录", encoding="utf-8")
        model = CountingModel()
        presenter = make(tmp_path, monkeypatch, model=model, enabled=True)

        connect(presenter, cycles=3)
        status = presenter.recording_status()

        assert status["recording"] is False
        assert "无法创建" in status["error"]
        assert len(presenter.view.voltages) >= 3      # 采样照常，不受记录故障牵连
        assert model.opened == 1
        disconnect(presenter)

    def test_the_view_is_told_about_the_failure_once_written(self, tmp_path, monkeypatch):
        (tmp_path / "records").write_text("blocked", encoding="utf-8")
        presenter = make(tmp_path, monkeypatch, enabled=True)

        connect(presenter)

        states = [state["error"] for state in presenter.view.recording_states]
        assert any(message and "无法创建" in message for message in states)
        disconnect(presenter)

    def test_recording_status_carries_everything_the_panel_needs(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch, enabled=True)

        connect(presenter, cycles=1)
        status = presenter.recording_status()

        assert set(status) == {"enabled", "recording", "file", "rows", "dir",
                               "error", "interval_ms"}
        assert status["interval_ms"] == 500
        assert Path(status["dir"]) == tmp_path / "records"
        disconnect(presenter)


class TestStartupReconcile:
    def test_a_recording_entry_surviving_a_kill_is_rejudged(self, tmp_path, monkeypatch):
        records = tmp_path / "records"
        records.mkdir()
        name = "20261121T132200_COM8.csv"
        (records / name).write_text(
            "ts_ms,iso_local,voltage_v,current_a\n"
            + "".join(f"{1700000000000 + i * 500},2026-11-21T13:22:0{i}+08:00,12.0,1.0\n"
                      for i in range(3)),
            encoding="utf-8", newline="")
        (records / INDEX_FILE_NAME).write_text(json.dumps({"version": 1, "sessions": [{
            "id": name[:-4], "file": name, "port": "COM8",
            "started_at": "2026-11-21T13:22:00+08:00", "ended_at": None,
            "rows": 500, "bytes": 999999, "status": "recording"}]}), encoding="utf-8")

        make(tmp_path, monkeypatch, enabled=False)   # 仅仅是启动，什么都没干

        entry = read_index(tmp_path)[0]
        assert entry["status"] == "interrupted"
        assert entry["rows"] == 3                    # 以盘上事实为准，不是清单里那个 500
        assert entry["bytes"] == (records / name).stat().st_size

    def test_startup_does_not_auto_record(self, tmp_path, monkeypatch):
        make(tmp_path, monkeypatch, enabled=False)

        assert presenter_mod.load_settings().enabled is False
        assert not (tmp_path / "records").exists()


class TestPortSelection:
    @staticmethod
    def ports():
        return [
            SimpleNamespace(device="COM3", description="USB Serial Port"),
            SimpleNamespace(device="COM8", description="Communications Port"),
            SimpleNamespace(device="COM9", description=None),
        ]

    def test_available_last_successful_port_is_preferred(self, tmp_path, monkeypatch):
        monkeypatch.setattr(presenter_mod.list_ports, "comports", self.ports)
        presenter = make(tmp_path, monkeypatch)
        presenter._connection_settings = presenter_mod.ConnectionSettings(port="COM9")

        assert presenter.get_available_ports() == (["COM3", "COM8", "COM9"], 2)

    def test_unavailable_last_port_falls_back_to_usb(self, tmp_path, monkeypatch):
        monkeypatch.setattr(presenter_mod.list_ports, "comports", self.ports)
        presenter = make(tmp_path, monkeypatch)
        presenter._connection_settings = presenter_mod.ConnectionSettings(port="COM7")

        assert presenter.get_available_ports() == (["COM3", "COM8", "COM9"], 0)

    def test_no_history_or_usb_port_leaves_default_selection(self, tmp_path, monkeypatch):
        monkeypatch.setattr(presenter_mod.list_ports, "comports", lambda: [
            SimpleNamespace(device="COM8", description="Communications Port")])
        presenter = make(tmp_path, monkeypatch)
        presenter._connection_settings = presenter_mod.ConnectionSettings()

        assert presenter.get_available_ports() == (["COM8"], None)


class TestConnectionStateIsReported:
    """互斥按钮与状态栏指示的唯一凭据就是这一句：视图收到的是连接结果，不是点击。"""

    def test_a_refused_open_reports_offline_not_silence(self, tmp_path, monkeypatch):
        """串口被占用时连接失败：必须回落未连接态，否则「连接」按钮永远灰着，用户无从重试。"""
        presenter = make(tmp_path, monkeypatch, model=CountingModel(open_ok=False))

        asyncio.run(Presenter.open_device.__wrapped__(presenter))

        assert presenter.view.connection_states == [(False, None)]
        assert presenter._connected_port is None
        assert presenter._refresh_voltage_current_task is None

    def test_a_successful_open_reports_online_with_the_port(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch)

        asyncio.run(Presenter.open_device.__wrapped__(presenter))
        disconnect(presenter)

        assert presenter.view.connection_states[0] == (True, "COM8")
        assert presenter.view.connection_states[-1] == (False, None)

    def test_successful_open_remembers_the_port(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch, port="COM9")
        saved = []
        monkeypatch.setattr(presenter_mod, "save_connection_settings", saved.append)

        asyncio.run(Presenter.open_device.__wrapped__(presenter))
        disconnect(presenter)

        assert [settings.port for settings in saved] == ["COM9"]
        assert saved[0].auto_connect is False

    def test_failed_open_does_not_replace_the_remembered_port(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch, model=CountingModel(open_ok=False), port="COM9")

        def unexpected_save(port):
            raise AssertionError(f"failed connection must not remember {port}")

        monkeypatch.setattr(presenter_mod, "save_connection_settings", unexpected_save)
        asyncio.run(Presenter.open_device.__wrapped__(presenter))

        assert presenter.view.connection_states == [(False, None)]

    def test_remembering_failure_does_not_break_a_successful_connection(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch)
        monkeypatch.setattr(presenter_mod, "save_connection_settings", lambda _settings: False)

        asyncio.run(Presenter.open_device.__wrapped__(presenter))
        disconnect(presenter)

        assert presenter.view.connection_states[0] == (True, "COM8")
        assert presenter._connected_port is None


async def wait_until(predicate):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 2.0
    while not predicate():
        if loop.time() >= deadline:
            raise AssertionError("condition did not become true")
        await asyncio.sleep(0)


class TestAutoReconnect:
    def test_checked_setting_connects_on_startup(self, tmp_path, monkeypatch):
        model = CountingModel()

        async def scenario():
            presenter = make(tmp_path, monkeypatch, model=model, port="COM9", auto_connect=True)
            await wait_until(lambda: presenter._connected_port == "COM9")

            assert model.opened_ports == ["COM9"]
            assert presenter.view.connection_states[-1] == (True, "COM9")
            await Presenter.close_device.__wrapped__(presenter)

        asyncio.run(scenario())

    def test_unchecked_setting_does_not_connect_on_startup(self, tmp_path, monkeypatch):
        model = CountingModel()

        async def scenario():
            presenter = make(tmp_path, monkeypatch, model=model, auto_connect=False)
            await asyncio.sleep(0)

            assert model.opened == 0
            assert presenter._auto_reconnect_task is None

        asyncio.run(scenario())

    @pytest.mark.parametrize(("failures", "expected"), [
        (0, 5.0),
        (9, 5.0),
        (10, 120.0),
        (11, 120.0),
    ])
    def test_retry_interval_switches_after_ten_failures(self, tmp_path, monkeypatch,
                                                       failures, expected):
        presenter = make(tmp_path, monkeypatch)
        presenter._auto_reconnect_failures = failures

        assert presenter._auto_reconnect_interval() == expected

    @pytest.mark.parametrize(("failures", "expected"), [(0, 5.0), (9, 120.0)])
    def test_loop_waits_the_selected_interval(self, tmp_path, monkeypatch, failures, expected):
        presenter = make(tmp_path, monkeypatch, model=CountingModel(open_ok=False))
        presenter._connection_settings = presenter_mod.ConnectionSettings(auto_connect=True)
        presenter._auto_reconnect_failures = failures
        delays = []

        async def stop_after_delay(delay):
            delays.append(delay)
            raise asyncio.CancelledError

        monkeypatch.setattr(presenter_mod.asyncio, "sleep", stop_after_delay)
        asyncio.run(presenter._auto_reconnect_loop())

        assert delays == [expected]
        assert presenter._auto_reconnect_failures == failures + 1

    def test_success_resets_the_failure_counter(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch)
        presenter._connection_settings = presenter_mod.ConnectionSettings(auto_connect=True)
        presenter._auto_reconnect_failures = 7

        asyncio.run(presenter._auto_reconnect_loop())
        disconnect(presenter)

        assert presenter._auto_reconnect_failures == 0

    def test_manual_disconnect_suppresses_reconnect(self, tmp_path, monkeypatch):
        model = CountingModel()

        async def scenario():
            presenter = make(tmp_path, monkeypatch, model=model)
            await Presenter.open_device.__wrapped__(presenter)
            presenter.set_auto_connect(True)
            await Presenter.close_device.__wrapped__(presenter)
            await asyncio.sleep(0)

            assert presenter._auto_reconnect_suppressed is True
            assert presenter._auto_reconnect_task is None
            assert model.opened == 1

        asyncio.run(scenario())

    @pytest.mark.parametrize("error", [
        serial.SerialException("port unplugged"),
        ConnectionError("serial connection closed"),
    ])
    def test_serial_disconnect_reconnects_when_checked(self, tmp_path, monkeypatch, error):
        model = CountingModel(voltage_error=error)

        async def scenario():
            presenter = make(tmp_path, monkeypatch, model=model)
            await Presenter.open_device.__wrapped__(presenter)
            presenter.set_auto_connect(True)
            await wait_until(lambda: model.opened >= 2 and presenter._connected_port == "COM8")
            model.voltage_error = None

            assert (False, None) in presenter.view.connection_states
            assert presenter.view.connection_states[-1] == (True, "COM8")
            await Presenter.close_device.__wrapped__(presenter)

        asyncio.run(scenario())

    def test_serial_disconnect_stays_offline_when_unchecked(self, tmp_path, monkeypatch):
        model = CountingModel(voltage_error=serial.SerialException("port unplugged"))

        async def scenario():
            presenter = make(tmp_path, monkeypatch, model=model)
            await Presenter.open_device.__wrapped__(presenter)
            await wait_until(
                lambda: presenter.view.connection_states[-1] == (False, None)
            )
            await asyncio.sleep(0)

            assert model.opened == 1
            assert presenter._auto_reconnect_task is None
            assert presenter.view.connection_states[-1] == (False, None)
            await Presenter.close_device.__wrapped__(presenter)

        asyncio.run(scenario())

    def test_unchecking_cancels_a_pending_retry(self, tmp_path, monkeypatch):
        model = CountingModel(open_ok=False)

        async def scenario():
            presenter = make(tmp_path, monkeypatch, model=model, auto_connect=True)
            await wait_until(lambda: presenter._auto_reconnect_failures == 1)

            assert presenter.set_auto_connect(False) is True
            await asyncio.sleep(0)

            assert presenter._auto_reconnect_task is None
            assert presenter._auto_reconnect_failures == 0
            assert model.opened == 1

        asyncio.run(scenario())

    def test_manual_disconnect_cancels_a_pending_retry(self, tmp_path, monkeypatch):
        model = CountingModel(open_ok=False)

        async def scenario():
            presenter = make(tmp_path, monkeypatch, model=model, auto_connect=True)
            await wait_until(lambda: presenter._auto_reconnect_failures == 1)

            await Presenter.close_device.__wrapped__(presenter)
            await asyncio.sleep(0)

            assert presenter._auto_reconnect_suppressed is True
            assert presenter._auto_reconnect_task is None
            assert model.opened == 1

        asyncio.run(scenario())

    def test_manual_connect_takes_over_from_a_pending_retry(self, tmp_path, monkeypatch):
        model = CountingModel(open_results=[False, True])

        async def scenario():
            presenter = make(tmp_path, monkeypatch, model=model, auto_connect=True)
            await wait_until(lambda: presenter._auto_reconnect_failures == 1)

            await Presenter.open_device.__wrapped__(presenter)

            assert model.opened == 2
            assert presenter._connected_port == "COM8"
            assert presenter._auto_reconnect_task is None
            await Presenter.close_device.__wrapped__(presenter)

        asyncio.run(scenario())

    def test_unchecking_during_open_closes_the_abandoned_handle(self, tmp_path, monkeypatch):
        class BlockingOpenModel(CountingModel):
            def __init__(self):
                super().__init__()
                self.started = asyncio.Event()

            async def open(self, port=None, **kwargs):
                self.opened += 1
                self.opened_ports.append(port)
                self.started.set()
                await asyncio.Event().wait()
                return True

        model = BlockingOpenModel()

        async def scenario():
            presenter = make(tmp_path, monkeypatch, model=model, auto_connect=True)
            await model.started.wait()
            assert presenter.set_auto_connect(False) is True
            await wait_until(lambda: presenter._auto_reconnect_task is None and model.closed == 1)

            assert model.opened == 1
            assert presenter._connected_port is None

        asyncio.run(scenario())

    def test_rechecking_during_cancellation_still_connects(self, tmp_path, monkeypatch):
        class BlockingFirstOpenModel(CountingModel):
            def __init__(self):
                super().__init__()
                self.started = asyncio.Event()

            async def open(self, port=None, **kwargs):
                self.opened += 1
                self.opened_ports.append(port)
                if self.opened == 1:
                    self.started.set()
                    await asyncio.Event().wait()
                return True

        model = BlockingFirstOpenModel()

        async def scenario():
            presenter = make(tmp_path, monkeypatch, model=model, auto_connect=True)
            await model.started.wait()
            assert presenter.set_auto_connect(False) is True
            assert presenter.set_auto_connect(True) is True
            await wait_until(lambda: presenter._connected_port == "COM8")

            assert model.opened == 2
            await Presenter.close_device.__wrapped__(presenter)

        asyncio.run(scenario())

    def test_failed_preference_write_does_not_enable_reconnect(self, tmp_path, monkeypatch):
        presenter = make(tmp_path, monkeypatch)
        monkeypatch.setattr(presenter_mod, "save_connection_settings", lambda _settings: False)

        assert presenter.set_auto_connect(True) is False
        assert presenter.auto_connect_enabled() is False

    def test_sampling_timeout_does_not_trigger_reconnect(self, tmp_path, monkeypatch):
        model = CountingModel(fail_voltage_on={1, 2, 3, 4})

        async def scenario():
            presenter = make(tmp_path, monkeypatch, model=model)
            await Presenter.open_device.__wrapped__(presenter)
            presenter.set_auto_connect(True)
            await wait_until(lambda: bool(presenter.view.error_messages))

            assert model.opened == 1
            assert presenter._connected_port == "COM8"
            assert presenter._auto_reconnect_task is None
            await Presenter.close_device.__wrapped__(presenter)

        asyncio.run(scenario())
