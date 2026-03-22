
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
    StatusQueryRequest, 
    VoltageQueryRequest, 
    CurrentQueryRequest, 
    SettingQueryRequest,
)


class PowerSupplyModel():

    def __init__(self):
        pass
    
    async def connect(self, port, baudrate = 115200) -> None:

        open_device = OpenDeviceRequest(serial_number=port, baud_rate=baudrate)
        rsp = await dispatcher.dispatch(open_device.model_dump_json().encode())

    async def close(self) -> None:
        close_device = CloseDeviceRequest()
        rsp = await dispatcher.dispatch(close_device.model_dump_json().encode())

    async def set_voltage(self, voltage: float) -> None:
        set_voltage = SetVoltageRequest(value=voltage)
        rsp = await dispatcher.dispatch(set_voltage.model_dump_json().encode())

    async def get_voltage(self) -> float:
        voltage_query = VoltageQueryRequest()
        rsp = await dispatcher.dispatch(voltage_query.model_dump_json().encode())
        return rsp.value

    async def get_current(self) -> float:
        current_query = CurrentQueryRequest()
        rsp = await dispatcher.dispatch(current_query.model_dump_json().encode())
        return rsp.value