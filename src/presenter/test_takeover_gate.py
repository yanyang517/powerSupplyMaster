"""面板写操作的控制权接管确认：空闲时不打扰，有人持有时先问用户。

对应设计 D1 的"面板豁免"：面板下发不检查也不改变控制权归属，
只在归属非空时要求用户确认，避免覆盖远程客户端正在做的控制。
"""
import asyncio
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QWidget

from server import access
from server.registry import ClientRegistry, Principal, Tier, use_registry
from server.session import hub, lease

from . import presenter as presenter_mod
from .presenter import Presenter


@pytest.fixture(scope="module", autouse=True)
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class FakeView(QWidget):
    """真实视图是 QWidget：准入弹窗要把它作为父窗口。"""

    def __init__(self, presenter=None):
        super().__init__()
        self.presenter = presenter

    def update_voltage_setting(self, value):
        pass

    def update_output_setting(self, value):
        pass

    def update_recording_state(self):
        pass


class FakeModel:
    def __init__(self):
        self.sent = []

    async def set_voltage(self, value):
        self.sent.append(("voltage", value))

    async def set_on_off(self, value):
        self.sent.append(("on_off", value))


@pytest.fixture(autouse=True)
def clean_state():
    lease.revoke()
    for session in list(hub):
        hub.close(session)
    presenter_mod.set_approval_handler(None)
    yield
    lease.revoke()
    for session in list(hub):
        hub.close(session)
    presenter_mod.set_approval_handler(None)


@pytest.fixture
def panel_presenter():
    return Presenter(FakeView, FakeModel)


def remote_holder(client_id="mcp-bridge"):
    session = hub.open("127.0.0.1:53100")
    session.authenticate(Principal(client_id=client_id, tier=Tier.L1, name="AI 助手"))
    lease.claim(client_id, Tier.L1)
    return session


def run_write(presenter, name, *args):
    """asyncSlot 包装后不能直接 await，取 functools.wraps 留下的原协程。"""
    coro = getattr(Presenter, name).__wrapped__(presenter, *args)
    return asyncio.run(coro)


class TestTakeoverGate:
    def test_idle_lease_writes_without_asking(self, panel_presenter, monkeypatch):
        asked = []
        monkeypatch.setattr(presenter_mod, "ask_yes_no",
                            lambda *a, **k: asked.append(a) or _yes())
        run_write(panel_presenter, "set_voltage", 12.0)
        assert panel_presenter.model.sent == [("voltage", 12.0)]
        assert asked == []

    def test_held_lease_asks_before_writing(self, panel_presenter, monkeypatch):
        remote_holder()
        seen = {}

        async def fake_ask(title, text, **kwargs):
            seen["text"] = text
            return False

        monkeypatch.setattr(presenter_mod, "ask_yes_no", fake_ask)
        run_write(panel_presenter, "set_voltage", 12.0)
        assert "mcp-bridge" in seen["text"]
        assert panel_presenter.model.sent == []

    def test_confirmed_takeover_writes_but_does_not_claim_lease(self, panel_presenter,
                                                                 monkeypatch):
        remote_holder()
        monkeypatch.setattr(presenter_mod, "ask_yes_no", _yes)
        run_write(panel_presenter, "set_on_off", True)
        assert panel_presenter.model.sent == [("on_off", True)]
        assert lease.holder == "mcp-bridge"

    def test_output_button_text_follows_the_written_value(self, panel_presenter, monkeypatch):
        remote_holder()
        monkeypatch.setattr(presenter_mod, "ask_yes_no", _yes)
        updates = []
        panel_presenter.view.update_output_setting = updates.append
        run_write(panel_presenter, "set_on_off", False)
        assert updates == [False]

    def test_declined_takeover_leaves_button_text_alone(self, panel_presenter, monkeypatch):
        remote_holder()

        async def refuse(*args, **kwargs):
            return False

        monkeypatch.setattr(presenter_mod, "ask_yes_no", refuse)
        updates = []
        panel_presenter.view.update_output_setting = updates.append
        run_write(panel_presenter, "set_on_off", True)
        assert updates == []


async def _yes(*args, **kwargs):
    return True


def empty_registry(tmp_path):
    path = tmp_path / "clients.json"
    path.write_text('{"schema_version": 1, "clients": {}}', encoding="utf-8")
    return ClientRegistry.load(path)


class TestAdmissionHandler:
    """presenter 注册的确认回调必须真的能放行/挡住一次准入。"""

    def _answer_first_dialog(self, approved):
        async def scenario(presenter, client_id, tier):
            task = asyncio.ensure_future(access.admit(
                hub.open("127.0.0.1:53101"), client_id, tier))
            await asyncio.sleep(0)  # 让回调把弹窗建出来
            assert len(presenter._admission_dialogs) == 1
            dialog = presenter._admission_dialogs[0]
            (dialog.allow_button if approved else dialog.reject_button).click()
            return await task

        return scenario

    def test_allowing_grants_access_and_persists_the_client(self, panel_presenter, tmp_path):
        registry = empty_registry(tmp_path)
        use_registry(registry)
        admission = asyncio.run(
            self._answer_first_dialog(True)(panel_presenter, "fresh-tool", Tier.L1))

        assert admission.granted
        assert admission.principal.tier is Tier.L1
        assert registry.get("fresh-tool").tier is Tier.L1
        assert panel_presenter._admission_dialogs == []

    def test_refusing_drops_the_connection_without_registering(self, panel_presenter, tmp_path):
        registry = empty_registry(tmp_path)
        use_registry(registry)
        admission = asyncio.run(
            self._answer_first_dialog(False)(panel_presenter, "creepy-tool", Tier.L2))

        assert not admission.granted
        assert registry.get("creepy-tool") is None
        assert admission.reason == "refused_by_user"
