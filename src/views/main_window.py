from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QDoubleSpinBox,
    QPushButton,
)

from PySide6.QtCore import Slot

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

        self._voltage_is_updating = False
        self._voltage_is_updateing_by_present = False

    def setupUi(self):
        self.ui.setupUi(self)

        available_ports, perfered_index = self.presenter.get_available_ports()
        self.ui.com_num_comboBox.addItems(available_ports)
    
    def connect_signal_slots(self):


        self.ui.voltage_spinBox.valueChanged.connect(self.on_voltage_spinbox_value_changed)
        self.ui.voltage_dial.valueChanged.connect(self.on_voltage_dial_value_changed)
        self.ui.connect_Btn.clicked.connect(self.presenter.open_device)
        self.ui.disconnect_Btn.clicked.connect(self.presenter.close_device)
        self.ui.ouput_ctrl_Btn.clicked.connect(lambda v: self.presenter.set_on_off(v))

        self.ui.max_voltage_spinbox.valueChanged.connect(lambda value: self.ui.voltage_spinBox.setMaximum(value))
        self.ui.max_voltage_spinbox.valueChanged.connect(lambda value: self.ui.voltage_dial.setMaximum(value*100))
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

    def update_voltage_setting(self, value: float):
        # self.ui.voltage_dial.setValue(value*100)
        self.ui.voltage_spinBox.setValue(value)

    def update_max_voltage(self, value: float):
        self._voltage_is_updateing_by_present = True
        self.on_voltage_spinbox_value_changed(value)
        self._voltage_is_updateing_by_present = False


    def update_current(self, value: float):
        """
        更新当前电流
        """
        self.ui.current_label.setText(f"{value:.2f} A")
        self.floating_window.update_current(value)

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
