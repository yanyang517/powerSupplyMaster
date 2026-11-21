"""悬浮窗右键菜单三个动作的接线与图标测试（任务 6.1 / 6.2 / 6.3）。

菜单通过 `buildContextMenu()` 取：`QMenu.exec` 是模态原生调用，Shiboken 的实例方法解析
绕不过去，打桩它会真的弹出一个等输入的菜单——所以构造与弹出在 floating_window 里就是分开的。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


class RecordingPresenter:
    """记录 MainWindow 会转发的写操作，供断言"输出被关闭"。"""

    def __init__(self):
        self.on_off_calls = []

    def get_available_ports(self):
        return [], 0

    def open_device(self):
        pass

    def close_device(self):
        pass

    def set_voltage(self, value):
        pass

    def set_on_off(self, value):
        self.on_off_calls.append(value)

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
    win = MainWindow(RecordingPresenter())
    yield win
    win.floating_window.close()
    win.close()


@pytest.fixture
def menu(window):
    return window.floating_window.buildContextMenu()


def test_menu_keeps_the_three_labels_in_order(menu):
    assert [action.text() for action in menu.actions()] == [
        "显示主窗口", "关闭电源输出", "隐藏悬浮窗",
    ]


def test_every_menu_action_has_an_icon(menu):
    assert [action.icon().isNull() for action in menu.actions()] == [False, False, False]


def test_show_main_action_emits_its_own_signal(window, menu):
    fired = []
    window.floating_window.request_show_main.connect(lambda: fired.append("show_main"))
    menu.actions()[0].trigger()
    assert fired == ["show_main"]
    assert window.presenter.on_off_calls == []


def test_output_off_action_reaches_the_presenter(window, menu):
    menu.actions()[1].trigger()
    assert window.presenter.on_off_calls == [False]


def test_hide_action_closes_only_the_floating_window(window, monkeypatch):
    """菜单构造时就绑好了 close，所以打桩必须在 build 之前。"""
    closed = []
    monkeypatch.setattr(window.floating_window, "close", lambda *a: closed.append(True))
    fired = []
    window.floating_window.request_show_main.connect(lambda: fired.append("show_main"))
    window.floating_window.request_output_off.connect(lambda: fired.append("output"))

    actions = window.floating_window.buildContextMenu().actions()
    actions[2].trigger()

    assert closed == [True]
    assert fired == []
    assert window.presenter.on_off_calls == []


def test_show_main_window_unminimizes_before_raising(window, monkeypatch):
    seen = []
    for name in ("showNormal", "raise_", "activateWindow"):
        monkeypatch.setattr(window, name, lambda *a, n=name: seen.append(n))
    window._show_main_window()
    assert seen == ["showNormal", "raise_", "activateWindow"]
