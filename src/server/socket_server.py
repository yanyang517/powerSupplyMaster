import asyncio
import json
import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from construct import Struct, Int32ub, Bytes, this
from .command_handle_base import CommandHandler, COMMAND_REGISTRY
from .request_handles import *
from pydantic import ValidationError
from .dispatcher import dispatcher

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



class SocketServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8888):
        self.host = host
        self.port = port
        self.dispatcher = dispatcher
    
    async def read_exact(self, reader: asyncio.StreamReader, n: int) -> bytes:
        """Read exactly n bytes from the stream"""
        data = b''
        while len(data) < n:
            chunk = await reader.read(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed while reading")
            data += chunk
        return data
    
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
            
            logger.debug(f"Message length: {message_length} bytes")
            
            # Read the payload based on the parsed length
            payload_bytes = await self.read_exact(reader, message_length)
            
            # Decode and parse JSON
            message_json = payload_bytes.decode('utf-8')
            # data = json.loads(message_json)
            
            return message_json
            
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
    async def handle_client(
        self, 
        reader: asyncio.StreamReader, 
        writer: asyncio.StreamWriter
    ):
        addr = writer.get_extra_info('peername')
        logger.info(f"Client connected: {addr}")
        
        try:
            while True:
                # Parse incoming message using construct
                data = await self.parse_message(reader)
                logger.info(f"Received from {addr}: {data}")
                if not data:
                    break
                
                try:
                    # Pydantic 验证 + 业务分发
                    response:BaseModel = await self.dispatcher.dispatch(data)
                    logger.info(f"response: {response}")
                    response_json = response.model_dump_json()
                    logger.info(f"Sending to {addr}: {response_json}")
                    
                except ValidationError as e:
                    error_response = {
                        "error": "validation_error",
                        "details": e.errors(include_url=False)
                    }
                    response_json = json.dumps(error_response)
                    
                except Exception as e:
                    error_response = {
                        "error": "internal_error",
                        "message": str(e)
                    }
                    response_json = json.dumps(error_response)
                
                # 发送响应
                response_data = await self.build_response(response_json)
                writer.write(response_data)
                await writer.drain()
                
        except asyncio.CancelledError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            print(f"Client disconnected: {addr}")
    
    async def start(self):
        server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        print(f"Server started on {self.host}:{self.port}")
        async with server:
            await server.serve_forever()

async def server_main():
    server = SocketServer()
    await server.start()
    
# 运行
if __name__ == "__main__":
    asyncio.run(server_main())