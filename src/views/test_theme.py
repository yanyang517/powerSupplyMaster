"""主题层约束自检。

这些断言对应 design.md 中由实测确立的三条硬约束：不声明字体族（离屏渲染中
指定 font-family 会导致整屏文字变豆腐块）、不使用动效与渐变（本机无独显）、
样式表与 palette 必须同源（否则宿主系统为浅色配色时底色分裂）。
"""

import re
from pathlib import Path

import pytest
from PySide6.QtGui import QPalette

from views.theme import TOKENS, build_palette, build_qss, tokens

MODE = "dark"

_FORBIDDEN_QSS_DECLARATIONS = (
    "font-family",
    "font-size",
    "box-shadow",
    "gradient",
    "animation",
    "transition",
)

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\b")


def test_build_qss_is_not_empty():
    assert build_qss(MODE).strip()


def test_build_qss_emits_every_token_value():
    qss = build_qss(MODE)
    missing = [k for k, v in tokens(MODE).items() if str(v) not in qss]
    assert not missing, f"tokens not present in stylesheet: {missing}"


def test_build_qss_has_no_forbidden_declarations():
    qss = build_qss(MODE).lower()
    found = [word for word in _FORBIDDEN_QSS_DECLARATIONS if word in qss]
    assert not found, f"forbidden declarations in stylesheet: {found}"


def test_build_qss_targets_readout_labels_by_object_name():
    qss = build_qss(MODE)
    assert "#volatage_label" in qss
    assert "#current_label" in qss


def test_output_switch_state_rule_is_scoped_to_its_object_name():
    """带语义色的状态规则必须限定到具体 objectName（design.md D4）。

    裸 `QPushButton:checked` 会让将来新增的任何 checkable 按钮静默继承接通态，
    这条断言是为了防止该漂移再次发生。
    """
    qss = build_qss(MODE)
    assert "#ouput_ctrl_Btn:checked" in qss
    assert not re.search(r"(?<![#\w])QPushButton\s*:\s*checked", qss), (
        "bare QPushButton:checked selector found; scope it to #ouput_ctrl_Btn"
    )


def test_build_palette_matches_tokens():
    t = tokens(MODE)
    palette = build_palette(MODE)
    checks = {
        QPalette.ColorRole.Window: t["surface"],
        QPalette.ColorRole.Base: t["surface_alt"],
        QPalette.ColorRole.ToolTipBase: t["plate"],
        QPalette.ColorRole.WindowText: t["text"],
        QPalette.ColorRole.Text: t["text"],
        QPalette.ColorRole.Highlight: t["primary"],
    }
    for role, expected in checks.items():
        assert palette.color(role).name() == expected, role


def test_unknown_mode_is_rejected():
    for factory in (build_qss, build_palette):
        with pytest.raises(ValueError):
            factory("light")


def test_no_literal_colors_outside_the_token_table():
    source = Path(__file__).with_name("theme.py").read_text(encoding="utf-8")
    declared = {v.lower() for v in TOKENS[MODE].values() if isinstance(v, str)}
    undeclared = {c.lower() for c in _HEX_COLOR.findall(source)} - declared
    assert not undeclared, f"hard-coded colors outside TOKENS: {sorted(undeclared)}"
