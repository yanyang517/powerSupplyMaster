"""更新提示的界面接线测试：状态栏常驻条、两个用户动作、关于页手动检查（任务 6.2、6.3、6.5）。

以离屏平台运行，假 checker 只提供判定与取数的替身，网络与真实状态文件都不参与。

运行方式（在 src 目录下）：python -m pytest views/test_update_notice.py
"""
import asyncio
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from update.notice import Notice
from views.main_window import MainWindow
from views.update_notice import (
    CHECK_BUTTON_TEXT,
    DISMISS_BUTTON_TEXT,
    VIEW_BUTTON_TEXT,
    ManualCheckRow,
    UpdateNoticeWidget,
)

NOTICE = Notice(text="发现新版本 v9.9.9（当前 v1.4.0）", url="https://example.invalid/9.9.9",
                version="9.9.9")


class FakeChecker:
    """只满足控制器用到的接口：回调挂载、强制检查、忽略落盘。"""

    def __init__(self, *, notice_to_report=None, outcome_to_report="", raise_on_check=False):
        self._on_notice = None
        self._on_outcome = None
        self.dismissed = []
        self.check_calls = []
        self.raise_on_check = raise_on_check
        self._notice = notice_to_report
        self._outcome = outcome_to_report

    def set_callbacks(self, *, on_notice=None, on_outcome=None):
        self._on_notice = on_notice
        self._on_outcome = on_outcome

    async def check(self, *, forced=False):
        self.check_calls.append(forced)
        if self.raise_on_check:
            raise RuntimeError("planted failure")
        if self._notice is not None and self._on_notice:
            self._on_notice(self._notice)
        if self._outcome and self._on_outcome:
            self._on_outcome(self._outcome)
        return self._notice

    def dismiss(self, version):
        self.dismissed.append(version)

    def start(self):
        return None


class StubPresenter:
    def get_available_ports(self):
        return [], 0

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
def widget(qapp):
    return UpdateNoticeWidget()


@pytest.fixture
def manual_row(qapp):
    return ManualCheckRow()


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "views.window_geometry.geometry_file_path", lambda *a, **k: tmp_path / "window_geometry.json"
    )
    win = MainWindow(StubPresenter())
    yield win
    win.floating_window.close()
    win.close()


class TestNoticeWidgetVisibility:
    def test_starts_hidden(self, widget):
        """没有新版本时状态栏上不该多出任何可见东西。"""
        assert widget.isHidden() is True

    def test_show_notice_makes_it_visible_with_text(self, widget):
        widget.show_notice(NOTICE)
        assert widget.isHidden() is False
        assert widget.label.text() == NOTICE.text
        assert widget.version == "9.9.9"

    def test_clear_hides_it_again(self, widget):
        widget.show_notice(NOTICE)
        widget.clear()
        assert widget.isHidden() is True
        assert widget.version is None

    def test_view_button_disabled_without_a_url(self, widget):
        """清单没给地址就别给一个点了没反应的按钮。"""
        widget.show_notice(Notice(text="x", url=None, version="9.9.9"))
        assert widget.view_button.isEnabled() is False
        assert widget.dismiss_button.isEnabled() is True


class TestUserActions:
    def test_view_button_emits_the_release_url(self, widget):
        seen = []
        widget.view_requested.connect(seen.append)
        widget.show_notice(NOTICE)
        widget.view_button.click()
        assert seen == [NOTICE.url]

    def test_dismiss_button_emits_the_version(self, widget):
        seen = []
        widget.dismiss_requested.connect(seen.append)
        widget.show_notice(NOTICE)
        widget.dismiss_button.click()
        assert seen == ["9.9.9"]

    def test_cleared_widget_cannot_emit_a_stale_url(self, widget):
        """clear 之后即便按钮被点到，也不该把上一次的地址再发一遍。"""
        seen = []
        widget.view_requested.connect(seen.append)
        widget.show_notice(NOTICE)
        widget.clear()
        widget.view_button.click()
        assert seen == []


class TestControllerWiring:
    def test_notice_reaches_the_widget(self, widget, manual_row):
        from views.update_notice import UpdateNoticeController
        checker = FakeChecker(notice_to_report=NOTICE)
        UpdateNoticeController(checker=checker, notice_widget=widget, manual_row=manual_row)
        assert asyncio.run(checker.check(forced=True)) is NOTICE
        assert widget.isHidden() is False

    def test_dismiss_records_and_hides(self, widget, manual_row):
        from views.update_notice import UpdateNoticeController
        checker = FakeChecker()
        controller = UpdateNoticeController(checker=checker, notice_widget=widget,
                                            manual_row=manual_row)
        widget.show_notice(NOTICE)
        controller._on_dismiss("9.9.9")
        assert checker.dismissed == ["9.9.9"]
        assert widget.isHidden() is True

    def test_view_action_opens_the_release_page(self, widget, manual_row):
        from views.update_notice import UpdateNoticeController
        opened = []
        controller = UpdateNoticeController(checker=FakeChecker(), notice_widget=widget,
                                            manual_row=manual_row, open_link=opened.append)
        widget.show_notice(NOTICE)
        widget.view_button.click()
        assert opened == [NOTICE.url]

    def test_manual_check_writes_the_outcome(self, widget, manual_row):
        from views.update_notice import UpdateNoticeController
        checker = FakeChecker(outcome_to_report="已是最新（v1.4.0）")
        UpdateNoticeController(checker=checker, notice_widget=widget, manual_row=manual_row)
        manual_row.check_button.click()
        assert checker.check_calls == [True], "手动入口必须以 forced 方式绕过节流"
        assert manual_row.result_label.text() == "已是最新（v1.4.0）"
        assert manual_row.check_button.isEnabled() is True

    def test_button_re_enables_even_if_the_check_raises(self, widget, manual_row):
        """检查抛异常时按钮不能停在"正在检查…"，否则用户以为界面死了。"""
        from views.update_notice import UpdateNoticeController
        checker = FakeChecker(raise_on_check=True)
        UpdateNoticeController(checker=checker, notice_widget=widget, manual_row=manual_row)
        manual_row.check_button.click()
        assert manual_row.check_button.isEnabled() is True
        assert "未完成" in manual_row.result_label.text()

    def test_open_url_refuses_empty(self):
        from views.update_notice import open_url
        assert open_url("") is False


class TestMainWindowIntegration:
    def test_status_bar_holds_the_notice_widget(self, window):
        """addWidgets 会把控件重新挂到状态栏下；这正是"常驻"而不是 showMessage 的证据。"""
        assert window.update_notice.parent() is window.ui.statusbar

    def test_notice_widget_starts_hidden_in_the_window(self, window):
        assert window.update_notice.isHidden() is True

    def test_about_tab_carries_the_manual_check_row(self, window):
        assert window.update_manual_row in window.ui.tab_about.findChildren(ManualCheckRow)
        assert window.update_manual_row.check_button.text() == CHECK_BUTTON_TEXT

    def test_manual_row_is_not_buried_in_version_labels(self, window):
        """检查行与结果标签在「关于」页可见，且结果标签起初为空。"""
        assert window.update_manual_row.result_label.text() == ""
        labels = [label.objectName() for label in window.ui.tab_about.findChildren(QLabel)]
        assert "update_notice_result_label" in labels

    def test_button_texts_are_the_chinese_labels(self, widget):
        assert widget.view_button.text() == VIEW_BUTTON_TEXT
        assert widget.dismiss_button.text() == DISMISS_BUTTON_TEXT
