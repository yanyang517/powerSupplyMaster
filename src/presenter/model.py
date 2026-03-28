
import logging

import asyncio

from device.scpi_power_supply import SCPI_PowerSupply

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PowerSupplyModel():

    def __init__(self):
        self.device = SCPI_PowerSupply()
        pass
    
    async def open(self, port, baudrate = 115200) -> bool:

        is_connected = await self.device.connect(serial_number=port, baudrate=baudrate)
        logger.info(f"device: {is_connected=}")
        return is_connected

    async def close(self) -> None:
        await self.device.disconnect()
        logger.info(f"Close device")
    async def set_voltage(self, voltage: float) -> None:
        await self.device.set_voltage(voltage)
        logger.info(f"Set voltage: {voltage}")

    async def set_on_off(self, value: bool) -> None:
        await self.device.set_on_off(value)
        logger.info(f"Set on/off: {value}")

    async def get_voltage(self) -> float:
        value = await self.device.get_voltage()
        return value


    async def get_current(self) -> float:
        value = await self.device.get_current()
        return value
    
    async def get_device_id(self) -> str:
        device_id = await self.device.get_identifier()
        return device_id
    