"""SocketServer 协议客户端：4 字节大端长度前缀 + JSON。

单条长连接、惰性建连、断连后下一次调用前透明重连重试一次（design D7）。
每条新连接建立后先 login：控制权按 `client_id` 存续，所以重连后重新登录即可拿回租约。
"""
import asyncio
import json
import logging
import struct
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 默认端口与 powerSupplyMaster 应用侧 server/runtime_config.py 的 SERVER_PORT 一致；
# 两侧一致性由主仓库 src/mcp_server/test_bridge.py 的线上协议回归兜底（design D3）。
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18888


class PsuUnavailableError(Exception):
    """无法与 SocketServer 建立或维持连接（app 未运行 / 连接中断）"""


class PsuProtocolError(Exception):
    """响应帧无法解析或 request_id 不匹配"""


class PsuAccessDeniedError(Exception):
    """登录被服务端拒绝（未登记且无人批准、等级不足、无界面模式下的准入限制）"""


class PsuClient:
    """协议客户端；默认身份即 MCP 桥本身。

    默认申请 L2 而不是 L1：桥的 set_output 走 set_on_off，按归级属 L2，
    以 L1 登录会让这个工具永远被拒。串口通断不在 L2 之内，仍只在 UI。
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 5.0,
                 client_id: str = "mcp-bridge", tier: str = "L2"):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.client_id = client_id
        self.tier = tier
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    async def _ensure_connection(self) -> None:
        if self._writer is None:
            self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
            await self._login()

    async def _login(self) -> None:
        """在建连的同一把锁内完成登录，避免业务请求抢在身份建立之前发出。"""
        try:
            response = await self._exchange({
                "type": "login",
                "request_id": uuid.uuid4().hex[:8],
                "client_id": self.client_id,
                "tier": self.tier,
            })
        except PsuProtocolError as e:
            raise PsuAccessDeniedError(f"login handshake failed: {e}")
        if response.get("status") != "success":
            raise PsuAccessDeniedError(
                f"login refused for {self.client_id}: {response.get('message') or response}"
            )

    async def _drop_connection(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None

    async def _read_exact(self, n: int) -> bytes:
        data = await self._reader.readexactly(n)
        return data

    async def _roundtrip(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self._ensure_connection()
        return await self._exchange(payload)

    async def _exchange(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request_id = payload["request_id"]
        body = json.dumps(payload).encode("utf-8")
        self._writer.write(struct.pack(">I", len(body)) + body)
        await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)

        header = await asyncio.wait_for(self._read_exact(4), timeout=self.timeout)
        (length,) = struct.unpack(">I", header)
        raw = await asyncio.wait_for(self._read_exact(length), timeout=self.timeout)
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise PsuProtocolError(f"unparsable response: {e}")
        rid = response.get("request_id")
        if rid is None and "error" in response:
            # server 异常兜底路径的 {"error": ...} 帧，不带 request_id，交由上层翻译
            return response
        if rid != request_id:
            raise PsuProtocolError(
                f"request_id mismatch: sent {request_id}, got {rid}"
            )
        return response

    async def request(self, request_type: str, **fields: Any) -> Dict[str, Any]:
        """发送一条协议请求并返回解析后的响应 dict。

        传输层失败时丢弃连接、重连并透明重试一次，仍失败则抛 PsuUnavailableError。
        """
        payload = {"type": request_type, "request_id": uuid.uuid4().hex[:8], **fields}
        last_error: Optional[Exception] = None
        async with self._lock:
            for attempt in (1, 2):
                try:
                    return await self._roundtrip(payload)
                except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, PsuProtocolError) as e:
                    last_error = e
                    logger.warning(f"attempt {attempt} failed for {request_type}: {e}")
                    await self._drop_connection()
        raise PsuUnavailableError(str(last_error))
