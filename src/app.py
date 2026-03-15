import sys
import asyncio
import logging

from qasync import QEventLoop, asyncSlot, asyncClose
from PySide6.QtWidgets import QApplication

from server.socket_server import SocketServer, server_main
from device.scpi_power_supply import SCPI_PowerSupply
from views.main_window import MainWindow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    app = QApplication(sys.argv)
    
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    window = MainWindow()
    window.show()
    
    loop.create_task(server_main())
    with loop:
        loop.run_forever()

if __name__ == '__main__':
    main()