# -- utf-8 --
import logging
import asyncio

import serial_asyncio
import serial  # 用于定义串口参数（如数据位、校验位）

logger = logging.getLogger(__name__)

# pyserial-asyncio 在 Windows 上默认每 0.5ms 轮询一次串口。qasync 会把延时
# 换算成 int(秒 * 1000) 毫秒的 Qt 定时器，0.5ms 因此被截断成 0ms，令事件循环
# 在串口连接期间持续空转。1ms 足以避免截断，额外响应延迟也可忽略。
MIN_SERIAL_POLL_INTERVAL_SECONDS = 0.001


def _clamp_serial_poll_interval(writer) -> None:
    """避免 Windows 串口传输退化成的 0ms 自续期轮询。"""
    transport = writer.transport
    transport._poll_wait_time = max(
        getattr(transport, "_poll_wait_time", 0.0),
        MIN_SERIAL_POLL_INTERVAL_SECONDS,
    )


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

        self._locker = asyncio.Lock()
        self._reader = None
        self._writer = None
        self.is_connected = False
        self.identifier = ""
        self.last_error = ""
        self.serial_number = ""
        self.baudrate = 115200
        # 一条查询超时后，设备仍可能随后送出响应。下一条命令发送前必须先
        # 消费这条迟到响应，否则无请求标识的 SCPI 逐行协议会永久错位。
        self._response_recovery_pending = False

    async def _send_cmd(self, command, wait_response: bool = True,
                        timeout: float = 1.0) -> bytes:

        async with self._locker:
            try:
                if self._response_recovery_pending:
                    logger.warning("waiting for late response before sending %r", command)
                    stale_response = await asyncio.wait_for(
                        self._reader.readline(), timeout=timeout)
                    if not stale_response:
                        raise ConnectionError("connection closed during response recovery")
                    logger.info("Discarded late response: %r", stale_response)
                    self._response_recovery_pending = False

                logger.info(f"Sending command: {command}")
                self._writer.write(command)
                try:
                    await asyncio.wait_for(self._writer.drain(), timeout=timeout)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    # write() 已把命令交给传输层；即使 drain 未完成，设备也可能
                    # 已经收到并回复。查询命令必须把这条回复留给下一次恢复读取。
                    if wait_response:
                        self._response_recovery_pending = True
                    raise

                if not wait_response:
                    return b""

                try:
                    response = await asyncio.wait_for(
                        self._reader.readline(), timeout=timeout)
                    if not response:
                        raise ConnectionError("serial connection closed")
                except asyncio.TimeoutError:
                    self._response_recovery_pending = True
                    raise
                except asyncio.CancelledError:
                    # 命令已经写出；取消读取不等于设备停止响应。
                    self._response_recovery_pending = True
                    raise
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

    async def set_current(self, current: float) -> None:
        await self._send_cmd(f"CURR {current:.03f}\n".encode(), wait_response=False)

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
        self._response_recovery_pending = False
        try:
            self.serial_number = serial_number
            self.baudrate = baudrate
            self._reader, self._writer = await serial_asyncio.open_serial_connection(url=self.serial_number, baudrate=self.baudrate)
            _clamp_serial_poll_interval(self._writer)

            self.identifier = await self.get_identifier()
            self.is_connected = True
            self.last_error = ""
        except Exception as e:
            logger.error(f"Error connecting to {self.serial_number}: {e}")
            self.last_error = str(e)
            if self._writer is not None:
                try:
                    self._writer.close()
                except Exception:
                    pass
            self._reader = None
            self._writer = None
            self.is_connected = False
            return False
        return self.is_connected

    async def disconnect(self) -> None:
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        self._reader = None
        self._writer = None
        self.is_connected = False
        self._response_recovery_pending = False

    async def get_on_off(self, *, timeout: float = 1.0) -> bool:
        response = await self._send_cmd(b"OUTP?\n", timeout=timeout)
        status = response.decode().strip().upper()
        if status == "ON":
            return True
        if status == "OFF":
            return False
        raise ValueError(f"invalid OUTP? response: {status!r}")


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
