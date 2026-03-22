from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QDoubleSpinBox,
    QPushButton,
)

from .ui.mainWindow import Ui_MainWindow
from .floating_window import FloatingWindow

class MainWindow(QMainWindow):
    def __init__(self, presenter = None):
        super().__init__()
        self.presenter = presenter
        self.ui = Ui_MainWindow()

        self.setupUi()
        self.connect_signal_slots()

        self.floating_window = FloatingWindow()
        # self.floating_window.show()

    def setupUi(self):
        self.ui.setupUi(self)

        available_ports, perfered_index = self.presenter.get_available_ports()
        self.ui.com_num_comboBox.addItems(available_ports)

    def connect_signal_slots(self):


        self.ui.voltage_spinBox.valueChanged.connect(self.presenter.set_voltage)
        self.ui.voltage_dial.valueChanged.connect(self.presenter.set_voltage)
        self.ui.connect_Btn.clicked.connect(self.presenter.open_device)
        self.ui.disconnect_Btn.clicked.connect(self.presenter.close_device)

        # self.ui.max_voltage_spinbox.valueChanged.connect(self.presenter.set_max_voltage)
        # self.ui.max_current_spinBox.valueChanged.connect(self.presenter.set_max_current)
        pass
    
    def update_voltage(self, value: float):
        """
        更新当前电压
        """
        self.ui.volatage_label.setText(f"{value:.2f} V")
        self.floating_window.update_voltage(value)

    def update_voltage_setting(self, value: float):
        self.ui.voltage_dial.setValue(value)
        self.ui.voltage_spinBox.setValue(value)

    def update_max_voltage(self, value: float):
        self.ui.max_voltage_spinbox.setValue(value)

    def update_current(self, value: float):
        """
        更新当前电流
        """
        self.ui.current_label.setText(f"{value:.2f} A")
        self.floating_window.update_current(value)

    def update_max_current_setting(self, value: float):
        self.ui.max_current_spinBox.setValue(value)


