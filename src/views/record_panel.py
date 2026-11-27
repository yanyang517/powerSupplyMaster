"""记录面板：使能开关、当前会话状态，以及历史会话的复看。

记录页整页由 Python 构建，沿用 AccessPanel 与 _swap_voltage_dial 的做法，由 MainWindow 在
代码里 addTab 挂上。开关与状态一律以 presenter 的快照为准，面板自己不判断
"该不该在录"，避免两处真相。

复看画的曲线只是抽稀后的包络，放大用的始终是内存里的原始样本：框选之后按更窄的
区间重新抽稀，所以放大看到的是变密的真实数据，而不是被拉伸的折线。
"""

import asyncio
import bisect
import logging

from PySide6.QtCore import Qt, QPoint, QPointF, QMargins, QRect, QSize, QDateTime, Signal
from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QValueAxis
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QRubberBand,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from recording.processing import decimate_min_max
from recording.reader import list_sessions, load_session, split_by_gaps, storage_summary
from recording.settings import NOMINAL_INTERVAL_MS

from .theme import tokens

logger = logging.getLogger(__name__)

# 抽稀桶数的下限：绘图宽度还没定下来时也别把整段压成几根柱子。
MIN_BUCKETS = 240

# 框选宽度小于这个像素数当作误点击，不放大。
MIN_ZOOM_PX = 6

_STATUS_LABELS = {
    "closed": "正常结束",
    "interrupted": "中断",
    "recording": "记录中",
}

_READOUT_EMPTY = "选择左侧会话以载入曲线"


def _format_duration(seconds) -> str:
    """时长写成一眼能读的样子：未知就写未知，而不是拿 0:00:00 冒充零时长会话。"""
    if seconds is None:
        return "—"
    total = int(seconds)
    if total < 60:
        return f"{total} 秒"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} 分 {secs:02d} 秒"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} 时 {minutes:02d} 分"


