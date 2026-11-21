"""取回最新发布清单。

三条硬约束（对应 `app/update-notice`）：

- 候选源并发拉取、按优先级取第一个解析成功的结果。实测本机到 GitHub raw 是
  握手超时而不是快速失败，顺序回退会让每次检查先白付一个超时（doc/update_notice.md）。
- 任何失败都只记 info 日志并返回 None：检查更新失败绝不能变成用户看得见的错误，
  更不能影响设备控制通路。
- 同步阻塞实现，调用方必须放到线程里跑（见 notice.py）。
"""
from __future__ import annotations

import concurrent.futures
import logging
import urllib.error
import urllib.request
from typing import Iterable

from . import manifest
from .settings import Source, update_settings

logger = logging.getLogger(__name__)

USER_AGENT = "powerSupplyMaster-update-check"


def fetch_text(url: str, timeout: float) -> str:
    """取回一个源的原始文本；网络与 HTTP 层的问题一律抛 ProbeError。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        # 允许跟随重定向：Gitee raw 实际落在 raw.giteeusercontent.com 上。
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise ProbeError(f"HTTP {status} from {url}")
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise ProbeError(f"HTTP {exc.code} from {url}") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ProbeError(f"{type(exc).__name__}: {reason}") from None


class ProbeError(RuntimeError):
    """单个源不可用；不代表"没有新版本"。"""


def probe_source(source: Source, timeout: float | None = None) -> manifest.LatestInfo:
    """取回并解析一个源；失败抛 ProbeError 或 ManifestError。"""
    limit = update_settings.timeout_seconds if timeout is None else timeout
    text = fetch_text(source.url, limit)
    return manifest.parse(text, source=source.name)


def _probe_quietly(source: Source, timeout: float | None):
    try:
        return probe_source(source, timeout)
    except (ProbeError, manifest.ManifestError) as exc:
        logger.info("update source %s unusable: %s", source.name, exc)
        return None


def fetch_latest(sources: Iterable[Source] | None = None,
                 timeout: float | None = None) -> manifest.LatestInfo | None:
    """并发问所有源，返回优先级最高的那个成功结果；全失败返回 None。"""
    candidates = tuple(sources) if sources is not None else tuple(update_settings.sources)
    if not candidates:
        logger.info("no update sources configured")
        return None

    limit = update_settings.timeout_seconds if timeout is None else timeout
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(candidates)) as pool:
        futures = {source.name: pool.submit(_probe_quietly, source, limit)
                   for source in candidates}
        results = {name: future.result() for name, future in futures.items()}

    for source in candidates:
        info = results.get(source.name)
        if info is not None:
            return info
    return None
