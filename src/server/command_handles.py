import asyncio
import json
import logging
from typing import Optional, Dict, Any
from .command_handle_base import CommandHandler

from device.scpi_power_supply import SCPI_PowerSupply

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Example command handlers with auto-registration
class EchoHandler(CommandHandler):
    """Simple echo command handler"""
    
    command_name = "echo"  # Auto-registers for 'echo' command
    
    async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
        message = data.get('message', '')
        logger.info(f"Echo command: {message}")
        return self._make_positive_response(data={"echo": message})


class PingHandler(CommandHandler):
    """Ping command handler"""
    
    command_name = "ping"  # Auto-registers for 'ping' command
    
    async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
        logger.info("Ping command received")
        return self._make_positive_response(data={
                "status": "success",
                "pong": True,
                "timestamp": asyncio.get_event_loop().time()
        })


class StatusHandler(CommandHandler):
    """Server status command handler"""
    
    command_name = "status"  # Auto-registers for 'status' command
    
    async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
        logger.info("Status command received")
        return self._make_positive_response(data={
            "status": "success",
                "connected_clients": 10,
                "server_status": "running",
                "timestamp": asyncio.get_event_loop().time()
        })


class OpenDeviceHandler(CommandHandler):
    """Open device command handler"""
    
    command_name = "open_device"  # Auto-registers for 'open_device' command
    
    async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
        device_id = data.get('device_id', None)
        is_connected = await SCPI_PowerSupply().connect(serial_number='COM3')
        # identifier = await SCPI_PowerSupply().get_identifier()
        logger.info(f"device: ")
        return self._make_positive_response(data={
            "status": "success",
            "device_id": device_id,
            "device_status": "connected" if is_connected else "disconnected",
            "timestamp": asyncio.get_event_loop().time()
        })

class CloseDeviceHandler(CommandHandler):
    """Close device command handler"""
    
    command_name = "close_device"  # Auto-registers for 'close_device' command
    
    async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
        device_id = data.get('device_id', None)
        await SCPI_PowerSupply('COM3').disconnect()
        logger.info(f"Close device command: {device_id}")


class SetVoltageHandler(CommandHandler):
    """Set voltage command handler"""
    
    command_name = "set_voltage"  # Auto-registers for 'set_voltage' command
    
    async def before_handle(self, data: Dict[str, Any], addr: tuple) -> tuple:
        voltage = data.get('value', None)
        if voltage is None:
            return self._make_error_response('Invalid voltage value')
        return self._make_positive_response({'value': voltage})
    async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
        voltage = data.get('value', None)
        logger.info(f"Set voltage command: {voltage}")

        # Perform actual voltage setting here
        await SCPI_PowerSupply('COM3').set_voltage(voltage)

        self._make_positive_response({'value': voltage, 'timestamp': asyncio.get_event_loop().time()})
