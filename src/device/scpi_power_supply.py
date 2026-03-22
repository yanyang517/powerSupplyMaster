# -- utf-8 --
import logging
import asyncio
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


    async def get_identifier(self) -> str:
        self._writer.write(b"*IDN?\n")
        await asyncio.wait_for( self._writer.drain() , timeout=1)

        response = await asyncio.wait_for( self._reader.readline() , timeout=1)
        return response.decode().strip()
    
    async def set_voltage(self, voltage: float) -> None:
        self._writer.write(f"VOLT {voltage:.02f}\n".encode())
        await asyncio.wait_for( self._writer.drain() , timeout=1)
        ret = await asyncio.wait_for( self._reader.readline() , timeout=1)
        # if "OK" is in ret:

    async def get_voltage(self) -> float:
        self._writer.write(b"VOLT?\n")
        await asyncio.wait_for( self._writer.drain() , timeout=1)

        response = await asyncio.wait_for( self._reader.readline() , timeout=1)

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


