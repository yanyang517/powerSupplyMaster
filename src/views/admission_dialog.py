"""新客户端准入弹窗：显示申请方身份并把用户决定写回待确认队列。

非模态呈现：等待用户应答期间，其他客户端的请求要继续被事件循环处理。
"""
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from server.session import PendingApproval, pending_approvals

logger = logging.getLogger(__name__)

_TIER_HINT = {
    "L1": "可设定电压/电流",
    "L2": "可设定电压/电流、切换输出开关、连接或断开设备",
}


class AdmissionDialog(QDialog):
    def __init__(self, approval: PendingApproval, parent=None):
        super().__init__(parent)
        self.approval = approval
        self.setModal(False)
        self.setWindowTitle("客户端准入请求")
        self.setAttribute(Qt.WA_DeleteOnClose)

        layout = QVBoxLayout(self)
        self.title_label = QLabel(f"新客户端申请接入：{approval.client_id}")
        self.detail_label = QLabel(
            f"来源：{approval.peer}\n"
            f"申请等级：{approval.tier.name}（{_TIER_HINT.get(approval.tier.name, '')}）"
        )
        self.status_label = QLabel("同意后写入客户端登记表并放行本次登录。")
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.reject_button = QPushButton("拒绝")
        self.allow_button = QPushButton("允许")
        self.reject_button.clicked.connect(lambda: self._answer(False))
        self.allow_button.clicked.connect(lambda: self._answer(True))
        buttons.addWidget(self.reject_button)
        buttons.addWidget(self.allow_button)
        layout.addLayout(buttons)

    def _answer(self, approved: bool) -> None:
        if not pending_approvals.decide(self.approval.request_id, approved):
            # 超时或已被别处应答：不再重复决定，只把状态告诉用户
            self._mark_stale()
            return
        logger.info("admission %s by panel: client=%s tier=%s",
                    "approved" if approved else "refused",
                    self.approval.client_id, self.approval.tier.name)
        self.done(QDialog.Accepted if approved else QDialog.Rejected)

    def _mark_stale(self) -> None:
        self.allow_button.setEnabled(False)
        self.reject_button.setEnabled(False)
        self.status_label.setText("该请求已超时或已被应答，无需再处理。")

    def closeEvent(self, event):
        """用户直接关窗视同拒绝，否则服务端的等待只能到超时才结束。"""
        pending_approvals.decide(self.approval.request_id, False)
        super().closeEvent(event)
