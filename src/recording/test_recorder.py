"""落盘侧的硬约束：成对写入、缺口不留占位、清单与盘上事实一致。

对应 specs/recording/data-capture 的"一条记录对应一个采样周期的成对读数""采样缺口
不得补造数据""会话自描述且可定位""异常退出后已落盘数据仍可复看""记录故障不伤及
控制与显示"。Recorder 不依赖 Qt 也不碰串口，所以这些都能在 tmp_path 里直接断言。
"""
import csv
import json

from recording import recorder as rc


class FakeClock:
    """可控单调钟：flush 节奏是按时钟判定的，真钟下这个测试要睡两秒。"""

    def __init__(self, now: float = 0.0, step: float = 0.5):
        self.now = now
        self.step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


class FailingWriter:
    """顶掉 csv.writer：写盘炸了之后的降级路径只能人造。

    直接给 _csv.writer.writerow 赋值是不行的，C 实现的 writer 拒绝实例属性。
    """

    def __init__(self, message="disk full"):
        self.message = message

    def writerow(self, _row):
        raise OSError(self.message)


def make(tmp_path, **kwargs):
    clock = kwargs.pop("monotonic", None) or FakeClock()
    rec = rc.Recorder(tmp_path / "records", monotonic=clock, **kwargs)
    return rec, clock


def open_name(rec):
    """会话结束 session 就没了，但文件名是断言要用的事实，提前留下。"""
    return rec.session["file"]


