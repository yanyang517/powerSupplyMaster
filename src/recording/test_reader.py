"""复看读取侧：列会话、整读 CSV、按间隔断段。

对应 specs/recording/history-review 的"复看入口列出已记录的会话""长会话载入有响应
上限""缺口呈现为空洞"。load_session 是协程，这里用 asyncio.run 直接驱动，不为几个
测试引入事件循环夹具。
"""
import asyncio
import json

from recording import reader as rd
from recording.recorder import INDEX_FILE_NAME, Recorder
from recording.test_recorder import FakeClock


def write_csv(path, rows):
    """newline="" 不能省：默认文本模式会把 \n 再翻成 \r\n，读出来就全是空行。"""
    path.write_text("ts_ms,iso_local,voltage_v,current_a\r\n"
                    + "".join(f"{ts},2026-11-21T13:22:00.000+08:00,{v},{i}\r\n"
                              for ts, v, i in rows),
                    encoding="utf-8", newline="")
    return path


def seeded_dir(tmp_path, sessions):
    """手工造一份清单 + 对应 CSV：复看侧要能对"别人写的盘"也成立。"""
    records = tmp_path / "records"
    records.mkdir(parents=True, exist_ok=True)
    for entry in sessions:
        (records / entry["file"]).write_text(
            "ts_ms,iso_local,voltage_v,current_a\n", encoding="utf-8")
    (records / INDEX_FILE_NAME).write_text(
        json.dumps({"version": 1, "sessions": sessions}), encoding="utf-8")
    return records


class TestListSessions:
    def test_sorted_newest_first(self, tmp_path):
        seeded_dir(tmp_path, [
            {"id": "old", "file": "old.csv", "started_at": "2026-11-20T10:00:00+08:00",
             "ended_at": "2026-11-20T11:00:00+08:00", "rows": 10, "status": "closed"},
            {"id": "new", "file": "new.csv", "started_at": "2026-11-21T10:00:00+08:00",
             "ended_at": "2026-11-21T10:00:30+08:00", "rows": 60, "status": "closed"},
        ])

        entries = rd.list_sessions(tmp_path / "records")

        assert [entry["id"] for entry in entries] == ["new", "old"]

    def test_duration_is_reported_for_the_list(self, tmp_path):
        seeded_dir(tmp_path, [
            {"id": "a", "file": "a.csv", "started_at": "2026-11-21T10:00:00+08:00",
             "ended_at": "2026-11-21T11:23:45+08:00", "rows": 10, "status": "closed"},
        ])

        assert rd.list_sessions(tmp_path / "records")[0]["duration_s"] == 5025.0

    def test_live_session_has_no_duration_rather_than_a_fake_one(self, tmp_path):
        """记录中的会话没有结束时刻，凑一个"现在"会让时长随刷新跳动。"""
        seeded_dir(tmp_path, [
            {"id": "live", "file": "live.csv", "started_at": "2026-11-21T10:00:00+08:00",
             "ended_at": None, "rows": 0, "status": "recording"},
        ])

        assert rd.list_sessions(tmp_path / "records")[0]["duration_s"] is None

    def test_unparsable_timestamps_yield_no_duration(self, tmp_path):
        seeded_dir(tmp_path, [
            {"id": "a", "file": "a.csv", "started_at": "昨天", "ended_at": "今天",
             "rows": 1, "status": "closed"},
        ])

        assert rd.list_sessions(tmp_path / "records")[0]["duration_s"] is None

    def test_missing_data_file_is_marked_unavailable_not_dropped(self, tmp_path):
        records = seeded_dir(tmp_path, [
            {"id": "here", "file": "here.csv", "started_at": "2026-11-21T10:00:00+08:00",
             "ended_at": "2026-11-21T10:01:00+08:00", "rows": 1, "status": "closed"},
            {"id": "gone", "file": "gone.csv", "started_at": "2026-11-21T09:00:00+08:00",
             "ended_at": "2026-11-21T09:01:00+08:00", "rows": 1, "status": "closed"},
        ])
        (records / "gone.csv").unlink()   # 手工删过文件或拷盘缺件，是复看列表的常态

        entries = rd.list_sessions(records)

        assert [entry["available"] for entry in entries] == [True, False]
        assert [entry["id"] for entry in entries] == ["here", "gone"]

    def test_empty_and_absent_directories_read_as_no_sessions(self, tmp_path):
        assert rd.list_sessions(tmp_path / "records") == []
        (tmp_path / "records").mkdir()
        assert rd.list_sessions(tmp_path / "records") == []


class TestStorageSummary:
    def test_counts_csv_files_only(self, tmp_path):
        records = seeded_dir(tmp_path, [])
        (records / "a.csv").write_text("x" * 100, encoding="utf-8")
        (records / "b.csv").write_text("x" * 50, encoding="utf-8")
        (records / "notes.txt").write_text("x" * 999, encoding="utf-8")

        summary = rd.storage_summary(records)

        assert summary["files"] == 2
        assert summary["bytes"] == 150

    def test_missing_directory_reports_zero(self, tmp_path):
        assert rd.storage_summary(tmp_path / "nope") == {"dir": str(tmp_path / "nope"),
                                                         "files": 0, "bytes": 0}


