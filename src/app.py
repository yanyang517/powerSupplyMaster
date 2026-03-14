import asyncio

from server.socket_server import SocketServer, main
from device.scpi_power_supply import SCPI_PowerSupply

if __name__ == '__main__':
    asyncio.run(main())