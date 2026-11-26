
import logging
import asyncio
import time

from PySide6.QtCore import Qt, QObject
from qasync import QEventLoop, asyncSlot, asyncClose
import serial
from serial.tools import list_ports
import serial_asyncio

from server.access import set_approval_handler
from server.session import lease
from recording.recorder import Recorder, reconcile_interrupted
from recording.settings import (NOMINAL_INTERVAL_MS, RecordSettings, load_settings,
                                records_dir_for, save_settings, settings_file_path)
from views.admission_dialog import AdmissionDialog
from views.confirmation import ask_yes_no

from .model import PowerSupplyModel

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 连续失败到这个次数才向界面明示：偶发一次超时不值得闪一下状态栏。
SAMPLING_FAILURE_THRESHOLD = 3

# 面板轮询周期：与记录侧标称周期同一个出处，改这里就等于改缺口的判定基准。
SAMPLE_INTERVAL_SECONDS = NOMINAL_INTERVAL_MS / 1000

class Presenter(QObject):
    def __init__(self, view_cls, model_cls=None):
        self.view = view_cls(presenter = self)
        self.model = PowerSupplyModel() if model_cls is None else model_cls()
        # self.view.connect_signal_slots(self)
        # self.view.setupUi()
        self.connect_signal_slots()
        self.view.show()

        self._refresh_voltage_current_task = None
        self._sample_failures = 0
        self._sampling_error_shown = False
        self._admission_dialogs = []
        set_approval_handler(self._on_admission_request)

        # 记录默认关闭：开关只由用户显式拨动，启动时绝不自动开录。
        self._record_settings = load_settings()
        self._recorder: Recorder | None = None
        self._recording_error: str | None = None
        self._connected_port: str | None = None
        # 上次进程被强杀时留下的 recording 条目在这里收尾，复看列表才不会挂着"正在录"。
        reconcile_interrupted(records_dir_for(self._record_settings))
        self.view.update_recording_state()

    def get_available_ports(self) -> list:
        '''
        return the available ports
        '''
        ports = list_ports.comports()
        ports_list = [port.device for port in ports]
        logger.info(f"Available ports: {ports_list}")

        perfered_index = [i for i, port in enumerate(ports) if 'USB' in port.description]
        return ports_list, perfered_index[0] if len(perfered_index) > 0 else None

    def connect_signal_slots(self):
        pass

    def _on_admission_request(self, approval) -> None:
        """服务端准入回调：与 Qt 共用事件循环，弹窗只呈现、不阻塞等待。"""
        dialog = AdmissionDialog(approval, parent=self.view)
        self._admission_dialogs.append(dialog)
        dialog.finished.connect(lambda _code, d=dialog: self._admission_dialogs.remove(d))
        dialog.show()

    async def _may_write_from_panel(self) -> bool:
        """面板写操作免于控制权检查，但有人持有时要先让用户确认接管。"""
        snap = lease.snapshot()
        if snap.holder is None:
            return True
        return await ask_yes_no(
            "电源正被远程控制",
            f"{snap.holder} 当前持有控制权（剩余 {snap.remaining_seconds:.0f} 秒）。\n"
            "确认由面板下发本次改动？",
            parent=self.view,
            yes_text="由面板下发",
        )

    # --- 记录：会话边界是设备连接，开关只由用户拨动 ---------------------------

    def recording_status(self) -> dict:
        """给记录面板的快照：面板只渲染这里给出的事实，自己不猜状态。"""
        recorder = self._recorder
        session = recorder.session if recorder is not None else None
        return {
            "enabled": self._record_settings.enabled,
            "recording": recorder is not None and recorder.active,
            "file": session.get("file") if session else None,
            "rows": recorder.rows if recorder is not None else 0,
            "dir": str(records_dir_for(self._record_settings)),
            "error": self._recording_error,
            # 断段要的是标称周期而不是实测间隔：面板拿它判缺口，少一项就画错。
            "interval_ms": NOMINAL_INTERVAL_MS,
        }

    def set_recording_enabled(self, enabled: bool) -> bool:
        """拨动记录开关：先落盘再生效，写不进配置就不改变当前运行状态。"""
        if enabled == self._record_settings.enabled:
            return True
        settings = RecordSettings(enabled=enabled, dir=self._record_settings.dir)
        if not save_settings(settings):
            self._note_recording_error(f"记录设置写不进 {settings_file_path()}")
            return False

        self._record_settings = settings
        if enabled:
            self._start_recording()
        else:
            self.stop_recording()
        self.view.update_recording_state()
        return True

    def _start_recording(self) -> None:
        """使能与连接先后到达都走这里：不要求用户为了开录再插拔一次。"""
        if not self._record_settings.enabled or self._connected_port is None:
            return
        if self._recorder is not None and self._recorder.active:
            return

        recorder = Recorder(records_dir_for(self._record_settings))
        self._recorder = recorder
        if recorder.start(self._connected_port):
            self._note_recording_error(None)
            return
        self._note_recording_error(recorder.failure_reason)

    def stop_recording(self) -> dict | None:
        if self._recorder is None:
            return None
        entry = self._recorder.stop()
        self.view.update_recording_state()
        return entry

    def _record_pair(self, voltage, current) -> None:
        if self._recorder is None or not self._recorder.active:
            return
        # 时间戳在成对读数都到手之后才取：先取会把串口往返耗时算进采样间隔。
        self._recorder.on_sample(int(time.time() * 1000), voltage, current)
        if not self._recorder.active:
            self._note_recording_error(self._recorder.failure_reason)
        self.view.update_recording_state()

    def _note_recording_error(self, message: str | None) -> None:
        """记录侧的故障只改状态：采样、显示与控制一律照常，缺口留给复看呈现。"""
        if message == self._recording_error:
            return
        if message:
            logger.error("记录异常：%s", message)
        self._recording_error = message
        self.view.update_recording_state()


    @asyncSlot()
    async def close_device(self):
        if self._refresh_voltage_current_task is not None:
            self._refresh_voltage_current_task.cancel()
            self._refresh_voltage_current_task = None

        self._sample_failures = 0
        self._clear_sampling_error()
        # 断开即结束会话：一段文件对应一次连接，复看时能对上"哪次接的哪台"。
        self.stop_recording()
        self._connected_port = None
        await self.model.close()
        self.view.update_connection_state(False)

    @asyncSlot()
    async def open_device(self):
        serial_port = self.view.ui.com_num_comboBox.currentText()
        baudrate = self.view.ui.baudrate_comboBox.currentText()

        ret = await self.model.open(port=serial_port)
        # 按钮互斥与状态栏指示只认连接结果：失败分支也要落回未连接态，
        # 否则一次连不上后「连接」按钮会一直灰着，用户没有任何重试入口。
        self.view.update_connection_state(ret is True, serial_port if ret is True else None)
        if ret is True:
            self._sample_failures = 0
            self._connected_port = serial_port
            self._start_recording()
            self._refresh_voltage_current_task = asyncio.create_task(self.refresh_voltage_current())
            
        ret = await self.model.get_device_id()
        self.view.update_device_id(ret)      
    
    async def refresh_voltage_current(self):
        """周期采样：一次采集失败只作废这一轮，循环本身不得终止。

        电压与电流必须成对取到才算一个有效周期——半途失败就整轮丢弃，
        既不刷新读数也不交给记录，缺口由复看侧按时间间隔呈现。
        """
        try:
            while True:
                try:
                    voltage = await self.model.get_voltage()
                    current = await self.model.get_current()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self._sample_failures += 1
                    logger.warning("采样失败（连续 %d 次）：%r", self._sample_failures, e)
                    if (self._sample_failures >= SAMPLING_FAILURE_THRESHOLD
                            and not self._sampling_error_shown):
                        self._sampling_error_shown = True
                        self.view.update_sampling_error(f"{type(e).__name__}: {e}")
                    await asyncio.sleep(SAMPLE_INTERVAL_SECONDS)
                    continue

                if self._sampling_error_shown:
                    self._clear_sampling_error()
                self._sample_failures = 0
                logger.info(f"{voltage=}, {current=}")
                # 记录与显示共用这一次采集：绝不为落盘多问设备一句。
                self._record_pair(voltage, current)
                self.view.update_voltage(voltage)
                self.view.update_current(current)
                await asyncio.sleep(SAMPLE_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Refresh voltage current task cancelled.")
            return

    def _clear_sampling_error(self) -> None:
        """异常指示只在显示过时才撤销，避免没亮过的灯每次成功都"关"一遍。"""
        if self._sampling_error_shown:
            self._sampling_error_shown = False
            self.view.update_sampling_error(None)
    
    @asyncSlot(float)
    async def set_voltage(self, voltage):
        if not await self._may_write_from_panel():
            logger.info("面板写操作被用户取消：set_voltage=%s", voltage)
            return

        self.view.update_voltage_setting(voltage)
        await self.model.set_voltage(voltage)
    
    # @asyncSlot(float)
    # async def set_max_voltage(self, voltage):
        # await self.model.set_max_voltage(voltage)
        # self.view.update_max_voltage(voltage)

    # @asyncSlot(float)
    # async def set_max_current(self, current):
    #     await self.model.set_max_current(current)
    #     self.view.update_max_current_setting(current)

    @asyncSlot(bool)
    async def set_on_off(self, value: bool):
        if not await self._may_write_from_panel():
            logger.info("面板写操作被用户取消：set_on_off=%s", value)
            return

        await self.model.set_on_off(value)
        self.view.update_output_setting(value)
        
