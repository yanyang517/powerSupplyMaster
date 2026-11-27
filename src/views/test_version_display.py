"""版本展示落点的控件级测试：窗口标题与「关于」页（任务 2.2）。

运行方式（在 src 目录下）：python -m pytest views/test_version_display.py
以离屏平台运行；几何恢复文件指向 tmp_path，避免测试写进仓库 config/。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

import version
from .main_window import MainWindow


class StubPresenter:
    """只提供 MainWindow 构造与接线阶段会访问的成员。"""

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


def _about_labels(window):
    return window.ui.tab_about.findChildren(QLabel)


class TestWindowTitle:
    def test_title_carries_the_version(self, window):
        assert version.__version__ in window.windowTitle()
        assert window.windowTitle().startswith("powerSupplyMaster")

    def test_title_replaces_the_default_placeholder(self, window):
        assert window.windowTitle() != "MainWindow"


class TestAboutTab:
    def test_about_tab_is_no_longer_empty(self, window):
        assert window.ui.tab_about.layout() is not None
        assert _about_labels(window)

    def test_version_channel_and_build_are_shown(self, window):
        texts = [label.text() for label in _about_labels(window)]
        assert any(version.__version__ in text for text in texts)
        assert any(version.channel in text for text in texts)
        assert any(text.startswith("构建") for text in texts)

    def test_dev_build_is_labelled_as_dev(self, window):
        """源码直跑必须显式暴露 dev，而不是显示一个看不出的来源。"""
        if not version.is_dev_build():
            pytest.skip("当前为注入了构建信息的发布构建")
        texts = [label.text() for label in _about_labels(window)]
        assert any("dev" in text for text in texts)

    def test_about_content_does_not_touch_control_tabs(self, window):
        """版本信息只落在「关于」页，设备控制区域不受影响。"""
        tabs = window.ui.tabWidget
        about_index = tabs.indexOf(window.ui.tab_about)
        assert about_index >= 0
        assert tabs.widget(0) is not window.ui.tab_about
