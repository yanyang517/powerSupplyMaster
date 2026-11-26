"""悬浮窗动态输出菜单：三态文案、禁用门控与三个动作互不串线。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


class RecordingPresenter:
    def __init__(self):
        self.output_toggles = 0

    def get_available_ports(self):
        return [], 0

    def auto_connect_enabled(self):
        return False

    def set_auto_connect(self, enabled):
        return True

    def open_device(self):
        pass

    def close_device(self):
        pass

    def set_voltage(self, value):
        pass

    def toggle_output(self):
        self.output_toggles += 1

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
        "views.window_geometry.geometry_file_path",
        lambda *a, **k: tmp_path / "window_geometry.json",
    )
    win = MainWindow(RecordingPresenter())
    yield win
    win.floating_window.close()
    win.close()


def output_action(window):
    return window.floating_window.buildContextMenu().actions()[1]


def test_unknown_output_is_unavailable_and_disabled(window):
    menu = window.floating_window.buildContextMenu()
    action = menu.actions()[1]

    assert [item.text() for item in menu.actions()] == [
        "显示主窗口", "输出状态不可用", "隐藏悬浮窗",
    ]
    assert not action.isEnabled()
    action.trigger()
    assert window.presenter.output_toggles == 0


@pytest.mark.parametrize(("state", "text"), [(True, "关闭输出"), (False, "开启输出")])
def test_confirmed_state_shows_next_action(window, state, text):
    window.update_connection_state(True, "COM8")
    window.update_output_state(state)

    action = output_action(window)

    assert action.text() == text
    assert action.isEnabled()
    assert window.floating_window.output_value is state


def test_output_action_emits_parameterless_toggle_request(window):
    fired = []
    window.floating_window.request_output_toggle.connect(lambda: fired.append("toggle"))
    window.update_connection_state(True, "COM8")
    window.update_output_state(True)

    output_action(window).trigger()

    assert fired == ["toggle"]
    assert window.presenter.output_toggles == 1


def test_every_menu_action_has_an_icon(window):
    assert [action.icon().isNull()
            for action in window.floating_window.buildContextMenu().actions()] == [
                False, False, False,
            ]


def test_show_main_action_emits_only_its_own_signal(window, monkeypatch):
    fired = []
    monkeypatch.setattr(window, "_show_main_window", lambda: fired.append("show_main"))
    window.floating_window.request_output_toggle.connect(lambda: fired.append("output"))

    window.floating_window.buildContextMenu().actions()[0].trigger()

    assert fired == ["show_main"]
    assert window.presenter.output_toggles == 0


def test_hide_action_closes_only_the_floating_window(window, monkeypatch):
    closed = []
    monkeypatch.setattr(window.floating_window, "close", lambda *a: closed.append(True))
    fired = []
    window.floating_window.request_show_main.connect(lambda: fired.append("show_main"))
    window.floating_window.request_output_toggle.connect(lambda: fired.append("output"))

    window.floating_window.buildContextMenu().actions()[2].trigger()

    assert closed == [True]
    assert fired == []
    assert window.presenter.output_toggles == 0


def test_show_main_window_unminimizes_before_raising(window, monkeypatch):
    seen = []
    for name in ("showNormal", "raise_", "activateWindow"):
        monkeypatch.setattr(window, name, lambda *a, n=name: seen.append(n))
    window._show_main_window()
    assert seen == ["showNormal", "raise_", "activateWindow"]
