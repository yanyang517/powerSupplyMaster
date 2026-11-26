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


class StubCombo:
    def __init__(self, text):
        self._text = text

    def currentText(self):
        return self._text


class FakeView(QWidget):
    """真实视图是 QWidget：准入弹窗要把它作为父窗口。"""

    def __init__(self, presenter=None):
        super().__init__()
        self.presenter = presenter
        self.ui = type("StubUI", (), {
            "com_num_comboBox": StubCombo("COM8"),
            "baudrate_comboBox": StubCombo("115200"),
        })()
        self.voltages = []
        self.currents = []

    def update_voltage_setting(self, value):
        pass

    def update_voltage(self, value):
        self.voltages.append(value)

    def update_current(self, value):
        self.currents.append(value)

    def update_connection_state(self, connected, port=None):
        pass

    def update_device_id(self, value):
        pass

    def update_output_state(self, value):
        pass

    def update_recording_state(self):
        pass


class FakeModel:
    def __init__(self):
        self.sent = []
        self.output_state = True
        self.output_queries = 0
        self.fail_output_query_on = set()
        self.output_query_started = None
        self.output_query_release = None

    async def open(self, port=None, **kwargs):
        return True

    async def close(self):
        pass

    async def get_device_id(self):
        return "FAKE-PSU"

    async def get_voltage(self):
        return 12.0

    async def get_current(self):
        return 0.5

    async def set_voltage(self, value):
        self.sent.append(("voltage", value))

    async def set_on_off(self, value):
        self.sent.append(("on_off", value))
        self.output_state = value

    async def get_on_off(self, *, timeout=1.0):
        self.output_queries += 1
        if self.output_query_started is not None:
            self.output_query_started.set()
        if self.output_query_release is not None:
            await self.output_query_release.wait()
        if self.output_queries in self.fail_output_query_on:
            raise asyncio.TimeoutError()
        return self.output_state


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
    presenter = Presenter(FakeView, FakeModel)
    presenter._connected_port = "COM8"
    presenter._output_state = True
    return presenter


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
        run_write(panel_presenter, "toggle_output")
        assert panel_presenter.model.sent == [("on_off", False)]
        assert panel_presenter.model.output_queries == 2  # 确认后一次，写后一次
        assert lease.holder == "mcp-bridge"

    def test_output_state_follows_device_readback(self, panel_presenter, monkeypatch):
        remote_holder()
        monkeypatch.setattr(presenter_mod, "ask_yes_no", _yes)
        updates = []
        panel_presenter.view.update_output_state = updates.append
        run_write(panel_presenter, "toggle_output")
        assert updates == [True, False]
        assert panel_presenter._output_state is False

    def test_declined_takeover_leaves_output_state_alone(self, panel_presenter, monkeypatch):
        remote_holder()

        async def refuse(*args, **kwargs):
            return False

        monkeypatch.setattr(presenter_mod, "ask_yes_no", refuse)
        updates = []
        panel_presenter.view.update_output_state = updates.append
        run_write(panel_presenter, "toggle_output")
        assert panel_presenter.model.sent == []
        assert panel_presenter.model.output_queries == 0
        assert updates == []
        assert panel_presenter._output_state is True

    def test_unknown_state_does_not_ask_or_write(self, panel_presenter, monkeypatch):
        asked = []
        monkeypatch.setattr(presenter_mod, "ask_yes_no",
                            lambda *a, **k: asked.append(a) or _yes())
        panel_presenter._output_state = None

        run_write(panel_presenter, "toggle_output")

        assert asked == []
        assert panel_presenter.model.sent == []
        assert panel_presenter.model.output_queries == 0

    def test_target_uses_fresh_state_after_takeover_confirmation(self, panel_presenter,
                                                                  monkeypatch):
        remote_holder()

        async def remote_changes_during_confirmation(*args, **kwargs):
            panel_presenter.model.output_state = False
            return True

        monkeypatch.setattr(presenter_mod, "ask_yes_no", remote_changes_during_confirmation)
        run_write(panel_presenter, "toggle_output")

        assert panel_presenter.model.sent == [("on_off", True)]
        assert panel_presenter._output_state is True

    def test_failed_write_readback_publishes_unknown(self, panel_presenter):
        panel_presenter.model.fail_output_query_on = {2}
        updates = []
        panel_presenter.view.update_output_state = updates.append

        run_write(panel_presenter, "toggle_output")

        assert panel_presenter.model.sent == [("on_off", False)]
        assert updates == [True, None]
        assert panel_presenter._output_state is None

    def test_takeover_confirmation_does_not_block_sampling(self, panel_presenter,
                                                           monkeypatch):
        remote_holder()
        confirmation_started = asyncio.Event()
        release_confirmation = asyncio.Event()

        async def wait_for_user(*args, **kwargs):
            confirmation_started.set()
            await release_confirmation.wait()
            return False

        monkeypatch.setattr(presenter_mod, "ask_yes_no", wait_for_user)

        async def scenario():
            toggle = asyncio.create_task(
                Presenter.toggle_output.__wrapped__(panel_presenter))
            sampling = None
            try:
                await confirmation_started.wait()
                sampling = asyncio.create_task(
                    panel_presenter.refresh_voltage_current())
                async with asyncio.timeout(1.0):
                    while not panel_presenter.view.voltages:
                        await asyncio.sleep(0)
                assert panel_presenter.view.voltages == [12.0]
                assert panel_presenter.view.currents == [0.5]
                assert panel_presenter.model.sent == []
            finally:
                release_confirmation.set()
                await toggle
                if sampling is not None:
                    sampling.cancel()
                    await asyncio.gather(sampling, return_exceptions=True)

        asyncio.run(scenario())

    def test_disconnect_cancels_pending_toggle_before_reconnect(self, panel_presenter,
                                                                 monkeypatch):
        remote_holder()
        confirmation_started = asyncio.Event()
        release_confirmation = asyncio.Event()

        async def wait_for_user(*args, **kwargs):
            confirmation_started.set()
            await release_confirmation.wait()
            return True

        monkeypatch.setattr(presenter_mod, "ask_yes_no", wait_for_user)

        async def scenario():
            toggle = asyncio.create_task(
                Presenter.toggle_output.__wrapped__(panel_presenter))
            try:
                await confirmation_started.wait()
                await Presenter.close_device.__wrapped__(panel_presenter)
                assert toggle.cancelled()
                assert panel_presenter._output_toggle_tasks == set()

                # 即使随后重连并放开旧确认，旧请求也不能向新会话下发命令。
                await Presenter.open_device.__wrapped__(panel_presenter)
                release_confirmation.set()
                await asyncio.sleep(0.05)
                assert panel_presenter.model.sent == []
            finally:
                release_confirmation.set()
                if not toggle.done():
                    toggle.cancel()
                await asyncio.gather(toggle, return_exceptions=True)
                await Presenter.close_device.__wrapped__(panel_presenter)

        asyncio.run(scenario())

    def test_old_calibration_cannot_overwrite_new_write(self, panel_presenter):
        model = panel_presenter.model
        model.output_query_started = asyncio.Event()
        model.output_query_release = asyncio.Event()
        updates = []
        panel_presenter.view.update_output_state = updates.append

        async def scenario():
            calibration = asyncio.create_task(
                panel_presenter._calibrate_output_state())
            try:
                await model.output_query_started.wait()
                toggle = asyncio.create_task(
                    Presenter.toggle_output.__wrapped__(panel_presenter))
                await asyncio.sleep(0)  # 切换在操作锁后排队
                model.output_query_release.set()
                await toggle
                assert panel_presenter._output_state is False
                assert updates[-1] is False
                assert model.sent == [("on_off", False)]
            finally:
                calibration.cancel()
                await asyncio.gather(calibration, return_exceptions=True)

        asyncio.run(scenario())


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
