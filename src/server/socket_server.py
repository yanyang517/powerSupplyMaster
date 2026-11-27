import asyncio
import json
import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from construct import Struct, Int32ub, Bytes, this
from .command_handle_base import CommandHandler, COMMAND_REGISTRY
from .request_handles import *
from .runtime_config import SERVER_HOST, SERVER_PORT, is_loopback_host
from pydantic import ValidationError
from .dispatcher import dispatcher
from .session import hub

logger = logging.getLogger(__name__)

# Length-prefixed JSON requests are small. Bound them before touching the payload
# so an untrusted peer cannot force a large allocation or occupy a slot forever.
MAX_FRAME_BYTES = 64 * 1024
DEFAULT_READ_TIMEOUT = 30.0
DEFAULT_IDLE_TIMEOUT = 300.0
# Must exceed the 60-second user approval window used by login admission.
DEFAULT_DISPATCH_TIMEOUT = 90.0
DEFAULT_WRITE_TIMEOUT = 10.0
DEFAULT_CLOSE_TIMEOUT = 2.0
DEFAULT_MAX_CONNECTIONS = 32


class FrameTooLargeError(ValueError):
    """The peer advertised a frame larger than the server accepts."""


class _SocketTimeout(TimeoutError):
    """Distinguish an inner operation timeout from an outer deadline."""


def _classify_bound_addresses(server) -> tuple[list[str], bool]:
    """Format and classify every actual socket address, failing closed."""
    addresses = []
    sockets = server.sockets or ()
    loopback_only = bool(sockets)
    for sock in sockets:
        try:
            host, port = sock.getsockname()[:2]
            host = str(host)
        except Exception:
            # A socket whose address cannot be read is not proof of loopback.
            loopback_only = False
            addresses.append("<unverifiable>")
            continue
        if not is_loopback_host(host):
            loopback_only = False
        addresses.append(f"[{host}]:{port}" if ":" in host else f"{host}:{port}")
    return addresses, loopback_only


def _bound_addresses(server) -> list[str]:
    """Format addresses reported by the sockets, not the requested host/port."""
    return _classify_bound_addresses(server)[0]


# Construct protocol definition for length-prefixed messages
# Format: 4-byte big-endian length + JSON payload
MessageProtocol = Struct(
    "length" / Int32ub,  # 4-byte big-endian unsigned integer
    "payload" / Bytes(this.length)  # Variable-length payload based on length field
)



