"""版本比较测试：严格大于、相等、更低、非法与 dev 短路（任务 5.2）。

样本版本一律用 9.x，避开当前真源版本号：见 `src/test_version.py` 的
`TestSingleSourceOfTruth`，仓库里除真源外不得出现字面版本号。

运行方式（在仓库根目录）：python -m pytest src/update/test_compare.py
"""
from __future__ import annotations

import pytest

from update import compare


class TestParse:
    @pytest.mark.parametrize("text,expected", [
        ("9.9.9", (9, 9, 9)),
        ("0.0.1", (0, 0, 1)),
        ("10.20.30", (10, 20, 30)),
        ("v9.8.7", (9, 8, 7)),
        (" 9.8.7 ", (9, 8, 7)),
    ])
    def test_accepts_three_digit_versions(self, text, expected):
        assert compare.parse(text) == expected

    @pytest.mark.parametrize("bad", ["9.9", "9.9.9.9", "9.9.x", "", "9.9.9-rc1", "dev", None, 7])
    def test_rejects_anything_else(self, bad):
        with pytest.raises(compare.VersionFormatError):
            compare.parse(bad)


class TestIsUpdate:
    def test_higher_remote_is_an_update(self):
        assert compare.is_update("9.9.10", "9.9.9") is True
        assert compare.is_update("9.10.0", "9.9.20") is True
        assert compare.is_update("10.0.0", "9.9.9") is True

    def test_equal_or_lower_is_not(self):
        assert compare.is_update("9.9.9", "9.9.9") is False
        assert compare.is_update("9.8.20", "9.9.9") is False

    def test_illegal_remote_never_prompts(self):
        """宁可不提示，也不因为读不懂就弹窗——预发布后缀当前一律不按更新处理。"""
        assert compare.is_update("9.9.9-rc1", "9.9.9") is False
        assert compare.is_update("garbage", "9.9.9") is False
        assert compare.is_update("9.9.10", "garbage") is False

    def test_numeric_not_lexicographic(self):
        assert compare.is_update("9.10.0", "9.9.0") is True
        assert compare.is_update("9.9.0", "9.10.0") is False
