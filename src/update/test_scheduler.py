"""调度层测试：探测在线程里跑不拖住事件循环，状态与忽略真正落盘（任务 6.1、6.3 持久化）。

运行方式（在仓库根目录）：python -m pytest src/update/test_scheduler.py
"""
from __future__ import annotations

import asyncio
import time

import pytest

from update import probe
from update.manifest import LatestInfo
from update.scheduler import UpdateChecker
from update.settings import UpdateSettings
from update.state import load_state

pytestmark = pytest.mark.asyncio

DAY = 24 * 3600.0
LOCAL = "1.4.0"


def latest(version="1.5.0", source="gitee"):
    return LatestInfo(version=version, date="2026-11-21",
                      release_urls={source: f"https://{source}/x/releases"},
                      channel="stable", source=source)


@pytest.fixture
def clock():
    return {"now": 1_000_000.0}


@pytest.fixture
def checker(tmp_path, clock):
    def build(probe_fn, **overrides):
        settings = overrides.pop("settings", UpdateSettings(interval_seconds=DAY))
        kwargs = {
            "settings": settings,
            "state_path": tmp_path / "update_state.json",
            "clock": lambda: clock["now"],
            "local_version": LOCAL,
            "is_dev": False,
            "gui": True,
            "enabled": True,
            "probe_fn": probe_fn,
        }
        kwargs.update(overrides)
        return UpdateChecker(**kwargs)
    return build


class TestDecisionWiring:
    async def test_due_check_notices_and_stamps_last_check(self, checker, clock, tmp_path):
        seen = []
        subject = checker(lambda: latest(), on_notice=seen.append)
        item = await subject.check()
        assert item is seen[0] and item.version == "1.5.0"
        assert load_state(tmp_path / "update_state.json").last_check == pytest.approx(clock["now"])

    async def test_no_notice_when_versions_match(self, checker):
        seen = []
        subject = checker(lambda: latest(version=LOCAL), on_notice=seen.append)
        assert await subject.check() is None
        assert seen == []

    async def test_disabled_makes_zero_requests(self, checker):
        calls = []
        subject = checker(lambda: calls.append(1) or latest(), enabled=False)
        assert await subject.check() is None
        assert calls == []

    async def test_headless_makes_zero_requests(self, checker):
        calls = []
        subject = checker(lambda: calls.append(1) or latest(), gui=False)
        assert await subject.check() is None
        assert calls == []

    async def test_dev_build_makes_zero_requests(self, checker):
        calls = []
        subject = checker(lambda: calls.append(1) or latest(), is_dev=True)
        assert await subject.check() is None
        assert calls == []

    async def test_second_check_inside_interval_is_throttled(self, checker):
        calls = []
        subject = checker(lambda: calls.append(1) or latest())
        await subject.check()
        await subject.check()
        assert len(calls) == 1

    async def test_forced_check_still_runs_inside_interval(self, checker):
        calls = []
        subject = checker(lambda: calls.append(1) or latest())
        await subject.check()
        await subject.check(forced=True)
        assert len(calls) == 2

    async def test_skipped_check_does_not_advance_the_clock(self, checker, clock, tmp_path):
        """跳过的一轮不该把节流时钟推后，否则用户永远等不到下一次真检查。"""
        subject = checker(lambda: latest())
        await subject.check()
        clock["now"] += DAY / 2
        await subject.check()
        assert load_state(tmp_path / "update_state.json").last_check == pytest.approx(1_000_000.0)


class TestDismiss:
    async def test_dismissed_version_stays_silent_after_restart(self, checker, tmp_path):
        first = checker(lambda: latest())
        await first.check()
        first.dismiss("1.5.0")

        # 新实例＝重启进程：只靠状态文件传话
        seen = []
        restarted = checker(lambda: latest(), on_notice=seen.append)
        assert await restarted.check(forced=True) is None
        assert seen == []

    async def test_ignoring_one_version_does_not_ignore_the_next(self, checker):
        first = checker(lambda: latest())
        first.dismiss("1.5.0")
        item = await checker(lambda: latest(version="1.6.0")).check()
        assert item is not None and item.version == "1.6.0"


