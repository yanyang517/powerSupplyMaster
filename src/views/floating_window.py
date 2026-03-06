from PySide6.QtWidgets import QWidget, QMenu
from PySide6.QtCore import Qt, Signal, Slot

from ui.floating_classic import Ui_Dialog


class FloatingWindow(QWidget):
    doubleClicked = Signal()

    def __init__(self):
        super().__init__(flags=Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.ui = Ui_Dialog(self)
        self.current_value = 0.0
        self.output_value = True

        self.customContextMenuRequested.connect(self.showContextMenu)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

    def showContextMenu(self, pos):
        menu = QMenu(self)
        menu.addAction("显示主窗口", self.close)
        menu.addAction("关闭电压输出", self.close)
        menu.addAction("隐藏悬浮窗", self.close)
        menu.exec(self.mapToGlobal(pos))

    @Slot(int)
    def update_transparency(self, value: int):
        self.setWindowOpacity(value / 100)

    @Slot(bool)
    def update_output(self, on: bool):
        self.output_value = on
        if on:
            self.ui.current_label.setText(f"{self.current_value:.2f} A")
        else:
            self.ui.current_label.setText("OFF")   # reuse current_label to indicate output state

    @Slot(float)
    def update_voltage(self, voltage: float):
        self.ui.voltage_label.setText(f"{voltage:.2f} V")
    
    @Slot(float)
    def update_current(self, current: float):
        self.current_value = current
        if self.output_value:
            self.ui.current_label.setText(f"{current:.2f} A")

    @Slot(float, float)
    def update_values(self, voltage: float, current: float):
        self.update_voltage(voltage)
        self.update_current(current)
