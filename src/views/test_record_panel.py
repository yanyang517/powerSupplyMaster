"""记录面板：状态渲染、会话列表文案、复看的缩放与读数。

对应 specs/recording/history-review 各条 MUST。用真实 QWidget（offscreen）而不是替身，
因为要断言的正是控件层的呈现事实：底色、动画开关、进度条量程、读数文本。
"""
import asyncio
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDateTime, Qt
from PySide6.QtCharts import QChart
from PySide6.QtWidgets import QApplication

from recording.recorder import Recorder
from views import record_panel as panel_mod
from views.record_panel import RecordPanel, _format_duration


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def recorded_session(tmp_path, rows=6, gap_at=None, port="COM8"):
    """用真实 Recorder 写一份会话，面板读的就是这份盘。"""
    rec = Recorder(tmp_path / "records")
    rec.start(port)
    for index in range(rows):
        ts = 1700000000000 + index * 500
        if gap_at is not None and index == gap_at:
            ts += 60_000          # 一次一分钟掉线
        rec.on_sample(ts, 12.0 + index * 0.1, 1.0 + index * 0.01)
    name = rec.session["file"]
    rec.stop()
    return name


def status_for(tmp_path, **overrides):
    status = {"enabled": True, "recording": False, "file": None, "rows": 0,
              "dir": str(tmp_path / "records"), "error": None, "interval_ms": 500}
    status.update(overrides)
    return status


def loaded_panel(tmp_path, name):
    panel = RecordPanel()
    panel.render(status_for(tmp_path))
    entry = next(item for item in panel._entries if item["file"] == name)
    asyncio.run(panel._load(f"{panel._status['dir']}/{name}", entry))
    return panel


class TestDurationFormat:
    @pytest.mark.parametrize("seconds,text", [
        (None, "—"),
        (0, "0 秒"),
        (45, "45 秒"),
        (125, "2 分 05 秒"),
        (5025, "1 时 23 分"),
    ])
    def test_formats_or_admits_unknown(self, seconds, text):
        assert _format_duration(seconds) == text


class TestSessionListText:
    def test_line_carries_time_port_rows_duration_state_size(self):
        entry = {"available": True, "started_at": "2026-11-21T13:22:00+08:00",
                 "ended_at": "2026-11-21T13:24:05+08:00", "duration_s": 125.0,
                 "port": "COM8", "rows": 250, "bytes": 1_048_576, "status": "closed"}

        text = RecordPanel._session_text(entry)

        assert "2026-11-21 13:22:00" in text and "COM8" in text
        assert "250 条" in text and "时长 2 分 05 秒" in text
        assert "正常结束" in text and "1.00 MB" in text

    def test_a_live_session_shows_unknown_rather_than_a_made_up_duration(self):
        entry = {"available": True, "started_at": "2026-11-21T13:22:00+08:00",
                 "duration_s": None, "port": "COM8", "rows": 0, "bytes": 0,
                 "status": "recording"}

        assert "时长 —" in RecordPanel._session_text(entry)

    def test_missing_file_stays_listed_but_says_so(self):
        entry = {"available": False, "started_at": "2026-11-21T13:22:00+08:00",
                 "port": "COM8"}

        assert "文件缺失" in RecordPanel._session_text(entry)


