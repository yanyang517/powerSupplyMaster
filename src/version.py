"""应用版本的唯一真源。

约定（见 openspec `app/version-info`）：

- 除本文件外，仓库内任何位置都不得再维护一份需要人工同步的版本号；界面、日志、
  exe 版本资源与控制通路回包一律从这里派生。
- `__version__` 必须是 `主.次.修订` 三段数字；发布用的 git tag 必须是 `v` + 它。
- 提交标识与构建时间属于构建期信息，由 `scripts/build_exe.ps1` 写入同目录的
  `_build_info.py`（已 gitignore）。源码直跑时该模块不存在，本次运行即被判定为
  非发布（开发）构建，而不是去猜测一个来源。
"""

from __future__ import annotations

import re

__version__ = "0.4.2"

#: 发布通道。当前只有 stable 一条，预发布通道落地时再扩展比较规则。
channel = "stable"

_VERSION_PATTERN = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")

try:  # 构建期注入；缺失即开发构建
    from _build_info import build_commit as BUILD_COMMIT, build_time as BUILD_TIME
except ImportError:
    BUILD_COMMIT = "unknown"
    BUILD_TIME = "unknown"


def is_valid_version(value: str | None = None) -> bool:
    """`__version__` 是否符合三段数字约定；构建脚本据此决定是否继续。"""
    return _VERSION_PATTERN.match(__version__ if value is None else value) is not None


def version_tuple(value: str | None = None) -> tuple[int, int, int]:
    """按数字段返回版本三元组，供比较与 exe 版本资源使用。"""
    match = _VERSION_PATTERN.match(__version__ if value is None else value)
    if match is None:
        raise ValueError(f"not a release version: {value or __version__!r}")
    return tuple(int(match.group(name)) for name in ("major", "minor", "patch"))  # type: ignore[return-value]


def is_dev_build() -> bool:
    """是否缺少构建期来源信息（源码直跑、或本地未打 tag 的构建）。"""
    return BUILD_COMMIT == "unknown" or BUILD_TIME == "unknown"


def tag_name() -> str:
    """与 `__version__` 对应的 git tag 名，发布校验以此比对。"""
    return f"v{__version__}"


def display_version() -> str:
    """界面与标题栏用的一行版本标识。"""
    return f"v{__version__} ({channel})"


def build_label() -> str:
    """构建来源的一行文本；开发构建明确写 dev 而不是留空。"""
    if is_dev_build():
        return "dev build (源码运行或未注入构建信息)"
    return f"{BUILD_COMMIT} · {BUILD_TIME}"


def summary() -> str:
    """启动日志与关于页共用的完整描述。"""
    return f"powerSupplyMaster {display_version()} {build_label()}"
