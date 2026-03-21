
import logging
import json

from typing import Callable, Awaitable, TypeVar, cast
from pydantic import BaseModel, ValidationError, TypeAdapter
from .protocal.protocal import RequestUnion, BaseRequest

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


request_type_adpter = TypeAdapter(RequestUnion)

T = TypeVar('T', bound=BaseModel)


class RequestDispatcher:
    """请求分发器 - 类型安全的路由系统"""
    
    def __init__(self):
        # 处理器注册表：type -> handler
        self._handlers: dict[str, Callable[[BaseRequest], Awaitable[BaseModel]]] = {}
        # 请求模型注册表（用于日志/监控）
        self._request_models: dict[str, type[BaseRequest]] = {}
    
    def get_instance() -> "RequestDispatcher":
        if not hasattr(RequestDispatcher, "_instance"):
            RequestDispatcher._instance = RequestDispatcher()
        return RequestDispatcher._instance
    
    def register(
        self, 
        request_type: str,
        request_model: type[T]
    ) -> Callable[[Callable[[T], Awaitable[BaseModel]]], Callable[[T], Awaitable[BaseModel]]]:
        """装饰器注册处理器"""
        
        def decorator(
            handler: Callable[[T], Awaitable[BaseModel]]
        ) -> Callable[[T], Awaitable[BaseModel]]:
            async def wrapped(raw_request: BaseRequest) -> BaseModel:
                # 类型转换并调用
                typed_request = cast(request_model, raw_request)
                return await handler(typed_request)
            
            self._handlers[request_type] = wrapped
            self._request_models[request_type] = request_model
            return handler
        
        return decorator
    
    async def dispatch(self, raw_data: str) -> BaseModel:
        """解析并分发请求"""
        
        logger.info(f"Received raw data: {raw_data}")
        # 第一步：解析为联合类型（自动根据 type 字段选择具体模型）
        try:
            # if isinstance(raw_data, bytes):
            #     raw_data = raw_data.decode('utf-8').rstrip('\n')
            
            # 使用 discriminator 自动路由到正确模型
            # logger.info(f"Received request: {raw_data}")
            # logger.info(json.loads(raw_data))  # 预检查

            request = request_type_adpter.validate_json(raw_data)
            logger.info(f"Parsed request: {request}")
        except ValidationError as e:
            logger.error(f"Invalid request format: {e}")
            raise ValueError(f"Invalid request format: {e}")
        
        # 获取处理器
        handler = self._handlers.get(request.type)
        if not handler:
            raise ValueError(f"Unknown request type: {request.type}")
        
        # 执行
        try:
            resp = await handler(request)
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            raise e
        logger.info(f"Response: {resp}")
        return resp
    
dispatcher= RequestDispatcher.get_instance()
