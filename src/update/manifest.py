"""发布清单 `update/latest.json` 的解析与校验。

清单是对外契约，一旦某源给出无法解析的内容，本模块只负责判定"这次获取失败"，
由调用方决定换下一个源——绝不把坏清单当成"没有新版本"。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping

from . import compare

SCHEMA_VERSION = 1
REQUIRED_KEYS = ("schema_version", "version", "date", "release_urls")


class ManifestError(ValueError):
    """清单不可信：JSON 非法、schema 不识别、必填字段缺失或版本格式不合约定。"""


@dataclass(frozen=True)
class LatestInfo:
    version: str
    date: str
    release_urls: Mapping[str, str] = field(default_factory=dict)
    channel: str = "stable"
    source: str = ""

    def release_url(self, preferred: str = "") -> str | None:
        """取发布页地址：优先本源对应的键，缺失时退回清单里任意一条。"""
        urls = dict(self.release_urls or {})
        if preferred and preferred in urls:
            return urls[preferred]
        for key in ("gitee", "github"):
            if key in urls:
                return urls[key]
        return next(iter(urls.values()), None)


def parse(text: str, source: str = "") -> LatestInfo:
    try:
        document = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from None

    if not isinstance(document, dict):
        raise ManifestError("manifest root is not an object")

    missing = [key for key in REQUIRED_KEYS if key not in document]
    if missing:
        raise ManifestError(f"manifest missing required keys: {', '.join(missing)}")

    schema = document["schema_version"]
    if schema != SCHEMA_VERSION:
        raise ManifestError(f"unsupported schema_version {schema!r}, expected {SCHEMA_VERSION}")

    version = document["version"]
    try:
        parts = compare.parse(version)
    except compare.VersionFormatError as exc:
        raise ManifestError(f"manifest release version is unusable: {exc}") from None
    # 统一成规范三段式：比较、提示文案和"已忽略版本"记录都依赖同一串字符，
    # 不能因为清单里多写了个 v 前缀就对不上。
    version = ".".join(str(part) for part in parts)

    release_urls = document["release_urls"]
    if not isinstance(release_urls, dict) or not release_urls:
        raise ManifestError("manifest release_urls must be a non-empty object")
    if not all(isinstance(url, str) and url.startswith("http") for url in release_urls.values()):
        raise ManifestError("manifest release_urls must all be http(s) URLs")

    date = document["date"]
    if not isinstance(date, str) or not date:
        raise ManifestError("manifest date must be a non-empty string")

    return LatestInfo(
        version=version,
        date=date,
        release_urls=release_urls,
        channel=str(document.get("channel", "stable")),
        source=source,
    )