class TestLoadSession:
    def test_reads_every_row_with_values(self, tmp_path):
        path = write_csv(tmp_path / "s.csv", [
            (1700000000000, 12.0, 1.0),
            (1700000000500, 12.5, 1.5),
        ])

        result = asyncio.run(rd.load_session(path))

        assert result.samples == [(1700000000000, 12.0, 1.0), (1700000000500, 12.5, 1.5)]
        assert result.skipped == 0

    def test_bad_lines_are_skipped_and_counted_not_fatal(self, tmp_path):
        path = tmp_path / "s.csv"
        path.write_text(
            "ts_ms,iso_local,voltage_v,current_a\n"
            "1700000000000,2026-11-21T13:22:00+08:00,12.0,1.0\n"
            "1700000000500,2026-11-21T13:22:00+08:00,abc,1.0\n"   # 非数值
            "半条记录\n",                                          # 列数不足
            encoding="utf-8")

        result = asyncio.run(rd.load_session(path))

        assert len(result.samples) == 1
        assert result.skipped == 2

    def test_progress_is_reported_and_the_loop_gets_the_turn_back(self, tmp_path):
        """分块让出事件循环：进度条要真刷得动，否则就是无指示冻结。"""
        rows = [(1700000000000 + index * 500, 12.0, 1.0) for index in range(25)]
        path = write_csv(tmp_path / "s.csv", rows)
        seen = []

        async def load():
            ticks = 0

            async def ticker():
                nonlocal ticks
                while True:
                    ticks += 1
                    await asyncio.sleep(0)

            task = asyncio.ensure_future(ticker())
            try:
                await rd.load_session(path, chunk_rows=10,
                                      on_progress=lambda rows_, _s: seen.append(rows_))
            finally:
                task.cancel()
            return ticks

        ticks = asyncio.run(load())

        assert seen == [10, 20, 25]
        assert ticks >= 3    # 载入期间别的任务确实被执行过，界面才画得出进度

    def test_header_line_is_not_mistaken_for_data(self, tmp_path):
        path = write_csv(tmp_path / "s.csv", [(1700000000000, 12.0, 1.0)])

        result = asyncio.run(rd.load_session(path))

        assert len(result.samples) == 1

    def test_file_without_header_still_reads(self, tmp_path):
        path = tmp_path / "s.csv"
        path.write_text("1700000000000,2026-11-21T13:22:00+08:00,12.0,1.0\n",
                        encoding="utf-8")

        assert len(asyncio.run(rd.load_session(path)).samples) == 1


class TestSplitByGaps:
    def test_empty_input_has_no_segments(self):
        assert rd.split_by_gaps([], 500) == []

    def test_continuous_sampling_is_one_segment(self):
        samples = [(1700000000000 + index * 500, 12.0, 1.0) for index in range(20)]

        assert [len(seg) for seg in rd.split_by_gaps(samples, 500)] == [20]

    def test_two_outages_make_three_segments(self):
        samples = [
            (1700000000000, 12.0, 1.0), (1700000000500, 12.0, 1.0),
            (1700000060000, 12.0, 1.0),
            (1700000060500, 12.0, 1.0),
            (1700000200000, 12.0, 1.0),
        ]

        segments = rd.split_by_gaps(samples, 500)

        assert [len(seg) for seg in segments] == [2, 2, 1]
        assert segments[0][0][0] == 1700000000000
        assert segments[-1][0][0] == 1700000200000
        # 每个断口两侧各留一条记录，中间那段空档一条都不许有。
        assert segments[1][0][0] == 1700000060000

    def test_a_gap_never_bridges_into_the_next_segment(self):
        samples = [(1700000000000, 12.0, 1.0), (1700000099000, 13.0, 2.0)]

        segments = rd.split_by_gaps(samples, 500)

        assert len(segments) == 2
        assert all(len(seg) == 1 for seg in segments)

    def test_threshold_is_the_nominal_interval_times_the_factor(self):
        """GAP_FACTOR 是"标称周期的倍数"，不是绝对毫秒：改了轮询周期阈值跟着走。"""
        samples = [(1700000000000, 12.0, 1.0), (1700000001000, 12.0, 1.0)]

        assert len(rd.split_by_gaps(samples, 500, factor=1.5)) == 2
        assert len(rd.split_by_gaps(samples, 500, factor=2.5)) == 1

    def test_out_of_order_rows_are_returned_sorted_by_ts(self, tmp_path):
        """时钟回拨会写出乱序行：复看按 ts_ms 排序，否则 bisect 取窗会取错区间。"""
        path = write_csv(tmp_path / "s.csv", [
            (1700000001000, 12.0, 1.0), (1700000000000, 12.1, 1.1)])

        result = asyncio.run(rd.load_session(path))

        assert [sample[0] for sample in result.samples] == [1700000000000, 1700000001000]


class TestRealFileRoundTrip:
    def test_recorder_output_is_readable_by_the_reader(self, tmp_path):
        rec = Recorder(tmp_path / "records", monotonic=FakeClock())
        rec.start("COM8")
        for index in range(6):
            rec.on_sample(1700000000000 + index * 500, 12.0 + index * 0.1, 1.0)
        name = rec.session["file"]
        rec.stop()

        result = asyncio.run(rd.load_session(tmp_path / "records" / name))

        assert len(result.samples) == 6
        assert result.skipped == 0
        assert len(rd.split_by_gaps(result.samples, 500)) == 1