class RecordPanel(QWidget):
    """记录使能、状态显示与历史复看。"""

    enable_requested = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._applying = False
        self._status: dict = {}
        self._entries: list[dict] = []
        self._samples: list[tuple[int, float, float]] = []
        self._times: list[int] = []
        self._full_span: tuple[int, int] | None = None
        self._zoom_span: tuple[int, int] | None = None
        self._readout_base = _READOUT_EMPTY
        self._nominal_ms = NOMINAL_INTERVAL_MS
        self._load_task = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self._build_switch_area())

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._build_session_list())
        splitter.addWidget(self._build_review_area())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 620])
        layout.addWidget(splitter, 1)

    # --- 使能与状态 -----------------------------------------------------------

    def _build_switch_area(self) -> QWidget:
        box = QWidget(self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.enable_check = QCheckBox("记录电压电流到磁盘", box)
        self.enable_check.toggled.connect(self._on_toggled)
        layout.addWidget(self.enable_check)

        self.status_label = QLabel("未开启记录", box)
        self.status_label.setObjectName("record_status_label")
        layout.addWidget(self.status_label)

        self.dir_label = QLabel("", box)
        self.dir_label.setObjectName("record_dir_label")
        self.dir_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.dir_label.setWordWrap(True)
        layout.addWidget(self.dir_label)

        self.error_label = QLabel("", box)
        self.error_label.setObjectName("record_error_label")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        return box

    def _on_toggled(self, checked: bool) -> None:
        """render() 回放状态时会动到复选框，那一次不算用户操作。"""
        if self._applying:
            return
        self.enable_requested.emit(checked)

    def render(self, status: dict) -> None:
        """按 presenter 的快照重画；记录目录变了就顺带重扫会话列表。"""
        if not status:
            return
        self._applying = True
        self.enable_check.setChecked(bool(status.get("enabled", False)))
        self._applying = False

        self.status_label.setText(self._status_text(status))
        self.dir_label.setText(f"目录：{status.get('dir', '')}")

        error = status.get("error")
        if error:
            self.error_label.setText(f"记录已中止：{error}")
            self.error_label.show()
        else:
            self.error_label.clear()
            self.error_label.hide()

        known_dir = self._status.get("dir")
        was_recording = bool(self._status.get("recording"))
        self._status = dict(status)
        self._nominal_ms = int(status.get("interval_ms") or NOMINAL_INTERVAL_MS)
        if status.get("dir") and status.get("dir") != known_dir:
            # 目录第一次报过来时也要扫：进面板就该看到列表，而不是先点一次
            # "重新扫描"才把盘上事实显示出来。
            self.refresh_sessions()
        elif was_recording and not status.get("recording"):
            # 刚结束的那条会话必须立刻出现在列表里：它的登记信息是这一刻才齐的，
            # 让用户再点一次"重新扫描"才能看见，等于把盘上事实藏起来。
            self.refresh_sessions()

    @staticmethod
    def _status_text(status: dict) -> str:
        if status.get("recording"):
            return f"正在记录：{status.get('file')}（已写入 {status.get('rows', 0)} 条）"
        if status.get("enabled"):
            return "已开启，等待设备连接后开始记录"
        return "未开启记录"

    # --- 会话列表 -------------------------------------------------------------

    def _build_session_list(self) -> QWidget:
        box = QWidget(self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel("历史会话", box)
        title.setObjectName("record_section_label")
        layout.addWidget(title)

        self.session_list = QListWidget(box)
        self.session_list.currentItemChanged.connect(self._on_session_selected)
        layout.addWidget(self.session_list, 1)

        self.capacity_label = QLabel("", box)
        self.capacity_label.setObjectName("record_dir_label")
        layout.addWidget(self.capacity_label)

        self.refresh_button = QPushButton("重新扫描", box)
        self.refresh_button.clicked.connect(self.refresh_sessions)
        layout.addWidget(self.refresh_button)
        return box

    def refresh_sessions(self) -> None:
        """重读清单与容量：盘上事实不缓存，缺失条目只标记不可用而不是消失。"""
        records_dir = self._status.get("dir")
        if not records_dir:
            return
        self._entries = list_sessions(records_dir)
        self.session_list.clear()
        for entry in self._entries:
            item = QListWidgetItem(self._session_text(entry), self.session_list)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            if not entry.get("available"):
                # 仍可看到但选不动：这段数据存在过，只是文件已经不在了。
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setToolTip("数据文件已不在记录目录中")
        if not self._entries:
            empty = QListWidgetItem("暂无记录会话", self.session_list)
            empty.setFlags(Qt.ItemFlag.NoItemFlags)

        summary = storage_summary(records_dir)
        self.capacity_label.setText(
            f"{summary['files']} 个文件，共 {summary['bytes'] / 1048576:.1f} MB")

    @staticmethod
    def _session_text(entry: dict) -> str:
        started = str(entry.get("started_at", ""))[:19].replace("T", " ")
        port = entry.get("port", "?")
        if not entry.get("available"):
            return f"{started}  {port}  文件缺失"
        state = _STATUS_LABELS.get(entry.get("status"), entry.get("status") or "未知")
        return (f"{started}  {port}\n"
                f"        {entry.get('rows', 0)} 条 · 时长 {_format_duration(entry.get('duration_s'))}"
                f" · {state} · {(entry.get('bytes') or 0) / 1048576:.2f} MB")

    # --- 复看区 ---------------------------------------------------------------

    def _build_review_area(self) -> QWidget:
        box = QWidget(self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row = QHBoxLayout()
        self.readout_label = QLabel(_READOUT_EMPTY, box)
        self.readout_label.setObjectName("record_dir_label")
        self.restore_button = QPushButton("还原", box)
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self._reset_zoom)
        row.addWidget(self.readout_label, 1)
        row.addWidget(self.restore_button)
        layout.addLayout(row)

        self.progress = QProgressBar(box)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.hide()
        layout.addWidget(self.progress)

        palette = tokens("dark")
        # 序列色只取自 token 表：与实时曲线的红/蓝同序，复看不必重新学配色。
        self.voltage_view = HistoryChartView("电压曲线", palette["danger"], "V", palette, box)
        self.current_view = HistoryChartView("电流曲线", palette["primary"], "A", palette, box)
        for view in (self.voltage_view, self.current_view):
            view.range_chosen.connect(self._on_range_chosen)
            view.reset_requested.connect(self._reset_zoom)
            view.hovered.connect(self._on_hover)
            view.hover_left.connect(self._on_hover_left)
            layout.addWidget(view, 1)
        return box

    def _on_session_selected(self, current, _previous) -> None:
        entry = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        if entry is None:
            return
        if not entry.get("available"):
            self._reset_review(f"数据文件已不在记录目录：{entry.get('file')}")
            return
        self._start_load(entry)

    def _reset_review(self, message: str) -> None:
        """把复看区回到空：留着上一个会话的曲线比一片空白更骗人。"""
        if self._load_task is not None:
            self._load_task.cancel()
            self._load_task = None
        self._samples = []
        self._times = []
        self._full_span = None
        self._zoom_span = None
        for view in (self.voltage_view, self.current_view):
            view.clear_points()
        self.progress.hide()
        self.restore_button.setEnabled(False)
        self._set_readout(message)

    def _start_load(self, entry: dict) -> None:
        """换会话就作废上一次载入：慢盘上连点两次不该画出两份数据。"""
        self._reset_review(f"载入 {entry.get('file')} …")

        rows = int(entry.get("rows") or 0)
        if rows > 0:
            self.progress.setRange(0, rows)
            self.progress.setValue(0)
        else:
            # 正在录的会话清单里 rows 还是 0，按"未知总量"走忙指示：
            # 拿 0..1 当总量会把刚开录显示成已经读完。
            self.progress.setRange(0, 0)
        self.progress.show()

        self._load_task = asyncio.ensure_future(
            self._load(f"{self._status['dir']}/{entry['file']}", entry))

    async def _load(self, path: str, entry: dict) -> None:
        task = asyncio.current_task()
        try:
            result = await load_session(path, on_progress=self._on_progress)
        except asyncio.CancelledError:
            return
        except OSError as exc:
            logger.error("record file unreadable: %s (%s)", path, exc)
            self.progress.hide()
            self._set_readout(f"载入失败：{exc}")
            return
        finally:
            # 只清自己的句柄：被顶掉的旧载入不该把新任务也一起抹掉。
            if self._load_task is task:
                self._load_task = None

        self.progress.hide()
        self._samples = result.samples
        self._times = [sample[0] for sample in result.samples]
        if not result.samples:
            self._set_readout("该会话没有可解析的记录")
            return

        self._full_span = (self._times[0], self._times[-1])
        skipped = f"，跳过 {result.skipped} 行" if result.skipped else ""
        self._set_readout(
            f"{len(self._samples)} 条{skipped} · {self._span_text(*self._full_span)}")
        self._draw()

    def _on_progress(self, rows: int, _skipped: int) -> None:
        if self.progress.maximum() > 0:
            self.progress.setValue(rows)

    def _draw(self) -> None:
        if not self._full_span:
            return
        lo, hi = self._zoom_span or self._full_span
        window = self._samples[bisect.bisect_left(self._times, lo):
                               bisect.bisect_right(self._times, hi)]
        if not window:
            # 框进空洞是常态：明说这段没记录，别留一张空图让人以为程序坏了。
            self.voltage_view.clear_points()
            self.current_view.clear_points()
            self._set_readout(f"{self._span_text(lo, hi)} 内没有记录（可还原）")
            self.restore_button.setEnabled(self._zoom_span is not None)
            return
        # 缺口先分段再抽稀：整段一次抽稀会让包络把洞两侧的线连起来。
        segments = split_by_gaps(window, self._nominal_ms)
        buckets = max(MIN_BUCKETS, int(self.voltage_view.width()))
        self.voltage_view.plot(segments, 1, buckets, (lo, hi))
        self.current_view.plot(segments, 2, buckets, (lo, hi))
        self.restore_button.setEnabled(self._zoom_span is not None)
        if len(segments) > 1:
            # 只改标签不动 _readout_base：重画（改宽、缩放）时这句不该越叠越长。
            # 中断次数写成数字：空洞容易看漏，"掉了几回"才对得上台架上发生的事。
            self.readout_label.setText(
                f"{self._readout_base} · 中断 {len(segments) - 1} 次")

    def _on_range_chosen(self, lo_ms: int, hi_ms: int) -> None:
        """两图共用时间轴：任一图框选，区间同时收敛到这一段。"""
        self._zoom_span = (lo_ms, hi_ms)
        self._set_readout(
            f"放大 {self._span_text(lo_ms, hi_ms)}（双击曲线或点「还原」回到全段）")
        self._draw()

    def _reset_zoom(self) -> None:
        if self._zoom_span is None or self._full_span is None:
            return
        self._zoom_span = None
        self._set_readout(f"全段 {self._span_text(*self._full_span)}")
        self._draw()

    def _set_readout(self, message: str) -> None:
        """写读数行的基线：悬停只是临时覆盖，光标离开要回到这句。"""
        self._readout_base = message
        self.readout_label.setText(message)

    def _on_hover(self, ts_ms: int) -> None:
        if not self._times:
            return
        index = bisect.bisect_right(self._times, ts_ms) - 1
        if index < 0:
            index = 0
        sample = self._samples[index]
        moment = QDateTime.fromMSecsSinceEpoch(int(sample[0])).toString("yyyy-MM-dd HH:mm:ss.zzz")
        self.readout_label.setText(
            f"{moment}  电压 {sample[1]:.3f} V  电流 {sample[2]:.3f} A")

    def _on_hover_left(self) -> None:
        self.readout_label.setText(self._readout_base)

    @staticmethod
    def _span_text(lo_ms: int, hi_ms: int) -> str:
        span_seconds = (hi_ms - lo_ms) / 1000
        if span_seconds < 1:
            return f"{span_seconds * 1000:.0f} 毫秒区间"
        fmt = "HH:mm:ss" if span_seconds < 3600 else "MM-dd HH:mm"
        lo = QDateTime.fromMSecsSinceEpoch(int(lo_ms)).toString(fmt)
        hi = QDateTime.fromMSecsSinceEpoch(int(hi_ms)).toString(fmt)
        return f"{lo} ~ {hi}"


class HistoryChartView(QChartView):
    """一张按时间铺开的历史曲线：框选放大、双击还原、悬停回报时刻。"""

    # 时间戳是 epoch 毫秒，超出 Signal(int) 的 4 字节上限（那只够表示 1970 年 1 月起的三周）。
    range_chosen = Signal("qlonglong", "qlonglong")
    reset_requested = Signal()
    hovered = Signal("qlonglong")
    hover_left = Signal()

    def __init__(self, title: str, color: str, unit: str, palette: dict, parent=None):
        super().__init__(parent)
        self._unit = unit
        self._pen_color = QColor(color)
        self._drag_origin = None
        self._has_points = False
        self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self._x_axis = QDateTimeAxis()
        self._y_axis = QValueAxis()

        chart = QChart()
        # QChart 自绘底色，不吃 QSS 也不吃 QPalette：不显式给就会在深色窗口里留一块白。
        chart.setBackgroundBrush(QBrush(QColor(palette["plate"])))
        chart.setBackgroundRoundness(6)
        chart.setAnimationOptions(QChart.NoAnimation)
        chart.setTitle(title)
        chart.setTitleBrush(QColor(palette["text"]))
        chart.legend().setVisible(False)

        self.setChart(chart)
        # QGraphicsView 自己那层底色仍是系统浅灰：不清掉会在图四周留一圈亮边。
        self.setBackgroundBrush(QBrush(QColor(palette["plate"])))
        chart.setMargins(QMargins(0, 0, 0, 0))
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(170)

        chart.addAxis(self._x_axis, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(self._y_axis, Qt.AlignmentFlag.AlignLeft)
        for axis in (self._x_axis, self._y_axis):
            axis.setLinePenColor(QColor(palette["border"]))
            axis.setGridLineColor(QColor(palette["border"]))
        self._x_axis.setLabelsColor(QColor(palette["text_dim"]))
        self._x_axis.setTickCount(6)
        self._y_axis.setLabelsColor(self._pen_color)

    def clear_points(self) -> None:
        for series in list(self.chart().series()):
            self.chart().removeSeries(series)
        self._has_points = False

    def plot(self, segments: list[list], column: int, buckets: int,
             span: tuple[int, int]) -> int:
        """每段一条独立序列：折线只在段内连，缺口两侧自然留空。

        抽稀桶数按段长在全局预算内分配，段多时每段至少留 2 点。截断段数会让
        落过盘的中断从图上消失，而"覆盖全部已落盘记录"是需求不是优化。
        """
        chart = self.chart()
        self.clear_points()
        total = sum(len(segment) for segment in segments)
        if not total:
            return 0

        low = high = None
        for segment in segments:
            share = max(2, buckets * len(segment) // total)
            envelope = decimate_min_max(
                [(float(sample[0]), float(sample[column])) for sample in segment], share)
            if not envelope:
                continue
            values = [y for _, y in envelope]
            series = QLineSeries()
            series.setColor(self._pen_color)
            chart.addSeries(series)
            # addAxis 只登记轴，归属要显式绑：不绑的话每段各拿一套默认轴，缩放时轴范围乱跳。
            chart.setAxisX(self._x_axis, series)
            chart.setAxisY(self._y_axis, series)
            series.replace([QPointF(x, y) for x, y in envelope])
            series.hovered.connect(self._on_point_hovered)
            low = min(values) if low is None else min(low, min(values))
            high = max(values) if high is None else max(high, max(values))

        self._has_points = low is not None
        if low is None:
            return 0

        lo, hi = span
        self._x_axis.setRange(QDateTime.fromMSecsSinceEpoch(int(lo)),
                              QDateTime.fromMSecsSinceEpoch(int(hi)))
        # 放大到秒级以下时把标签精度提上来，否则整条轴只显示同一个 HH:mm。
        self._x_axis.setFormat("HH:mm:ss" if (hi - lo) < 3_600_000 else "MM-dd\nHH:mm")

        pad = (high - low) * 0.08 or max(abs(high) * 0.1, 0.5)
        self._y_axis.setRange(max(0.0, low - pad), high + pad)
        return sum(item.count() for item in chart.series())

    def _on_point_hovered(self, point, state) -> None:
        """hovered 同时给出进入与离开：离开也要报，读数才不会赖在旧点上。"""
        if state:
            self.hovered.emit(int(point.x()))
        else:
            self.hover_left.emit()

    def _ms_at(self, pixel_x: int, pixel_y: int) -> float:
        """视口坐标折算成毫秒：先换成场景坐标，再交给 QChart.mapToValue。

        自己按绘图区插值会漏掉 QChartView 的边框与滚动偏移；mapToValue 走的就是轴自身
        的映射，框选端点才和画出来的位置一致。
        """
        chart = self.chart()
        series = chart.series()
        if not series:
            return 0.0
        point = self.mapToScene(QPoint(int(pixel_x), int(pixel_y)))
        area = chart.plotArea()
        x = min(max(float(point.x()), area.x()), area.x() + area.width())
        y = min(max(float(point.y()), area.y()), area.y() + area.height())
        return chart.mapToValue(QPointF(x, y), series[0]).x()

    # --- 框选放大 -------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if (event.button() == Qt.MouseButton.LeftButton and self._has_points
                and self.chart().plotArea().width() > 0):
            self._drag_origin = event.position().toPoint()
            self._rubber.setGeometry(QRect(self._drag_origin, QSize()))
            self._rubber.show()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_origin is not None:
            self._rubber.setGeometry(
                QRect(self._drag_origin, event.position().toPoint()).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        origin, self._drag_origin = self._drag_origin, None
        self._rubber.hide()
        if origin is None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        end = event.position().toPoint()
        if abs(end.x() - origin.x()) >= MIN_ZOOM_PX:
            lo, hi = sorted((self._ms_at(origin.x(), origin.y()),
                             self._ms_at(end.x(), end.y())))
            if hi > lo:
                self.range_chosen.emit(int(lo), int(hi))
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        self.reset_requested.emit()
        event.accept()
