"""提示判定链：把"要不要探测、要不要提示、提示什么"与 Qt 与网络都隔开。

这一层是纯函数，时钟、版本、清单全部注入，因此 6.4 要求的五条短路能在不联网、
不起界面的前提下逐条验证。真正的取数在 probe.py，界面在 views/main_window.py。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from . import compare
from .manifest import LatestInfo
from .state import UpdateState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Notice:
    """一条可以显示给用户的提示：文案 + 发布页地址。"""

    text: str
    url: str | None
    version: str

    def __str__(self) -> str:  # 日志与测试断言都只关心文案
        return self.text


def should_probe(state: UpdateState, *, now: float, interval_seconds: float,
                 enabled: bool = True, is_dev: bool = False,
                 gui: bool = True, forced: bool = False) -> tuple[bool, str]:
    """本次是否值得发一次网络请求；返回 (是否, 原因)。

    顺序按"最不该被打扰的情形"排：功能关掉 > 没有界面 > dev 构建 > 还在间隔内。
    """
    if not enabled:
        return False, "disabled"
    if not gui:
        return False, "headless"
    if is_dev and not forced:
        # 本地源码直跑的构建来源未知，拿它比版本只会得出无意义结论。
        return False, "dev-build"
    if not forced:
        elapsed = state.seconds_since_last_check(now=now)
        if elapsed is not None and elapsed < interval_seconds:
            return False, f"throttled ({elapsed:.0f}s < {interval_seconds:.0f}s)"
    return True, "due"


def build_notice(remote: LatestInfo | None, *, local_version: str,
                 state: UpdateState) -> Notice | None:
    """由清单结果构造提示；不需要提示时返回 None，并说明为什么。"""
    if remote is None:
        return None
    if not compare.is_update(remote.version, local_version):
        return None
    if state.is_dismissed(remote.version):
        return None
    return Notice(
        text=f"发现新版本 v{remote.version}（当前 v{local_version}）",
        url=remote.release_url(remote.source),
        version=remote.version,
    )


def outcome_text(remote: LatestInfo | None, notice: Notice | None, *,
                 local_version: str, state: UpdateState | None = None,
                 probed: bool = True, reason: str = "") -> str:
    """关于页"立即检查"的可见结果文案：几种"没有提示"必须互相可辨。

    状态栏只在有更新时出声，其余情形静默；手动入口是给开发者和排障用的，
    静默的原因（网络失败 / 已被忽略 / 本来就是最新）要写清楚。
    """
    if not probed:
        return reason or "未发起检查"
    if notice is not None:
        return notice.text
    if remote is None:
        return "检查失败：所有更新源都不可用（详见日志）"
    if state is not None and state.is_dismissed(remote.version):
        return f"v{remote.version} 有新版本，但你已选择忽略该版本"
    if remote.version == local_version:
        return f"已是最新（v{local_version}）"
    if compare.is_update(local_version, remote.version):
        return f"本地 v{local_version} 比清单上的 v{remote.version} 更新（dev 或未发布版本）"
    return f"已是最新（当前 v{local_version}，最新 v{remote.version}）"
