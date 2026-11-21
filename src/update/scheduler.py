"""探测调度：把同步取数放进线程，把结果交给界面回调。

两条硬约束（对应设计 D5/D7）：

- 取数是 `urllib` 同步调用，必须 `asyncio.to_thread` 包起来。应用与 Qt 共用
  qasync 的一个事件循环，任何在循环里的阻塞都直接表现为界面卡死。
- 这一层不做任何 Qt 调用，回调由调用方注入，因此判定链、节流、忽略与"不阻塞循环"
  都能在纯 asyncio 测试里验证，不需要起界面也不需要联网。
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable

from . import notice as notice_logic
from . import probe, state as state_module
from .settings import UpdateSettings, update_settings

logger = logging.getLogger(__name__)


class UpdateChecker:
    """一次检查的完整流程：判定 -> 取数（线程） -> 提示 -> 记状态。"""

    def __init__(self, *, settings: UpdateSettings = update_settings,
                 state_path=None,
                 clock: Callable[[], float] = time.time,
                 local_version: str | None = None,
                 is_dev: bool | None = None,
                 gui: bool = True,
                 enabled: bool = True,
                 probe_fn: Callable = probe.fetch_latest,
                 on_notice: Callable[[notice_logic.Notice], None] | None = None,
                 on_outcome: Callable[[str], None] | None = None):
        self.settings = settings
        self.state_path = Path(state_path) if state_path is not None else state_module.state_file_path()
        self.clock = clock
        self.gui = gui
        self.enabled = enabled
        self._probe_fn = probe_fn
        self._on_notice = on_notice
        self._on_outcome = on_outcome
        # 默认值在调用时才取，避免导入期就把 version/dev 状态钉死（测试要能改）
        self._local_version = local_version
        self._is_dev = is_dev
        self._task: asyncio.Task | None = None

    # -- 注入点 ---------------------------------------------------------------

    def set_callbacks(self, *, on_notice=None, on_outcome=None) -> None:
        """界面接线用：checker 先于控件构造，回调只能事后挂上。"""
        if on_notice is not None:
            self._on_notice = on_notice
        if on_outcome is not None:
            self._on_outcome = on_outcome

    @property
    def local_version(self) -> str:
        if self._local_version is not None:
            return self._local_version
        import version
        return version.__version__

    @property
    def is_dev(self) -> bool:
        if self._is_dev is not None:
            return self._is_dev
        import version
        return version.is_dev_build()

    def load_state(self) -> state_module.UpdateState:
        return state_module.load_state(self.state_path)

    def save_state(self, state: state_module.UpdateState) -> bool:
        return state_module.save_state(self.state_path, state)

    # -- 判定与执行 -----------------------------------------------------------

    def _emit_outcome(self, text: str) -> None:
        if self._on_outcome is not None:
            self._on_outcome(text)

    async def check(self, *, forced: bool = False) -> notice_logic.Notice | None:
        """跑一次检查；返回给出的提示，没提示就是 None。"""
        state = self.load_state()
        should, reason = notice_logic.should_probe(
            state,
            now=self.clock(),
            interval_seconds=self.settings.interval_seconds,
            enabled=self.enabled,
            is_dev=self.is_dev,
            gui=self.gui,
            forced=forced,
        )
        if not should:
            logger.info("update check skipped: %s", reason)
            if forced:
                self._emit_outcome(notice_logic.outcome_text(
                    None, None, local_version=self.local_version, probed=False, reason=reason))
            return None

        remote = await asyncio.to_thread(self._probe_fn)
        # 只有真发起了请求才写 last_check：跳过的时候不该把节流时钟也推进。
        self.save_state(replace(state, last_check=self.clock()))
        current = self.load_state()
        item = notice_logic.build_notice(remote, local_version=self.local_version, state=current)
        if item is not None:
            logger.info("update available: %s (%s)", item.version, item.url)
            if self._on_notice is not None:
                self._on_notice(item)
        else:
            logger.info("update check finished with nothing to show")
        self._emit_outcome(notice_logic.outcome_text(
            remote, item, local_version=self.local_version, state=current))
        return item

    def dismiss(self, dismissed_version: str) -> state_module.UpdateState:
        """记住"这个版本不再提示"，立即落盘，重启后仍然生效。"""
        state = replace(self.load_state(), dismissed_version=dismissed_version)
        self.save_state(state)
        return state

    # -- 调度 -----------------------------------------------------------------

    def start(self) -> asyncio.Task:
        """启动延迟后检查一次，此后按间隔重复；同一实例只挂一个循环。"""
        if self._task is not None and not self._task.done():
            return self._task
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._run_periodic())
        return self._task

    async def _run_periodic(self) -> None:
        try:
            await asyncio.sleep(self.settings.startup_delay_seconds)
            while True:
                try:
                    await self.check()
                except asyncio.CancelledError:
                    raise
                except Exception:  # 探测永远不能把主职能带崩
                    logger.exception("update check failed unexpectedly")
                await asyncio.sleep(self.settings.interval_seconds)
        except asyncio.CancelledError:
            logger.info("update checker stopped")
            raise

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
