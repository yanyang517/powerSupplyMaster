
import logging
import asyncio

import asyncio

from PySide6.QtCore import Qt, QObject
from qasync import QEventLoop, asyncSlot, asyncClose
import serial
from serial.tools import list_ports
import serial_asyncio

from server.access import set_approval_handler
from server.session import lease
from views.admission_dialog import AdmissionDialog
from views.confirmation import ask_yes_no

from .model import PowerSupplyModel

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Presenter(QObject):
    def __init__(self, view_cls, model_cls=None):
        self.view = view_cls(presenter = self)
        self.model = PowerSupplyModel() if model_cls is None else model_cls()
        # self.view.connect_signal_slots(self)
        # self.view.setupUi()
        self.connect_signal_slots()
        self.view.show()

        self._refresh_voltage_current_task = None
        self._admission_dialogs = []
        set_approval_handler(self._on_admission_request)

    def get_available_ports(self) -> list:
        '''
        return the available ports
        '''
        ports = list_ports.comports()
        ports_list = [port.device for port in ports]
        logger.info(f"Available ports: {ports_list}")

        perfered_index = [i for i, port in enumerate(ports) if 'USB' in port.description]
        return ports_list, perfered_index[0] if len(perfered_index) > 0 else None

    def connect_signal_slots(self):
        pass

    def _on_admission_request(self, approval) -> None:
        """服务端准入回调：与 Qt 共用事件循环，弹窗只呈现、不阻塞等待。"""
        dialog = AdmissionDialog(approval, parent=self.view)
        self._admission_dialogs.append(dialog)
        dialog.finished.connect(lambda _code, d=dialog: self._admission_dialogs.remove(d))
        dialog.show()

    async def _may_write_from_panel(self) -> bool:
        """面板写操作免于控制权检查，但有人持有时要先让用户确认接管。"""
        snap = lease.snapshot()
        if snap.holder is None:
            return True
        return await ask_yes_no(
            "电源正被远程控制",
            f"{snap.holder} 当前持有控制权（剩余 {snap.remaining_seconds:.0f} 秒）。\n"
            "确认由面板下发本次改动？",
            parent=self.view,
            yes_text="由面板下发",
        )


    @asyncSlot()
    async def close_device(self):
        # self._period_task_stop_event.set()

        self._refresh_voltage_current_task.cancel()

            
        await self.model.close()

    @asyncSlot()
    async def open_device(self):
        serial_port = self.view.ui.com_num_comboBox.currentText()
        baudrate = self.view.ui.baudrate_comboBox.currentText()

        ret = await self.model.open(port=serial_port)
        # self._refresh_timer.
        if ret is True:
            self._refresh_voltage_current_task = asyncio.create_task(self.refresh_voltage_current())
            pass
            
        ret = await self.model.get_device_id()
        self.view.update_device_id(ret)      
    
    async def refresh_voltage_current(self):
        try:
            while True:
                voltage = await self.model.get_voltage()
                current = await self.model.get_current()
                logger.info(f"{voltage=}, {current=}")
                self.view.update_voltage(voltage)
                self.view.update_current(current)
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info("Refresh voltage current task cancelled.")
            return
    
    @asyncSlot(float)
    async def set_voltage(self, voltage):
        if not await self._may_write_from_panel():
            logger.info("面板写操作被用户取消：set_voltage=%s", voltage)
            return

        self.view.update_voltage_setting(voltage)
        await self.model.set_voltage(voltage)
    
    # @asyncSlot(float)
    # async def set_max_voltage(self, voltage):
        # await self.model.set_max_voltage(voltage)
        # self.view.update_max_voltage(voltage)

    # @asyncSlot(float)
    # async def set_max_current(self, current):
    #     await self.model.set_max_current(current)
    #     self.view.update_max_current_setting(current)

    @asyncSlot(bool)
    async def set_on_off(self, value: bool):
        if not await self._may_write_from_panel():
            logger.info("面板写操作被用户取消：set_on_off=%s", value)
            return

        await self.model.set_on_off(value)
        self.view.update_output_setting(value)
        
