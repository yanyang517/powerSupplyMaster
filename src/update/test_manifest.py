"""发布清单解析测试：schema、必填字段与坏输入一律判定为"这次获取失败"（任务 5.1）。

运行方式（在仓库根目录）：python -m pytest src/update/test_manifest.py
"""
from __future__ import annotations

import json

import pytest

from update import manifest

GOOD = {
    "schema_version": 1,
    "version": "1.2.0",
    "channel": "stable",
    "date": "2026-01-02",
    "release_urls": {"gitee": "https://gitee.com/a/b/releases"},
}


def doc(**overrides):
    document = dict(GOOD)
    for key, value in overrides.items():
        if value is None:
            document.pop(key, None)
        else:
            document[key] = value
    return json.dumps(document)


class TestParseOk:
    def test_returns_latest_info(self):
        info = manifest.parse(doc(), source="gitee")
        assert info.version == "1.2.0"
        assert info.date == "2026-01-02"
        assert info.source == "gitee"

    def test_channel_defaults_to_stable(self):
        assert manifest.parse(doc(channel=None)).channel == "stable"

    def test_release_url_prefers_the_winning_source(self):
        info = manifest.parse(doc(release_urls={
            "github": "https://github.com/a/b/releases",
            "gitee": "https://gitee.com/a/b/releases",
        }), source="github")
        assert info.release_url("github") == "https://github.com/a/b/releases"

    def test_release_url_falls_back_when_key_absent(self):
        info = manifest.parse(doc(), source="mirror")
        assert info.release_url("mirror") == "https://gitee.com/a/b/releases"

    def test_version_is_normalised_to_three_digits(self):
        """清单多写一个 v 前缀不能把比较和"已忽略版本"对掉。"""
        assert manifest.parse(doc(version="v1.2.0")).version == "1.2.0"


class TestParseRejects:
    @pytest.mark.parametrize("text", ["", "{", "not json at all", "[]", '"str"', "42"])
    def test_non_object_json(self, text):
        with pytest.raises(manifest.ManifestError):
            manifest.parse(text)

    def test_unsupported_schema_version(self):
        with pytest.raises(manifest.ManifestError, match="schema_version"):
            manifest.parse(doc(schema_version=2))

    @pytest.mark.parametrize("key", ["schema_version", "version", "date", "release_urls"])
    def test_missing_required_key(self, key):
        with pytest.raises(manifest.ManifestError, match=key):
            manifest.parse(doc(**{key: None}))

    def test_illegal_version_string(self):
        with pytest.raises(manifest.ManifestError, match="release version"):
            manifest.parse(doc(version="1.0.0-rc1"))

    @pytest.mark.parametrize("urls", [{}, [], "https://x", {"a": "ftp://x"}, None])
    def test_release_urls_must_be_usable_map(self, urls):
        with pytest.raises(manifest.ManifestError):
            manifest.parse(doc(release_urls=urls))

    def test_empty_date(self):
        with pytest.raises(manifest.ManifestError, match="date"):
            manifest.parse(doc(date=""))