class TestRender:
    def test_empty_directory_gives_an_explicit_empty_state(self, tmp_path):
        panel = RecordPanel()

        panel.render(status_for(tmp_path))

        assert panel.session_list.count() == 1
        assert "暂无记录" in panel.session_list.item(0).text()

    def test_missing_data_file_is_unselectable_not_gone(self, tmp_path):
        name = recorded_session(tmp_path, rows=3)
        panel = RecordPanel()
        panel.render(status_for(tmp_path))
        assert panel.session_list.item(0).flags() != Qt.ItemFlag.NoItemFlags

        (tmp_path / "records" / name).unlink()   # 手工删过文件，拷盘缺件是复看的常态
        panel.refresh_sessions()

        assert panel.session_list.count() == 1
        assert "文件缺失" in panel.session_list.item(0).text()
        assert panel.session_list.item(0).flags() == Qt.ItemFlag.NoItemFlags

    def test_capacity_line_counts_files_and_bytes(self, tmp_path):
        recorded_session(tmp_path, rows=20)

        panel = RecordPanel()
        panel.render(status_for(tmp_path))

        assert "1 个文件" in panel.capacity_label.text()
        assert "MB" in panel.capacity_label.text()

    def test_failure_reason_is_shown_and_cleared(self, tmp_path):
        panel = RecordPanel()

        panel.render(status_for(tmp_path, error="写入失败：disk full"))
        assert "disk full" in panel.error_label.text()
        assert panel.error_label.isVisibleTo(panel)

        panel.render(status_for(tmp_path))
        assert panel.error_label.text() == ""
        assert not panel.error_label.isVisibleTo(panel)

    def test_the_checkbox_does_not_echo_back_at_the_presenter(self, tmp_path):
        """render 写复选框时绝不能触发 enable_requested，否则开关自己转起来。"""
        panel = RecordPanel()
        fired = []
        panel.enable_requested.connect(fired.append)

        panel.render(status_for(tmp_path, enabled=True))

        assert panel.enable_check.isChecked() is True
        assert fired == []

    def test_user_toggle_is_forwarded_once(self, tmp_path):
        panel = RecordPanel()
        panel.render(status_for(tmp_path, enabled=False))
        fired = []
        panel.enable_requested.connect(fired.append)

        panel.enable_check.setChecked(True)

        assert fired == [True]

    def test_a_session_that_just_closed_appears_without_a_manual_rescan(self, tmp_path):
        """记录中那份盘上还没有可看会话；关闭登记齐了就必须立刻列出来。"""
        panel = RecordPanel()
        panel.render(status_for(tmp_path, recording=True))
        rec = Recorder(tmp_path / "records")
        rec.start("COM8")
        for index in range(4):
            rec.on_sample(1700000000000 + index * 500, 12.0, 1.0)
        name = rec.session["file"]
        rec.stop()

        panel.render(status_for(tmp_path, recording=False))

        listed = panel.session_list.item(0).data(Qt.ItemDataRole.UserRole)
        assert listed["file"] == name
        assert "COM8" in panel.session_list.item(0).text()

    def test_rescan_is_skipped_when_nothing_changed(self, tmp_path):
        panel = RecordPanel()
        panel.render(status_for(tmp_path))
        scans = []
        panel.refresh_sessions = lambda: scans.append(1)

        panel.render(status_for(tmp_path, rows=10))
        panel.render(status_for(tmp_path, rows=20))

        assert scans == []


class TestProgressBar:
    def test_a_finished_session_gets_a_determinate_range(self, tmp_path):
        name = recorded_session(tmp_path, rows=12)
        panel = RecordPanel()
        panel.render(status_for(tmp_path))
        entry = next(item for item in panel._entries if item["file"] == name)

        async def scenario():
            panel._start_load(entry)
            range_seen = (panel.progress.minimum(), panel.progress.maximum())
            panel._load_task.cancel()
            return range_seen

        assert asyncio.run(scenario()) == (0, 12)

    def test_a_live_session_with_zero_rows_loads_as_busy(self, tmp_path):
        """正在录的会话清单里 rows 还是 0：报 0..1 会把刚开录显示成已读完。"""
        name = recorded_session(tmp_path, rows=4)
        panel = RecordPanel()
        panel.render(status_for(tmp_path))
        entry = next(item for item in panel._entries if item["file"] == name)
        entry["rows"] = 0

        async def scenario():
            panel._start_load(entry)
            range_seen = (panel.progress.minimum(), panel.progress.maximum())
            panel._load_task.cancel()
            return range_seen

        assert asyncio.run(scenario()) == (0, 0)


