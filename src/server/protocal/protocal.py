import logging
import uuid
from typing import Literal, Annotated, Union

from pydantic import TypeAdapter, BaseModel, Field, Tag, field_validator
from ..runtime_config import MAX_CLIENT_ID_LENGTH
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
    """登录即准入申请：client_id 由客户端自报，登记表是准入名单而非凭据库。"""
    type: Literal["login"] = "login"
    client_id: str = Field(min_length=1, max_length=MAX_CLIENT_ID_LENGTH)
    tier: Literal["L0", "L1", "L2"] = "L0"

    @field_validator("client_id", mode="before")
    @classmethod
    def trim_client_id(cls, value):
        return value.strip() if isinstance(value, str) else value


class LogoutRequest(BaseRequest):
    type: Literal["logout"] = "logout"


class LeaseStatusRequest(BaseRequest):
    """谁正在控制这台电源。"""
    type: Literal["lease_status"] = "lease_status"


class ListClientsRequest(BaseRequest):
    """当前有哪些连接（含未登录）。"""
    type: Literal["list_clients"] = "list_clients"


class ReleaseLeaseRequest(BaseRequest):
    type: Literal["release_lease"] = "release_lease"


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

class OnOffQueryRequest(BaseRequest):
    type: Literal["on_off_query"] = "on_off_query"
    cache: bool = Field(default=False)

class SettingQueryRequest(BaseRequest):
    type: Literal["setting_query"] = "setting_query"
    cache: bool = Field(default=True)

class DeviceIdQueryRequest(BaseRequest):
    type: Literal["device_id_query"] = "device_id_query"
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

class SetOnOffRequest(BaseRequest):
    type: Literal["set_on_off"] = "set_on_off"
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
    Annotated[OnOffQueryRequest, Tag("on_off_query")],

    Annotated[SetVoltageRequest, Tag("set_voltage")],
    Annotated[SetCurrentRequest, Tag("set_current")],
    Annotated[SetOnOffRequest, Tag("set_on_off")],

    Annotated[DeviceIdQueryRequest, Tag("device_id_query")],

    Annotated[LeaseStatusRequest, Tag("lease_status")],
    Annotated[ListClientsRequest, Tag("list_clients")],
    Annotated[ReleaseLeaseRequest, Tag("release_lease")],

]


#############

class BaseResponse(BaseModel):
    """基础响应模型"""
    status: Literal["success", "error"] = "success"
    message: str = ""
    # 写命令显式声明“尚未写入设备”时，分发器才允许回滚新建预留。
    # 其他错误响应一律视为结果不明并隔离，不能靠 message 文本猜测。
    failure_stage: Literal["pre_write"] | None = None
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="唯一请求ID")
    timestamp: float = Field(default_factory=lambda: __import__('time').time())

class VauleResponse(BaseResponse):
    """带值的响应模型"""
    value: Union[float, int, bool, str]

class SettingError(BaseModel):
    """设置值被运行时安全限值拒绝；字段可供 GUI 与客户端共同判定。"""
    code: Literal["negative", "over_limit", "non_finite", "invalid_limit"]
    setting: Literal["voltage", "current"]
    value: Union[float, str]
    minimum: float
    maximum: Union[float, str]
    unit: Literal["V", "A"]
    message: str

class SettingErrorResponse(BaseResponse):
    """结构化限值错误，同时保留已有 message 契约供 MCP 桥展示。"""
    error: SettingError

class SettingResponse(BaseResponse):
    """setting_query 响应：当前生效的设置类命令限值，外加服务端实例的应用版本。

    version 是必填项：客户端（含 MCP 桥）靠它判断"连的是哪一版上位机"，
    漏填不该静默通过模型校验。
    """
    max_voltage: float
    max_current: float
    version: str = Field(description="服务端运行实例的应用版本号，取自 src/version.py 真源")


class LoginResponse(BaseResponse):
    """登录响应：只表明会话生效等级，不返回任何可复用为凭据的字段。"""
    client_id: str
    tier: str
    reason: str


class LeaseStatusResponse(BaseResponse):
    """控制权状态；holder 为 None 表示无人持有。"""
    holder: str | None = None
    tier: str | None = None
    remaining_seconds: float = 0.0
    held_seconds: float = 0.0
    since_last_write_seconds: float = 0.0
    holder_connected: bool = False


class ListClientsResponse(BaseResponse):
    """连接列表与控制权归属是两份名单，不能混为一份。"""
    clients: list[dict] = Field(default_factory=list)
    lease: dict = Field(default_factory=dict)

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


