"""面板治理入口的控件级测试：控制权展示、吊销确认、客户端列表与准入弹窗应答。

运行方式（在 src 目录下）：python -m pytest views/test_client_access.py
以离屏平台运行，不依赖真实显示器；弹窗应答用假 future 代替事件循环。
"""
import asyncio
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QGroupBox

from server.registry import Principal, Tier
from server.session import PendingApproval, hub, lease, pending_approvals

from . import access_panel as panel_mod
from .access_panel import AccessPanel
from .admission_dialog import AdmissionDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class RecordingFuture:
    """代替 asyncio.Future：这里只关心用户答案有没有写回待确认项。"""

    def __init__(self):
        self.result = None

    def done(self):
        return self.result is not None

    def set_result(self, value):
        self.result = value


@pytest.fixture
def clean_state(qapp):
    lease.revoke()
    for session in list(hub):
        hub.close(session)
    for approval in list(pending_approvals):
        pending_approvals.discard(approval.request_id)
    yield
    lease.revoke()
    for session in list(hub):
        hub.close(session)
    for approval in list(pending_approvals):
        pending_approvals.discard(approval.request_id)


@pytest.fixture
def panel(clean_state, qapp):
    # 生成器帧持有两个 QGroupBox，避免它们在用例结束时先于面板被回收
    manage_box, clients_box = QGroupBox(), QGroupBox()
    yield AccessPanel(manage_box, clients_box)
    manage_box.deleteLater()
    clients_box.deleteLater()


def connected_holder(client_id="mcp-bridge", tier=Tier.L1):
    session = hub.open("127.0.0.1:53000")
    session.authenticate(Principal(client_id=client_id, tier=tier, name="AI 助手"))
    lease.claim(client_id, tier)
    return session


class TestHolderDisplay:
    def test_free_lease_shows_idle(self, panel):
        assert panel.holder_label.text() == "控制权：空闲"
        assert panel.revoke_button.isEnabled() is False

    def test_connected_holder_shows_remaining_time(self, panel):
        connected_holder()
        panel.refresh()
        text = panel.holder_label.text()
        assert "mcp-bridge" in text and "剩余" in text
        assert panel.revoke_button.isEnabled() is True

    def test_disconnected_holder_is_marked_offline(self, panel):
        session = connected_holder()
        hub.close(session)
        panel.refresh()
        assert "已断线" in panel.holder_label.text()
        assert "已断线" in panel.client_list.item(0).text()


class TestClientList:
    def test_lists_sessions_and_pending_admissions(self, panel):
        connected_holder()
        hub.open("127.0.0.1:53001")
        approval = PendingApproval(request_id="ap1", client_id="new-tool",
                                   tier=Tier.L1, peer="127.0.0.1:53002",
                                   future=RecordingFuture())
        pending_approvals.add(approval)
        panel.refresh()

        rows = [panel.client_list.item(i).text() for i in range(panel.client_list.count())]
        joined = "\n".join(rows)
        assert "mcp-bridge" in joined and "未登录" in joined
        assert "待确认准入" in joined and "new-tool" in joined

    def test_empty_hub_shows_placeholder(self, panel):
        assert "无连接" in panel.client_list.item(0).text()


class TestPanelRevoke:
    def _answer_with(self, monkeypatch, approved):
        async def fake_ask(title, text, **kwargs):
            fake_ask.asked = (title, text)
            return approved
        monkeypatch.setattr(panel_mod, "ask_yes_no", fake_ask)
        return fake_ask

    def test_confirmed_revoke_frees_lease_and_audits(self, panel, monkeypatch, caplog):
        """吊销只改归属：设备输出由面板写路径负责，这里必须一条写入都不发。"""
        connected_holder()
        asked = self._answer_with(monkeypatch, True)
        asyncio.run(panel._confirm_and_revoke())

        assert lease.holder is None
        assert panel.revoke_button.isEnabled() is False
        assert "mcp-bridge" in asked.asked[1]
        audit = [r.message for r in caplog.records if r.name == "server.audit"]
        assert any("origin=panel" in line and "mcp-bridge" in line for line in audit)

    def test_declined_revoke_keeps_lease(self, panel, monkeypatch):
        connected_holder()
        self._answer_with(monkeypatch, False)
        asyncio.run(panel._confirm_and_revoke())
        assert lease.holder == "mcp-bridge"

    def test_nothing_to_revoke_does_not_ask(self, panel, monkeypatch):
        asked = self._answer_with(monkeypatch, True)
        asyncio.run(panel._confirm_and_revoke())
        assert not hasattr(asked, "asked")


class TestAdmissionDialog:
    def _approval(self, client_id="new-tool"):
        approval = PendingApproval(request_id="ap-" + client_id, client_id=client_id,
                                   tier=Tier.L1, peer="127.0.0.1:53009",
                                   future=RecordingFuture())
        pending_approvals.add(approval)
        return approval

    def test_allow_resolves_the_pending_request(self, clean_state, qapp):
        approval = self._approval()
        dialog = AdmissionDialog(approval)
        dialog.allow_button.click()
        assert approval.future.result is True
        assert len(pending_approvals) == 0

    def test_refuse_resolves_with_false(self, clean_state, qapp):
        approval = self._approval("refused-tool")
        dialog = AdmissionDialog(approval)
        dialog.reject_button.click()
        assert approval.future.result is False

    def test_shows_identity_source_and_requested_tier(self, clean_state, qapp):
        approval = self._approval("curious-client")
        dialog = AdmissionDialog(approval)
        assert "curious-client" in dialog.title_label.text()
        assert "127.0.0.1:53009" in dialog.detail_label.text()
        assert "L1" in dialog.detail_label.text()

    def test_closing_the_window_counts_as_refusal(self, clean_state, qapp):
        approval = self._approval("ignored-tool")
        dialog = AdmissionDialog(approval)
        dialog.close()
        assert approval.future.result is False

    def test_answering_after_timeout_does_not_double_decide(self, clean_state, qapp):
        approval = self._approval("late-tool")
        dialog = AdmissionDialog(approval)
        pending_approvals.discard(approval.request_id)  # 服务端超时已回收
        dialog.allow_button.click()
        assert approval.future.result is None
        assert dialog.allow_button.isEnabled() is False
