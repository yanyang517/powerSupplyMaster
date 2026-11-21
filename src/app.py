import sys
import asyncio
import logging
import argparse
from pathlib import Path

from qasync import QEventLoop, asyncSlot, asyncClose
from PySide6.QtWidgets import QApplication

from server.socket_server import SocketServer, server_main
from server.runtime_config import runtime_config
from server.registry import ClientRegistry, RegistryError, clients_file_path, use_registry
from server.session import lease_config
from device.scpi_power_supply import SCPI_PowerSupply
from views.main_window import MainWindow
from views.theme import build_palette, build_qss
from presenter.presenter import Presenter
from presenter.model import PowerSupplyModel
from views import update_notice
import version

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-gui', action='store_true', help='Run without GUI (server mode only)')
    parser.add_argument('--no-update-check', action='store_true',
                        help='skip the background check for a newer release (GUI mode only)')
    parser.add_argument('--max-voltage', type=float, default=runtime_config.max_voltage,
                        help=f'Max allowed set voltage in V (default: {runtime_config.max_voltage})')
    parser.add_argument('--max-current', type=float, default=runtime_config.max_current,
                        help=f'Max allowed set current in A (default: {runtime_config.max_current})')
    parser.add_argument('--clients', default=None, metavar='JSON',
                        help=f'client registry file (default: {clients_file_path()})')
    parser.add_argument('--lease-ttl', type=float, default=lease_config.ttl_seconds, metavar='SECONDS',
                        help=f'control lease timeout in seconds (default: {lease_config.ttl_seconds:g})')
    return parser.parse_args()

def bootstrap_access(clients_arg, lease_ttl: float) -> ClientRegistry:
    """加载客户端登记表并设定控制权时限；登记表不可用时拒绝启动而不是空表运行。"""
    lease_config.ttl_seconds = lease_ttl
    try:
        registry = ClientRegistry.load(Path(clients_arg) if clients_arg else None)
    except RegistryError as e:
        logger.error("client registry unusable, refusing to start: %s", e)
        raise SystemExit(2)
    use_registry(registry)
    logger.info("client registry: %d client(s), lease ttl %.0fs", len(registry), lease_config.ttl_seconds)
    return registry

def main(args=None):
    args = parse_args()
    logger.info(version.summary())
    runtime_config.max_voltage = args.max_voltage
    runtime_config.max_current = args.max_current
    logger.info(f"Control limits: max_voltage={runtime_config.max_voltage}V, max_current={runtime_config.max_current}A")
    bootstrap_access(args.clients, args.lease_ttl)
    update_check_enabled = not args.no_update_check
    if not args.no_gui:
        app = QApplication(sys.argv)
        # 固定深色外观：宿主为浅色配色时也必须一致，所以样式表之外还要显式给 QPalette。
        app.setStyle('Fusion')
        app.setPalette(build_palette('dark'))
        app.setStyleSheet(build_qss('dark'))
    
        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)
        
        # window = MainWindow()
        # window.show()

        presenter = Presenter(MainWindow)

        # 更新提示：只在 GUI 模式接线，--no-gui 通路一次网络请求都不发。
        notifier = update_notice.attach(presenter.view, enabled=update_check_enabled)
        if update_check_enabled:
            notifier.start()
        else:
            logger.info("update check disabled by --no-update-check")

        loop.create_task(server_main())
        with loop:
            loop.run_forever()
    else:
        asyncio.run(server_main())

if __name__ == '__main__':
    main(sys.argv)