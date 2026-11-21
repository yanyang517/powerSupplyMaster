from PySide6.QtWidgets import QWidget, QMenu, QMainWindow
from PySide6.QtCore import Qt, Signal, Slot

from .ui.floating_classic_ui import Ui_Dialog
from . import icons
from . import window_geometry as wg


class FloatingWindow(QMainWindow):
    doubleClicked = Signal()
    # 悬浮窗不持有 presenter，也不反向找主窗口：动作交给宿主接线，和 doubleClicked 同一套路。
    request_show_main = Signal()
    request_output_off = Signal()

    def __init__(self):
        super().__init__(flags=Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        # Create a central widget for the QMainWindow
        self._central_widget = QWidget(self)
        self.setCentralWidget(self._central_widget)
        
        self.ui = Ui_Dialog()
        self.ui.setupUi(self._central_widget)
        self.current_value = 0.0
        self.output_value = True

        self._transparency = 0.2

        self.setWindowOpacity(self._transparency)

        self._central_widget.customContextMenuRequested.connect(self.showContextMenu)
        
        # For drag-to-move functionality
        self._drag_pos = None
        
        # Set fixed size to match the UI design
        self.setFixedSize(407, 81)

        # 无边框窗口没有地方显示它，但任务栏预览与截图取的是这个图标；设置图标本身
        # 不会给 FramelessWindowHint 加回任何装饰。
        self.setWindowIcon(icons.app_icon())

        self._restore_position()

        # Set distinct colors for voltage and current labels
        # Voltage: Bright Blue - highly visible on both white and black backgrounds
        self.ui.voltage_label.setStyleSheet("color: rgb(0, 123, 255); font-weight: bold;")
        # Current: Teal/Cyan - visible on both white and black backgrounds
        self.ui.current_label.setStyleSheet("color: rgb(0, 139, 139); font-weight: bold;")

        self.repaint()

    def _restore_position(self):
        """Place the window from history, else at the bottom-right of the screen."""
        entries = wg.load_entries(wg.geometry_file_path())
        rect = wg.restored_rect(entries, "floating", self.width(), self.height())
        if rect is not None:
            self.move(rect[0], rect[1])
            return
        available = wg.primary_available_rect()
        if available is not None:
            self.move(*wg.default_floating_pos(available, self.width(), self.height()))

    # change transparency when mouse over
    def enterEvent(self, event):
        new_transparency = self._transparency + 0.1 
        new_transparency = new_transparency if new_transparency < 1.0 else 1.0
        self.setWindowOpacity(new_transparency)
        super().enterEvent(event)
    def leaveEvent(self, event):
        self.setWindowOpacity(self._transparency)
        super().leaveEvent(event)

    # impl drag to move
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Store the offset between mouse position and window top-left corner
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            # Move window to global mouse position minus the stored offset
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
            
            
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        # Reset drag position when mouse is released
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

    def buildContextMenu(self) -> QMenu:
        """菜单构造与弹出分开：`QMenu.exec` 是模态原生调用，Shiboken 层面拦不住，
        测试只能拿到这个构建入口来逐项验证动作落点。"""
        menu = QMenu(self)
        for text, glyph, handler in (
            ("显示主窗口", "tabler/window", self._ask_show_main),
            ("关闭电源输出", "tabler/power", self._ask_output_off),
            ("隐藏悬浮窗", "tabler/eye-off", self.close),
        ):
            menu.addAction(icons.icon(glyph, "text", 16), text).triggered.connect(handler)
        return menu

    def showContextMenu(self, pos):
        self.buildContextMenu().exec(self.mapToGlobal(pos))

    def _ask_show_main(self):
        self.request_show_main.emit()

    def _ask_output_off(self):
        self.request_output_off.emit()

    @Slot(int)
    def update_transparency(self, value: int):
        """Update the window transparency."""
        value = min(100, max(0, value))
        self._transparency = value / 100
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
