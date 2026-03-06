import asyncio
import json
import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from construct import Struct, Int32ub, Bytes, this

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Construct protocol definition for length-prefixed messages
# Format: 4-byte big-endian length + JSON payload
MessageProtocol = Struct(
    "length" / Int32ub,  # 4-byte big-endian unsigned integer
    "payload" / Bytes(this.length)  # Variable-length payload based on length field
)


class CommandHandler(ABC):
    """Abstract base class for command handlers"""
    
    @abstractmethod
    async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
        """Handle command and return response"""
        pass


class SocketServer:
    """Async socket server using asyncio with construct-based protocol parsing"""
    
    def __init__(self, host: str = '0.0.0.0', port: int = 8888):
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.clients = set()
        self.command_handlers: Dict[str, CommandHandler] = {}
        
    def register_handler(self, cmd: str, handler: CommandHandler):
        """Register a command handler"""
        self.command_handlers[cmd] = handler
        logger.info(f"Registered handler for command: {cmd}")
    
    async def read_exact(self, reader: asyncio.StreamReader, n: int) -> bytes:
        """Read exactly n bytes from the stream"""
        data = b''
        while len(data) < n:
            chunk = await reader.read(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed while reading")
            data += chunk
        return data
    
    async def parse_message(self, reader: asyncio.StreamReader) -> Dict[str, Any]:
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
            
            logger.debug(f"Message length: {message_length} bytes")
            
            # Read the payload based on the parsed length
            payload_bytes = await self.read_exact(reader, message_length)
            
            # Decode and parse JSON
            message_json = payload_bytes.decode('utf-8')
            data = json.loads(message_json)
            
            return data
            
        except Exception as e:
            logger.error(f"Failed to parse message: {e}", exc_info=True)
            raise
    
    async def build_response(self, response_data: Dict[str, Any]) -> bytes:
        """
        Build response message with length prefix using construct
        
        Args:
            response_data: Dictionary to serialize as JSON
            
        Returns:
            Bytes with format: 4-byte length + JSON payload
        """
        # Serialize response to JSON
        response_json = json.dumps(response_data)
        response_bytes = response_json.encode('utf-8')
        
        # Build message with length prefix using construct
        message = MessageProtocol.build({
            'length': len(response_bytes),
            'payload': response_bytes
        })
        
        return message
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle individual client connections"""
        addr = writer.get_extra_info('peername')
        logger.info(f"New connection from {addr}")
        
        self.clients.add(writer)
        
        try:
            while True:
                try:
                    # Parse incoming message using construct
                    data = await self.parse_message(reader)
                    
                    cmd = data.get('cmd', 'unknown')
                    logger.info(f"Received from {addr}: cmd='{cmd}'")
                    
                    # Process the message and get response
                    response = await self.process_message(data, addr)
                    
                    # Build and send response using construct
                    response_message = await self.build_response(response)
                    writer.write(response_message)
                    await writer.drain()
                    
                except ConnectionError as e:
                    logger.info(f"Client {addr} disconnected: {e}")
                    break
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from {addr}: {e}")
                    error_response = {
                        "status": "error",
                        "message": f"Invalid JSON: {str(e)}"
                    }
                    await self.send_error_response(writer, error_response)
                    break
                    
                except asyncio.IncompleteReadError:
                    logger.info(f"Client {addr} closed connection unexpectedly")
                    break
                
        except asyncio.CancelledError:
            logger.info(f"Connection to {addr} cancelled")
        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}", exc_info=True)
        finally:
            # Clean up
            self.clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
            logger.info(f"Connection closed with {addr}")
    
    async def send_error_response(self, writer: asyncio.StreamWriter, error_response: dict):
        """Send error response to client"""
        try:
            response_message = await self.build_response(error_response)
            writer.write(response_message)
            await writer.drain()
        except Exception as e:
            logger.error(f"Error sending error response: {e}")
    
    async def process_message(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
        """
        Process incoming JSON message and route to appropriate handler based on cmd
        
        Expected format:
        {
            "cmd": "command_name",
            ... other payload data
        }
        
        Returns:
        {
            "status": "success" | "error",
            "data": ... (response data),
            "message": ... (optional error message)
        }
        """
        try:
            # Extract command
            cmd = data.get('cmd')
            
            if not cmd:
                logger.warning(f"No 'cmd' field in message from {addr}")
                return {
                    "status": "error",
                    "message": "Missing 'cmd' field in request"
                }
            
            logger.debug(f"Processing command '{cmd}' from {addr}")
            
            # Route to appropriate handler based on cmd
            if cmd in self.command_handlers:
                handler = self.command_handlers[cmd]
                try:
                    response = await handler.handle(data, addr)
                    # Ensure response has status field
                    if "status" not in response:
                        response["status"] = "success"
                    return response
                except Exception as e:
                    logger.error(f"Handler error for cmd '{cmd}': {e}", exc_info=True)
                    return {
                        "status": "error",
                        "message": f"Handler error: {str(e)}"
                    }
            else:
                logger.warning(f"Unknown command '{cmd}' from {addr}")
                return {
                    "status": "error",
                    "message": f"Unknown command: {cmd}"
                }
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Internal error: {str(e)}"
            }
    
    async def start(self):
        """Start the socket server"""
        self.server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port
        )
        
        addr = self.server.sockets[0].getsockname()
        logger.info(f"Server started on {addr[0]}:{addr[1]}")
        
        async with self.server:
            await self.server.serve_forever()
    
    async def stop(self):
        """Stop the socket server"""
        logger.info("Stopping server...")
        
        # Close all client connections
        for writer in self.clients:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.error(f"Error closing client connection: {e}")
        
        self.clients.clear()
        
        # Stop the server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Server stopped")
    
    def get_connected_clients(self) -> int:
        """Get the number of connected clients"""
        return len(self.clients)


# Example command handlers
class EchoHandler(CommandHandler):
    """Simple echo command handler"""
    
    async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
        message = data.get('message', '')
        logger.info(f"Echo command: {message}")
        return {
            "status": "success",
            "data": {
                "echo": message,
                "timestamp": asyncio.get_event_loop().time()
            }
        }


class PingHandler(CommandHandler):
    """Ping command handler"""
    
    async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
        logger.info("Ping command received")
        return {
            "status": "success",
            "data": {
                "pong": True,
                "server_time": asyncio.get_event_loop().time()
            }
        }


class StatusHandler(CommandHandler):
    """Server status command handler"""
    
    async def handle(self, data: Dict[str, Any], addr: tuple) -> Dict[str, Any]:
        logger.info("Status command received")
        return {
            "status": "success",
            "data": {
                "server_status": "running",
                "connected_clients": len(addr),
                "uptime": "N/A"
            }
        }


async def main():
    """Main entry point with example command handlers"""
    server = SocketServer(host='0.0.0.0', port=8888)
    
    # Register example command handlers
    server.register_handler('echo', EchoHandler())
    server.register_handler('ping', PingHandler())
    server.register_handler('status', StatusHandler())
    
    logger.info("Registered commands: echo, ping, status")
    logger.info("Using construct library for protocol parsing")
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    finally:
        await server.stop()


if __name__ == '__main__':
    asyncio.run(main())