def disk_rows(records_dir, name):
    """绕过缓冲直接看盘上有什么：flush 是否发生只能这么验。"""
    with open(records_dir / name, "r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def index_of(tmp_path):
    return json.loads((tmp_path / "records" / "index.json").read_text(encoding="utf-8"))


class TestRowFormat:
    def test_header_is_self_describing(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM8")
        name = open_name(rec)

        assert disk_rows(rec.records_dir, name)[0] == [
            "ts_ms", "iso_local", "voltage_v", "current_a"]
        rec.stop()

    def test_one_cycle_writes_exactly_one_paired_row(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM8")
        name = open_name(rec)
        rec.on_sample(1700000000123, 12.34, 1.25)
        rec.on_sample(1700000000623, 12.35, 1.26)
        rec._handle.flush()

        rows = disk_rows(rec.records_dir, name)

        assert int(rows[1][0]) == 1700000000123
        assert rows[1][2] == "12.34" and rows[1][3] == "1.25"
        assert rows[2][2] == "12.35" and rows[2][3] == "1.26"
        # iso_local 要脱离应用也能判读：带时区偏移的 ISO 文本。
        assert "+" in rows[1][1] or "-" in rows[1][1][10:]
        assert rec.rows == 2
        rec.stop()

    def test_incomplete_reading_is_dropped_whole(self, tmp_path):
        """电压有、电流没有：宁可这个周期在数据里消失，也不留半条记录。"""
        rec, _ = make(tmp_path)
        rec.start("COM8")
        name = open_name(rec)
        rec.on_sample(1700000000123, 12.34, None)
        rec.on_sample(1700000000623, None, 1.26)
        rec._handle.flush()

        assert len(disk_rows(rec.records_dir, name)) == 1
        assert rec.rows == 0
        rec.stop()

    def test_failed_cycle_leaves_no_placeholder_row(self, tmp_path):
        """缺口只由相邻两行的时间差体现：不写空值，也不复制上一周期的读数。"""
        rec, _ = make(tmp_path)
        rec.start("COM8")
        name = open_name(rec)
        rec.on_sample(1700000000000, 12.0, 1.0)
        # 中间那个周期采集失败，调用方根本走不到 on_sample。
        rec.on_sample(1700000001000, 12.1, 1.1)
        rec.stop()

        rows = disk_rows(rec.records_dir, name)

        assert len(rows) == 3
        assert int(rows[1][0]) == 1700000000000
        assert int(rows[2][0]) == 1700000001000
        assert "" not in rows[2]

    def test_sample_after_stop_is_ignored(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM8")
        name = open_name(rec)
        rec.stop()

        assert rec.on_sample(1700000002000, 12.0, 1.0) is False
        assert rec.rows == 0
        assert not (rec.records_dir / name).exists()


class TestFlushCadence:
    def test_buffered_rows_reach_disk_on_the_flush_interval(self, tmp_path):
        clock = FakeClock(now=0.0, step=0.5)
        rec = rc.Recorder(tmp_path / "records", monotonic=clock)
        rec.start("COM8")
        name = open_name(rec)
        for _ in range(3):                       # 0.5/1.0/1.5 < 2.0，还没到 flush
            rec.on_sample(1700000000000, 12.0, 1.0)

        assert len(disk_rows(rec.records_dir, name)) == 1

        rec.on_sample(1700000002000, 12.0, 1.0)  # 第 4 个采样踩到 2.0，触发 flush

        assert len(disk_rows(rec.records_dir, name)) == 5   # 列头 + 4 条
        rec.stop()

    def test_rows_are_buffered_between_flushes(self, tmp_path):
        """不是每行一次同步 IO：两个 flush 之间的行只在内存里，盘上会滞后几条。"""
        clock = FakeClock(now=0.0, step=0.5)
        rec = rc.Recorder(tmp_path / "records", monotonic=clock)
        rec.start("COM8")
        name = open_name(rec)
        for index in range(100):                 # 50 秒，每 2 秒左右刷一次
            rec.on_sample(1700000000000 + index * 500, 12.0, 1.0)

        lag = rec.rows - (len(disk_rows(rec.records_dir, name)) - 1)

        assert rec.rows == 100
        assert 0 <= lag <= 4
        rec.stop()


class TestSessionIndex:
    def test_registered_as_recording_the_moment_the_session_starts(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.on_sample(1700000000000, 12.0, 1.0)   # 没 start 就喂：什么都不该发生

        assert not (tmp_path / "records").exists()

        rec.start("COM8")
        entry = index_of(tmp_path)["sessions"][0]

        assert entry["status"] == "recording"
        assert entry["port"] == "COM8"
        assert entry["ended_at"] is None
        assert entry["rows"] == 0
        rec.stop()

    def test_close_writes_ended_at_rows_bytes(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM8")
        name = open_name(rec)
        for index in range(5):
            rec.on_sample(1700000000000 + index * 500, 12.0 + index, 1.0)
        rec.stop()

        entry = index_of(tmp_path)["sessions"][0]

        assert entry["status"] == "closed"
        assert entry["rows"] == 5
        assert entry["bytes"] == (tmp_path / "records" / name).stat().st_size
        assert entry["ended_at"]
        assert entry["file"] == f"{entry['id']}.csv"

    def test_zero_record_session_leaves_no_file_and_no_entry(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM8")
        name = open_name(rec)

        assert rec.stop() is None
        assert index_of(tmp_path)["sessions"] == []
        assert not (tmp_path / "records" / name).exists()
        assert list(rec.records_dir.glob("*.csv")) == []

    def test_file_name_carries_the_port_and_is_safe(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM/8")

        assert "/" not in rec.session["file"]
        assert "COM_8" in rec.session["file"]
        rec.stop()

    def test_same_second_reconnect_does_not_overwrite_the_previous_file(self, tmp_path):
        first = rc.Recorder(tmp_path / "records", monotonic=FakeClock())
        first.start("COM8")
        first.on_sample(1700000000000, 12.0, 1.0)
        first.stop()
        second = rc.Recorder(tmp_path / "records", monotonic=FakeClock())
        second.start("COM8")
        second.on_sample(1700000005000, 13.0, 2.0)
        second.stop()

        names = [entry["file"] for entry in index_of(tmp_path)["sessions"]]

        assert len(set(names)) == 2
        assert all((tmp_path / "records" / name).is_file() for name in names)

    def test_unique_path_yields_a_free_name(self, tmp_path):
        target = tmp_path / "20261121T132200_COM8.csv"
        target.write_text("x", encoding="utf-8")

        assert rc._unique_path(tmp_path, target.name).name == "20261121T132200_COM8_2.csv"

    def test_start_twice_does_not_open_a_second_file(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM8")
        name = rec.session["file"]

        assert rec.start("COM9") is True
        assert rec.session["file"] == name
        rec.stop()


class TestCrashRecovery:
    def test_leftover_recording_entry_becomes_interrupted_with_real_counts(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM8")
        for index in range(3):
            rec.on_sample(1700000000000 + index * 500, 12.0, 1.0)
        rec._handle.flush()
        # 进程在这里被强杀：没走 stop，清单里还是 status=recording、rows=0。

        changed = rc.reconcile_interrupted(tmp_path / "records")

        entry = index_of(tmp_path)["sessions"][0]
        assert changed == 1
        assert entry["status"] == "interrupted"
        assert entry["rows"] == 3
        assert entry["bytes"] == (tmp_path / "records" / entry["file"]).stat().st_size
        assert entry["ended_at"]     # 至少知道数据到什么时候为止

    def test_reconcile_is_idempotent_and_leaves_closed_entries_alone(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM8")
        rec.on_sample(1700000000000, 12.0, 1.0)
        rec.stop()

        assert rc.reconcile_interrupted(tmp_path / "records") == 0
        assert index_of(tmp_path)["sessions"][0]["status"] == "closed"

    def test_reconcile_survives_a_missing_data_file(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM8")
        rec.on_sample(1700000000000, 12.0, 1.0)
        rec._handle.close()
        (tmp_path / "records" / open_name(rec)).unlink()

        assert rc.reconcile_interrupted(tmp_path / "records") == 1
        entry = index_of(tmp_path)["sessions"][0]
        assert entry["status"] == "interrupted"
        assert entry["rows"] == 0 and entry["bytes"] == 0

    def test_reconcile_on_a_directory_that_never_recorded(self, tmp_path):
        assert rc.reconcile_interrupted(tmp_path / "nowhere") == 0


class TestWriteFailure:
    def test_uncreatable_directory_stops_recording_without_raising(self, tmp_path):
        blocker = tmp_path / "records"
        blocker.write_text("我不是目录", encoding="utf-8")
        rec, _ = make(tmp_path)

        assert rec.start("COM8") is False
        assert rec.active is False
        assert "无法创建" in rec.failure_reason
        assert not (tmp_path / "records" / "index.json").exists()

    def test_write_error_ends_the_session_and_keeps_earlier_rows(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM8")
        name = open_name(rec)
        rec.on_sample(1700000000000, 12.0, 1.0)
        rec._handle.flush()

        rec._csv_writer = FailingWriter("disk full")

        assert rec.on_sample(1700000000500, 12.1, 1.1) is False
        assert rec.active is False
        assert "disk full" in rec.failure_reason

        entry = index_of(tmp_path)["sessions"][0]
        assert entry["status"] == "interrupted"
        assert entry["rows"] == 1
        assert len(disk_rows(rec.records_dir, name)) == 2   # 第一条已经在盘上，不丢

    def test_write_error_before_any_row_leaves_nothing_behind(self, tmp_path):
        rec, _ = make(tmp_path)
        rec.start("COM8")
        name = open_name(rec)

        rec._csv_writer = FailingWriter("device busy")
        rec.on_sample(1700000000000, 12.0, 1.0)

        assert index_of(tmp_path)["sessions"] == []
        assert not (tmp_path / "records" / name).exists()

    def test_recorder_never_reads_the_device_itself(self, tmp_path):
        """记录器只吃调用方喂进来的值：自己读串口会让每周期多两次往返。"""
        import inspect

        text = inspect.getsource(rc)

        assert "import serial" not in text
        assert "get_voltage" not in text and "get_current" not in text


class TestIndexRobustness:
    def test_unreadable_index_reads_as_empty(self, tmp_path):
        path = tmp_path / "index.json"
        path.write_text("{not json", encoding="utf-8")

        assert rc.load_index(path) == []

    def test_unsupported_version_reads_as_empty(self, tmp_path):
        path = tmp_path / "index.json"
        path.write_text(json.dumps({"version": 99, "sessions": [{"id": "a"}]}),
                        encoding="utf-8")

        assert rc.load_index(path) == []

    def test_entries_without_id_are_dropped(self, tmp_path):
        path = tmp_path / "index.json"
        path.write_text(json.dumps({"version": 1, "sessions": [{"file": "x.csv"}]}),
                        encoding="utf-8")

        assert rc.load_index(path) == []
