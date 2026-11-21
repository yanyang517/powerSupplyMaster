"""面板周期采样的健壮性：单次失败不作废整个会话，中断必须看得见。

对应 specs/ui/live-curve：一次超时不得使周期采样永久停止；连续失败要在界面
明示，而不是让读数停在最后一次成功值上假装一切正常。
"""
import asyncio

from . import presenter as presenter_mod
from .presenter import Presenter


class RecordingView:
    """只记录调用：本文件关心的是采样侧行为，不是控件外观。"""

    def __init__(self, presenter=None):
        self.presenter = presenter
        self.voltages = []
        self.currents = []
        self.error_messages = []

    def show(self):
        pass

    def update_voltage(self, value):
        self.voltages.append(value)

    def update_current(self, value):
        self.currents.append(value)

    def update_sampling_error(self, message):
        self.error_messages.append(message)

    def update_recording_state(self):
        pass


class FlakyModel:
    """按调用序号抛错的假设备，用来精确制造"第几轮失败"。"""

    def __init__(self, fail_voltage_on=(), fail_current_on=()):
        self.fail_voltage_on = set(fail_voltage_on)
        self.fail_current_on = set(fail_current_on)
        self.voltage_calls = 0
        self.current_calls = 0

    async def get_voltage(self):
        self.voltage_calls += 1
        if self.voltage_calls in self.fail_voltage_on:
            raise asyncio.TimeoutError()
        return float(self.voltage_calls)

    async def get_current(self):
        self.current_calls += 1
        if self.current_calls in self.fail_current_on:
            raise asyncio.TimeoutError()
        return float(self.current_calls) / 10


def make_presenter(model):
    presenter = Presenter(RecordingView, lambda: model)
    return presenter


def sample_for(presenter, view, expected, timeout=5.0):
    """跑采样循环直到视图收到 expected 个成功周期，然后取消任务。"""

    async def scenario():
        task = asyncio.create_task(presenter.refresh_voltage_current())
        try:
            deadline = asyncio.get_running_loop().time() + timeout
            while len(view.voltages) < expected:
                if asyncio.get_running_loop().time() > deadline:
                    raise AssertionError(
                        f"采样未按预期继续：得到 {view.voltages}，需要 {expected} 个成功周期")
                await asyncio.sleep(0)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def _no_wait(monkeypatch):
    monkeypatch.setattr(presenter_mod, "SAMPLE_INTERVAL_SECONDS", 0)


class TestSamplingKeepsRunning:
    def test_recovers_after_a_single_timeout(self, monkeypatch):
        model = FlakyModel(fail_voltage_on={2})
        presenter = make_presenter(model)
        view = presenter.view
        _no_wait(monkeypatch)

        sample_for(presenter, view, 4)

        # 第 2 轮作废，第 3 轮起照常采样：循环没有跟着异常一起死掉。
        # 电流计数器不跳号——那一轮根本没走到电流查询，正是"成对才算一条"的体现。
        assert view.voltages == [1.0, 3.0, 4.0, 5.0]
        assert view.currents == [0.1, 0.2, 0.3, 0.4]

    def test_incomplete_pair_is_dropped_whole(self, monkeypatch):
        """电压取到、电流取不到：整轮丢弃，绝不让视图只显示一半的新值。"""
        model = FlakyModel(fail_current_on={2})
        presenter = make_presenter(model)
        view = presenter.view
        _no_wait(monkeypatch)

        sample_for(presenter, view, 3)

        assert view.voltages == [1.0, 3.0, 4.0]
        assert view.currents == [0.1, 0.3, 0.4]

    def test_survives_many_consecutive_failures(self, monkeypatch):
        model = FlakyModel(fail_voltage_on=set(range(1, 40)))
        presenter = make_presenter(model)
        view = presenter.view
        _no_wait(monkeypatch)

        sample_for(presenter, view, 2)

        assert view.voltages == [40.0, 41.0]


class TestSamplingFailureIsVisible:
    def test_no_indicator_below_the_threshold(self, monkeypatch):
        model = FlakyModel(fail_voltage_on={1, 2})
        presenter = make_presenter(model)
        view = presenter.view
        _no_wait(monkeypatch)

        sample_for(presenter, view, 1)

        assert view.error_messages == []

    def test_indicator_shows_once_at_the_threshold(self, monkeypatch):
        model = FlakyModel(fail_voltage_on={1, 2, 3, 4, 5})
        presenter = make_presenter(model)
        view = presenter.view
        _no_wait(monkeypatch)

        sample_for(presenter, view, 1)

        # 越过阈值后不再重复推送异常，避免状态栏每半秒闪一次。
        assert len(view.error_messages) == 2
        assert "TimeoutError" in view.error_messages[0]
        assert view.error_messages[1] is None

    def test_indicator_clears_on_the_first_success(self, monkeypatch):
        model = FlakyModel(fail_voltage_on={1, 2, 3})
        presenter = make_presenter(model)
        view = presenter.view
        _no_wait(monkeypatch)

        sample_for(presenter, view, 1)

        assert view.error_messages == [view.error_messages[0], None]
