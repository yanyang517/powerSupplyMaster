import sys
import asyncio
import logging
import argparse

from qasync import QEventLoop, asyncSlot, asyncClose
from PySide6.QtWidgets import QApplication

from server.socket_server import SocketServer, server_main
from device.scpi_power_supply import SCPI_PowerSupply
from views.main_window import MainWindow
from presenter.presenter import Presenter
from presenter.model import PowerSupplyModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-gui', action='store_true', help='Run without GUI (server mode only)')
    return parser.parse_args()

def main(args=None):
    args = parse_args()
    if not args.no_gui:
        app = QApplication(sys.argv)
    
        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)
        
        # window = MainWindow()
        # window.show()

        presenter = Presenter(MainWindow)
        
        loop.create_task(server_main())
        with loop:
            loop.run_forever()
    else:
        asyncio.run(server_main())

if __name__ == '__main__':
    main(sys.argv)