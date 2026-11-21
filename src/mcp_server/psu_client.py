"""SocketServer 协议客户端：4 字节大端长度前缀 + JSON。

单条长连接、惰性建连、断连后下一次调用前透明重连重试一次（design D7）。
"""
import asyncio
import json
import logging
import struct
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PsuUnavailableError(Exception):
    """无法与 SocketServer 建立或维持连接（app 未运行 / 连接中断）"""


class PsuProtocolError(Exception):
    """响应帧无法解析或 request_id 不匹配"""


class PsuClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8888, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    async def _ensure_connection(self) -> None:
        if self._writer is None:
            self._reader, self._writer = await asyncio.open_connection(self.host, self.port)

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
        request_id = payload["request_id"]
        body = json.dumps(payload).encode("utf-8")
        await self._ensure_connection()
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