class TestChartPresentation:
    def test_animation_is_explicitly_off(self, tmp_path):
        panel = RecordPanel()

        for view in (panel.voltage_view, panel.current_view):
            assert view.chart().animationOptions() == QChart.AnimationOption.NoAnimation

    def test_both_background_layers_are_the_dark_plate(self, tmp_path):
        """图表画布与 QGraphicsView 那层都要设色，只设一个会在四周留一圈浅灰。"""
        plate = panel_mod.tokens("dark")["plate"]
        panel = RecordPanel()

        for view in (panel.voltage_view, panel.current_view):
            assert view.chart().backgroundBrush().color().name() == plate
            assert view.backgroundBrush().color().name() == plate

    def test_series_colors_follow_the_token_table(self, tmp_path):
        name = recorded_session(tmp_path, rows=8)
        palette = panel_mod.tokens("dark")

        panel = loaded_panel(tmp_path, name)

        assert panel.voltage_view.chart().series()[0].color().name() == palette["danger"]
        assert panel.current_view.chart().series()[0].color().name() == palette["primary"]

    def test_curves_share_the_time_axis_and_have_their_own_vertical(self, tmp_path):
        name = recorded_session(tmp_path, rows=8)

        panel = loaded_panel(tmp_path, name)

        for view in (panel.voltage_view, panel.current_view):
            assert view._x_axis.min().toMSecsSinceEpoch() == panel._full_span[0]
            assert view._x_axis.max().toMSecsSinceEpoch() == panel._full_span[1]
        assert (panel.voltage_view._y_axis.min(), panel.voltage_view._y_axis.max()) != (
            panel.current_view._y_axis.min(), panel.current_view._y_axis.max())


class TestGapRendering:
    def test_an_outage_becomes_two_series_not_one_line(self, tmp_path):
        name = recorded_session(tmp_path, rows=8, gap_at=4)

        panel = loaded_panel(tmp_path, name)

        assert len(panel.voltage_view.chart().series()) == 2

    def test_a_continuous_session_stays_one_series(self, tmp_path):
        name = recorded_session(tmp_path, rows=8)

        panel = loaded_panel(tmp_path, name)

        assert len(panel.voltage_view.chart().series()) == 1

    def test_every_outage_is_drawn_not_just_the_first_few(self, tmp_path):
        """几百次短中断是常态（供电抖动、串口 flap），一条都不许从图上消失。"""
        outages = 300
        ts = 1700000000000
        path = tmp_path / "flap.csv"
        with open(path, "w", newline="", encoding="utf-8") as handle:
            handle.write("ts_ms,iso_local,voltage_v,current_a\n")
            for _ in range(outages):
                for index in range(6):
                    handle.write(f"{ts + index * 500},"
                                 f"2026-11-21T13:22:00+08:00,12.0,1.0\n")
                ts += 6 * 500 + 5000        # 每次断 5 秒，稳过缺口阈值
        entry = {"file": path.name, "rows": 0, "available": True}

        panel = RecordPanel()
        panel.render(status_for(tmp_path))
        asyncio.run(panel._load(str(path), entry))

        assert len(panel.voltage_view.chart().series()) == outages
        assert len(panel.current_view.chart().series()) == outages
        # 每次中断都要数得出来：截断会把"掉了几回"这个数字一起抹掉。
        assert f"中断 {outages - 1} 次" in panel.readout_label.text()

    def test_the_outage_count_survives_a_redraw(self, tmp_path):
        """改宽度与缩放都会重画，读数那句不该越叠越长。"""
        name = recorded_session(tmp_path, rows=8, gap_at=7)
        panel = loaded_panel(tmp_path, name)

        panel._draw()
        panel._draw()

        assert panel.readout_label.text().count("中断") == 1


