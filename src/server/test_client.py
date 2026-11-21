import asyncio
import json
import logging
import pytest
import pytest_asyncio
from typing import Tuple
from construct import Struct, Int32ub, Bytes, this

from .protocal.protocal import (
    BaseModel, BaseRequest,
    EchoRequest,
    OpenDeviceRequest,
    CloseDeviceRequest,
    LoginRequest,
    LogoutRequest,

    VauleResponse,

    VoltageQueryRequest,
    CurrentQueryRequest,
    StatusQueryRequest,
    
    SetVoltageRequest,
    SetCurrentRequest,
    SetMaxCurrentRequest,
    SetMaxVoltageRequest,
)

# 集成测试身份：需要在服务端登记表里存在（默认 config/clients.json 已带这条）
CLIENT_ID = "test-client"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Construct protocol definition (same as server)
MessageProtocol = Struct(
    "length" / Int32ub,
    "payload" / Bytes(this.length)
)

@pytest.mark.asyncio
class JsonSocketClient:
    """JSON protocol socket client with construct-based message parsing"""
    
    def __init__(self, host: str = '127.0.0.1', port: int = 8888):
        self.host = host
        self.port = port
        self.client_id = CLIENT_ID
        

    async def connect(self) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)

    async def close(self) -> None:
        self._writer.close()    
    
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

    async def request(self, req):
        rsp = await self.send_command(self._reader, self._writer, req)
        return rsp

    async def login(self, tier: str = "L2") -> dict:
        """业务命令之前必须有身份：新门控对未登录连接一律拒绝（echo 除外）。"""
        return await self.request(LoginRequest(client_id=self.client_id, tier=tier))

@pytest.mark.asyncio
class TestSocketServer:
    """Test suite for socket server functionality"""
    
    async def test_echo_command(self):
        """Test 2: Echo command - returns the same message"""
        client = JsonSocketClient()
        reader, writer = await asyncio.open_connection(client.host, client.port)

        try:
            req = EchoRequest(message='Hello, Server!')
            response = await client.send_command(reader, writer, req)
            
            logger.info(f"Request: {{'cmd': 'echo', 'message': 'Hello, Server!'}}")
            logger.info(f"Response: {response}")
            
            assert response['status'] == 'success'
            assert response['message'] == 'Hello, Server!'
            logger.info("✅ Echo command test PASSED")
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_open_device_command(self):
        """Test 5: Connect to device command"""
        client = JsonSocketClient()
        reader, writer = await asyncio.open_connection(client.host, client.port)
        await client.send_command(reader, writer, LoginRequest(client_id=CLIENT_ID, tier="L2"))

        try:
            req = OpenDeviceRequest(serial_number='COM8')
            response = await client.send_command(reader, writer, req)
            
            logger.info(f"Request: {{'cmd': 'open_device', 'serial_number': 'COM8'}}")
            logger.info(f"Response: {response}")
            
            assert response['status'] == 'success'
            logger.info("✅ Open device command test PASSED")
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def test_close_device_command(self):
        """Test 6: Close device command"""
        client = JsonSocketClient()
        reader, writer = await asyncio.open_connection(client.host, client.port)
        await client.send_command(reader, writer, LoginRequest(client_id=CLIENT_ID, tier="L2"))

        try:
            req = CloseDeviceRequest(device_id='device_id_123')
            response = await client.send_command(reader, writer, req)
            
            logger.info(f"Request: {{'cmd': 'close_device', 'device_id': 'device_id_123'}}")
            assert response['status'] == 'success'
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def test_set_voltage_command(self):
        """Test 7: Set voltage command"""
        client = JsonSocketClient()
        reader, writer = await asyncio.open_connection(client.host, client.port)
        await client.send_command(reader, writer, LoginRequest(client_id=CLIENT_ID, tier="L2"))

        try:
            req = OpenDeviceRequest(serial_number='COM8')
            response = await client.send_command(reader, writer, req)
            
            logger.info(f"Request: {{'cmd': 'open_device', 'serial_number': 'COM8'}}")
            logger.info(f"Response: {response}")
            
            assert response['status'] == 'success'
        
            req = SetVoltageRequest(value=5.0)
            response = await client.send_command(reader, writer, req)
            
            logger.info(f"Request: {{'cmd': 'set_voltage', 'value': 5.0}}")
            logger.info(f"Response: {response}")
            assert response['status'] == 'success'
            logger.info("✅ Set voltage command test PASSED")
            # await asyncio.sleep(1)
            # req = VoltageQueryRequest()
            # response = await client.send_command(reader, writer, req)
            # logger.info(f"Request: {{'cmd': 'voltage_query'}}")
            # logger.info(f"Response: {response}")
            # assert response['status'] == 'success'
            # assert response['value'] == 5.0
            # logger.info("✅ Set voltage query test PASSED")
        finally:
            writer.close()
            await writer.wait_closed()
    async def test_login_command(self):
        """Test login command"""
        client = JsonSocketClient()
        reader, writer = await asyncio.open_connection(client.host, client.port)

        try:
            req = LoginRequest(client_id=CLIENT_ID, tier='L1')
            response = await client.send_command(reader, writer, req)
            
            logger.info(f"Request: {{'cmd': 'login', 'client_id': CLIENT_ID}}")
            logger.info(f"Response: {response}")
            
            assert response['status'] == 'success'
            # 生效等级取登记表里的值：申请更低等级不会改变登记身份，只有超出时才降格
            assert response['client_id'] == CLIENT_ID and response['tier'] == 'L2'
            logger.info("✅ Login command test PASSED")
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_logout_command(self):
        """Test logout command"""
        client = JsonSocketClient()
        reader, writer = await asyncio.open_connection(client.host, client.port)
        await client.send_command(reader, writer, LoginRequest(client_id=CLIENT_ID, tier="L2"))

        try:
            req = LogoutRequest()
            response = await client.send_command(reader, writer, req)
            
            logger.info(f"Request: {{'cmd': 'logout'}}")
            logger.info(f"Response: {response}")
            
            assert response['status'] == 'success'
            logger.info("✅ Logout command test PASSED")
        finally:
            writer.close()
            await writer.wait_closed()


    @pytest.mark.skip(reason="Unknown command test needs to be implemented later")
    async def test_unknown_command(self):
        """Test unknown command error handling"""
        from typing import Literal
        
        client = JsonSocketClient()
        reader, writer = await asyncio.open_connection(client.host, client.port)
        await client.send_command(reader, writer, LoginRequest(client_id=CLIENT_ID, tier="L2"))

        try:
            # Create a request with an unknown command type
            class UnknownRequest(BaseRequest):
                type: Literal["unknown_cmd"] = "unknown_cmd"
                data: str = "test"
            
            req = UnknownRequest(data="test data")
            response = await client.send_command(reader, writer, req)
            
            logger.info(f"Request: {{'cmd': 'unknown_cmd'}}")
            logger.info(f"Response: {response}")
            
            assert response['status'] == 'error'
            assert 'Unknown command' in response.get('message', '')
            logger.info("✅ Unknown command error handling test PASSED")
        finally:
            writer.close()
            await writer.wait_closed()


