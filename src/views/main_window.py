import logging
import math

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QDoubleSpinBox,
    QPushButton,
    QTabWidget,
)

from PySide6.QtCore import Slot, QTimer, Qt, QPointF, QSize
from PySide6.QtGui import QFont

from .ui.mainWindow_ui import Ui_MainWindow
from server.runtime_config import runtime_config
import version
from recording.processing import trim_to_window
from .access_panel import AccessPanel
from .dark_dial import DarkDial
from .floating_window import FloatingWindow
from .live_chart_view import LiveChartView
from .record_panel import RecordPanel
from .theme import tokens
from .update_notice import ManualCheckRow, UpdateNoticeWidget
from . import icons
from . import window_geometry as wg

logger = logging.getLogger(__name__)

ICON_PX = 16

# 页签字形按 objectName 映射：页序变动时不至于静默错位到别的页签上。
_TAB_GLYPHS = {
    "tab_control": "lucide/gauge",
    "tab_wave": "tabler/wave-sine",
    "tab_client": "tabler/users",
    "tab_floating": "tabler/picture-in-picture",
    "tab_record": "tabler/clock",
    "tab_about": "lucide/info",
}

class MainWindow(QMainWindow):
    def __init__(self, presenter = None):
        super().__init__()
        self.presenter = presenter
        self.ui = Ui_MainWindow()

        # Data storage for chart
        self.max_data_points = 100  # Maximum number of data points to display
        self.voltage_data = []
        self.current_data = []
        self.voltage_data_count = 0
        self.current_data_count = 0
        
        # Chart initialization flag
        self._chart_initialized = False
        self._device_connected = False
        self._output_state: bool | None = None

        self.setupUi()
        self._confirmed_voltage_setting = self.ui.voltage_spinBox.value()
        self._voltage_is_updating = False
        self._voltage_is_updateing_by_present = False
        self.connect_signal_slots()
        # 初始态显式落一次：基础布局的两钮同亮，互斥形态必须由状态层接管。
        self.update_connection_state(False)
        self.access_panel = AccessPanel(self.ui.groupBox_10, self.ui.groupBox_9)
        self._restore_geometry()

        self.floating_window = FloatingWindow()
        self.floating_window.request_show_main.connect(self._show_main_window)
        self.floating_window.request_output_toggle.connect(self.toggle_output)
        self.floating_window.show()

    def setupUi(self):
        self.ui.setupUi(self)
        self.ui.tabWidget.setTabShape(QTabWidget.TabShape.Rounded)
        self._swap_voltage_dial()
        self._apply_runtime_voltage_limit()
        self._apply_button_icons()
        self._mount_connection_indicator()

        # Initialize the chart in groupBox_8
        self._setup_chart()
        self._fill_about_tab()
        self._mount_record_tab()
        # 页签图标要排在记录页挂载之后刷：那一页是代码 addTab 上来的，
        # 早一步刷图标会静默漏掉它（映射表按 objectName 认页）。
        self._apply_tab_icons()

        available_ports, perfered_index = self.presenter.get_available_ports()
        self.ui.com_num_comboBox.addItems(available_ports)
        if perfered_index is not None and 0 <= perfered_index < len(available_ports):
            self.ui.com_num_comboBox.setCurrentIndex(perfered_index)
        self.ui.auto_reconnect_CB.setChecked(self.presenter.auto_connect_enabled())

    def _apply_runtime_voltage_limit(self):
        """让电压/电流上限显示与启动时生效的安全限值一致，而非 .ui 的静态值。"""
        voltage_limit = float(runtime_config.max_voltage)
        self.ui.max_voltage_spinbox.setMaximum(voltage_limit)
        self.ui.max_voltage_spinbox.setValue(voltage_limit)
        # 上限框只展示启动参数；编辑它不能改变服务端真实限值。
        self.ui.max_voltage_spinbox.setReadOnly(True)
        self.ui.max_voltage_spinbox.setToolTip("由启动参数 --max-voltage 配置")
        self.ui.voltage_spinBox.setMaximum(voltage_limit)
        # QDial 使用整数分度；向下取整避免旋钮放出服务端不允许的分数伏值。
        self.ui.voltage_dial.setMaximum(math.floor(voltage_limit * 100 + 1e-9))

        current_limit = float(runtime_config.max_current)
        self.ui.max_current_spinBox.setMaximum(current_limit)
        self.ui.max_current_spinBox.setValue(current_limit)
        self.ui.max_current_spinBox.setReadOnly(True)
        self.ui.max_current_spinBox.setToolTip("由启动参数 --max-current 配置")

    def _mount_record_tab(self):
        """基础布局没有「记录」这一页，整页在代码侧 addTab 挂上（同 _swap_voltage_dial 的约定）。

        这里只建控件：状态要等 Presenter 把 recorder 装好才存在，首轮渲染由
        presenter 显式调 update_recording_state() 触发。
        """
        self.record_panel = RecordPanel(self.ui.tabWidget)
        self.record_panel.setObjectName("tab_record")
        self.ui.tabWidget.addTab(self.record_panel, "记录")
        self.record_panel.enable_requested.connect(self.presenter.set_recording_enabled)

    def update_recording_state(self):
        """把 presenter 的记录快照原样交给面板渲染，视图侧不自行判断。"""
        self.record_panel.render(self.presenter.recording_status())

    def _fill_about_tab(self):
        """在基础布局的空「关于」页上挂版本信息。

        布局、文案和样式统一在 Python 侧维护。「立即检查」行由 update_notice 接线时
        追加到同一个布局里。
        """
        self.setWindowTitle(f"powerSupplyMaster {version.display_version()}")

        layout = QVBoxLayout(self.ui.tab_about)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(6)

        # 标识放最上方；渲染失败就整块不挂，留个空 QLabel 会在标题前顶出一段空白。
        mark = icons.mark_pixmap(48)
        if mark is not None:
            mark_label = QLabel(self.ui.tab_about)
            mark_label.setObjectName("about_mark_label")
            mark_label.setPixmap(mark)
            layout.addWidget(mark_label)

        title = QLabel(f"powerSupplyMaster {version.display_version()}")
        title.setObjectName("about_title_label")
        layout.addWidget(title)

        for text in (
            f"版本 {version.__version__}",
            f"通道 {version.channel}",
            f"构建 {version.build_label()}",
        ):
            layout.addWidget(self._about_line(text))

        # 「立即检查」行：后台节流提示在开发机上几乎不会出声，手动入口才是可验证的那一个。
        self.update_manual_row = ManualCheckRow(self.ui.tab_about)
        layout.addWidget(self.update_manual_row)

        layout.addStretch(1)

        self.update_notice = UpdateNoticeWidget(self)
        # addWidget 而不是 showMessage：状态栏的瞬时消息通道会被任何一次
        # showMessage 覆盖，更新提示需要一直挂在栏上直到用户处置。
        self.ui.statusbar.addWidget(self.update_notice)

    def _about_line(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("about_meta_label")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _apply_tab_icons(self):
        tabs = self.ui.tabWidget
        tabs.setIconSize(QSize(ICON_PX, ICON_PX))
        # 按页签自己的 objectName 认字形：记录页是代码 addTab 上来的，
        # 不在基础布局里，按属性名去找它会静默漏掉一整页。
        for index in range(tabs.count()):
            glyph = _TAB_GLYPHS.get(tabs.widget(index).objectName())
            if glyph is None:
                continue
            tabs.setTabIcon(index, icons.icon(glyph, "text", ICON_PX))

    def _apply_button_icons(self):
        for button, glyph, role in (
            (self.ui.connect_Btn, "lucide/plug", "primary"),
            (self.ui.disconnect_Btn, "tabler/plug-off", "danger"),
        ):
            button.setIconSize(QSize(ICON_PX, ICON_PX))
            button.setIcon(icons.icon(glyph, role, ICON_PX))
        self.ui.ouput_ctrl_Btn.setIconSize(QSize(ICON_PX, ICON_PX))
        self.ui.ouput_ctrl_Btn.toggled.connect(self._set_output_icon)
        self._set_output_icon(self.ui.ouput_ctrl_Btn.isChecked())

    def _mount_connection_indicator(self):
        """状态栏右角的连接指示。

        用 addPermanentWidget 而不是 showMessage：后者是瞬时消息通道，会被采样
        异常提示（update_sampling_error）随时覆盖，连接状态必须一直在。永久部件
        由 QStatusBar 排在栏的右端，与左角的更新提示条（addWidget）各占一角。
        """
        self.connection_status_label = QLabel("未连接", self.ui.statusbar)
        self.connection_status_label.setObjectName("conn_status_off")
        self.ui.statusbar.addPermanentWidget(self.connection_status_label, 0)

    def _set_output_icon(self, checked: bool):
        """输出开关两态同字形、只换色：它已有 2px 边框 + 字重 + 文字三重形态线索。"""
        self.ui.ouput_ctrl_Btn.setIcon(
            icons.icon("tabler/power", "success" if checked else "text", ICON_PX)
        )

    def _swap_voltage_dial(self):
        """把基础布局的 QDial 换成自绘的 DarkDial。

        必须在 connect_signal_slots() 之前调用：接线有四处引用
        self.ui.voltage_dial，替换晚于接线会让旧控件的连接静默失效。
        """
        old = self.ui.voltage_dial
        new = DarkDial(parent=old.parentWidget())
        new.setObjectName(old.objectName())
        for getter, setter in (
            ("minimum", "setMinimum"),
            ("maximum", "setMaximum"),
            ("singleStep", "setSingleStep"),
            ("pageStep", "setPageStep"),
            ("value", "setValue"),
            ("notchesVisible", "setNotchesVisible"),
            ("notchTarget", "setNotchTarget"),
            ("wrapping", "setWrapping"),
        ):
            getattr(new, setter)(getattr(old, getter)())
        new.setSizePolicy(old.sizePolicy())

        layout = self._find_layout(old, old.parentWidget().layout())
        if layout is not None:
            layout.replaceWidget(old, new)
        else:
            new.setParent(old.parentWidget())
            new.setGeometry(old.geometry())
        old.setParent(None)
        old.deleteLater()
        self.ui.voltage_dial = new

    @staticmethod
    def _find_layout(widget, layout):
        if layout is None:
            return None
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            if item.widget() is widget:
                return layout
            found = MainWindow._find_layout(widget, item.layout())
            if found is not None:
                return found
        return None

    def _restore_geometry(self):
        entries = wg.load_entries(wg.geometry_file_path())
        rect = wg.restored_rect(entries, "main", self.width(), self.height())
        if rect is None:
            available = wg.primary_available_rect()
            if available is None:
                return
            rect = wg.default_main_rect(available, self.width(), self.height())
        self.setGeometry(*rect)

    def _save_geometry(self):
        floating = self.floating_window
        wg.save_geometry(
            wg.geometry_file_path(),
            self.geometry().getRect(),
            (floating.x(), floating.y()),
            wg.screen_name(self),
            wg.screen_name(floating),
        )

    def closeEvent(self, event):
        # 关窗算正常收尾：会话要以 closed 落清单，否则下次启动只能改判成 interrupted。
        self.presenter.stop_recording()
        self._save_geometry()
        super().closeEvent(event)

    def _setup_chart(self):
        """在波形页挂载两张共用主题与交互的实时图表。"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(6)
        self.ui.groupBox_8.setLayout(main_layout)
        palette = tokens("dark")

        self.voltage_chart_view = LiveChartView(
            "电压曲线",
            palette["danger"],
            "V",
            window_size=self.max_data_points,
            y_range=(0.0, 20.0),
            x_title="采样序号",
            y_title="电压 (V)",
            y_ticks=7,
        )
        self.current_chart_view = LiveChartView(
            "电流曲线",
            palette["primary"],
            "A",
            window_size=self.max_data_points,
            y_range=(0.0, 10.0),
            x_title="采样序号",
            y_title="电流 (A)",
            y_ticks=6,
        )

        # 保留原有属性接口，既有采样与回归测试无需知道视图已经重构。
        self.voltage_chart = self.voltage_chart_view.chart()
        self.voltage_series = self.voltage_chart_view.series
        self.voltage_axis_x = self.voltage_chart_view.axis_x
        self.voltage_axis_y = self.voltage_chart_view.axis_y
        self.current_chart = self.current_chart_view.chart()
        self.current_series = self.current_chart_view.series
        self.current_axis_x = self.current_chart_view.axis_x
        self.current_axis_y = self.current_chart_view.axis_y

        main_layout.addWidget(self.voltage_chart_view)
        main_layout.addWidget(self.current_chart_view)
        self._chart_initialized = True

    @Slot(bool)
    def _on_auto_reconnect_toggled(self, checked: bool):
        if self.presenter.set_auto_connect(checked):
            return
        # 写盘失败时恢复控件，避免界面显示一个并未生效的勾选状态。
        checkbox = self.ui.auto_reconnect_CB
        checkbox.blockSignals(True)
        try:
            checkbox.setChecked(not checked)
        finally:
            checkbox.blockSignals(False)

    def connect_signal_slots(self):


        self.ui.voltage_spinBox.valueChanged.connect(self.on_voltage_spinbox_value_changed)
        self.ui.voltage_dial.valueChanged.connect(self.on_voltage_dial_value_changed)
        self.ui.connect_Btn.clicked.connect(self.presenter.open_device)
        self.ui.disconnect_Btn.clicked.connect(self.presenter.close_device)
        self.ui.auto_reconnect_CB.toggled.connect(self._on_auto_reconnect_toggled)
        self.ui.ouput_ctrl_Btn.clicked.connect(self.toggle_output)
        self.ui.max_voltage_spinbox.valueChanged.connect(
            lambda _value: self._apply_runtime_voltage_limit()
        )
        self.ui.max_current_spinBox.valueChanged.connect(
            lambda _value: self._apply_runtime_voltage_limit()
        )

        # Connect chart hover events for legend interaction
        # self.chart.legend().hovered.connect(self._on_legend_hovered)
        # self.ui.max_voltage_spinbox.valueChanged.connect(self.presenter.set_max_voltage)
        # self.ui.max_current_spinBox.valueChanged.connect(self.presenter.set_max_current)
        pass
    
    @Slot(float)
    def on_voltage_dial_value_changed(self, value: float):
        if self._voltage_is_updating:
            return
        self._voltage_is_updating = True
        self.ui.voltage_spinBox.setValue(value/100)
        self._voltage_is_updating = False

    @Slot(float)
    def on_voltage_spinbox_value_changed(self, value: float):

        if not self._voltage_is_updateing_by_present:
            self.presenter.set_voltage(value)

        # 旋钮只跟随已确认设置值；用户输入本身不代表设备已经接受。
    

    def update_voltage(self, value: float):
        """
        更新当前电压
        """
        self.ui.volatage_label.setText(f"{value:.2f} V")
        self.floating_window.update_voltage(value)
        
        # Update chart data
        self._update_chart_data(value, "voltage")
    
    def update_current(self, value: float):
        """
        更新当前电流
        """
        self.ui.current_label.setText(f"{value:.2f} A")
        self.floating_window.update_current(value)
        
        # Update chart data
        self._update_chart_data(value, "current")

    def toggle_output(self, checked: bool = False):
        """点击只代表切换请求；先撤销自动勾选，最终外观只由设备回读决定。"""
        self.ui.ouput_ctrl_Btn.setChecked(self._output_state is True)
        self.presenter.toggle_output()

    def _show_main_window(self):
        """最小化状态下 raise_() 单独不起作用，必须先 showNormal()。"""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def update_output_state(self, value: bool | None):
        """主窗口与悬浮窗共用的三态渲染入口。"""
        self._output_state = value
        button = self.ui.ouput_ctrl_Btn
        available = self._device_connected and value is not None
        button.setEnabled(available)
        button.setChecked(value is True)
        if value is True:
            button.setText("关闭输出")
        elif value is False:
            button.setText("开启输出")
        else:
            button.setText("输出状态不可用")
        floating = getattr(self, "floating_window", None)
        if floating is not None:
            floating.update_output_state(value)

    def update_device_id(self, value):
        """presenter 连接后回填设备标识；读不到时留空而不是报错。"""
        self.ui.device_info_lineEdit.setText(str(value) if value else "")

    def update_connection_state(self, connected: bool, port: str | None = None):
        """连接状态唯一入口：两按钮互斥使能，右角指示同步措辞与配色。

        状态只由 presenter 的 open/close 结果驱动，绝不挂在按钮 clicked 上——
        串口占用导致的连接失败必须停在未连接态，否则指示灯就是谎报。
        """
        self.ui.connect_Btn.setEnabled(not connected)
        self.ui.disconnect_Btn.setEnabled(connected)
        self._device_connected = connected
        if not connected:
            self.update_output_state(None)
        if connected:
            self.connection_status_label.setText(f"已连接 {port}" if port else "已连接")
            self.connection_status_label.setObjectName("conn_status_on")
        else:
            self.connection_status_label.setText("未连接")
            self.connection_status_label.setObjectName("conn_status_off")
        # objectName 换了要重 polish，QSS 按 #conn_status_on/off 认色（见 theme.py）。
        self.connection_status_label.style().unpolish(self.connection_status_label)
        self.connection_status_label.style().polish(self.connection_status_label)

    def update_voltage_setting(self, value: float):
        """只在设备写入成功后发布；同步旋钮并守住最后一次已确认值。"""
        self._voltage_is_updateing_by_present = True
        try:
            self.ui.voltage_spinBox.setValue(value)
        finally:
            self._voltage_is_updateing_by_present = False
        self._voltage_is_updating = True
        try:
            self.ui.voltage_dial.setValue(value * 100)
        finally:
            self._voltage_is_updating = False
        self._confirmed_voltage_setting = value

    def update_setting_error(self, error: dict):
        """展示与 TCP 一致的限值文案，并撤销用户输入的未确认电压。"""
        self.ui.statusbar.showMessage(error["message"])
        if error["setting"] == "voltage":
            self.update_voltage_setting(self._confirmed_voltage_setting)

    def update_max_voltage(self, value: float):
        self._voltage_is_updateing_by_present = True
        self.on_voltage_spinbox_value_changed(value)
        self._voltage_is_updateing_by_present = False

    def _update_chart_data(self, value: float, data_type: str):
        """Update chart with new voltage or current data point"""
        if not self._chart_initialized or not self.ui.groupBox_8.isChecked():
            return
        
        if data_type == "voltage":
            self.voltage_data_count += 1
            self.voltage_data = trim_to_window(self.voltage_data + [value], self.max_data_points)
            self.voltage_chart_view.replace_points(
                self._window_points(self.voltage_data, self.voltage_data_count))
            self.voltage_chart_view.follow_latest(self.voltage_data_count - 1)

        elif data_type == "current":
            self.current_data_count += 1
            self.current_data = trim_to_window(self.current_data + [value], self.max_data_points)
            self.current_chart_view.replace_points(
                self._window_points(self.current_data, self.current_data_count))
            self.current_chart_view.follow_latest(self.current_data_count - 1)

    def _window_points(self, values, count):
        """给窗口内的每个值配回它的全局采样序号，整段替换进序列。

        QLineSeries::append 不会替滚动窗口让路，所以这里不追加而是替换：
        序列里永远只有最后 max_data_points 个点。
        """
        start = count - len(values)
        return [QPointF(start + offset, value) for offset, value in enumerate(values)]

    def update_sampling_error(self, message):
        """采集中断必须看得见：读数停在最后一次成功值而不加提示，等于谎报正常。"""
        if message:
            self.ui.statusbar.showMessage(f"通信异常：{message}（采样仍在重试）")
            self.floating_window.update_stale(True)
            return
        self.ui.statusbar.clearMessage()
        self.floating_window.update_stale(False)
