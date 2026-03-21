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

# class DataQueryRequest(BaseRequest):
#     type: Literal["data_query"] = "data_query"
#     query: str
#     limit: int = Field(default=100, le=1000)

# class DataUpdateRequest(BaseRequest):
#     type: Literal["data_update"] = "data_update"
#     record_id: str
#     changes: dict

class OpenDeviceRequest(BaseRequest):
    type: Literal["open_device"] = "open_device"
    # device_id: str
    serial_number: str
    baud_rate: int = Field(default=115200)

class CloseDeviceRequest(BaseRequest):
    type: Literal["close_device"] = "close_device"
    device_id: str


class DataQueryRequest(BaseRequest):
    type: Literal["data_query"] = "data_query"
    query: str
    limit: int = Field(default=100, le=1000)

class DataUpdateRequest(BaseRequest):
    type: Literal["data_update"] = "data_update"
    record_id: str
    changes: dict

# 联合类型 - Pydantic 自动根据 type 字段反序列化
RequestUnion = Union[
    Annotated[LoginRequest, Tag("login")],
    Annotated[LogoutRequest, Tag("logout")],
    Annotated[DataQueryRequest, Tag("data_query")],
    Annotated[DataUpdateRequest, Tag("data_update")],

    Annotated[EchoRequest, Tag("echo")],
    Annotated[OpenDeviceRequest, Tag("open_device")]
    , Annotated[CloseDeviceRequest, Tag("close_device")]

]


#############

class BaseResponse(BaseModel):
    """基础响应模型"""
    status: Literal["success", "error"] = "success"
    message: str = ""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="唯一请求ID")
    timestamp: float = Field(default_factory=lambda: __import__('time').time())


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


