import logging

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QDoubleSpinBox,
    QPushButton,
)

from PySide6.QtCore import Slot, QTimer, Qt, QPointF
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QAbstractSeries, QValueAxis
from PySide6.QtGui import QColor, QFont, QPainter

from .ui.mainWindow import Ui_MainWindow
from .floating_window import FloatingWindow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, presenter = None):
        super().__init__()
        self.presenter = presenter
        self.ui = Ui_MainWindow()

        # Data storage for chart
        self.max_data_points = 100  # Maximum number of data points to display
        self.voltage_data = [0.0] * self.max_data_points
        self.current_data = [0.0] * self.max_data_points
        self.time_data = list(range(self.max_data_points))
        self.voltage_data_count = 0
        self.current_data_count = 0
        
        # Chart initialization flag
        self._chart_initialized = False

        self.setupUi()
        self.connect_signal_slots()

        self.floating_window = FloatingWindow()
        # self.floating_window.show()

        self._voltage_is_updating = False
        self._voltage_is_updateing_by_present = False

    def setupUi(self):
        self.ui.setupUi(self)

        # Initialize the chart in groupBox_8
        self._setup_chart()

        available_ports, perfered_index = self.presenter.get_available_ports()
        self.ui.com_num_comboBox.addItems(available_ports)
    
    def _setup_chart(self):
        """Initialize the voltage and current chart in groupBox_8"""
        # Create layout for groupBox_8
        layout = QVBoxLayout()
        self.ui.groupBox_8.setLayout(layout)
        
        # Create chart view
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        
        # Create chart
        self.chart = QChart()
        self.chart.setTitle("Voltage and Current Waveform")
        self.chart.setAnimationOptions(QChart.SeriesAnimations)
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)
        
        # Create voltage series
        self.voltage_series = QLineSeries()
        self.voltage_series.setName("Voltage (V)")
        self.voltage_series.setColor(QColor(255, 99, 132))  # Red
        self.voltage_series.setPointsVisible(False)  # Hide points by default
        
        # Create current series
        self.current_series = QLineSeries()
        self.current_series.setName("Current (A)")
        self.current_series.setColor(QColor(54, 162, 235))  # Blue
        self.current_series.setPointsVisible(False)  # Hide points by default
        
        # Add series to chart
        self.chart.addSeries(self.voltage_series)
        self.chart.addSeries(self.current_series)
        
        # Create axes
        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("Sample Point")
        self.axis_x.setRange(0, 100)
        self.axis_x.setTickCount(11)  # Show 11 ticks (0-100 with step 10)
        
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("Value")
        self.axis_y.setRange(0, 5)  # Will be adjusted dynamically
        self.axis_y.setTickCount(11)
        
        # Attach axes to series
        self.voltage_series.attachAxis(self.axis_x)
        self.voltage_series.attachAxis(self.axis_y)
        self.current_series.attachAxis(self.axis_x)
        self.current_series.attachAxis(self.axis_y)

        self.chart.setAxisX(self.axis_x, self.voltage_series)
        self.chart.setAxisY(self.axis_y, self.voltage_series)

        self.chart.setAxisX(self.axis_x, self.current_series)
        self.chart.setAxisY(self.axis_y, self.current_series)
        
        # Enable hover events for data points
        self.voltage_series.hovered.connect(self._on_series_hovered)
        self.current_series.hovered.connect(self._on_series_hovered)
        
        # Add chart to view
        self.chart_view.setChart(self.chart)
        
        # Add chart view to layout
        layout.addWidget(self.chart_view)
        
        # Create tooltip label
        self.tooltip_label = QLabel()
        self.tooltip_label.setAlignment(Qt.AlignCenter)
        self.tooltip_label.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.9);
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
                font-size: 12px;
            }
        """)
        self.tooltip_label.hide()
        layout.addWidget(self.tooltip_label)
        
        # Initialize with empty data points
        # initial_points = [QPointF(i, v) for i, v in zip(range(self.max_data_points), range(self.max_data_points))]
        # self.voltage_series.replace(initial_points)
        
        # initial_points = [QPointF(i, v) for i, v in zip(range(self.max_data_points), range(self.max_data_points, 0, -1))]
        # self.current_series.replace(initial_points)

        self.voltage_series.clear()
        self.current_series.clear()
        
        self._chart_initialized = True

    def connect_signal_slots(self):


        self.ui.voltage_spinBox.valueChanged.connect(self.on_voltage_spinbox_value_changed)
        self.ui.voltage_dial.valueChanged.connect(self.on_voltage_dial_value_changed)
        self.ui.connect_Btn.clicked.connect(self.presenter.open_device)
        self.ui.disconnect_Btn.clicked.connect(self.presenter.close_device)
        self.ui.ouput_ctrl_Btn.clicked.connect(lambda v: self.presenter.set_on_off(v))

        self.ui.max_voltage_spinbox.valueChanged.connect(lambda value: self.ui.voltage_spinBox.setMaximum(value))
        self.ui.max_voltage_spinbox.valueChanged.connect(lambda value: self.ui.voltage_dial.setMaximum(value*100))
        
        # Connect chart hover events for legend interaction
        # self.chart.legend().hovered.connect(self._on_legend_hovered)
        # self.ui.max_voltage_spinbox.valueChanged.connect(self.presenter.set_max_voltage)
        # self.ui.max_current_spinBox.valueChanged.connect(self.presenter.set_max_current)
        pass
    
    @Slot(QAbstractSeries, bool)
    def _on_legend_hovered(self, series: QAbstractSeries, state: bool):
        """Handle legend hover events to highlight/unhighlight series"""
        if state:
            # Highlight the hovered series
            series.setOpacity(1.0)
            series.setPointsVisible(True)
            # Dim other series
            if series == self.voltage_series:
                self.current_series.setOpacity(0.3)
            else:
                self.voltage_series.setOpacity(0.3)
        else:
            # Reset all series
            self.voltage_series.setOpacity(1.0)
            self.current_series.setOpacity(1.0)
            self.voltage_series.setPointsVisible(False)
            self.current_series.setPointsVisible(False)

    @Slot(QAbstractSeries, bool)
    def _on_series_hovered(self, series: QAbstractSeries, state: bool):
        """Handle series hover events to show/hide data point tooltips"""
        if state:
            # Get the current point coordinates
            points = series.pointsVector()
            for point in points:
                if point.x() == series.atX():  # Find hovered point
                    value = point.y()
                    series_name = "Voltage" if series == self.voltage_series else "Current"
                    unit = "V" if series == self.voltage_series else "A"
                    
                    # Show tooltip
                    self.tooltip_label.setText(f"{series_name}: {value:.2f} {unit}\nPoint: {int(point.x())}")
                    self.tooltip_label.show()
                    
                    # Highlight this series
                    series.setPointsVisible(True)
                    series.setOpacity(1.0)
                    
                    # Dim other series
                    if series == self.voltage_series:
                        self.current_series.setOpacity(0.3)
                    else:
                        self.voltage_series.setOpacity(0.3)
                    
                    break
        else:
            # Hide tooltip and reset series
            self.tooltip_label.hide()
            self.voltage_series.setOpacity(1.0)
            self.current_series.setOpacity(1.0)
            self.voltage_series.setPointsVisible(False)
            self.current_series.setPointsVisible(False)

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
        
        if self._voltage_is_updating:
            return
        self._voltage_is_updating = True
        self.ui.voltage_dial.setValue(value*100)
        self._voltage_is_updating = False
    

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

    def update_voltage_setting(self, value: float):
        # self.ui.voltage_dial.setValue(value*100)
        self.ui.voltage_spinBox.setValue(value)

    def update_max_voltage(self, value: float):
        self._voltage_is_updateing_by_present = True
        self.on_voltage_spinbox_value_changed(value)
        self._voltage_is_updateing_by_present = False

    def _update_chart_data(self, value: float, data_type: str):
        """Update chart with new voltage or current data point"""
        if not self._chart_initialized:
            return
        
        # Add new data point
        if data_type == "voltage":
            logger.info(f"Adding new voltage data point: {value:.2f} @ {self.voltage_data_count}")
            self.voltage_series.append(QPointF(self.voltage_data_count, value))
            self.voltage_data_count += 1

            self.voltage_data.append(value)
            # Keep only the last max_data_points
            if len(self.voltage_data) > self.max_data_points:
                self.voltage_data.pop(0)
        elif data_type == "current":
            logger.info(f"Adding new current data point: {value:.2f} @ {self.current_data_count}")
            self.current_series.append(QPointF(self.current_data_count, value))
            self.current_data_count += 1

            self.current_data.append(value)
            # Keep only the last max_data_points
            if len(self.current_data) > self.max_data_points:
                self.current_data.pop(0)
        

        # Update time axis
        # self.time_data.append(len(self.voltage_data))
        # if len(self.time_data) > self.max_data_points:
        #     self.time_data.pop(0)
        
        x_min = self.current_data_count - 100 if self.current_data_count > 100 else 0
        self.axis_x.setRange(x_min, self.current_data_count)
        # Update series data using QPointF
        # voltage_points = [QPointF(i, v) for i, v in enumerate(self.voltage_data)]
        # current_points = [QPointF(i, c) for i, c in enumerate(self.current_data)]
        
        # self.voltage_series.replace(voltage_points)
        # self.current_series.replace(current_points)

        # self.voltage_series.append(QPointF(len(self.voltage_data), self.voltage_data))
        
        # Adjust Y-axis range dynamically based on data
        # max_voltage = max(self.voltage_data) if self.voltage_data else 30
        # max_current = max(self.current_data) if self.current_data else 10
        # max_value = max(max_voltage, max_current * 3)  # Scale current to be visible alongside voltage
        
        # Set axis range with some padding
        # self.axis_y.setRange(0, max_value * 1.1)

    def update_max_current_setting(self, value: float):
        self.ui.max_current_spinBox.setValue(value)

    def update_device_id(self, value: str):
        self.ui.device_info_lineEdit.setText(value)

    
    def _set_ctrl_widget_enable(self, enable: bool):
        self.ui.ouput_ctrl_Btn.setEnabled(enable)
        self.ui.max_voltage_spinbox.setEnabled(enable)
        self.ui.max_current_spinBox.setEnabled(enable)
        self.ui.voltage_spinBox.setEnabled(enable)
        self.ui.voltage_dial.setEnabled(enable)
        self.ui.volatage_label.setEnabled(enable)
        self.ui.current_label.setEnabled(enable)
