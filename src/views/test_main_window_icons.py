"""主窗口图标落点的控件级测试（任务 4.4）。

以离屏平台运行；几何恢复文件指向 tmp_path，避免测试写进仓库 config/。
这里测的是"落点接上了没有"，取色与降级由 test_icons.py 负责。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from .main_window import _TAB_GLYPHS, MainWindow


class StubPresenter:
    """只提供 MainWindow 构造与接线阶段会访问的成员。"""

    def get_available_ports(self):
        return [], 0

    def open_device(self):
        pass

    def close_device(self):
        pass

    def set_voltage(self, value):
        pass

    def set_on_off(self, value):
        pass

    # 记录页在 _mount_record_tab 阶段就引用它们，桩件缺一个就构造不出窗口。
    def set_recording_enabled(self, enabled):
        return True

    def recording_status(self):
        return {}

    def stop_recording(self):
        pass


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "views.window_geometry.geometry_file_path", lambda *a, **k: tmp_path / "window_geometry.json"
    )
    win = MainWindow(StubPresenter())
    yield win
    win.floating_window.close()
    win.close()


def test_tab_glyph_table_names_exist_in_ui(window):
    """objectName 写错时 _apply_tab_icons 会静默跳过，这条把静默失败变成显式失败。"""
    tabs = window.ui.tabWidget
    for name in _TAB_GLYPHS:
        if name == "tab_record":
            # 记录页不在 .ui 里，是代码 addTab 挂的，只能从窗口上找
            page = window.record_panel
        else:
            page = getattr(window.ui, name, None)
            assert page is not None, f"{name} 不在 uic 生成的控件里"
        assert page.objectName() == name, f"{name} 与页的 objectName 不符"
        assert tabs.indexOf(page) >= 0, f"{name} 不在 tabWidget 上"


def test_every_tab_carries_icon_and_still_carries_text(window):
    tabs = window.ui.tabWidget
    assert tabs.count() == len(_TAB_GLYPHS)
    for i in range(tabs.count()):
        assert not tabs.tabIcon(i).isNull(), f"第 {i} 页无图标"
        assert tabs.tabText(i), f"第 {i} 页文字被图标取代"


@pytest.mark.parametrize(
    "name", ["connect_Btn", "disconnect_Btn", "ouput_ctrl_Btn"]
)
def test_button_keeps_text_beside_its_icon(window, name):
    button = getattr(window.ui, name)
    assert not button.icon().isNull(), f"{name} 无图标"
    assert button.text(), f"{name} 只剩图标没有文字"


def test_output_button_icon_is_the_same_glyph_in_both_states(window):
    """两态同字形、只换色：availableSizes 相同而像素不同，正是 D8 那条"只换色"的形态。"""
    button = window.ui.ouput_ctrl_Btn
    off = button.icon()
    button.setChecked(True)
    on = button.icon()
    assert off.availableSizes() == on.availableSizes()
    assert off.pixmap(QSize(16, 16)).toImage() != on.pixmap(QSize(16, 16)).toImage()
