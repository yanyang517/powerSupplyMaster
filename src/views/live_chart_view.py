"""实时波形图表：统一深色外观，并提供缩放、复位和采样点提示。"""

from math import hypot

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import QLabel

from .theme import tokens


class LiveChartView(QChartView):
    """一张以采样序号为横轴的实时曲线视图。"""

    def __init__(
        self,
        title: str,
        color: str,
        unit: str,
        *,
        window_size: int = 100,
        y_range: tuple[float, float] = (0.0, 20.0),
        x_title: str = "",
        y_title: str = "",
        x_ticks: int = 11,
        y_ticks: int = 7,
        parent=None,
    ):
        super().__init__(parent)
        palette = tokens("dark")
        self._unit = unit
        self._window_size = window_size
        self._default_y_range = y_range
        self._zoom_factor = 1.2
        self._pen_color = QColor(color)
        self._auto_follow = True
        self._latest_index = 0

        chart = QChart()
        chart.setTitle(title)
        chart.setTitleBrush(QColor(palette["text"]))
        chart.setBackgroundBrush(QBrush(QColor(palette["plate"])))
        chart.setBackgroundRoundness(6)
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        chart.legend().setVisible(False)

        self.setChart(chart)
        self.setBackgroundBrush(QBrush(QColor(palette["plate"])))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.viewport().setMouseTracking(True)

        self.tooltip = QLabel(self.viewport())
        self.tooltip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.tooltip.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.tooltip.setMargin(6)
        self.tooltip.setTextFormat(Qt.TextFormat.PlainText)
        self.tooltip.setStyleSheet(
            f"background-color: {palette['surface']}; color: {palette['text']};"
            f"border: 1px solid {palette['border']}; border-radius: 4px;"
        )
        self.tooltip.hide()

        self.series = QLineSeries()
        self.series.setName(f"{title} ({unit})")
        self.series.setColor(self._pen_color)
        self.series.setPointsVisible(False)
        chart.addSeries(self.series)

        self.axis_x = QValueAxis()
        self.axis_x.setTitleText(x_title)
        self.axis_x.setRange(0, window_size - 1)
        self.axis_x.setTickCount(x_ticks)
        self.axis_x.setLinePenColor(QColor(palette["border"]))
        self.axis_x.setGridLineColor(QColor(palette["border"]))
        self.axis_x.setLabelsColor(QColor(palette["text_dim"]))

        self.axis_y = QValueAxis()
        self.axis_y.setTitleText(y_title)
        self.axis_y.setRange(*y_range)
        self.axis_y.setTickCount(y_ticks)
        self.axis_y.setTitleBrush(self._pen_color)
        self.axis_y.setLabelsColor(self._pen_color)
        self.axis_y.setLinePenColor(QColor(palette["border"]))
        self.axis_y.setGridLineColor(QColor(palette["border"]))

        chart.setAxisX(self.axis_x, self.series)
        chart.setAxisY(self.axis_y, self.series)

    @property
    def auto_follow(self) -> bool:
        return self._auto_follow

    def replace_points(self, points) -> None:
        """替换当前滚动窗口，数据裁剪仍由调用方负责。"""
        self.hide_tooltip()
        self.series.replace(list(points))

    def follow_latest(self, latest_index: int) -> None:
        """自动跟随开启时，把横轴移动到以最新采样序号结尾的窗口。"""
        self._latest_index = max(0, int(latest_index))
        if not self._auto_follow:
            return
        upper = max(float(self._latest_index), float(self._window_size))
        lower = max(0.0, upper - self._window_size)
        self.axis_x.setRange(lower, upper)

    def _value_at(self, position: QPointF):
        """把视口位置映射到绘图区内的数据坐标。"""
        chart = self.chart()
        scene_position = chart.mapToScene(position)
        if not chart.plotArea().contains(scene_position):
            return None
        return chart.mapToValue(scene_position, self.series)

    def _zoom_axis(
        self,
        axis: QValueAxis,
        anchor: float,
        delta: int,
        *,
        bounds: tuple[float, float],
        min_span: float,
    ) -> None:
        """围绕数据锚点缩放，并把结果限制在目标轴的允许范围内。"""
        factor = self._zoom_factor if delta > 0 else 1.0 / self._zoom_factor
        old_min, old_max = axis.min(), axis.max()
        old_span = old_max - old_min
        span = old_span / factor
        span = max(min_span, min(span, bounds[1] - bounds[0]))
        ratio = (anchor - old_min) / old_span if old_span else 0.5
        lower = anchor - ratio * span
        lower = max(bounds[0], min(lower, bounds[1] - span))
        axis.setRange(lower, lower + span)

    def wheelEvent(self, event: QWheelEvent) -> None:
        modifiers = event.modifiers()
        delta = event.angleDelta().y()
        if (
            not self.isEnabled()
            or self.series.count() == 0
            or delta == 0
            or not (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        ):
            super().wheelEvent(event)
            return

        value = self._value_at(event.position())
        if value is None:
            super().wheelEvent(event)
            return

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            points = self.series.pointsVector()
            lower, upper = min(point.x() for point in points), max(point.x() for point in points)
            if upper - lower < 2.0:
                center = (lower + upper) / 2.0
                lower, upper = center - 1.0, center + 1.0
            self._zoom_axis(
                self.axis_x,
                value.x(),
                delta,
                bounds=(lower, upper),
                min_span=2.0,
            )
            self._auto_follow = False
        else:
            lower, upper = self._default_y_range
            self._zoom_axis(
                self.axis_y,
                value.y(),
                delta,
                bounds=(lower, upper),
                min_span=(upper - lower) * 0.02,
            )
        event.accept()

    def reset_view(self) -> None:
        """恢复默认双轴范围并重新开启横轴实时跟随。"""
        self.axis_x.setRange(0.0, float(self._window_size))
        self.axis_y.setRange(*self._default_y_range)
        self._auto_follow = True
        self.follow_latest(self._latest_index)
        self.hide_tooltip()

    def hide_tooltip(self) -> None:
        self.tooltip.hide()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        if not enabled:
            self.hide_tooltip()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.isEnabled() or self._value_at(event.position()) is None:
            self.hide_tooltip()
            super().mouseMoveEvent(event)
            return

        position = event.position()
        chart = self.chart()
        plot_area = chart.plotArea()
        nearest = None
        nearest_distance = 10.0
        for point in self.series.pointsVector():
            screen_position = chart.mapToPosition(point, self.series)
            if not plot_area.contains(screen_position):
                continue
            distance = hypot(screen_position.x() - position.x(), screen_position.y() - position.y())
            if distance <= nearest_distance:
                nearest = point
                nearest_distance = distance

        if nearest is None:
            self.hide_tooltip()
        else:
            self.tooltip.setText(
                f"采样点 {nearest.x():g}\n{nearest.y():.2f} {self._unit}"
            )
            self.tooltip.adjustSize()
            x = min(max(8, int(position.x()) + 12), max(8, self.viewport().width() - self.tooltip.width() - 8))
            y = min(max(8, int(position.y()) + 12), max(8, self.viewport().height() - self.tooltip.height() - 8))
            self.tooltip.move(x, y)
            self.tooltip.show()
            self.tooltip.raise_()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self.hide_tooltip()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.isEnabled():
            self.reset_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
