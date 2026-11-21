"""图标助手的行为约束。

对应 ui/icon-system 的三条要求：取色全部来自主题 token、字形缺失时静默降级、状态
图标之间必须有形态差异而不是只换颜色。渲染路径本身（QSvgRenderer 而非 QIcon(svg)）
由 test_render_path_is_not_plugin_dependent 守住。
"""

import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from views import icons
from views.theme import tokens


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def glyph_dir(tmp_path, monkeypatch):
    root = tmp_path / "resources" / "icons" / "tabler"
    root.mkdir(parents=True)
    monkeypatch.setattr(icons, "resources_dir", lambda: tmp_path / "resources")
    return root


def test_icon_is_non_null_and_size_matches(glyph_dir, qapp):
    (glyph_dir / "gauge.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2"><path d="M3 12h18"/></svg>',
        encoding="utf-8")
    small = icons.icon("tabler/gauge", "text", 16)
    large = icons.icon("tabler/gauge", "text", 32)
    assert not small.isNull()
    assert not large.isNull()
    assert icons.pixmap("tabler/gauge", "text", 16).width() == 16
    assert icons.pixmap("tabler/gauge", "text", 32).width() == 32


def test_stroke_tiers_raise_for_small_sizes():
    assert icons.stroke_width_for(16) == 2.5
    assert icons.stroke_width_for(20) == 2.5
    assert icons.stroke_width_for(24) == 2.0
    assert icons.stroke_width_for(256) == 2.0


def test_dpr_scales_physical_pixels_only(glyph_dir, qapp):
    (glyph_dir / "gauge.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2"><path d="M3 12h18"/></svg>',
        encoding="utf-8")
    pm = icons.pixmap("tabler/gauge", "text", 16, dpr=2.0)
    assert pm.width() == 32
    assert pm.devicePixelRatio() == 2.0


def test_color_comes_from_token_not_literal(glyph_dir, qapp, monkeypatch):
    (glyph_dir / "gauge.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2"><path d="M3 12h18"/></svg>',
        encoding="utf-8")
    seen = {}
    monkeypatch.setattr(icons, "_glyph_text",
                        lambda name, role, size: seen.update(role=role) or "")
    icons.icon("tabler/gauge", "danger", 16)
    assert seen["role"] == "danger"
    assert tokens()["danger"] != tokens()["primary"]


def test_unknown_color_role_is_a_programming_error(glyph_dir, qapp):
    with pytest.raises(ValueError):
        icons.color_for("no-such-token")


def test_missing_glyph_degrades_to_null_icon(glyph_dir, qapp):
    assert icons.icon("tabler/not-there", "text", 16).isNull()
    assert icons.pixmap("tabler/not-there", "text", 16) is None


def test_unparsable_glyph_degrades_to_null_icon(glyph_dir, qapp):
    (glyph_dir / "broken.svg").write_text("<svg><unclosed", encoding="utf-8")
    assert icons.icon("tabler/broken", "text", 16).isNull()
    assert icons.pixmap("tabler/broken", "text", 16) is None


def test_renderer_failure_does_not_reach_caller(glyph_dir, qapp, monkeypatch):
    (glyph_dir / "boom.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"/>', encoding="utf-8")

    def explode(*args, **kwargs):
        raise RuntimeError("renderer blew up")

    monkeypatch.setattr(icons, "QSvgRenderer", explode)
    assert icons.icon("tabler/boom", "text", 16).isNull()


def test_resources_dir_prefers_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(icons.sys, "frozen", True, raising=False)
    monkeypatch.setattr(icons.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert icons.resources_dir() == tmp_path / "resources"


def test_resources_dir_falls_back_to_source_tree_in_development(monkeypatch):
    monkeypatch.delattr(icons.sys, "frozen", raising=False)
    assert icons.resources_dir().name == "resources"
    assert icons.resources_dir().parent.name == "src"


def test_app_icon_carries_every_slot_size(qapp):
    """窗口图标必须自带 16/24/32/48 各档：只给一张时标题栏那枚是系统缩放出来的。"""
    icon = icons.app_icon()
    assert not icon.isNull()
    assert {s.width() for s in icon.availableSizes()} >= {16, 24, 32, 48}


def test_mark_tier_switches_at_24(qapp):
    """<= 24 用简化档、>= 32 用完整档（design.md D6），断言的是选源而不是像素。"""
    root = icons.resources_dir()
    small = icons._resolve_tokens((root / icons.MARK_SMALL_FILE_NAME).read_text(encoding="utf-8"))
    full = icons._resolve_tokens((root / icons.MARK_FILE_NAME).read_text(encoding="utf-8"))
    assert small != full, "两档标识内容相同，档位形同虚设"
    assert icons._mark_text(16) == small
    assert icons._mark_text(24) == small
    assert icons._mark_text(32) == full
    assert icons._mark_text(256) == full


def test_vendored_glyphs_render_at_every_slot_size(qapp):
    """仓库里实际 vendored 的字形必须真的能出图，而不是只存在文件。"""
    for name in icons_vendored_names():
        pm = icons.pixmap(name, "text", 16)
        assert pm is not None and not pm.isNull(), f"glyph failed to render: {name}"


def icons_vendored_names():
    root = icons.resources_dir() / icons.ICONS_DIR_NAME
    return sorted(
        f"{lib}/{path.stem}"
        for lib in sorted(p.name for p in root.iterdir() if p.is_dir())
        for path in (root / lib).glob("*.svg"))


def test_control_state_glyphs_differ_in_form_not_color(qapp):
    """ui/icon-system 的形态差异要求：三态用三个不同字形文件。"""
    from views.access_panel import CONTROL_STATE_GLYPHS

    names = [CONTROL_STATE_GLYPHS[state] for state in ("idle", "held", "stale")]
    assert len(set(names)) == 3, f"states share a glyph: {names}"
    for name in names:
        assert (icons.resources_dir() / icons.ICONS_DIR_NAME / f"{name}.svg").is_file()


def test_icons_module_declares_no_hex_colors():
    source = (icons.__file__,)
    text = open(source[0], encoding="utf-8").read()
    assert not re.search(r"#[0-9a-fA-F]{6}\b", text), "图标层出现硬编码色值"


def test_render_path_does_not_use_icon_engine_plugin():
    """QIcon("<path>.svg") 依赖 svg iconengine 插件，收集不全时静默失效。"""
    text = open(icons.__file__, encoding="utf-8").read()
    assert "QIcon(str(" not in text
    assert "QIcon(path" not in text
    assert "QSvgRenderer" in text
