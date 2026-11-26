"""实时曲线的窗口与中断指示：跑一下午也不该越来越卡、越来越假。

对应 specs/ui/live-curve 的"滚动曲线点数有界"与"采集中断状态可见"。
这里刻意构造真实 MainWindow（offscreen），因为要断言的正是 QLineSeries 本身。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from views.main_window import MainWindow


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


class StubPresenter:
    """视图构造期只用到这些方法；信号槽接线需要它们存在。"""

    def get_available_ports(self):
        return [], None

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
