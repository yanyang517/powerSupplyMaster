"""更新提示的本机状态：`config/update_state.json` 的读写。

这里存的两样东西都只服务提示本身——上次探测时间（节流依据）和用户忽略过的版本
（不再重复提示）。文件缺失、不是 JSON、schema 不识别、字段非法，一律退回空状态并
记一条日志：更新提示是可丢特性，任何异常都不能影响主职能启动。

路径解析与 `views/window_geometry.py` 保持一致：源码直跑落在仓库 `config/`，
PyInstaller 冻结后落在 exe 同级 `config/`（可写、跨升级保留）。
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import compare

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
CONFIG_DIR_NAME = "config"
STATE_FILE_NAME = "update_state.json"


def state_file_path(module_file: str = __file__) -> Path:
    """Absolute path of the state file, independent of the process cwd."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_DIR_NAME / STATE_FILE_NAME
    return Path(module_file).resolve().parents[2] / CONFIG_DIR_NAME / STATE_FILE_NAME


@dataclass(frozen=True)
class UpdateState:
    """last_check: 上次真正发起探测的 epoch 秒；dismissed: 用户选择忽略的版本号。"""

    last_check: float | None = None
    dismissed_version: str | None = None

    def seconds_since_last_check(self, now: float | None = None) -> float | None:
        """距上次探测的秒数；从未探测过返回 None（调用方据此放行首次检查）。"""
        if self.last_check is None:
            return None
        return max(0.0, (time.time() if now is None else now) - self.last_check)

    def is_dismissed(self, version: str | None) -> bool:
        return bool(version) and version == self.dismissed_version


def empty_state() -> UpdateState:
    return UpdateState()


def _to_epoch(text) -> float | None:
    """ISO-8601 文本 -> epoch 秒；无法解析返回 None。"""
    if not isinstance(text, str) or not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def _from_epoch(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state(path) -> UpdateState:
    """读取状态；任何不可用内容都换成空状态，本函数不抛异常。"""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.info("update state file missing, starting fresh: %s", path)
        return empty_state()
    except OSError as exc:
        logger.warning("update state file unreadable, starting fresh: %s (%s)", path, exc)
        return empty_state()

    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("update state file is not valid JSON, starting fresh: %s (%s)", path, exc)
        return empty_state()

    if not isinstance(document, dict):
        logger.warning("update state file is not an object, starting fresh: %s", path)
        return empty_state()

    if document.get("schema_version") != SCHEMA_VERSION:
        logger.warning("update state schema_version %r unsupported, starting fresh: %s",
                       document.get("schema_version"), path)
        return empty_state()

    raw_check = document.get("last_check")
    last_check = _to_epoch(raw_check)
    if raw_check is not None and last_check is None:
        logger.warning("update state last_check %r is not an ISO-8601 string, ignored", raw_check)

    dismissed = document.get("dismissed_version")
    if dismissed is not None:
        try:
            # 规范化后入内存：手工写成 "v1.2.0" 的忽略记录仍然生效，
            # 比较时不会再因为一个前缀 v 而对不上清单里的版本号。
            dismissed = ".".join(str(part) for part in compare.parse(dismissed))
        except compare.VersionFormatError as exc:
            logger.warning("update state dismissed_version is unusable, ignored: %s", exc)
            dismissed = None

    return UpdateState(last_check=last_check, dismissed_version=dismissed)


def save_state(path, state: UpdateState) -> bool:
    """原子写状态；失败只记日志、返回 False，不向上抛。"""
    path = Path(path)
    document = {
        "schema_version": SCHEMA_VERSION,
        "last_check": None if state.last_check is None else _from_epoch(state.last_check),
        "dismissed_version": state.dismissed_version,
    }
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("failed to save update state to %s (%s)", path, exc)
        try:
            if tmp.exists():
                os.remove(tmp)
        except OSError as cleanup_exc:
            logger.warning("failed to remove temporary update state file %s (%s)", tmp, cleanup_exc)
        return False
    return True
