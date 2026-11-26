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
#: 文档与规格里是叙述性文字。测试夹具同样不得使用当前版本号——规格要求
#: "除真源外不出现字面版本号"，用例里的样本版本一律另取数字。
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
        assert version_module.version_tuple() == (0, 4, 0)

    def test_rejects_non_numeric_and_extra_segments(self):
        for bad in ("1.0", "1.0.0.0", "v1.0.0", "1.0.x", "", "1.0.0-rc1"):
            assert version_module.is_valid_version(bad) is False
            with pytest.raises(ValueError):
                version_module.version_tuple(bad)

    def test_tag_name_is_v_prefixed_version(self):
        assert version_module.tag_name() == f"v{version_module.__version__}"


class TestBuildInfoFallback:
    def test_unknown_build_info_marks_dev_build(self, monkeypatch):
        """dev 判定只看来源信息是否为未知，与本机此刻有没有 _build_info.py 无关。"""
        monkeypatch.setattr(version_module, "BUILD_COMMIT", "unknown")
        monkeypatch.setattr(version_module, "BUILD_TIME", "unknown")
        assert version_module.is_dev_build() is True
        assert "dev" in version_module.build_label()

    def test_half_injected_build_info_still_counts_as_dev(self, monkeypatch):
        """只写进一个字段也不能冒充发布构建：来源不完整就等于来源未知。"""
        monkeypatch.setattr(version_module, "BUILD_COMMIT", "dead123")
        monkeypatch.setattr(version_module, "BUILD_TIME", "unknown")
        assert version_module.is_dev_build() is True

    def test_injected_build_info_makes_it_a_release_build(self, injected_build_info):
        reloaded = injected_build_info
        assert reloaded.is_dev_build() is False
        assert reloaded.BUILD_COMMIT == "dead123"
        assert "dead123" in reloaded.build_label()
        assert "dev" not in reloaded.build_label()

    def test_state_restored_after_injection(self):
        assert version_module.BUILD_COMMIT != "dead123"


class TestDisplayHelpers:
    def test_display_and_summary_contain_the_version(self):
        assert version_module.__version__ in version_module.display_version()
        assert version_module.__version__ in version_module.summary()
        assert version_module.channel in version_module.display_version()


class TestVersionResource:
    """exe 版本资源的渲染：占位符、语法与语言表键都必须对。

    语言表键写错时 PyInstaller 仍会嵌入 FixedFileInfo（FileMajorPart 有值），
    但 FileVersion/ProductName 这些字符串字段全空——肉眼只在文件属性里看到
    "没有版本信息"，所以这条断言盯的就是那个键。
    """

    @staticmethod
    def _load():
        import importlib.util

        path = REPO_ROOT / "scripts" / "make_version_info.py"
        spec = importlib.util.spec_from_file_location("make_version_info", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_rendered_resource_is_valid_python(self):
        import ast

        ast.parse(self._load().render())

    def test_rendered_resource_uses_the_english_codepage_table(self):
        text = self._load().render()
        assert "StringTable('040904B0'" in text
        assert "FileVersion'" in text and "ProductName'" in text

    def test_rendered_resource_carries_the_version(self):
        text = self._load().render()
        major, minor, patch = version_module.version_tuple()
        assert f"filevers=({major}, {minor}, {patch}, 0)" in text
        assert f"StringStruct('ProductVersion', '{version_module.__version__}')" in text


def find_literal_versions(roots, literal, allowed=(), base=REPO_ROOT) -> list[str]:
    """列出把 `literal` 当字面量写死、因而 bump 版本时必须同步修改的文件。"""
    offenders = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            if path.resolve() in allowed:
                continue
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if f'"{literal}"' in text or f"'{literal}'" in text or f": '{literal}'" in text:
                offenders.append(path.relative_to(base).as_posix())
    return offenders


class TestSingleSourceOfTruth:
    def test_no_other_literal_version(self):
        """规格场景：除真源外不得出现需要同步维护的字面版本号。"""
        assert find_literal_versions(
            LITERAL_VERSION_SCAN_ROOTS,
            version_module.__version__,
            LITERAL_VERSION_ALLOWED,
        ) == []

    def test_scan_really_catches_a_hardcoded_version(self, tmp_path):
        """扫描不是走过场：写死版本号的文件（含用例与 CI 配置）必须被抓到。"""
        source_root = tmp_path / "src"
        workflows = tmp_path / ".github" / "workflows"
        source_root.mkdir()
        workflows.mkdir(parents=True)
        (source_root / "helper.py").write_text('PINNED = "9.9.9"\n', encoding="utf-8")
        (source_root / "test_helper.py").write_text('SAMPLE = "9.9.9"\n', encoding="utf-8")
        (workflows / "release.yml").write_text("env:\n  VERSION: '9.9.9'\n", encoding="utf-8")
        (source_root / "notes.md").write_text("9.9.9\n", encoding="utf-8")
        offenders = find_literal_versions([source_root, workflows], "9.9.9", base=tmp_path)
        assert sorted(offenders) == [
            ".github/workflows/release.yml",
            "src/helper.py",
            "src/test_helper.py",
        ]

    def test_scan_skips_only_the_allowed_files(self, tmp_path):
        source_root = tmp_path / "src"
        source_root.mkdir()
        truth = source_root / "version.py"
        truth.write_text('__version__ = "9.9.9"\n', encoding="utf-8")
        assert find_literal_versions([source_root], "9.9.9", {truth.resolve()}, base=tmp_path) == []
        assert find_literal_versions([source_root], "9.9.9", (), base=tmp_path) == ["src/version.py"]
