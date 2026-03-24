# -- utf-8 --
import logging
import asyncio
from asyncio.locks import Lock

import serial_asyncio
import serial  # 用于定义串口参数（如数据位、校验位）

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def singleton(cls):
    instances = {}
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance

@singleton
class SCPI_PowerSupply(object):
    '''SCPI Power Supply'''

    def __init__(self):
        super().__init__()

        self._locker = Lock()

    async def _send_cmd(self, command):
        
        async with self._locker:
            try:
                self._writer.write(command)
                await asyncio.wait_for( self._writer.drain() , timeout=1)
                
                response = await asyncio.wait_for( self._reader.readline() , timeout=1)
            except asyncio.TimeoutError as e:
                logger.error(f"send_cmd timeout: {command=}, {e}")
                raise e
            finally:
                pass

        return response

    async def get_identifier(self) -> str:
        response = await self._send_cmd(b"*IDN?\n")
        return response.decode().strip()
    
    async def set_voltage(self, voltage: float) -> None:
        response = await self._send_cmd(f"VOLT {voltage:.02f}\n".encode())
        # if "OK" is in response:

    async def get_voltage(self) -> float:
        response = await self._send_cmd(b"VOLT?\n")

        return float(response.decode().strip())
    
    async def set_on_off(self, on: bool) -> None:
        if on:
            await self._send_cmd(b"OUTP ON\n")
        else:
            await self._send_cmd(b"OUTP OFF\n")
        
    
    # get current
    async def get_current(self) -> float:
        response = await self._send_cmd(b"CURR?\n")

        return float(response.decode().strip())

    async def connect(self, *, serial_number, baudrate: int = 115200) -> bool:
        try:
            self.serial_number = serial_number
            self.baudrate = baudrate
            self._reader, self._writer = await serial_asyncio.open_serial_connection(url=self.serial_number, baudrate=self.baudrate)

            self.identifier = await self.get_identifier()
            self.is_connected = True
        except Exception as e:
            logger.error(f"Error connecting to {self.serial_number}: {e}")
            return False
        return self.is_connected

    async def disconnect(self) -> None:
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self.is_connected = False

    async def get_on_off(self) -> bool:
        response = await self._send_cmd(b"OUTP?\n")
        return response.decode().strip() == "ON"