class SocketServer:
    def __init__(
        self,
        host: str = SERVER_HOST,
        port: int = SERVER_PORT,
        *,
        max_frame_bytes: int = MAX_FRAME_BYTES,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        dispatch_timeout: float = DEFAULT_DISPATCH_TIMEOUT,
        write_timeout: float = DEFAULT_WRITE_TIMEOUT,
        close_timeout: float = DEFAULT_CLOSE_TIMEOUT,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
    ):
        if max_frame_bytes <= 0 or max_connections <= 0:
            raise ValueError("max_frame_bytes and max_connections must be positive")
        timeouts = (read_timeout, idle_timeout, dispatch_timeout,
                    write_timeout, close_timeout)
        if any(timeout <= 0 for timeout in timeouts):
            raise ValueError("timeouts must be positive")
        self.host = host
        self.port = port
        self.dispatcher = dispatcher
        self.max_frame_bytes = max_frame_bytes
        self.read_timeout = read_timeout
        self.idle_timeout = idle_timeout
        self.dispatch_timeout = dispatch_timeout
        self.write_timeout = write_timeout
        self.close_timeout = close_timeout
        self.max_connections = max_connections
        # Callbacks run synchronously until their first await, so admission is
        # atomic on the event-loop thread and never creates an over-cap session.
        self._active_connections = 0

    async def _timed(self, awaitable, timeout: float, operation: str):
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout)
        except _SocketTimeout:
            raise
        except asyncio.TimeoutError as e:
            raise _SocketTimeout(f"{operation} timed out after {timeout:g}s") from e

    async def read_exact(self, reader: asyncio.StreamReader, n: int) -> bytes:
        """Read exactly n bytes, bounding each individual read operation."""
        data = bytearray()
        while len(data) < n:
            chunk = await self._timed(
                reader.read(n - len(data)), self.read_timeout, "socket read"
            )
            if not chunk:
                raise ConnectionError("Connection closed while reading")
            data.extend(chunk)
        return bytes(data)
    
    async def parse_message(self, reader: asyncio.StreamReader) -> str:
        """
        Parse incoming message using construct library
        
        Reads 4-byte length prefix followed by JSON payload
        Returns parsed JSON data as dictionary
        """
        try:
            # Read the length prefix (4 bytes)
            length_bytes = await self.read_exact(reader, 4)
            
            # Parse length using construct
            length_struct = Struct("length" / Int32ub)
            parsed_length = length_struct.parse(length_bytes)
            message_length = parsed_length.length
            if message_length > self.max_frame_bytes:
                # Do not allocate or consume a payload advertised as oversized.
                raise FrameTooLargeError(
                    f"frame length {message_length} exceeds limit {self.max_frame_bytes}"
                )

            logger.debug(f"Message length: {message_length} bytes")
            
            # Read the payload based on the parsed length
            payload_bytes = await self.read_exact(reader, message_length)
            
            # Decode and parse JSON
            message_json = payload_bytes.decode('utf-8')
            # data = json.loads(message_json)
            
            return message_json
            
        except (ConnectionError, TimeoutError, FrameTooLargeError):
            raise
        except Exception as e:
            logger.error(f"Failed to parse message: {e}", exc_info=True)
            raise
    
    async def build_response(self, response_json) -> bytes:
        """
        Build response message with length prefix using construct
        
        Args:
            response_data: Dictionary to serialize as JSON
            
        Returns:
            Bytes with format: 4-byte length + JSON payload
        """
        # Serialize response to JSON
        response_bytes = response_json.encode('utf-8')
        
        # Build message with length prefix using construct
        message = MessageProtocol.build({
            'length': len(response_bytes),
            'payload': response_bytes
        })
        
        return message
    async def _close_writer(self, writer: asyncio.StreamWriter, peer: str) -> None:
        try:
            writer.close()
            await self._timed(writer.wait_closed(), self.close_timeout, "socket close")
        except Exception as e:
            # A killed peer can reset close/wait_closed on Windows Proactor.
            logger.debug("closing socket of %s: %s", peer, e)

    async def _reject_connection(self, writer: asyncio.StreamWriter, peer: str) -> None:
        logger.warning(
            "Rejecting client %s: connection limit reached (%d active)",
            peer, self._active_connections,
        )
        try:
            response = json.dumps({"error": "connection_limit_exceeded"})
            writer.write(await self.build_response(response))
            await self._timed(writer.drain(), self.write_timeout, "rejection write")
        except Exception as e:
            logger.debug("could not send rejection to %s: %s", peer, e)
        finally:
            await self._close_writer(writer, peer)

    async def handle_client(
        self, 
        reader: asyncio.StreamReader, 
        writer: asyncio.StreamWriter
    ):
        addr = writer.get_extra_info('peername')
        peer = f"{addr[0]}:{addr[1]}" if addr else "unknown"
        if self._active_connections >= self.max_connections:
            await self._reject_connection(writer, peer)
            return

        self._active_connections += 1
        session = None
        logger.info("Client connected: %s (active=%d)", addr, self._active_connections)
        try:
            session = hub.open(peer)
            dispatch_timed_out = False
            while True:
                # Bound time spent waiting for a complete frame as well as each read.
                data = await self._timed(
                    self.parse_message(reader), self.idle_timeout, "idle read"
                )
                logger.info(f"Received from {addr}: {data}")
                if not data:
                    break
                
                try:
                    # Pydantic 验证 + 授权判定 + 业务分发
                    response:BaseModel = await self._timed(
                        self.dispatcher.dispatch(data, session),
                        self.dispatch_timeout,
                        "request dispatch",
                    )
                    logger.info(f"response: {response}")
                    response_json = response.model_dump_json()
                    logger.info(f"Sending to {addr}: {response_json}")
                    
                except ValidationError as e:
                    error_response = {
                        "error": "validation_error",
                        "details": e.errors(include_url=False)
                    }
                    response_json = json.dumps(error_response)

                except TimeoutError:
                    logger.warning("Request dispatch timed out for %s", peer)
                    dispatch_timed_out = True
                    response_json = json.dumps({
                        "error": "dispatch_timeout",
                        "message": "request processing timed out",
                    })
                    
                except Exception as e:
                    error_response = {
                        "error": "internal_error",
                        "message": str(e)
                    }
                    response_json = json.dumps(error_response)
                
                # 发送响应
                response_data = await self.build_response(response_json)
                writer.write(response_data)
                await self._timed(writer.drain(), self.write_timeout, "response write")

                if dispatch_timed_out:
                    # The handler may have reached the device before cancellation.
                    # Never reuse a session whose request outcome is uncertain.
                    logger.warning("Closing session %s after dispatch timeout", session.session_id)
                    break

                if session.close_after_response:
                    logger.info(f"Closing session {session.session_id}: admission refused")
                    break
                
        except asyncio.CancelledError:
            # Cleanup runs in finally; callers must still observe cancellation.
            logger.debug("Client handler cancelled: %s", peer)
            raise
        except FrameTooLargeError as e:
            logger.warning("Rejecting oversized frame from %s: %s", peer, e)
        except (TimeoutError, ConnectionError) as e:
            # EOF is normal for short-lived MCP clients; stalls are worth a warning.
            log = logger.info if isinstance(e, ConnectionError) else logger.warning
            log("Client disconnected: %s (%s)", peer, e)
        finally:
            # 会话随连接结束丢弃；控制权不在此处释放（见设计 D1）。
            if session is not None:
                hub.close(session)
            self._active_connections -= 1
            await self._close_writer(writer, peer)

    async def start(self):
        server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        addresses, loopback_only = _classify_bound_addresses(server)
        if addresses:
            logger.info("Server started on %s", ", ".join(addresses))
        else:
            logger.warning(
                "Server started without bound socket addresses (requested %s:%s)",
                self.host,
                self.port,
            )
        if not loopback_only:
            bound = ", ".join(addresses) if addresses else "<no bound addresses>"
            logger.warning(
                "control server actual bound addresses %s are not all known to be loopback-only. "
                "This build has NO authentication, token, or mTLS: client_id is self-declared, "
                "and the allow-list, tiers, and control lease provide authorization only. "
                "Use a non-loopback bind ONLY on an isolated, trusted intranet/experimental "
                "network. For any other network, keep the loopback default (omit --listen or "
                "use --listen 127.0.0.1) and connect through a trusted tunnel instead.",
                bound,
            )
        async with server:
            await server.serve_forever()


async def server_main(host: str = SERVER_HOST):
    server = SocketServer(host)
    await server.start()


# 运行
if __name__ == "__main__":
    asyncio.run(server_main())
