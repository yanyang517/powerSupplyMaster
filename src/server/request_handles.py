import asyncio
import json
import logging
from typing import Optional, Dict, Any

# from .command_handle_base import CommandHandler

from device.scpi_power_supply import SCPI_PowerSupply

from .dispatcher import dispatcher
from .protocal.protocal import (
    BaseModel, BaseRequest, BaseResponse, VauleResponse,
    EchoRequest,
    LoginRequest, 
    LogoutRequest, 
    OpenDeviceRequest,
    CloseDeviceRequest,

    VoltageQueryRequest,
    CurrentQueryRequest,
    StatusQueryRequest,
    
    SetVoltageRequest,
    SetCurrentRequest,
    SetMaxCurrentRequest,
    SetMaxVoltageRequest,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dispatcher.register("echo", BaseRequest)
async def handle_echo(request: EchoRequest) -> BaseModel:
    """Echo command handler"""
    logger.info(f"Echo command: {request.message}")
    return BaseResponse(request_id = request.request_id, status="success", message=request.message)

@dispatcher.register("login", LoginRequest)
async def handle_login(request: LoginRequest) -> BaseModel:
    """登录处理"""
    # 实际业务逻辑...
    return BaseModel(status="success", session="token_123")

@dispatcher.register("logout", LogoutRequest)
async def handle_logout(request: LogoutRequest) -> BaseModel:
    """登出处理"""
    return BaseModel(status="success")


# Example command handlers with auto-registration
# class EchoHandler(CommandHandler):
#     """Simple echo command handler"""
    
#     command_name = "echo"  # Auto-registers for 'echo' command
    
#     async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
#         msg = data.get('message', '')
#         logger.info(f"Echo command: {msg}")
#         return EchoResponse(success=True, message=msg, timestamp=asyncio.get_event_loop().time()).model_dump()


# class StatusHandler(CommandHandler):
#     """Server status command handler"""
    
#     command_name = "status"  # Auto-registers for 'status' command
    
#     async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
#         logger.info("Status command received")
#         return self._make_positive_response(data={
#             "status": "success",
#                 "connected_clients": 10,
#                 "server_status": "running",
#                 "timestamp": asyncio.get_event_loop().time()
#         })

@dispatcher.register("open_device", OpenDeviceRequest)
async def handle_open_device(req: OpenDeviceRequest) -> BaseResponse:
    # device_name = req.device_id
    is_connected = await SCPI_PowerSupply().connect(serial_number=req.serial_number, baudrate=req.baud_rate)
    # identifier = await SCPI_PowerSupply().get_identifier()
    logger.info(f"device: ")
    return BaseResponse(request_id=req.request_id, status="success")


@dispatcher.register("close_device", CloseDeviceRequest)
async def handle(req: CloseDeviceRequest) -> BaseResponse:
    device_id = req.device_id
    await SCPI_PowerSupply().disconnect()
    logger.info(f"Close device command: {device_id}")
    return BaseResponse(request_id=req.request_id, status="success")

@dispatcher.register("set_voltage", SetVoltageRequest)
async def handle(self, req: SetVoltageRequest) -> BaseResponse:
    voltage = req.value
    logger.info(f"Set voltage command: {voltage}")

    # Perform actual voltage setting here
    await SCPI_PowerSupply().set_voltage(voltage)
    return VauleResponse(request_id=req.request_id, status="success", value=voltage)