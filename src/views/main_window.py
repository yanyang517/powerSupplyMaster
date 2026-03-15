from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QDoubleSpinBox,
    QPushButton,
)


class MainWindow(QMainWindow):
    def __init__(self, presenter = None):
        super().__init__()
        self.presenter = presenter
        self.setWindowTitle("Power Supply Master")
        self.resize(600, 400)
        central = QWidget()
        layout = QVBoxLayout(central)
        self.status_label = QLabel("Disconnected")
        layout.addWidget(self.status_label)

        # controls for voltage/current
        ctrl_layout = QHBoxLayout()
        self.voltage_spin = QDoubleSpinBox()
        self.voltage_spin.setPrefix("V: ")
        self.voltage_spin.setRange(0, 1000)
        self.current_spin = QDoubleSpinBox()
        self.current_spin.setPrefix("I: ")
        self.current_spin.setRange(0, 100)
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._on_apply)
        ctrl_layout.addWidget(self.voltage_spin)
        ctrl_layout.addWidget(self.current_spin)
        ctrl_layout.addWidget(self.apply_button)
        layout.addLayout(ctrl_layout)

        self.setCentralWidget(central)

    def update_status(self, text: str):
        self.status_label.setText(text)

    def _on_apply(self):
        v = self.voltage_spin.value()
        i = self.current_spin.value()
        if self.presenter:
            self.presenter.apply_settings(voltage=v, current=i)
