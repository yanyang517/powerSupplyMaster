"""更新提示的界面部分：状态栏条与关于页手动检查行，以及把两者接到 checker 上的控制器。

三件界面上的讲究：

- 状态栏用 `addWidget` 挂常驻控件，不用 `showMessage`：后者是瞬时消息通道，
  任何一次 `showMessage`（包括设备状态提示）都会把更新提示抹掉。
- 「查看发布页」只在 URL 存在时才使能；清单没给地址时不该出现一个点了没反应的按钮。
- 配色一律走 objectName 限定的 QSS 规则（`theme.build_qss` 追加），不写内联样式，
  与既有主题层保持一致。
"""
from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from update.notice import Notice

logger = logging.getLogger(__name__)

VIEW_BUTTON_TEXT = "查看发布页"
DISMISS_BUTTON_TEXT = "忽略此版本"
CHECK_BUTTON_TEXT = "立即检查"


class UpdateNoticeWidget(QWidget):
    """状态栏里的常驻提示条：默认隐藏，只在真的有新版本时出现。"""

    view_requested = Signal(str)
    dismiss_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("update_notice_widget")
        self._version: str | None = None
        self._url: str | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.label = QLabel("")
        self.label.setObjectName("update_notice_label")
        layout.addWidget(self.label)

        self.view_button = QPushButton(VIEW_BUTTON_TEXT)
        self.view_button.setObjectName("update_notice_button")
        self.view_button.clicked.connect(self._on_view)
        layout.addWidget(self.view_button)

        self.dismiss_button = QPushButton(DISMISS_BUTTON_TEXT)
        self.dismiss_button.setObjectName("update_notice_button")
        self.dismiss_button.clicked.connect(self._on_dismiss)
        layout.addWidget(self.dismiss_button)

        self.setVisible(False)

    # -- 状态 -----------------------------------------------------------------

    def show_notice(self, notice: Notice) -> None:
        self._version = notice.version
        self._url = notice.url
        self.label.setText(notice.text)
        self.view_button.setEnabled(bool(notice.url))
        self.setVisible(True)

    def clear(self) -> None:
        self._version = None
        self._url = None
        self.label.setText("")
        self.setVisible(False)

    @property
    def version(self) -> str | None:
        return self._version

    def _on_view(self) -> None:
        if self._url:
            self.view_requested.emit(self._url)

    def _on_dismiss(self) -> None:
        if self._version:
            self.dismiss_requested.emit(self._version)


class ManualCheckRow(QWidget):
    """关于页的「立即检查」：绕过节流与 dev 短路，把结果写在页面上。"""

    check_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("update_manual_row")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.check_button = QPushButton(CHECK_BUTTON_TEXT)
        self.check_button.setObjectName("update_notice_button")
        self.check_button.clicked.connect(self.check_requested.emit)
        layout.addWidget(self.check_button)

        self.result_label = QLabel("")
        self.result_label.setObjectName("update_notice_result_label")
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result_label, 1)

    def set_busy(self, busy: bool) -> None:
        self.check_button.setEnabled(not busy)
        if busy:
            self.result_label.setText("正在检查…")

    def set_result(self, text: str) -> None:
        self.check_button.setEnabled(True)
        self.result_label.setText(text)


def open_url(url: str) -> bool:
    """用系统默认浏览器打开发布页；打不开只记日志，不弹错误框。"""
    if not url:
        return False
    try:
        return bool(QDesktopServices.openUrl(QUrl(url)))
    except Exception:  # pragma: no cover - 防御：桌面服务不可用
        logger.warning("failed to open release page: %s", url)
        return False


class UpdateNoticeController:
    """把 checker（纯逻辑）与两个界面控件接起来，并负责启动后台调度。"""

    def __init__(self, *, checker, notice_widget: UpdateNoticeWidget,
                 manual_row: ManualCheckRow | None = None, open_link=open_url):
        self.checker = checker
        self.widget = notice_widget
        self.manual_row = manual_row
        self._open_link = open_link
        notice_widget.view_requested.connect(self._on_view)
        notice_widget.dismiss_requested.connect(self._on_dismiss)
        if manual_row is not None:
            manual_row.check_requested.connect(self.check_now)
        checker.set_callbacks(on_notice=self._show, on_outcome=self._report)
        self._outcome_reported = True

    # -- 回调 -----------------------------------------------------------------

    def _show(self, notice: Notice) -> None:
        self.widget.show_notice(notice)

    def _report(self, text: str) -> None:
        self._outcome_reported = True
        if self.manual_row is not None:
            self.manual_row.set_result(text)

    def _on_view(self, url: str) -> None:
        self._open_link(url)

    def _on_dismiss(self, version: str) -> None:
        self.checker.dismiss(version)
        self.widget.clear()
        logger.info("update v%s dismissed by user", version)

    # -- 动作 -----------------------------------------------------------------

    def start(self):
        """GUI 启动时挂后台调度；探测本身在 to_thread 里跑，不阻塞事件循环。"""
        return self.checker.start()

    def check_now(self):
        """关于页按钮：强制检查一次，结果由 _report 写回 manual_row。

        GUI 里（qasync 循环正在跑）返回 task，不阻塞按钮回调；没有运行中的循环时
        同步跑完并返回结果，测试与非 GUI 排查走的都是这条路。
        """
        self._outcome_reported = False
        if self.manual_row is not None:
            self.manual_row.set_busy(True)
        coroutine = self._checked()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)
        return loop.create_task(coroutine)

    async def _checked(self):
        """手动检查的执行体：任何异常都收在这里，不许顺着 Qt 槽函数往上抛。"""
        try:
            return await self.checker.check(forced=True)
        except Exception:
            logger.exception("manual update check failed")
            if not self._outcome_reported and self.manual_row is not None:
                self.manual_row.set_result("检查未完成，请稍后重试")
            return None


def attach(window, *, enabled: bool = True, gui: bool = True, checker=None):
    """把更新提示接到已建好的主窗口上，返回控制器（调用方负责 start）。

    放在 views 侧而不是 app.py：控件的 objectName 与回调配对是界面细节，
    app.py 只需要说"接上"和"这条通路开不开"。
    """
    if checker is None:
        from update.scheduler import UpdateChecker
        checker = UpdateChecker(enabled=enabled, gui=gui)
    return UpdateNoticeController(
        checker=checker,
        notice_widget=window.update_notice,
        manual_row=window.update_manual_row,
    )
