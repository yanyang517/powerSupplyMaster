"""app/version-info 能力测试：版本真源、构建来源回落、字面版本号唯一性。

运行方式（在仓库根目录）：python -m pytest src/test_version.py
"""
import importlib
import sys
from pathlib import Path

import pytest

import version as version_module

REPO_ROOT = Path(version_module.__file__).resolve().parents[1]

#: 允许出现字面版本号的位置：对外公告副本由 gen_manifest --check 卡一致性，
#: 文档与规格里是叙述性文字。
LITERAL_VERSION_SCAN_ROOTS = (
    REPO_ROOT / "src",
    REPO_ROOT / "scripts",
    REPO_ROOT / ".github" / "workflows",
)
LITERAL_VERSION_ALLOWED = {
    Path(version_module.__file__).resolve(),
}
SCAN_SUFFIXES = {".py", ".ps1", ".yml", ".yaml"}


@pytest.fixture
def injected_build_info(tmp_path, monkeypatch):
    """临时提供 _build_info.py，并在用例结束后还原模块状态。"""
    (tmp_path / "_build_info.py").write_text(
        'build_commit = "dead123"\nbuild_time = "2026-11-21T09:30:00Z"\n', encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("_build_info", None)
    try:
        yield importlib.reload(version_module)
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("_build_info", None)
        importlib.reload(version_module)


class TestVersionDefinition:
    def test_version_follows_three_digit_semver(self):
        assert version_module.is_valid_version() is True
        assert version_module.version_tuple() == (1, 0, 0)

    def test_rejects_non_numeric_and_extra_segments(self):
        for bad in ("1.0", "1.0.0.0", "v1.0.0", "1.0.x", "", "1.0.0-rc1"):
            assert version_module.is_valid_version(bad) is False
            with pytest.raises(ValueError):
                version_module.version_tuple(bad)

    def test_tag_name_is_v_prefixed_version(self):
        assert version_module.tag_name() == f"v{version_module.__version__}"


class TestBuildInfoFallback:
    def test_missing_build_info_marks_dev_build(self):
        """源码直跑时没有 _build_info，必须显式判定为开发构建而不是猜来源。"""
        assert "_build_info" not in sys.modules
        assert version_module.is_dev_build() is True
        assert "dev" in version_module.build_label()

    def test_injected_build_info_makes_it_a_release_build(self, injected_build_info):
        reloaded = injected_build_info
        assert reloaded.is_dev_build() is False
        assert reloaded.BUILD_COMMIT == "dead123"
        assert "dead123" in reloaded.build_label()
        assert "dev" not in reloaded.build_label()

    def test_state_restored_after_injection(self):
        assert version_module.is_dev_build() is True


class TestDisplayHelpers:
    def test_display_and_summary_contain_the_version(self):
        assert version_module.__version__ in version_module.display_version()
        assert version_module.__version__ in version_module.summary()
        assert version_module.channel in version_module.display_version()


class TestSingleSourceOfTruth:
    def test_no_other_literal_version(self):
        """规格场景：除真源外不得出现需要同步维护的字面版本号。"""
        literal = version_module.__version__
        offenders = []
        for root in LITERAL_VERSION_SCAN_ROOTS:
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                    continue
                if path.resolve() in LITERAL_VERSION_ALLOWED:
                    continue
                if "__pycache__" in path.parts:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                if f'"{literal}"' in text or f"'{literal}'" in text or f": '{literal}'" in text:
                    offenders.append(str(path.relative_to(REPO_ROOT)))
        assert offenders == []
