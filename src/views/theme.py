"""主题层：控制面板外观的唯一色值来源。

样式表只覆盖它写到的属性，菜单、tooltip、下拉弹出列表等仍从 QPalette 取色，
因此 build_palette 与 build_qss 必须同源，否则宿主系统为浅色配色时会出现底色分裂。
"""

from PySide6.QtGui import QColor, QPalette

TOKENS = {
    "dark": {
        "surface": "#232629",
        "surface_alt": "#2b2f33",
        "plate": "#12151a",
        "border": "#3a4048",
        "border_strong": "#4d5560",
        "text": "#e6e8ea",
        "text_dim": "#9aa3ad",
        "primary": "#4b9fea",
        "success": "#2fbf71",
        "danger": "#e5534b",
        "hover": "#33383d",
        "radius": "6px",
        "radius_small": "4px",
        "gap": "8px",
        "gap_small": "4px",
    },
}

# 字号与字体族一律不在此声明：窗口与读数标签的字号由 Python UI 代码设定，样式表的字体属性
# 优先级高于 setFont，全局声明会把 36pt 读数压成普通字号。
_QSS_TEMPLATE = """
QWidget {{
    color: {text};
    background-color: {surface};
}}

QMainWindow, QDialog {{
    background-color: {surface};
}}

QToolTip {{
    color: {text};
    background-color: {plate};
    border: 1px solid {border};
}}

QGroupBox {{
    border: 1px solid {border};
    border-radius: {radius};
    margin-top: 12px;
    padding-top: {gap};
    background-color: {surface};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: {gap};
    padding: 0 {gap_small};
    color: {text_dim};
}}

QGroupBox::indicator {{
    width: 14px;
    height: 14px;
}}

QLabel {{
    background-color: transparent;
    color: {text};
}}

QPushButton {{
    color: {text};
    background-color: {surface_alt};
    border: 1px solid {border};
    border-radius: {radius_small};
    padding: {gap_small} 12px;
}}

QPushButton:hover {{
    background-color: {hover};
    border-color: {border_strong};
}}

QPushButton:pressed {{
    background-color: {plate};
}}

QPushButton:disabled {{
    color: {text_dim};
    background-color: {surface};
    border-color: {border};
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QAbstractSpinBox {{
    color: {text};
    background-color: {surface_alt};
    border: 1px solid {border};
    border-radius: {radius_small};
    padding: {gap_small} {gap_small};
    selection-background-color: {primary};
}}

QLineEdit:read-only {{
    background-color: {plate};
    color: {text_dim};
}}

QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    background-color: {surface};
    border: 1px solid {border};
    width: 16px;
}}

QComboBox {{
    color: {text};
    background-color: {surface_alt};
    border: 1px solid {border};
    border-radius: {radius_small};
    padding: {gap_small} {gap_small};
}}

QComboBox:hover {{
    border-color: {border_strong};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 18px;
    border-left: 1px solid {border};
}}

QComboBox QAbstractItemView {{
    color: {text};
    background-color: {surface_alt};
    border: 1px solid {border_strong};
    selection-background-color: {primary};
    selection-color: {plate};
    outline: 0;
}}

QCheckBox {{
    background-color: transparent;
    color: {text};
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {border_strong};
    border-radius: 3px;
    background-color: {surface_alt};
}}

QCheckBox::indicator:checked {{
    background-color: {primary};
    border-color: {primary};
}}

QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: {radius};
    top: -1px;
    background-color: {surface};
}}

QTabBar::tab {{
    color: {text_dim};
    background-color: {surface_alt};
    border: 1px solid {border};
    border-bottom: none;
    border-top-left-radius: {radius_small};
    border-top-right-radius: {radius_small};
    padding: {gap_small} 12px;
}}

QTabBar::tab:selected {{
    color: {text};
    background-color: {surface};
    border-color: {border_strong};
}}

QTabBar::tab:hover {{
    color: {text};
}}

QStatusBar {{
    background-color: {surface};
    color: {text_dim};
}}

QScrollBar:vertical {{
    background-color: {surface};
    width: 12px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {border_strong};
    min-height: 20px;
    border-radius: 3px;
}}

QScrollBar:horizontal {{
    background-color: {surface};
    height: 12px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background-color: {border_strong};
    min-width: 20px;
    border-radius: 3px;
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
"""

# 读数与输出开关按 objectName 绑定，避免依赖控件类型之外的隐式层级。
_READOUT_TEMPLATE = """
#{name} {{
    color: {text};
    background-color: {plate};
    border: 1px solid {border};
    border-radius: {radius_small};
    padding: {gap_small} {gap};
}}
"""

# 通信按钮用描边与文字表达语义，不用整块语义色填充：实心填充会和输出开关的
# :checked 状态色抢注意力，而后者才是需要一眼看出的危险状态。
_SEMANTIC_BUTTON = {
    "connect_Btn": "primary",
    "disconnect_Btn": "danger",
}

_SEMANTIC_BUTTON_TEMPLATE = """
#{name} {{
    color: {color};
    border: 1px solid {color};
}}

#{name}:hover {{
    color: {color};
    background-color: {hover};
    border-color: {color};
}}
"""

# 接通态不用实心色块：两态差异要同时落在色相、线宽与字重上，任一失效都不至于看不出来
# （design.md D10）。规则限定在单个 objectName 上，避免将来新增的 checkable 按钮继承。
_OUTPUT_SWITCH_TEMPLATE = """
#ouput_ctrl_Btn:checked {{
    color: {success};
    background-color: {surface_alt};
    border: 2px solid {success};
    font-weight: bold;
}}
"""

