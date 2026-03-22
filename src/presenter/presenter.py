
import logging
import asyncio

import asyncio

from PySide6.QtCore import Qt, QObject
from qasync import QEventLoop, asyncSlot, asyncClose
import serial
from serial.tools import list_ports
import serial_asyncio
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


    @asyncSlot()
    async def close_device(self):
        await self.model.close_device()

        if self._refresh_voltage_current_task is not None:
            self._refresh_voltage_current_task.cancel()
            self._refresh_voltage_current_task = None

    @asyncSlot()
    async def open_device(self):
        serial_port = self.view.ui.com_num_comboBox.currentText()
        baudrate = self.view.ui.baudrate_comboBox.currentText()
        await self.model.connect(port=serial_port)
        # self._refresh_timer.

        self._refresh_voltage_current_task = asyncio.create_task(self.refresh_voltage_current())
        
    
    @asyncSlot()
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

        await self.model.set_voltage(voltage)
        self.view.update_voltage_setting(voltage)
    
    # @asyncSlot(float)
    # async def set_max_voltage(self, voltage):
        # await self.model.set_max_voltage(voltage)
        # self.view.update_max_voltage(voltage)

    # @asyncSlot(float)
    # async def set_max_current(self, current):
    #     await self.model.set_max_current(current)
    #     self.view.update_max_current_setting(current)
        
