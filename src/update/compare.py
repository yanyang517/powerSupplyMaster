"""版本号比较：只做"远端是否严格更新"这一件事。

不引入 packaging：它虽在环境中，但进运行时导入图就要额外确认 PyInstaller 收集，
而这里需要的只是三段数字。预发布后缀（`-rc1`）按解析失败处理，宁可不提示。
"""
from __future__ import annotations

import re

_VERSION_PATTERN = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


class VersionFormatError(ValueError):
    """不是 `主.次.修订` 三段数字。"""


def parse(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise VersionFormatError(f"version must be a string, got {type(value).__name__}")
    match = _VERSION_PATTERN.match(value.strip().lstrip("vV"))
    if match is None:
        raise VersionFormatError(f"not a release version: {value!r}")
    return (int(match.group("major")), int(match.group("minor")), int(match.group("patch")))


def is_update(remote: str, local: str) -> bool:
    """远端是否严格大于本地；任一侧格式不合约定时返回 False（不提示）。"""
    try:
        return parse(remote) > parse(local)
    except VersionFormatError:
        return False
