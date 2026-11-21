"""自绘深色旋钮。

`Fusion` 的 `drawDial` 既不读样式表也不读 palette：把单个 `QDial` 的九个 palette
角色全设成近黑，盘体仍渲染为中亮蓝灰（见 design.md D5 的实测记录）。深色面板里
它是唯一压不暗的一块，因此盘体只能在 `paintEvent` 里自己画。

交互仍归 `QDial`：本类不重写鼠标与滚轮事件，所以取值手感、键盘步进都保持原样。
绘制用的角度必须与 Qt 自身一致，否则指示点位置会和拖拽算出的 value 错位。
"""

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QDial

from .theme import tokens

# 与 qtbase 的 qdial.cpp 保持一致：起始 225°、终止 -15°、张角 240°（数学角，逆时针为正）。
_START_ANGLE = 225.0
_SPAN_ANGLE = 240.0

# 各元素相对盘体半径的位置，集中在此便于整体调参。
_OUTER_RING = 1.0
_NOTCH_OUTER = 0.95
_NOTCH_INNER = 0.86
_POINTER_OUTER = 0.62
_POINTER_INNER = 0.20
_HANDLE = 0.70


class DarkDial(QDial):
    def __init__(self, mode: str = "dark", parent=None):
        super().__init__(parent)
        self._tokens = tokens(mode)

    def sizeHint(self):
        return QSize(160, 160)

    def minimumSizeHint(self):
        return QSize(80, 80)

    def paintEvent(self, event):
        span = self.maximum() - self.minimum()
        frac = 0.0 if span <= 0 else (self.value() - self.minimum()) / span
        angle = math.radians(_START_ANGLE - _SPAN_ANGLE * frac)

        t = self._tokens
        face = QColor(t["plate"])
        ring = QColor(t["border_strong"])
        accent = QColor(t["primary"]) if self.isEnabled() else QColor(t["text_dim"])

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side = min(self.width(), self.height()) - 4
        radius = side / 2.0
        center = QRectF(self.rect()).center()
        dial = QRectF(center.x() - radius, center.y() - radius, side, side)

        painter.setPen(QPen(ring, 1))
        painter.setBrush(face)
        painter.drawEllipse(dial)

        if self.notchesVisible() and span > 0:
            self._draw_notches(painter, center, radius, span)

        # 指针线让读数在远距离下也能判向，仅靠指示点在深色底上不易分辨。
        painter.setPen(QPen(accent, 2, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(
            self._point(center, radius, angle, _POINTER_INNER),
            self._point(center, radius, angle, _POINTER_OUTER),
        )

        handle = self._point(center, radius, angle, _HANDLE)
        dot = min(radius * 0.11, 9.0)
        painter.setPen(QPen(ring, 1))
        painter.setBrush(face)
        painter.drawEllipse(handle, dot + 2.0, dot + 2.0)
        painter.setBrush(accent)
        painter.drawEllipse(handle, dot, dot)
        painter.end()

    def _draw_notches(self, painter, center, radius, span):
        t = self._tokens
        painter.setPen(QPen(QColor(t["text_dim"]), 1))
        target = self.notchTarget() or 10.0
        count = max(int(span / target), 1)
        for i in range(count + 1):
            angle = math.radians(_START_ANGLE - _SPAN_ANGLE * i / count)
            painter.drawLine(
                self._point(center, radius, angle, _NOTCH_INNER),
                self._point(center, radius, angle, _NOTCH_OUTER),
            )

    @staticmethod
    def _point(center, radius, angle, scale):
        # 设备坐标 y 轴向下，故 sin 取负，与 Qt 的绘制约定相同。
        r = radius * scale
        return QPointF(center.x() + r * math.cos(angle), center.y() - r * math.sin(angle))
