"""实时曲线的窗口与中断指示：跑一下午也不该越来越卡、越来越假。

对应 specs/ui/live-curve 的"滚动曲线点数有界"与"采集中断状态可见"。
这里刻意构造真实 MainWindow（offscreen），因为要断言的正是 QLineSeries 本身。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from views.main_window import MainWindow
from views.live_chart_view import LiveChartView
from views.theme import tokens


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


class StubPresenter:
    """视图构造期只用到这些方法；信号槽接线需要它们存在。"""

    def get_available_ports(self):
        return [], None

    def auto_connect_enabled(self):
        return False

    def set_auto_connect(self, enabled):
        return True

    def open_device(self):
        pass

    def close_device(self):
        pass

    def set_voltage(self, value):
        pass

    def toggle_output(self):
        pass

    # 记录页在 _mount_record_tab 阶段就引用它们，桩件缺一个就构造不出窗口。
    def set_recording_enabled(self, enabled):
        return True

    def recording_status(self):
        return {}

    def stop_recording(self):
        pass


@pytest.fixture
def window(qapp):
    return MainWindow(presenter=StubPresenter())


def chart_snapshot(window):
    return (
        window.voltage_data_count,
        window.current_data_count,
        list(window.voltage_data),
        list(window.current_data),
        [(point.x(), point.y()) for point in window.voltage_series.pointsVector()],
        [(point.x(), point.y()) for point in window.current_series.pointsVector()],
        (window.voltage_axis_x.min(), window.voltage_axis_x.max()),
        (window.current_axis_x.min(), window.current_axis_x.max()),
    )


def send_wheel(view, data_position, modifiers, delta=120):
    """把数据坐标对应的屏幕位置交给真实的 Qt 滚轮事件。"""
    position = view.chart().mapToPosition(data_position, view.series)
    event = QWheelEvent(
        position,
        position,
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(view.viewport(), event)


def prepared_chart(qapp, *, title="电压曲线", color="#e5534b", unit="V"):
    view = LiveChartView(title, color, unit)
    view.resize(640, 360)
    view.show()
    view.replace_points([QPointF(index, 10.0) for index in range(100)])
    view.follow_latest(99)
    qapp.processEvents()
    return view


def double_click(view):
    position = view.viewport().rect().center()
    event = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        position,
        position,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view.viewport(), event)


def move_mouse(view, position):
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        position,
        position,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view.viewport(), event)


class TestLiveChartTheme:
    def test_chart_and_view_share_the_dark_plate(self, qapp):
        palette = tokens("dark")
        view = LiveChartView("电压曲线", palette["danger"], "V")

        assert view.chart().backgroundBrush().color().name() == palette["plate"]
        assert view.backgroundBrush().color().name() == palette["plate"]

    def test_title_axes_and_series_use_theme_colors(self, qapp):
        palette = tokens("dark")
        view = LiveChartView("电流曲线", palette["primary"], "A")

        assert view.chart().titleBrush().color().name() == palette["text"]
        assert view.axis_x.linePenColor().name() == palette["border"]
        assert view.axis_x.gridLineColor().name() == palette["border"]
        assert view.axis_x.labelsColor().name() == palette["text_dim"]
        assert view.axis_y.labelsColor().name() == palette["primary"]
        assert view.axis_y.gridLineColor().name() == palette["border"]
        assert view.series.color().name() == palette["primary"]


class TestLiveChartData:
    def test_initial_ranges_match_the_live_window(self, qapp):
        view = LiveChartView("电压曲线", "#e5534b", "V", y_range=(0.0, 20.0))

        assert (view.axis_x.min(), view.axis_x.max()) == (0.0, 99.0)
        assert (view.axis_y.min(), view.axis_y.max()) == (0.0, 20.0)
        assert view.auto_follow

    def test_replace_points_and_follow_latest_keep_global_indices(self, qapp):
        view = LiveChartView("电压曲线", "#e5534b", "V")
        points = [QPointF(4901 + offset, 10.0 + offset / 10) for offset in range(100)]

        view.replace_points(points)
        view.follow_latest(5000)

        assert view.series.count() == 100
        assert view.series.at(0).x() == 4901
        assert view.series.at(99).x() == 5000
        assert (view.axis_x.min(), view.axis_x.max()) == (4900.0, 5000.0)
        assert (view.axis_y.min(), view.axis_y.max()) == (0.0, 20.0)


class TestLiveChartZoom:
    def test_ctrl_wheel_zooms_only_x_around_pointer(self, qapp):
        view = prepared_chart(qapp)

        send_wheel(view, QPointF(25.0, 10.0), Qt.KeyboardModifier.ControlModifier)

        assert (view.axis_x.min(), view.axis_x.max()) == pytest.approx((4.166666666666664, 87.5))
        assert (view.axis_y.min(), view.axis_y.max()) == (0.0, 20.0)
        assert not view.auto_follow

    def test_shift_wheel_zooms_only_y_around_pointer(self, qapp):
        view = prepared_chart(qapp)

        send_wheel(view, QPointF(25.0, 5.0), Qt.KeyboardModifier.ShiftModifier)

        assert (view.axis_x.min(), view.axis_x.max()) == (0.0, 100.0)
        assert (view.axis_y.min(), view.axis_y.max()) == pytest.approx((5.0 - 0.25 * (20.0 / 1.2), 5.0 + 0.75 * (20.0 / 1.2)))
        assert view.auto_follow

    def test_wheel_direction_and_control_priority(self, qapp):
        view = prepared_chart(qapp)
        both = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier

        send_wheel(view, QPointF(25.0, 5.0), both, delta=120)
        zoomed = (view.axis_x.min(), view.axis_x.max())
        send_wheel(view, QPointF(25.0, 5.0), both, delta=-120)

        assert (view.axis_x.min(), view.axis_x.max()) == pytest.approx((0.0, 99.0))
        assert zoomed[1] - zoomed[0] < 100.0
        assert (view.axis_y.min(), view.axis_y.max()) == (0.0, 20.0)

    def test_plain_wheel_and_outside_plot_leave_ranges_unchanged(self, qapp):
        view = prepared_chart(qapp)
        original = ((view.axis_x.min(), view.axis_x.max()), (view.axis_y.min(), view.axis_y.max()))

        send_wheel(view, QPointF(25.0, 5.0), Qt.KeyboardModifier.NoModifier)
        event = QWheelEvent(QPointF(1, 1), QPointF(1, 1), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(view.viewport(), event)

        assert ((view.axis_x.min(), view.axis_x.max()), (view.axis_y.min(), view.axis_y.max())) == original

    def test_repeated_zoom_stays_bounded_and_does_not_invert_axes(self, qapp):
        view = prepared_chart(qapp)
        for _ in range(100):
            send_wheel(view, QPointF(50.0, 10.0), Qt.KeyboardModifier.ControlModifier)
        for _ in range(100):
            send_wheel(view, QPointF(50.0, 10.0), Qt.KeyboardModifier.ShiftModifier)

        assert 2.0 <= view.axis_x.max() - view.axis_x.min() <= 99.0
        assert 0.0 <= view.axis_x.min() < view.axis_x.max() <= 99.0
        assert 0.4 <= view.axis_y.max() - view.axis_y.min() <= 20.0
        assert 0.0 <= view.axis_y.min() < view.axis_y.max() <= 20.0


class TestLiveChartViewport:
    def test_charts_zoom_independently(self, qapp):
        voltage = prepared_chart(qapp, title="电压", color="#e5534b", unit="V")
        current = prepared_chart(qapp, title="电流", color="#4b9fea", unit="A")
        current_range = ((current.axis_x.min(), current.axis_x.max()), (current.axis_y.min(), current.axis_y.max()))

        send_wheel(voltage, QPointF(25.0, 5.0), Qt.KeyboardModifier.ControlModifier)
        send_wheel(voltage, QPointF(25.0, 5.0), Qt.KeyboardModifier.ShiftModifier)

        assert ((current.axis_x.min(), current.axis_x.max()), (current.axis_y.min(), current.axis_y.max())) == current_range
        assert current.auto_follow

    def test_x_zoom_pauses_follow_but_keeps_updating_points(self, qapp):
        view = prepared_chart(qapp)
        send_wheel(view, QPointF(25.0, 10.0), Qt.KeyboardModifier.ControlModifier)
        viewport = (view.axis_x.min(), view.axis_x.max())

        view.replace_points([QPointF(index, 10.0) for index in range(100, 200)])
        view.follow_latest(199)

        assert (view.axis_x.min(), view.axis_x.max()) == viewport
        assert view.series.count() == 100
        assert view.series.at(0).x() == 100
        assert view.series.at(99).x() == 199

    def test_y_zoom_preserves_x_follow(self, qapp):
        view = prepared_chart(qapp)
        send_wheel(view, QPointF(25.0, 5.0), Qt.KeyboardModifier.ShiftModifier)
        y_range = (view.axis_y.min(), view.axis_y.max())

        view.replace_points([QPointF(index, 10.0) for index in range(100, 200)])
        view.follow_latest(199)

        assert (view.axis_y.min(), view.axis_y.max()) == y_range
        assert (view.axis_x.min(), view.axis_x.max()) == (99.0, 199.0)
        assert view.auto_follow

    def test_double_click_resets_both_axes_and_resumes_follow(self, qapp):
        view = prepared_chart(qapp)
        send_wheel(view, QPointF(25.0, 5.0), Qt.KeyboardModifier.ControlModifier)
        send_wheel(view, QPointF(25.0, 5.0), Qt.KeyboardModifier.ShiftModifier)

        double_click(view)

        assert (view.axis_x.min(), view.axis_x.max()) == (0.0, 100.0)
        assert (view.axis_y.min(), view.axis_y.max()) == (0.0, 20.0)
        assert view.auto_follow
        view.follow_latest(299)
        assert (view.axis_x.min(), view.axis_x.max()) == (199.0, 299.0)


class TestLiveChartTooltip:
    def test_near_sample_shows_index_value_and_unit(self, qapp):
        view = prepared_chart(qapp)
        position = view.chart().mapToPosition(QPointF(42.0, 10.0), view.series) + QPointF(2.0, 0.0)

        move_mouse(view, position)

        assert view.tooltip.isVisible()
        assert view.tooltip.text() == "采样点 42\n10.00 V"
        assert view.tooltip.styleSheet().find(tokens("dark")["surface"]) >= 0

    def test_far_from_samples_hides_tooltip(self, qapp):
        view = prepared_chart(qapp)
        point = view.chart().mapToPosition(QPointF(42.0, 10.0), view.series)
        move_mouse(view, point)
        assert view.tooltip.isVisible()

        move_mouse(view, point + QPointF(30.0, 30.0))

        assert not view.tooltip.isVisible()

    def test_leaving_plot_hides_tooltip(self, qapp):
        view = prepared_chart(qapp)
        move_mouse(view, view.chart().mapToPosition(QPointF(42.0, 10.0), view.series))
        assert view.tooltip.isVisible()

        move_mouse(view, QPointF(1.0, 1.0))

        assert not view.tooltip.isVisible()

    def test_data_replacement_and_disable_hide_tooltip(self, qapp):
        view = prepared_chart(qapp)
        move_mouse(view, view.chart().mapToPosition(QPointF(42.0, 10.0), view.series))
        assert view.tooltip.isVisible()

        view.replace_points([QPointF(index, 10.0) for index in range(100)])
        assert not view.tooltip.isVisible()
        move_mouse(view, view.chart().mapToPosition(QPointF(42.0, 10.0), view.series))
        assert view.tooltip.isVisible()

        view.setEnabled(False)
        assert not view.tooltip.isVisible()
        ranges = ((view.axis_x.min(), view.axis_x.max()), (view.axis_y.min(), view.axis_y.max()))
        move_mouse(view, view.chart().mapToPosition(QPointF(42.0, 10.0), view.series))
        send_wheel(view, QPointF(42.0, 10.0), Qt.KeyboardModifier.ControlModifier)
        assert not view.tooltip.isVisible()
        assert ((view.axis_x.min(), view.axis_x.max()), (view.axis_y.min(), view.axis_y.max())) == ranges


class TestRollingWindow:
    @pytest.fixture(autouse=True)
    def enable_waveform(self, window):
        window.ui.groupBox_8.setChecked(True)

    def test_series_stays_bounded_after_a_long_run(self, window):
        for _ in range(5000):
            window.update_voltage(12.0)
            window.update_current(1.0)

        assert window.voltage_series.count() <= window.max_data_points
        assert window.current_series.count() <= window.max_data_points

    def test_window_slides_instead_of_growing(self, window):
        for _ in range(5000):
            window.update_voltage(12.0)

        x_min, x_max = window.voltage_axis_x.min(), window.voltage_axis_x.max()

        assert x_max - x_min == window.max_data_points
        assert x_min > 0

    def test_newest_point_is_kept(self, window):
        for index in range(500):
            window.update_voltage(float(index))

        points = window.voltage_series.pointsVector()

        assert points[-1].y() == 499.0
        assert points[0].y() == 400.0


class TestWaveformDisplayToggle:
    def test_default_unchecked_disables_charts_but_keeps_toggle_enabled(self, window):
        assert not window.ui.groupBox_8.isChecked()
        assert window.ui.groupBox_8.isEnabled()
        assert not window.voltage_chart_view.isEnabled()
        assert not window.current_chart_view.isEnabled()

    def test_unchecked_ignores_samples_but_updates_readouts(self, window):
        before = chart_snapshot(window)

        window.update_voltage(12.34)
        window.update_current(1.23)

        assert chart_snapshot(window) == before
        assert window.ui.volatage_label.text() == "12.34 V"
        assert window.ui.current_label.text() == "1.23 A"
        assert window.floating_window.ui.voltage_label.text() == "12.34 V"
        assert window.floating_window.ui.current_label.text() == "1.23 A"

    def test_pause_keeps_snapshot_and_resume_skips_hidden_samples(self, window):
        window.ui.groupBox_8.setChecked(True)
        window.update_voltage(10.0)
        window.update_current(1.0)
        before = chart_snapshot(window)

        window.ui.groupBox_8.setChecked(False)
        assert not window.voltage_chart_view.isEnabled()
        assert not window.current_chart_view.isEnabled()

        window.update_voltage(20.0)
        window.update_current(2.0)
        window.update_voltage(30.0)
        window.update_current(3.0)

        assert chart_snapshot(window) == before
        assert window.ui.volatage_label.text() == "30.00 V"
        assert window.ui.current_label.text() == "3.00 A"

        window.ui.groupBox_8.setChecked(True)
        assert window.voltage_chart_view.isEnabled()
        assert window.current_chart_view.isEnabled()
        assert chart_snapshot(window) == before

        window.update_voltage(11.0)
        window.update_current(1.5)

        assert window.voltage_data_count == 2
        assert window.current_data_count == 2
        assert window.voltage_data == [10.0, 11.0]
        assert window.current_data == [1.0, 1.5]
        voltage_points = window.voltage_series.pointsVector()
        current_points = window.current_series.pointsVector()
        assert [point.y() for point in voltage_points] == [10.0, 11.0]
        assert [point.y() for point in current_points] == [1.0, 1.5]


class TestMainWindowChartInteraction:
    def test_main_window_uses_live_views_without_legacy_tooltips(self, window):
        assert isinstance(window.voltage_chart_view, LiveChartView)
        assert isinstance(window.current_chart_view, LiveChartView)
        assert window.voltage_chart is window.voltage_chart_view.chart()
        assert window.voltage_series is window.voltage_chart_view.series
        assert window.current_axis_x is window.current_chart_view.axis_x
        assert not hasattr(window, "voltage_tooltip_label")
        assert not hasattr(window, "current_tooltip_label")

    def test_interactions_preserve_readouts_counts_and_bounded_curves(self, qapp, window):
        window.ui.tabWidget.setCurrentWidget(window.ui.tab_wave)
        window.ui.groupBox_8.setChecked(True)
        window.show()
        for index in range(250):
            window.update_voltage(10.0 + index / 100.0)
            window.update_current(1.0 + index / 1000.0)
        qapp.processEvents()
        readouts = (
            window.ui.volatage_label.text(),
            window.ui.current_label.text(),
            window.floating_window.ui.voltage_label.text(),
            window.floating_window.ui.current_label.text(),
        )
        counts = (window.voltage_data_count, window.current_data_count)
        view = window.voltage_chart_view

        send_wheel(view, QPointF(200.0, 12.0), Qt.KeyboardModifier.ControlModifier)
        send_wheel(view, QPointF(200.0, 5.0), Qt.KeyboardModifier.ShiftModifier)
        move_mouse(view, view.chart().mapToPosition(QPointF(200.0, 12.0), view.series))

        assert view.tooltip.isVisible()
        assert readouts == (
            window.ui.volatage_label.text(),
            window.ui.current_label.text(),
            window.floating_window.ui.voltage_label.text(),
            window.floating_window.ui.current_label.text(),
        )
        assert counts == (window.voltage_data_count, window.current_data_count)
        assert window.voltage_series.count() == window.max_data_points
        assert window.current_series.count() == window.max_data_points

        viewport = (view.axis_x.min(), view.axis_x.max())
        for index in range(20):
            window.update_voltage(20.0 + index / 100.0)
            window.update_current(2.0 + index / 1000.0)
        assert (view.axis_x.min(), view.axis_x.max()) == viewport
        assert not view.tooltip.isVisible()
        assert window.voltage_series.count() == window.max_data_points
        assert window.current_series.count() == window.max_data_points

        double_click(view)

        assert view.auto_follow
        assert not view.tooltip.isVisible()
        assert (view.axis_x.min(), view.axis_x.max()) == (169.0, 269.0)
        assert (view.axis_y.min(), view.axis_y.max()) == (0.0, 20.0)
        assert window.voltage_data_count == 270
        assert window.current_data_count == 270


class TestStaleReadoutIndicator:
    def test_status_bar_and_floating_window_show_the_break(self, window):
        window.update_voltage(12.34)
        window.update_current(1.23)

        window.update_sampling_error("TimeoutError: ")

        assert "TimeoutError" in window.ui.statusbar.currentMessage()
        assert window.floating_window.ui.voltage_label.text() == "-- V"
        assert window.floating_window.ui.current_label.text() == "-- A"

    def test_readouts_come_back_with_the_first_success(self, window):
        window.update_voltage(12.34)
        window.update_current(1.23)
        window.update_sampling_error("TimeoutError: ")

        window.update_sampling_error(None)

        assert window.floating_window.ui.voltage_label.text() == "12.34 V"
        assert window.ui.statusbar.currentMessage() == ""

    def test_a_late_sample_does_not_mask_the_break(self, window):
        window.update_voltage(12.34)
        window.update_sampling_error("TimeoutError: ")

        window.update_voltage(11.0)

        assert window.floating_window.ui.voltage_label.text() == "-- V"
