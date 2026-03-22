import logging
import uuid
from typing import Literal, Annotated, Union

from pydantic import TypeAdapter, BaseModel, Field, Tag
# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 基础请求模型
class BaseRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="唯一请求ID")
    timestamp: float = Field(default_factory=lambda: __import__('time').time())

class EchoRequest(BaseRequest):
    """
    Echo 请求模型
    用于测试，返回相同的消息
    """
    type: Literal["echo"] = "echo"
    message: str


# 具体请求类型 - 使用 Literal 作为鉴别器
class LoginRequest(BaseRequest):
    type: Literal["login"] = "login"
    username: str
    password: str  # 实际应使用 SecretStr

class LogoutRequest(BaseRequest):
    type: Literal["logout"] = "logout"
    session_token: str


class OpenDeviceRequest(BaseRequest):
    type: Literal["open_device"] = "open_device"
    # device_id: str
    serial_number: str
    baud_rate: int = Field(default=115200)

class CloseDeviceRequest(BaseRequest):
    type: Literal["close_device"] = "close_device"
    device_id: str


class VoltageQueryRequest(BaseRequest):
    type: Literal["voltage_query"] = "voltage_query"
    cache: bool = Field(default=False)

class CurrentQueryRequest(BaseRequest):
    type: Literal["current_query"] = "current_query"
    cache: bool = Field(default=False)

class StatusQueryRequest(BaseRequest):
    type: Literal["output_query"] = "output_query"
    cache: bool = Field(default=False)

class SettingQueryRequest(BaseRequest):
    type: Literal["setting_query"] = "setting_query"
    cache: bool = Field(default=True)

# 设置请求
class SetVoltageRequest(BaseRequest):
    type: Literal["set_voltage"] = "set_voltage"
    value: float
    unit: Literal["V", "mV"] = "V"

class SetCurrentRequest(BaseRequest):
    type: Literal["set_current"] = "set_current"
    value: float
    unit: Literal["A", "mA"] = "A"

class SetMaxCurrentRequest(BaseRequest):
    type: Literal["set_max_current"] = "set_max_current"
    value: float
    unit: Literal["A", "mA"] = "A"

class SetMaxVoltageRequest(BaseRequest):
    type: Literal["set_max_voltage"] = "set_max_voltage"
    value: float
    unit: Literal["V", "mV"] = "V"

class SetOutputRequest(BaseRequest):
    type: Literal["set_output"] = "set_output"
    value: bool


# 联合类型 - Pydantic 自动根据 type 字段反序列化
RequestUnion = Union[
    Annotated[LoginRequest, Tag("login")],
    Annotated[LogoutRequest, Tag("logout")],

    Annotated[EchoRequest, Tag("echo")],

    Annotated[OpenDeviceRequest, Tag("open_device")], 
    Annotated[CloseDeviceRequest, Tag("close_device")],

    Annotated[VoltageQueryRequest, Tag("voltage_query")],
    Annotated[CurrentQueryRequest, Tag("current_query")],
    Annotated[StatusQueryRequest, Tag("output_query")],
    Annotated[SettingQueryRequest, Tag("setting_query")],

    Annotated[SetVoltageRequest, Tag("set_voltage")],
    Annotated[SetCurrentRequest, Tag("set_current")],

]


#############

class BaseResponse(BaseModel):
    """基础响应模型"""
    status: Literal["success", "error"] = "success"
    message: str = ""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="唯一请求ID")
    timestamp: float = Field(default_factory=lambda: __import__('time').time())

class VauleResponse(BaseResponse):
    """带值的响应模型"""
    value: Union[float, int, bool]

# schema = RequestUnion.model_json_schema()
# logger.info("Schema 生成成功，深度正常")
# request_type_adpter = TypeAdapter(RequestUnion)

# 或者使用 Tag（Pydantic v2 更灵活的方式）
""" RequestUnionV2 = Union[
    Annotated[LoginRequest, Tag("login")],
    Annotated[LogoutRequest, Tag("logout")],
    Annotated[DataQueryRequest, Tag("data_query")],
    Annotated[DataUpdateRequest, Tag("data_update")],
] """


