
import logging

import asyncio

from server.dispatcher import dispatcher
from server.protocal.protocal import (
    BaseRequest, 
    BaseResponse, 
    LoginRequest, 
    LogoutRequest, 
    OpenDeviceRequest, 
    CloseDeviceRequest, 
    SetVoltageRequest, 
    SetCurrentRequest, 
    SetMaxVoltageRequest, 
    SetMaxCurrentRequest, 
    SetOnOffRequest,
    StatusQueryRequest, 
    VoltageQueryRequest, 
    CurrentQueryRequest, 
    SettingQueryRequest,
    DeviceIdQueryRequest,
)


class PowerSupplyModel():

    def __init__(self):
        pass
    
    async def connect(self, port, baudrate = 115200) -> bool:

        open_device = OpenDeviceRequest(serial_number=port, baud_rate=baudrate)
        rsp = await dispatcher.dispatch(open_device.model_dump_json().encode())
        if rsp.status == "success":
            return True
        else:
            return False

    async def close(self) -> None:
        close_device = CloseDeviceRequest(device_id='')
        rsp = await dispatcher.dispatch(close_device.model_dump_json().encode())

    async def set_voltage(self, voltage: float) -> None:
        set_voltage = SetVoltageRequest(value=voltage)
        rsp = await dispatcher.dispatch(set_voltage.model_dump_json().encode())
    
    async def set_on_off(self, value: bool) -> None:
        set_on_off = SetOnOffRequest(value=value)
        rsp = await dispatcher.dispatch(set_on_off.model_dump_json().encode())

    async def get_voltage(self) -> float:
        voltage_query = VoltageQueryRequest()
        rsp = await dispatcher.dispatch(voltage_query.model_dump_json().encode())
        return rsp.value

    async def get_current(self) -> float:
        current_query = CurrentQueryRequest()
        rsp = await dispatcher.dispatch(current_query.model_dump_json().encode())
        return rsp.value
    
    async def get_device_id(self) -> str:
        status_query = DeviceIdQueryRequest()
        rsp = await dispatcher.dispatch(status_query.model_dump_json().encode())
        return rsp.value
    