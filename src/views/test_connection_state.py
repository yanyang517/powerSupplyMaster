"""连接/断开按钮互斥与状态栏右角连接指示的控件级测试。

状态唯一驱动源是 presenter 传给 update_connection_state 的结果，而不是按钮的
clicked 信号：串口被占用导致的连接失败必须停在未连接态，指示栏不能谎报在线。
离屏平台运行，几何文件指向 tmp_path，与 test_main_window_icons.py 同一套路。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


class StubPresenter:
    """只提供 MainWindow 构造与接线阶段会访问的成员。"""

    def __init__(self):
        self.output_toggles = 0

    def get_available_ports(self):
        return [], 0

    def open_device(self):
        pass

    def close_device(self):
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
    win = MainWindow(StubPresenter())
    yield win
    win.floating_window.close()
    win.close()


class TestButtonExclusivity:
    def test_only_connect_is_live_before_a_connection(self, window):
        assert window.ui.connect_Btn.isEnabled()
        assert not window.ui.disconnect_Btn.isEnabled()

    def test_connected_state_flips_both_buttons_together(self, window):
        window.update_connection_state(True, "COM8")

        assert not window.ui.connect_Btn.isEnabled()
        assert window.ui.disconnect_Btn.isEnabled()

    def test_disconnect_returns_to_the_initial_pair(self, window):
        window.update_connection_state(True, "COM8")

        window.update_connection_state(False)

        assert window.ui.connect_Btn.isEnabled()
        assert not window.ui.disconnect_Btn.isEnabled()


class TestOutputStateRendering:
    def test_initial_output_is_unknown_and_disabled(self, window):
        button = window.ui.ouput_ctrl_Btn
        assert button.text() == "输出状态不可用"
        assert not button.isChecked()
        assert not button.isEnabled()

    def test_connection_alone_does_not_guess_output_state(self, window):
        window.update_connection_state(True, "COM8")
        assert window.ui.ouput_ctrl_Btn.text() == "输出状态不可用"
        assert not window.ui.ouput_ctrl_Btn.isEnabled()

    @pytest.mark.parametrize(("state", "text", "checked"), [
        (True, "关闭输出", True),
        (False, "开启输出", False),
    ])
    def test_confirmed_state_renders_next_action(self, window, state, text, checked):
        window.update_connection_state(True, "COM8")
        window.update_output_state(state)

        button = window.ui.ouput_ctrl_Btn
        assert button.text() == text
        assert button.isChecked() is checked
        assert button.isEnabled()
        assert window.floating_window.output_value is state

    def test_failed_calibration_disables_both_output_controls(self, window):
        window.update_connection_state(True, "COM8")
        window.update_output_state(True)

        window.update_output_state(None)

        assert window.ui.ouput_ctrl_Btn.text() == "输出状态不可用"
        assert not window.ui.ouput_ctrl_Btn.isEnabled()
        assert not window.floating_window.buildContextMenu().actions()[1].isEnabled()

    def test_click_sends_toggle_without_keeping_optimistic_check(self, window):
        window.update_connection_state(True, "COM8")
        window.update_output_state(True)

        window.ui.ouput_ctrl_Btn.click()

        assert window.presenter.output_toggles == 1
        assert window.ui.ouput_ctrl_Btn.isChecked()

    def test_disconnect_clears_confirmed_output_state(self, window):
        window.update_connection_state(True, "COM8")
        window.update_output_state(True)

        window.update_connection_state(False)

        assert window._output_state is None
        assert window.ui.ouput_ctrl_Btn.text() == "输出状态不可用"
        assert not window.ui.ouput_ctrl_Btn.isChecked()
        assert not window.ui.ouput_ctrl_Btn.isEnabled()


class TestStatusBarIndicator:
    """指示在状态栏右角：addPermanentWidget 挂的永久部件，不受 showMessage 覆盖。"""

    def test_starts_offline(self, window):
        label = window.connection_status_label
        assert label.text() == "未连接"
        assert label.objectName() == "conn_status_off"

    def test_shows_the_port_once_connected(self, window):
        window.update_connection_state(True, "COM8")

        label = window.connection_status_label
        assert label.text() == "已连接 COM8"
        assert label.objectName() == "conn_status_on"

    def test_says_connected_without_a_port(self, window):
        window.update_connection_state(True)

        assert window.connection_status_label.text() == "已连接"

    def test_back_to_offline_after_disconnect(self, window):
        window.update_connection_state(True, "COM8")

        window.update_connection_state(False)

        label = window.connection_status_label
        assert label.text() == "未连接"
        assert label.objectName() == "conn_status_off"

    def test_survives_a_transient_sampling_message(self, window):
        window.update_connection_state(True, "COM8")

        window.update_sampling_error("TimeoutError: read timed out")

        assert window.connection_status_label.text() == "已连接 COM8"
        assert window.ui.statusbar.currentMessage()
