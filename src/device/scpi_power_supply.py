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

    async def _send_cmd(self, command, wait_response: bool = True) -> bytes:
        
        async with self._locker:
            try:
                logger.info(f"Sending command: {command}")
                self._writer.write(command)
                await asyncio.wait_for( self._writer.drain() , timeout=1)

                if not wait_response:
                    return b""

                response = await asyncio.wait_for( self._reader.readline() , timeout=1)
                logger.info(f"Received response: {response}")
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
        await self._send_cmd(f"VOLTage {voltage:.02f}\n".encode(), wait_response=False)
        # if "OK" is in response:

    async def get_voltage(self) -> float:
        response = await self._send_cmd(b"MEASure:VOLTage?\n")

        return float(response.decode().strip().split()[0])
    
    async def set_on_off(self, on: bool) -> None:
        if on:
            await self._send_cmd(b"OUTP ON\n", wait_response=False)
        else:
            await self._send_cmd(b"OUTP OFF\n", wait_response=False)

    # get current
    async def get_current(self) -> float:
        response = await self._send_cmd(b"MEASure:CURRent?\n")

        return float(response.decode().strip().split()[0])

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


if __name__ == "__main__":
    async def main():
        psu = SCPI_PowerSupply()
        await psu.connect(serial_number="COM4", baudrate=115200)
        identifier = await psu.get_identifier()
        print(f"Connected to: {identifier}")
        await psu.set_voltage(5.0)
        voltage = await psu.get_voltage()
        print(f"Voltage set to: {voltage} V")
        await psu.set_on_off(True)
        on_off = await psu.get_on_off()
        print(f"Output status: {'ON' if on_off else 'OFF'}")
        current = await psu.get_current()
        print(f"Current: {current} A")
        await psu.disconnect()

    asyncio.run(main())