class TestEventLoopStaysResponsive:
    async def test_blocking_probe_runs_off_the_loop(self, checker):
        """探测里人为睡 0.3 秒，循环仍要照常心跳——这就是 6.1 要的证明。"""
        slept = 0.3

        def slow_probe():
            time.sleep(slept)
            return latest()

        ticks = 0

        async def heartbeat():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        subject = checker(slow_probe)
        beat = asyncio.ensure_future(heartbeat())
        started = time.monotonic()
        item = await subject.check()
        elapsed = time.monotonic() - started
        beat.cancel()
        try:
            await beat
        except asyncio.CancelledError:
            pass
        assert item is not None
        assert elapsed >= slept, "to_thread 没生效：探测把循环一起睡了"
        assert ticks >= 10, f"探测期间循环只心跳了 {ticks} 次，界面会卡住"


class TestOutcomeCallback:
    async def test_outcome_reports_new_release(self, checker):
        seen = []
        subject = checker(lambda: latest(), on_outcome=seen.append)
        await subject.check(forced=True)
        assert "1.5.0" in seen[0]

    async def test_outcome_reports_failure_as_failure(self, checker):
        seen = []
        subject = checker(lambda: None, on_outcome=seen.append)
        await subject.check(forced=True)
        assert "失败" in seen[0]

    async def test_outcome_reports_why_it_was_skipped(self, checker):
        seen = []
        subject = checker(lambda: latest(), is_dev=True, on_outcome=seen.append)
        await subject.check(forced=False)
        assert seen == []  # 自动检查静默，不该往界面上写东西

    async def test_forced_dev_check_actually_probes(self, checker):
        """dev 构建点"立即检查"就该真去问一次：短路是为后台静音，不是为手动入口设闸。"""
        seen = []
        calls = []
        subject = checker(lambda: calls.append(1) or latest(),
                          is_dev=True, on_outcome=seen.append)
        item = await subject.check(forced=True)
        assert calls == [1]
        assert item is not None and "1.5.0" in seen[0]


class TestPeriodicScheduling:
    async def test_start_probes_after_the_startup_delay(self, checker):
        """循环起来就该发一次请求；后续重复由节流挡住，而不是由调度层再发。"""
        calls = []
        settings = UpdateSettings(startup_delay_seconds=0.01, interval_seconds=0.02)
        subject = checker(lambda: calls.append(1) or latest(version=LOCAL), settings=settings)
        task = subject.start()
        await asyncio.sleep(0.09)
        await subject.stop()
        assert len(calls) == 1, "首次检查后又被节流放行，说明 last_check 没写进去"
        assert task.cancelled() or task.done()

    async def test_start_is_idempotent(self, checker):
        calls = []
        settings = UpdateSettings(startup_delay_seconds=0.0, interval_seconds=DAY)
        subject = checker(lambda: calls.append(1) or latest(), settings=settings)
        first = subject.start()
        assert subject.start() is first
        await asyncio.sleep(0.02)
        await subject.stop()
        assert len(calls) == 1

    async def test_stop_cancels_without_leaving_a_task(self, checker):
        settings = UpdateSettings(startup_delay_seconds=0.01, interval_seconds=60.0)
        subject = checker(lambda: latest(), settings=settings)
        subject.start()
        await asyncio.sleep(0.02)
        await subject.stop()
        assert subject._task is None

    async def test_a_broken_probe_does_not_kill_the_loop(self, checker):
        calls = []

        def boom():
            calls.append(1)
            raise probe.ProbeError("planted failure")

        # 间隔为 0：节流不拦手，专门看异常之后周期任务还活不活着
        subject = checker(boom, settings=UpdateSettings(startup_delay_seconds=0.0,
                                                        interval_seconds=0.0))
        task = subject.start()
        await asyncio.sleep(0.15)
        await subject.stop()
        assert len(calls) >= 2, "探测异常把周期任务带崩了"
        assert task.cancelled() or task.done()
