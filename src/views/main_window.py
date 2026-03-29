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
        """Initialize separate voltage and current charts in groupBox_8"""
        # Create main vertical layout for groupBox_8
        main_layout = QVBoxLayout()
        main_layout.setSpacing(6)  # Add spacing between charts
        self.ui.groupBox_8.setLayout(main_layout)
        
        # ===== Voltage Chart Setup =====
        # Create voltage chart view
        self.voltage_chart_view = QChartView()
        self.voltage_chart_view.setRenderHint(QPainter.Antialiasing)
        
        # Create voltage chart
        self.voltage_chart = QChart()
        self.voltage_chart.setTitle("电压曲线")
        self.voltage_chart.setAnimationOptions(QChart.SeriesAnimations)
        self.voltage_chart.legend().setVisible(False)
        # self.voltage_chart.legend().setAlignment(Qt.AlignLeft)
        
        # Create voltage series
        self.voltage_series = QLineSeries()
        self.voltage_series.setName("Voltage (V)")
        self.voltage_series.setColor(QColor(255, 99, 132))  # Red
        self.voltage_series.setPointsVisible(False)
        
        # Add series to voltage chart
        self.voltage_chart.addSeries(self.voltage_series)
        
        # Create X axis for voltage
        self.voltage_axis_x = QValueAxis()
        # self.voltage_axis_x.setTitleText("Sample Point")
        self.voltage_axis_x.setRange(0, self.max_data_points - 1)
        self.voltage_axis_x.setTickCount(11)
        
        # Create Y axis for voltage
        self.voltage_axis_y = QValueAxis()
        # self.voltage_axis_y.setTitleText("Voltage (V)")
        self.voltage_axis_y.setRange(0, 20)
        self.voltage_axis_y.setTickCount(7)
        self.voltage_axis_y.setTitleBrush(QColor(255, 99, 132))
        self.voltage_axis_y.setLabelsColor(QColor(255, 99, 132))
        
        # Attach axes to voltage series
        self.voltage_chart.setAxisX(self.voltage_axis_x, self.voltage_series)
        self.voltage_chart.setAxisY(self.voltage_axis_y, self.voltage_series)
        
        # Enable hover events for voltage series
        self.voltage_series.hovered.connect(self._on_voltage_series_hovered)
        
        # Add voltage chart to view
        self.voltage_chart_view.setChart(self.voltage_chart)
        
        # Create voltage tooltip label
        self.voltage_tooltip_label = QLabel()
        self.voltage_tooltip_label.setAlignment(Qt.AlignCenter)
        self.voltage_tooltip_label.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.9);
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
                font-size: 12px;
            }
        """)
        self.voltage_tooltip_label.hide()
        
        # Add voltage chart and tooltip to layout
        main_layout.addWidget(self.voltage_chart_view)
        main_layout.addWidget(self.voltage_tooltip_label)
        
        # ===== Current Chart Setup =====
        # Create current chart view
        self.current_chart_view = QChartView()
        self.current_chart_view.setRenderHint(QPainter.Antialiasing)
        
        # Create current chart
        self.current_chart = QChart()
        self.current_chart.setTitle("电流曲线")
        self.current_chart.setAnimationOptions(QChart.SeriesAnimations)
        self.current_chart.legend().setVisible(False)
        # self.current_chart.legend().setAlignment(Qt.AlignLeft)
        
        # Create current series
        self.current_series = QLineSeries()
        self.current_series.setName("Current (A)")
        self.current_series.setColor(QColor(54, 162, 235))  # Blue
        self.current_series.setPointsVisible(False)
        
        # Add series to current chart
        self.current_chart.addSeries(self.current_series)
        
        # Create X axis for current
        self.current_axis_x = QValueAxis()
        self.current_axis_x.setTitleText("Sample Point")
        self.current_axis_x.setRange(0, self.max_data_points - 1)
        self.current_axis_x.setTickCount(11)
        
        # Create Y axis for current
        self.current_axis_y = QValueAxis()
        self.current_axis_y.setTitleText("Current (A)")
        self.current_axis_y.setRange(0, 10)
        self.current_axis_y.setTickCount(6)
        self.current_axis_y.setTitleBrush(QColor(54, 162, 235))
        self.current_axis_y.setLabelsColor(QColor(54, 162, 235))
        
        # Attach axes to current series
        self.current_chart.setAxisX(self.current_axis_x, self.current_series)
        self.current_chart.setAxisY(self.current_axis_y, self.current_series)
        
        # Enable hover events for current series
        self.current_series.hovered.connect(self._on_current_series_hovered)
        
        # Add current chart to view
        self.current_chart_view.setChart(self.current_chart)
        
        # Create current tooltip label
        self.current_tooltip_label = QLabel()
        self.current_tooltip_label.setAlignment(Qt.AlignCenter)
        self.current_tooltip_label.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.9);
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
                font-size: 12px;
            }
        """)
        self.current_tooltip_label.hide()
        
        # Add current chart and tooltip to layout
        main_layout.addWidget(self.current_chart_view)
        main_layout.addWidget(self.current_tooltip_label)
        
        # Initialize with empty data points
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
    def _on_voltage_series_hovered(self, series: QAbstractSeries, state: bool):
        """Handle voltage series hover events to show/hide data point tooltips"""
        if state:
            # Get the current point coordinates
            points = series.pointsVector()
            for point in points:
                if point.x() == series.atX():  # Find hovered point
                    value = point.y()
                    
                    # Show tooltip
                    self.voltage_tooltip_label.setText(f"Voltage: {value:.2f} V\nPoint: {int(point.x())}")
                    self.voltage_tooltip_label.show()
                    
                    # Highlight this series
                    series.setPointsVisible(True)
                    series.setOpacity(1.0)
                    
                    break
        else:
            # Hide tooltip and reset series
            self.voltage_tooltip_label.hide()
            self.voltage_series.setOpacity(1.0)
            self.voltage_series.setPointsVisible(False)

    @Slot(QAbstractSeries, bool)
    def _on_current_series_hovered(self, series: QAbstractSeries, state: bool):
        """Handle current series hover events to show/hide data point tooltips"""
        if state:
            # Get the current point coordinates
            points = series.pointsVector()
            for point in points:
                if point.x() == series.atX():  # Find hovered point
                    value = point.y()
                    
                    # Show tooltip
                    self.current_tooltip_label.setText(f"Current: {value:.2f} A\nPoint: {int(point.x())}")
                    self.current_tooltip_label.show()
                    
                    # Highlight this series
                    series.setPointsVisible(True)
                    series.setOpacity(1.0)
                    
                    break
        else:
            # Hide tooltip and reset series
            self.current_tooltip_label.hide()
            self.current_series.setOpacity(1.0)
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
            self.voltage_series.append(QPointF(self.voltage_data_count, value))
            self.voltage_data_count += 1

            self.voltage_data.append(value)
            # Keep only the last max_data_points
            if len(self.voltage_data) > self.max_data_points:
                self.voltage_data.pop(0)
                
            # Update X axis range to show rolling window effect
            x_min = self.voltage_data_count - self.max_data_points if self.voltage_data_count > self.max_data_points else 0
            x_max = self.voltage_data_count if self.voltage_data_count > 100 else 100
            self.voltage_axis_x.setRange(x_min, x_max)
            
            # Update voltage axis range dynamically
            # max_voltage = max(self.voltage_data) if self.voltage_data else 5
            # min_voltage = min(self.voltage_data) if self.voltage_data else 0
            # padding = (max_voltage - min_voltage) * 0.1 if max_voltage != min_voltage else 0.5
            # self.voltage_axis_y.setRange(max(0, min_voltage - padding), max_voltage + padding)
            
        elif data_type == "current":
            self.current_series.append(QPointF(self.current_data_count, value))
            self.current_data_count += 1

            self.current_data.append(value)
            # Keep only the last max_data_points
            if len(self.current_data) > self.max_data_points:
                self.current_data.pop(0)
            
            # Update X axis range to show rolling window effect
            x_min = self.current_data_count - self.max_data_points if self.current_data_count > self.max_data_points else 0
            x_max = self.current_data_count if self.current_data_count > 100 else 100
            self.current_axis_x.setRange(x_min, x_max)
            
            # Update current axis range dynamically
            # max_current = max(self.current_data) if self.current_data else 2
            # min_current = min(self.current_data) if self.current_data else 0
            # padding = (max_current - min_current) * 0.1 if max_current != min_current else 0.2
            # self.current_axis_y.setRange(max(0, min_current - padding), max_current + padding)
