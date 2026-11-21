import asyncio
import json
import logging
from typing import Optional, Dict, Any

# from .command_handle_base import CommandHandler

from device.scpi_power_supply import SCPI_PowerSupply

from .dispatcher import dispatcher
from .registry import Tier
from .access import admit
from .session import Session, hub, lease
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
    OnOffQueryRequest,
    DeviceIdQueryRequest,
    SettingQueryRequest,
    LeaseStatusRequest,
    ListClientsRequest,
    ReleaseLeaseRequest,

    LoginResponse,
    LeaseStatusResponse,
    ListClientsResponse,
    
    SetVoltageRequest,
    SetCurrentRequest,
    SetMaxCurrentRequest,
    SetMaxVoltageRequest,
    SetOnOffRequest,
    SettingResponse,
)
from .runtime_config import runtime_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dispatcher.register("echo", BaseRequest, tier=Tier.L0, public=True)
async def handle_echo(request: EchoRequest) -> BaseModel:
    """Echo command handler"""
    logger.info(f"Echo command: {request.message}")
    return BaseResponse(request_id = request.request_id, status="success", message=request.message)

@dispatcher.register("login", LoginRequest, tier=Tier.L0, public=True, needs_session=True)
async def handle_login(request: LoginRequest, session: Session) -> BaseModel:
    """登录即准入：已登记按登记等级生效，未登记走首次准入流程。"""
    admission = await admit(session, request.client_id, Tier[request.tier])
    if not admission.granted:
        return BaseResponse(request_id=request.request_id, status="error",
                            message=f"[{admission.reason}] {admission.message}")
    session.authenticate(admission.principal)
    logger.info("session %s logged in as %r (%s)", session.session_id,
                session.client_id, session.tier.name)
    return LoginResponse(
        request_id=request.request_id,
        status="success",
        message=admission.message,
        client_id=session.client_id,
        tier=session.tier.name,
        reason=admission.reason,
    )

@dispatcher.register("logout", LogoutRequest, tier=Tier.L0, needs_session=True)
async def handle_logout(request: LogoutRequest, session: Session) -> BaseModel:
    """登出只丢会话身份；控制权按自己的时限存续。"""
    client_id = session.client_id
    session.logout()
    logger.info("session %s logged out (client=%s)", session.session_id, client_id)
    return BaseResponse(request_id=request.request_id, status="success")


@dispatcher.register("lease_status", LeaseStatusRequest, tier=Tier.L0)
async def handle_lease_status(request: LeaseStatusRequest) -> BaseResponse:
    snap = lease.snapshot()
    return LeaseStatusResponse(
        request_id=request.request_id,
        status="success",
        holder=snap.holder,
        tier=snap.tier,
        remaining_seconds=round(snap.remaining_seconds, 1),
        held_seconds=round(snap.held_seconds, 1),
        since_last_write_seconds=round(snap.since_last_write_seconds, 1),
        holder_connected=snap.holder_connected,
    )


@dispatcher.register("list_clients", ListClientsRequest, tier=Tier.L0)
async def handle_list_clients(request: ListClientsRequest) -> BaseResponse:
    return ListClientsResponse(
        request_id=request.request_id,
        status="success",
        clients=[s.describe() for s in hub],
        lease=lease.describe(),
    )


@dispatcher.register("release_lease", ReleaseLeaseRequest, tier=Tier.L0, needs_session=True)
async def handle_release_lease(request: ReleaseLeaseRequest, session: Session) -> BaseResponse:
    if lease.release(session.client_id):
        return BaseResponse(request_id=request.request_id, status="success",
                            message=f"lease released by {session.client_id}")
    return BaseResponse(request_id=request.request_id, status="error",
                        message=f"[not_holder] control lease belongs to {lease.holder!r}, "
                                f"only the holder can release it")


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

def _device_not_connected(req: BaseRequest) -> BaseResponse:
    return BaseResponse(request_id=req.request_id, status="error", message="device not connected")

@dispatcher.register("open_device", OpenDeviceRequest, tier=Tier.L2)
async def handle_open_device(req: OpenDeviceRequest) -> BaseResponse:
    psu = SCPI_PowerSupply()
    is_connected = await psu.connect(serial_number=req.serial_number, baudrate=req.baud_rate)
    if not is_connected:
        logger.error(f"Open device failed: {psu.last_error}")
        return BaseResponse(request_id=req.request_id, status="error", message=f"connect failed: {psu.last_error}")
    logger.info(f"device connected: {psu.identifier}")
    return BaseResponse(request_id=req.request_id, status="success", message=psu.identifier)