@pytest_asyncio.fixture
async def opened_device():
    client = JsonSocketClient()
    await client.connect()
    assert (await client.login())['status'] == 'success'

    req = OpenDeviceRequest(serial_number='COM8')
    response = await client.request(req)
    
    yield client
    
    await client.close()


@pytest.mark.asyncio
class TestDevice:
    """Test suite for server functionality"""
    
    async def test_set_voltage_command(self, opened_device):
        """Test 7: Set voltage command"""

        client = opened_device
        req = SetVoltageRequest(value=5.0)
        response = await client.request(req)
        
        logger.info(f"Request: {{'cmd': 'set_voltage', 'value': 5.0}}")
        logger.info(f"Response: {response}")
        assert response['status'] == 'success'
        logger.info("✅ Set voltage command test PASSED")
    
    async def test_voltage_query_command(self, opened_device):
        """Test 8: Voltage query command"""
        client = opened_device
        req = VoltageQueryRequest()
        response = await client.request(req)
        
        logger.info(f"Request: {{'cmd': 'voltage_query'}}")
        logger.info(f"Response: {response}")
        assert response['status'] == 'success'
        assert abs(response['value'] - 5.0) < 0.11


@pytest.mark.asyncio
class TestVoltageDevice:
    """Test suite for server functionality"""
    _target_voltage = 5.0
    async def test_set_voltage_command(self, opened_device):
        """Test 7: Set voltage command"""

        client = opened_device
        req = SetVoltageRequest(value=self._target_voltage)
        response = await client.request(req)
        
        logger.info(f"Request: {{'cmd': 'set_voltage', 'value': 5.0}}")
        logger.info(f"Response: {response}")
        assert response['status'] == 'success'
        logger.info("✅ Set voltage command test PASSED")
    
    #repeat 5 times
    @pytest.mark.repeat(5)
    async def test_repeat_voltage_query_command(self, opened_device):
        """Test 8: Voltage query command"""
        client = opened_device
        req = VoltageQueryRequest()
        response = await client.request(req)
        
        logger.info(f"Request: {{'cmd': 'voltage_query'}}")
        logger.info(f"Response: {response}")
        assert response['status'] == 'success'
        assert abs(response['value'] - self._target_voltage) < 0.11


        



@pytest.mark.asyncio
class TestConnectionManagement:
    """Test suite for connection management"""
    
    async def test_connection_establishment(self):
        """Test that client can establish connection to server"""
        client = JsonSocketClient()
        
        try:
            reader, writer = await asyncio.open_connection(client.host, client.port)
            logger.info("✅ Connection established successfully")
            assert writer.is_closing() is False
            
            writer.close()
            await writer.wait_closed()
            logger.info("✅ Connection closed successfully")
        except ConnectionRefusedError:
            pytest.fail("Could not connect! Is the server running?")

    async def test_multiple_connections(self):
        """Test multiple simultaneous connections"""
        client = JsonSocketClient()
        connections = []
        
        try:
            # Create multiple connections
            for i in range(3):
                reader, writer = await asyncio.open_connection(client.host, client.port)
                connections.append((reader, writer))
                logger.info(f"✅ Connection {i+1} established")
            
            assert len(connections) == 3
            
            # Close all connections
            for reader, writer in connections:
                writer.close()
                await writer.wait_closed()
            
            logger.info("✅ All connections closed successfully")
        except ConnectionRefusedError:
            pytest.fail("Could not connect! Is the server running?")


if __name__ == '__main__':
    pytest.main([__file__, "-v", "-s"])