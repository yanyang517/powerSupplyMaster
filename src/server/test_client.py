import asyncio
import json
import logging
from construct import Struct, Int32ub, Bytes, this

from protocal.protocal import (
    BaseModel, BaseRequest, #BaseResponse,
    LoginRequest, #LoginResponse, 
    LogoutRequest, #LogoutResponse, 
    DataQueryRequest, #DataQueryResponse
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Construct protocol definition (same as server)
MessageProtocol = Struct(
    "length" / Int32ub,
    "payload" / Bytes(this.length)
)


class JsonSocketClient:
    """JSON protocol socket client with construct-based message parsing"""
    
    def __init__(self, host: str = '127.0.0.1', port: int = 8888):
        self.host = host
        self.port = port
    
    async def build_message(self, payload_json) -> bytes:
        """Build message with length prefix using construct"""
        payload_bytes = payload_json.encode('utf-8')
        
        message = MessageProtocol.build({
            'length': len(payload_bytes),
            'payload': payload_bytes
        })
        
        logger.debug(f"Built message: , size={len(payload_bytes)} bytes")
        return message
    
    async def parse_response(self, reader: asyncio.StreamReader) -> dict:
        """Parse response using construct library"""
        length_bytes = await reader.readexactly(4)
        length_struct = Struct("length" / Int32ub)
        parsed_length = length_struct.parse(length_bytes)
        message_length = parsed_length.length
        
        payload_bytes = await reader.readexactly(message_length)
        response_json = payload_bytes.decode('utf-8')
        response = json.loads(response_json)
        
        return response
    
    async def send_command(self, reader: asyncio.StreamReader, 
                          writer: asyncio.StreamWriter, req) -> dict:
        """Send a command and receive response"""

        message = await self.build_message(req.model_dump_json())
        writer.write(message)
        await writer.drain()
        
        response = await self.parse_response(reader)
        return response
    
    async def run_tests(self):
        """Run comprehensive test commands"""
        try:
            logger.info("=" * 60)
            logger.info("Starting Socket Server Tests")
            logger.info("=" * 60)
            logger.info(f"Connecting to {self.host}:{self.port}...")
            
            reader, writer = await asyncio.open_connection(self.host, self.port)
            logger.info("✅ Connected!n")
            
            try:
                # Test 1: Ping command
                # logger.info("=" * 60)
                # logger.info("Test 1: Ping Command")
                # logger.info("=" * 60)
                # response = await self.send_command(reader, writer, 'ping')
                # logger.info(f"Request: {{'cmd': 'ping'}}")
                # logger.info(f"Response: {response}")
                # assert response['status'] == 'success'
                # assert response['data']['pong'] == True
                # logger.info("✅ Test 1 PASSEDn")
                
                # Test 2: Echo command
                # logger.info("=" * 60)
                # logger.info("Test 2: Echo Command")
                # logger.info("=" * 60)
                # req = EchoRequest(message='Hello, Server!', timestamp=asyncio.get_running_loop().time())
                # response = await self.send_command(reader, writer, 'echo', **req.model_dump())
                # logger.info(f"Request: {{'cmd': 'echo', 'message': 'Hello, Server!'}}")
                # logger.info(f"Response: {response}")
                # assert response['success'] == True
                # assert response['message'] == 'Hello, Server!'
                # logger.info("✅ Test 2 PASSEDn")


                logger.info("=" * 60)
                logger.info("Test 2: Echo Command")
                logger.info("=" * 60)
                req = DataQueryRequest(query='Hello, Server!')
                response = await self.send_command(reader, writer, req)
                logger.info(f"Response: {response}")
                assert response['status'] == 'success'
                assert response['message'] == 'Hello, Server!'
                logger.info("✅ Test 2 PASSEDn")
                
                # Test 3: Status command
                # logger.info("=" * 60)
                # logger.info("Test 3: Status Command")
                # logger.info("=" * 60)
                # response = await self.send_command(reader, writer, 'status')
                # logger.info(f"Request: {{'cmd': 'status'}}")
                # logger.info(f"Response: {response}")
                # assert response['status'] == 'success'
                # assert response['data']['server_status'] == 'running'
                # logger.info("✅ Test 3 PASSEDn")
                
                # Test 4: Unknown command
                # logger.info("=" * 60)
                # logger.info("Test 4: Unknown Command (Error Handling)")
                # logger.info("=" * 60)
                # response = await self.send_command(reader, writer, 'unknown_cmd')
                # logger.info(f"Request: {{'cmd': 'unknown_cmd'}}")
                # logger.info(f"Response: {response}")
                # assert response['status'] == 'error'
                # assert 'Unknown command' in response['message']
                # logger.info("✅ Test 4 PASSEDn")
                
                # Test 5: Connect to device
                # logger.info("=" * 60)
                # logger.info("Test 5: Connect to Device")
                # logger.info("=" * 60)
                # response = await self.send_command(reader, writer, 'open_device', serial_number='COM3')
                # logger.info(f"Request: {{'cmd': 'open_device', 'serial_number': 'COM3'}}")
                # logger.info(f"Response: {response}")
                # assert response['status'] == 'success'
                # assert response['data']['device_status'] == 'connected'
                # logger.info("✅ Test 5 PASSEDn")
                

                # print("All tests passed!")
                logger.info("=" * 60)
                logger.info("🎉 ALL TESTS PASSED!")
                logger.info("=" * 60)
            finally:
                writer.close()
                await writer.wait_closed()
                logger.info("n✅ Connection closed")
                
        except ConnectionRefusedError:
            logger.error("❌ Could not connect! Is the server running?")
            logger.error("Please start the server first:")
            logger.error("  python srcserversocket_server.py")
        except Exception as e:
            logger.error(f"❌ Test failed: {e}", exc_info=True)


async def main():
    client = JsonSocketClient()
    await client.run_tests()


if __name__ == '__main__':
    asyncio.run(main())