@dispatcher.register("close_device", CloseDeviceRequest, tier=Tier.L2)
async def handle(req: CloseDeviceRequest) -> BaseResponse:
    device_id = req.device_id
    await SCPI_PowerSupply().disconnect()
    logger.info(f"Close device command: {device_id}")
    return BaseResponse(request_id=req.request_id, status="success")

@dispatcher.register("set_voltage", SetVoltageRequest, tier=Tier.L1)
async def handle(req: SetVoltageRequest) -> BaseResponse:
    psu = SCPI_PowerSupply()
    if not psu.is_connected:
        return _device_not_connected(req)

    voltage = req.value
    limit = runtime_config.max_voltage
    if not 0 <= voltage <= limit:
        message = f"voltage {voltage:.2f}V out of allowed range 0~{limit:.2f}V"
        logger.warning(f"Set voltage rejected: {message}")
        return BaseResponse(request_id=req.request_id, status="error", message=message)

    logger.info(f"Set voltage command: {voltage}")
    await psu.set_voltage(voltage)
    return VauleResponse(request_id=req.request_id, status="success", value=voltage)

@dispatcher.register("set_current", SetCurrentRequest, tier=Tier.L1)
async def handle(req: SetCurrentRequest) -> BaseResponse:
    psu = SCPI_PowerSupply()
    if not psu.is_connected:
        return _device_not_connected(req)

    current = req.value
    limit = runtime_config.max_current
    if not 0 <= current <= limit:
        message = f"current {current:.3f}A out of allowed range 0~{limit:.3f}A"
        logger.warning(f"Set current rejected: {message}")
        return BaseResponse(request_id=req.request_id, status="error", message=message)

    logger.info(f"Set current command: {current}")
    await psu.set_current(current)
    return VauleResponse(request_id=req.request_id, status="success", value=current)

@dispatcher.register("set_on_off", SetOnOffRequest, tier=Tier.L2)
async def handle(req: SetOnOffRequest) -> BaseResponse:
    psu = SCPI_PowerSupply()
    if not psu.is_connected:
        return _device_not_connected(req)

    status = req.value
    logger.info(f"Set on/off command: {status}")
    await psu.set_on_off(status)
    return VauleResponse(request_id=req.request_id, status="success", value=status)


@dispatcher.register("setting_query", SettingQueryRequest, tier=Tier.L0)
async def handle(req: SettingQueryRequest) -> BaseResponse:
    return SettingResponse(
        request_id=req.request_id,
        status="success",
        max_voltage=runtime_config.max_voltage,
        max_current=runtime_config.max_current,
    )

@dispatcher.register("voltage_query", VoltageQueryRequest, tier=Tier.L0)
async def handle(req: VoltageQueryRequest) -> BaseResponse:
    psu = SCPI_PowerSupply()
    if not psu.is_connected:
        return _device_not_connected(req)
    voltage = await psu.get_voltage()
    logger.info(f"Voltage query command: {voltage}")
    return VauleResponse(request_id=req.request_id, status="success", value=voltage)

# current_query
@dispatcher.register("current_query", CurrentQueryRequest, tier=Tier.L0)
async def handle(req: CurrentQueryRequest) -> BaseResponse:
    psu = SCPI_PowerSupply()
    if not psu.is_connected:
        return _device_not_connected(req)
    current = await psu.get_current()
    logger.info(f"Current query command: {current}")
    return VauleResponse(request_id=req.request_id, status="success", value=current)

# on_off_query
@dispatcher.register("on_off_query", OnOffQueryRequest, tier=Tier.L0)
async def handle(req: OnOffQueryRequest) -> BaseResponse:
    psu = SCPI_PowerSupply()
    if not psu.is_connected:
        return _device_not_connected(req)
    status = await psu.get_on_off()
    logger.info(f"Status query command: {status}")
    return VauleResponse(request_id=req.request_id, status="success", value=status)

@dispatcher.register("device_id_query", DeviceIdQueryRequest, tier=Tier.L0)
async def handle(req: DeviceIdQueryRequest) -> BaseResponse:
    psu = SCPI_PowerSupply()
    if not psu.is_connected:
        return _device_not_connected(req)
    device_id = await psu.get_identifier()
    logger.info(f"Device ID query command: {device_id}")
    return VauleResponse(request_id=req.request_id, status="success", value=device_id)
