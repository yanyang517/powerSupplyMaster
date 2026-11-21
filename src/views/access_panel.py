"""客户端与控制权面板：直读服务端进程内单例，而不是走一遍协议。

面板是治理入口，不应受自己正在治理的规则约束，因此这里直接读
`hub` / `lease` / `pending_approvals`，吊销也直接落到服务端。
"""
import asyncio
import logging

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from server import access
from server.session import hub, lease, lease_config, pending_approvals

from .confirmation import ask_yes_no
from . import icons

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_MS = 1000

# 控制权三态各用一个字形文件：状态差异靠形态（实心点 / 空心环 / 虚线环）而不是靠色相，
# 见 openspec change add-app-and-ui-icons 的 ui/icon-system 形态差异要求。
CONTROL_STATE_GLYPHS = {
    "idle": "tabler/circle",
    "held": "tabler/circle-dot",
    "stale": "tabler/circle-dashed",
}
CONTROL_STATE_ROLES = {
    "idle": "text_dim",
    "held": "success",
    "stale": "text_dim",
}
REVOKE_GLYPH = "tabler/shield-x"


def _control_state(snap) -> str:
    if snap.holder is None:
        return "idle"
    return "held" if snap.holder_connected else "stale"


class AccessPanel(QObject):
    def __init__(self, manage_box, clients_box):
        super().__init__()
        self._tasks = []
        self._holder_state = None
        self._revoke_role = None

        manage_box.setLayout(QVBoxLayout())
        self.holder_icon = QLabel(manage_box)
        self.holder_label = QLabel(manage_box)
        self.revoke_button = QPushButton("吊销控制权", manage_box)
        self.revoke_button.clicked.connect(self._revoke_requested)
        row = QHBoxLayout()
        row.addWidget(self.holder_icon)
        row.addWidget(self.holder_label, 1)
        row.addWidget(self.revoke_button)
        manage_box.layout().addLayout(row)

        clients_box.setLayout(QVBoxLayout())
        self.client_list = QListWidget(clients_box)
        clients_box.layout().addWidget(self.client_list)

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def _holder_text(self, snap) -> str:
        if snap.holder is None:
            return "控制权：空闲"
        if not snap.holder_connected:
            return (f"控制权：{snap.holder} 已断线，"
                    f"剩余 {snap.remaining_seconds:.0f} 秒")
        return (f"控制权：{snap.holder}（{snap.tier}，剩余 "
                f"{snap.remaining_seconds:.0f}/{lease_config.ttl_seconds:.0f} 秒）")

    def _client_rows(self, snap) -> list[tuple[str, str, str]]:
        """(文本, 字形, 取色角色) 三元组：文本始终是主线索，图标只补形态。

        原先的 `●` `◀` 字符标记去掉：它们本是唯一的形态线索，现在由字形承担，
        而"持有控制权""已断线"这些词一直留着。
        """
        rows = []
        if snap.holder is not None and not snap.holder_connected:
            rows.append((f"{snap.holder} 已断线，仍持有控制权（剩余 "
                         f"{snap.remaining_seconds:.0f} 秒）",
                         "tabler/user-off", "text_dim"))
        for session in hub:
            info = session.describe()
            if info["authenticated"]:
                flag = "  持有控制权" if info["client_id"] == snap.holder else ""
                rows.append((f"{info['client_id']}  {info['name'] or '-'}  "
                             f"{info['tier']}  {info['peer']}{flag}",
                             "tabler/user-check",
                             "success" if flag else "text"))
            else:
                rows.append((f"（未登录）{info['peer']}  "
                             f"已连接 {info['uptime_seconds']:.0f} 秒",
                             "tabler/user", "text"))
        for approval in pending_approvals:
            waited = approval.describe()["waiting_seconds"]
            rows.append((f"待确认准入：{approval.client_id} 申请 "
                         f"{approval.tier.name}（已等待 {waited:.0f} 秒）",
                         "tabler/clock", "text_dim"))
        return rows or [("（无连接）", "tabler/circle", "text_dim")]

    def refresh(self) -> None:
        """面板状态是读出来的而不是推送的：控制权随时可能超时释放。"""
        snap = lease.snapshot()
        self.holder_label.setText(self._holder_text(snap))
        self._set_holder_icon(_control_state(snap))
        enabled = lease.holder is not None
        self.revoke_button.setEnabled(enabled)
        self._set_revoke_icon("danger" if enabled else "text_dim")
        self.client_list.clear()
        for text, glyph, role in self._client_rows(snap):
            item = QListWidgetItem(text)
            item.setIcon(icons.icon(glyph, role))
            self.client_list.addItem(item)

    def _set_holder_icon(self, state: str) -> None:
        if state == self._holder_state:
            return
        self._holder_state = state
        pm = icons.pixmap(CONTROL_STATE_GLYPHS[state], CONTROL_STATE_ROLES[state])
        self.holder_icon.setPixmap(pm if pm is not None else QPixmap())

    def _set_revoke_icon(self, role: str) -> None:
        if role == self._revoke_role:
            return
        self._revoke_role = role
        self.revoke_button.setIcon(icons.icon(REVOKE_GLYPH, role))

    def _revoke_requested(self) -> None:
        if lease.holder is None:
            return
        # Qt 信号里不在事件循环上下文中，用 ensure_future 交给 qasync 的循环
        task = asyncio.ensure_future(self._confirm_and_revoke())
        self._tasks.append(task)
        task.add_done_callback(self._tasks.remove)

    async def _confirm_and_revoke(self) -> None:
        holder = lease.holder
        if holder is None:
            return
        approved = await ask_yes_no(
            "吊销控制权",
            f"当前由 {holder} 控制电源输出。确认吊销其控制权？\n"
            "吊销不会改变设备输出状态与设定值。",
            parent=self.revoke_button.window(),
            yes_text="吊销",
        )
        if approved:
            access.panel_revoke()
        self.refresh()

    def stop(self) -> None:
        self._timer.stop()
