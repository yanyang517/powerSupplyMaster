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
        self.floating_window.show()

    def setupUi(self):
        self.ui.setupUi(self)

    def connect_signal_slots(self):


        # dial and spinbox
        # self.ui.dial.valueChanged.connect(self.presenter.on_dial_value_changed)
        
        pass