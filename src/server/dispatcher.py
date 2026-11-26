
import logging

from typing import Callable, Awaitable, TypeVar, cast
from pydantic import BaseModel, ValidationError, TypeAdapter
from .protocal.protocal import RequestUnion, BaseRequest, BaseResponse
from . import access
from .registry import Tier
from .session import Session

logger = logging.getLogger(__name__)


request_type_adpter = TypeAdapter(RequestUnion)

T = TypeVar('T', bound=BaseModel)


class RequestDispatcher:
    """请求分发器 - 类型安全的路由系统"""

    def __init__(self):
        # 处理器注册表：type -> handler
        self._handlers: dict[str, Callable[..., Awaitable[BaseModel]]] = {}
        # 请求模型注册表（用于日志/监控）
        self._request_models: dict[str, type[BaseRequest]] = {}
        # 命令授权等级：未登记的命令无法被调用
        self._tiers: dict[str, Tier] = {}
        # public 命令允许未登录连接调用（仅 echo 探活）
        self._public: set[str] = set()

    def get_instance() -> "RequestDispatcher":
        if not hasattr(RequestDispatcher, "_instance"):
            RequestDispatcher._instance = RequestDispatcher()
        return RequestDispatcher._instance

    def register(
        self,
        request_type: str,
        request_model: type[T],
        *,
        tier: Tier,
        needs_session: bool = False,
        public: bool = False,
    ) -> Callable[..., Awaitable[BaseModel]]:
        """装饰器注册处理器。tier 为必填项：漏声明等级会在导入期直接失败。"""

        def decorator(
            handler: Callable[..., Awaitable[BaseModel]]
        ) -> Callable[..., Awaitable[BaseModel]]:
            async def wrapped(raw_request: BaseRequest, session: Session) -> BaseModel:
                # 类型转换并调用
                typed_request = cast(request_model, raw_request)
                if needs_session:
                    return await handler(typed_request, session)
                return await handler(typed_request)

            self._handlers[request_type] = wrapped
            self._request_models[request_type] = request_model
            self._tiers[request_type] = tier
            if public:
                self._public.add(request_type)
            return handler

        return decorator

    def tier_of(self, request_type: str) -> Tier | None:
        return self._tiers.get(request_type)

    async def dispatch(self, raw_data: str, session: Session) -> BaseModel:
        """解析请求，完成授权判定后才进入业务处理器。"""

        logger.info(f"Received raw data: {raw_data}")
        try:
            request = request_type_adpter.validate_json(raw_data)
            logger.info(f"Parsed request: {request}")
        except ValidationError as e:
            logger.error(f"Invalid request format: {e}")
            raise ValueError(f"Invalid request format: {e}")

        # 获取处理器
        handler = self._handlers.get(request.type)
        if not handler:
            raise ValueError(f"Unknown request type: {request.type}")

        tier = self._tiers[request.type]
        if request.type in self._public:
            decision = access.ALLOW
        else:
            decision = access.evaluate(session, request.type, tier)

        if decision.denied:
            access.audit(session, request.type, tier, decision)
            return BaseResponse(request_id=request.request_id, status="error",
                                message=f"[{decision.reason}] {decision.message}")

        # 执行
        try:
            resp = await handler(request, session)
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            access.audit(session, request.type, tier, access.ALLOW, handler_status="exception")
            raise e

        status = str(getattr(resp, "status", "success"))
        if tier.needs_lease and status == "success":
            access.record_write(session)
        access.audit(session, request.type, tier, access.ALLOW, handler_status=status)
        logger.info(f"Response: {resp}")
        return resp

dispatcher= RequestDispatcher.get_instance()
