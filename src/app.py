import sys
import asyncio
import logging
import argparse
from datetime import datetime
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

# --- 启动失败的可见性 -------------------------------------------------------
# 被 --windowed 打成的产物双击时没有控制台，Windows 上 sys.stderr 会是 None，日志因此
# 静默丢失（实测 CPython 3.13 不抛异常：Handler.handleError 被 `if raiseExceptions and
# sys.stderr` 短路）。用户只剩「双击没反应」，所以致命的启动错误必须另有不依赖 stderr 的通道。
LOGS_DIR_NAME = "logs"
STARTUP_ERROR_FILE_NAME = "startup_error.log"


def has_console() -> bool:
    """stderr 是否真能把日志送到用户眼前。

    不要用 kernel32.GetConsoleWindow() 判断：从 cmd/CI 启动的 --windowed 进程同样继承控制台
    句柄，会把「其实看得见」误判成看不见。
    """
    return callable(getattr(getattr(sys, "stderr", None), "write", None))


def startup_error_log_path() -> Path:
    """<exe 同级>/logs/startup_error.log，与 registry.clients_file_path() 的 frozen 规则一致。

    落在 logs/ 而不是 config/：config/ 是准入名单这类设置的地盘，而这里服务的恰恰是
    「设置出问题时」；.gitignore 也已为 logs/ 预留。
    """
    return Path(sys.executable).resolve().parent / LOGS_DIR_NAME / STARTUP_ERROR_FILE_NAME


def show_startup_error_dialog(title: str, text: str) -> bool:
    """原生错误弹窗，返回是否真的显示过；任何失败都只记日志，不向外抛。

    不用 QMessageBox：本函数在 QApplication 创建之前被调用（--no-gui 下更是压根不创建），
    而 ctypes + user32 属标准库，不需要事件循环。
    """
    if sys.platform != "win32":
        return False
    MB_ICONERROR = 0x10
    MB_SETFOREGROUND = 0x00040000
    try:
        import ctypes

        # 显式声明签名：x64 上按默认 int 传递指针会被截断。
        user32 = ctypes.windll.user32
        user32.MessageBoxW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        user32.MessageBoxW.restype = ctypes.c_int
        user32.MessageBoxW(None, text, title, MB_ICONERROR | MB_SETFOREGROUND)
        return True
    except Exception as e:
        logger.warning("startup error dialog unavailable: %s", e)
        return False


def report_startup_failure(message: str) -> None:
    """把致命的启动错误送到 stderr 之外：exe 同级日志文件 + 无控制台时的原生弹窗。

    先落盘再弹窗，弹窗文案里带上日志路径。本函数不向外抛（写不了文件就只剩弹窗），
    报告的失败不能改变退出码，也不能盖掉原始错误。
    """
    log_path = None
    if getattr(sys, "frozen", False):
        path = startup_error_log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n")
            log_path = path
        except OSError as e:
            logger.warning("cannot write startup error log %s: %s", path, e)
    if not has_console():
        text = message if log_path is None else f"{message}\n\n详情已记录到：{log_path}"
        show_startup_error_dialog("powerSupplyMaster 启动失败", text)


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
        report_startup_failure(str(e))
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