# 关于页与状态栏的提示控件同样只靠 objectName 限定作用域（见本文件既有约定）：
# 版本信息是次要内容，颜色用 text_dim 而不是 text，层级只靠字重表达——
# test_theme.py 禁止样式表出现 font-size。
_ABOUT_TEMPLATE = """
#about_title_label {{
    font-weight: bold;
    color: {text};
}}

#about_meta_label {{
    color: {text_dim};
}}
"""

# 更新提示条：文字与状态栏既有配色一致（text_dim），只有动作按钮用主色提亮，
# 让"这是一条可点的提示"从颜色上成立，而不是靠字号。
_UPDATE_TEMPLATE = """
#update_notice_widget {{
    background-color: {surface_alt};
    border: 1px solid {border};
    border-radius: {radius_small};
}}

#update_notice_label {{
    color: {text_dim};
}}

#update_notice_result_label {{
    color: {text_dim};
}}

#update_notice_button {{
    color: {primary};
    background-color: transparent;
    border: 1px solid {border_strong};
    border-radius: {radius_small};
    padding: 0 {gap_small};
}}

#update_notice_button:hover {{
    background-color: {hover};
}}
"""

# 记录页：状态与目录是次要信息（text_dim），只有"记录已中止"用危险色——
# 它意味着这段数据不完整，用户需要立刻分辨出来。
_RECORD_TEMPLATE = """
#record_status_label {{
    color: {text};
    font-weight: bold;
}}

#record_dir_label {{
    color: {text_dim};
}}

#record_error_label {{
    color: {danger};
}}
"""

# 状态栏右角的连接指示：接通绿、断开灰（text_dim 与栏内既有次要文字同值）。
# 两态是两个 objectName（conn_status_on/off），措辞之外的第二通道落在色相上。
_CONN_STATUS_TEMPLATE = """
#conn_status_on {{
    color: {success};
}}

#conn_status_off {{
    color: {text_dim};
}}
"""

# 禁用态必须按 objectName 再降一次色：上面 `#connect_Btn` 的 ID 优先级压过全局
# `QPushButton:disabled`，不补这条的话按钮禁下去了颜色还是语义色，看不出不能点。
# 降色用 text_dim，与栏内次要文字同值；描边轮廓保留，位置与含义都还在。
_DISABLED_SEMANTIC_BUTTON_TEMPLATE = """
#{name}:disabled {{
    color: {text_dim};
    border-color: {border};
}}
"""


def tokens(mode: str = "dark") -> dict:
    try:
        return TOKENS[mode]
    except KeyError:
        raise ValueError(f"unknown theme mode: {mode!r}") from None


def build_qss(mode: str = "dark") -> str:
    t = tokens(mode)
    qss = _QSS_TEMPLATE.format(**t)
    for name in ("volatage_label", "current_label"):
        qss += _READOUT_TEMPLATE.format(name=name, **t)
    for name, token in _SEMANTIC_BUTTON.items():
        qss += _SEMANTIC_BUTTON_TEMPLATE.format(
            name=name, color=t[token], hover=t["hover"]
        )
        qss += _DISABLED_SEMANTIC_BUTTON_TEMPLATE.format(
            name=name, text_dim=t["text_dim"], border=t["border"]
        )
    qss += _OUTPUT_SWITCH_TEMPLATE.format(**t)
    qss += _ABOUT_TEMPLATE.format(**t)
    qss += _UPDATE_TEMPLATE.format(**t)
    qss += _RECORD_TEMPLATE.format(**t)
    qss += _CONN_STATUS_TEMPLATE.format(**t)
    return qss


def build_palette(mode: str = "dark") -> QPalette:
    t = tokens(mode)
    surface = QColor(t["surface"])
    surface_alt = QColor(t["surface_alt"])
    plate = QColor(t["plate"])
    text = QColor(t["text"])
    text_dim = QColor(t["text_dim"])
    primary = QColor(t["primary"])
    border = QColor(t["border"])

    palette = QPalette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        palette.setColor(group, QPalette.ColorRole.Window, surface)
        palette.setColor(group, QPalette.ColorRole.WindowText, text)
        palette.setColor(group, QPalette.ColorRole.Base, surface_alt)
        palette.setColor(group, QPalette.ColorRole.AlternateBase, plate)
        palette.setColor(group, QPalette.ColorRole.ToolTipBase, plate)
        palette.setColor(group, QPalette.ColorRole.ToolTipText, text)
        palette.setColor(group, QPalette.ColorRole.Text, text)
        palette.setColor(group, QPalette.ColorRole.Button, surface)
        palette.setColor(group, QPalette.ColorRole.ButtonText, text)
        palette.setColor(group, QPalette.ColorRole.BrightText, text)
        palette.setColor(group, QPalette.ColorRole.Highlight, primary)
        palette.setColor(group, QPalette.ColorRole.HighlightedText, plate)
        palette.setColor(group, QPalette.ColorRole.PlaceholderText, text_dim)
        palette.setColor(group, QPalette.ColorRole.Link, primary)
        palette.setColor(group, QPalette.ColorRole.Light, border)
        palette.setColor(group, QPalette.ColorRole.Midlight, border)
        palette.setColor(group, QPalette.ColorRole.Mid, border)
        palette.setColor(group, QPalette.ColorRole.Dark, plate)
        palette.setColor(group, QPalette.ColorRole.Shadow, plate)

    disabled_text = QColor(text_dim)
    for group in (QPalette.ColorGroup.Disabled,):
        palette.setColor(group, QPalette.ColorRole.WindowText, disabled_text)
        palette.setColor(group, QPalette.ColorRole.Text, disabled_text)
        palette.setColor(group, QPalette.ColorRole.ButtonText, disabled_text)

    return palette