class TestZoom:
    def test_rect_selection_narrows_both_charts_together(self, tmp_path):
        name = recorded_session(tmp_path, rows=20)
        panel = loaded_panel(tmp_path, name)
        lo, hi = panel._full_span
        window = (lo + 2000, lo + 5000)

        panel._on_range_chosen(*window)

        for view in (panel.voltage_view, panel.current_view):
            assert (view._x_axis.min().toMSecsSinceEpoch(),
                    view._x_axis.max().toMSecsSinceEpoch()) == window
        assert panel.restore_button.isEnabled()

    def test_restore_returns_to_the_first_and_last_record(self, tmp_path):
        name = recorded_session(tmp_path, rows=20)
        panel = loaded_panel(tmp_path, name)
        full = panel._full_span
        panel._on_range_chosen(full[0] + 2000, full[0] + 5000)

        panel._reset_zoom()

        for view in (panel.voltage_view, panel.current_view):
            assert (view._x_axis.min().toMSecsSinceEpoch(),
                    view._x_axis.max().toMSecsSinceEpoch()) == full
        assert not panel.restore_button.isEnabled()

    def test_zooming_in_returns_raw_point_density(self, tmp_path):
        """抽稀只属于全段：放大到 5 秒窗内应当看到窗里的每一条原始记录。"""
        name = recorded_session(tmp_path, rows=2000)
        panel = loaded_panel(tmp_path, name)
        wide = sum(series.count() for series in panel.voltage_view.chart().series())
        lo, _hi = panel._full_span

        panel._on_range_chosen(lo, lo + 5000)

        drawn = sum(series.count() for series in panel.voltage_view.chart().series())
        assert wide < 2000    # 整段确实是包络抽稀过的
        assert drawn == 11    # 500 ms 周期、窗含首尾 = 11 条，一条不被合并

    def test_zooming_into_a_hole_says_so_instead_of_showing_an_empty_chart(self, tmp_path):
        name = recorded_session(tmp_path, rows=8, gap_at=7)
        panel = loaded_panel(tmp_path, name)
        lo, hi = panel._full_span

        panel._on_range_chosen(lo + 4000, lo + 24_000)   # 断口内、两侧记录之外

        assert "没有记录" in panel.readout_label.text()
        assert panel.voltage_view.chart().series() == []


class TestHover:
    def test_readout_shows_the_row_that_was_hovered(self, tmp_path):
        name = recorded_session(tmp_path, rows=6)
        panel = loaded_panel(tmp_path, name)
        sample = panel._samples[2]

        panel._on_hover(sample[0])

        text = panel.readout_label.text()
        assert f"{sample[1]:.3f} V" in text and f"{sample[2]:.3f} A" in text
        moment = QDateTime.fromMSecsSinceEpoch(int(sample[0])).toString("yyyy-MM-dd HH:mm:ss.zzz")
        assert moment in text

    def test_leaving_restores_the_previous_baseline(self, tmp_path):
        name = recorded_session(tmp_path, rows=6)
        panel = loaded_panel(tmp_path, name)
        baseline = panel.readout_label.text()
        panel._on_hover(panel._samples[1][0])

        panel._on_hover_left()

        assert panel.readout_label.text() == baseline

    def test_the_view_reports_leaving_as_well_as_entering(self, tmp_path):
        view = panel_mod.HistoryChartView("电压曲线", "#ff0000", "V",
                                          panel_mod.tokens("dark"))
        seen = []
        view.hovered.connect(seen.append)
        view.hover_left.connect(lambda: seen.append("left"))

        view._on_point_hovered(panel_mod.QPointF(1700000000000.0, 12.0), True)
        view._on_point_hovered(panel_mod.QPointF(1700000000000.0, 12.0), False)

        assert seen == [1700000000000, "left"]


class TestNoDestructivePath:
    def test_the_panel_never_deletes_or_rotates_records(self):
        import inspect

        text = inspect.getsource(panel_mod)

        for forbidden in ("os.remove", "unlink(", ".truncate(", "rmtree", "removeDataset"):
            assert forbidden not in text, f"复看页出现了删除路径：{forbidden}"
