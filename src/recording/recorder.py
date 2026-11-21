"""把每个采样周期的成对读数追加写入按会话切分的 CSV，并维护会话清单。

一次会话 = 一段"记录使能且设备已连接"的时间。会话建立即以 status=recording 登记到
records/index.json，结束时改写为 closed；进程被强杀留下的 recording 条目在下次启动
时按文件实际内容改判为 interrupted，已落盘的数据保持可复看。

采集失败不写占位行：缺口由复看侧按相邻记录的时间间隔呈现。
"""

import csv
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from .settings import atomic_write_json

logger = logging.getLogger(__name__)

INDEX_FILE_NAME = "index.json"
INDEX_SCHEMA_VERSION = 1

# 脱离应用也能判读的固定列头：ts_ms 供绘图与排序，iso_local 供人读。
CSV_HEADER = ["ts_ms", "iso_local", "voltage_v", "current_a"]

STATUS_RECORDING = "recording"
STATUS_CLOSED = "closed"
STATUS_INTERRUPTED = "interrupted"

# 每这么多秒把缓冲刷到盘上：每行都 flush 会让一次磁盘抖动直接拖住事件循环，
# 从不 flush 又会在崩溃时丢掉整段。2 秒 = 500ms 轮询下的 4 个采样周期。
FLUSH_INTERVAL_SECONDS = 2.0

_FILE_NAME_STEM = "%Y%m%dT%H%M%S"


def _iso(ts_seconds: float) -> str:
    return datetime.fromtimestamp(ts_seconds).astimezone().isoformat(timespec="milliseconds")


def load_index(index_path) -> list[dict]:
    """读会话清单；文件缺失或内容不可用一律当作"没有历史"，不抛异常。"""
    path = Path(index_path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        logger.warning("record index unreadable, treating it as empty: %s (%s)", path, exc)
        return []

    if not isinstance(document, dict) or document.get("version") != INDEX_SCHEMA_VERSION:
        logger.warning("record index version unsupported, treating it as empty: %s", path)
        return []
    sessions = document.get("sessions")
    if not isinstance(sessions, list):
        return []
    return [entry for entry in sessions if isinstance(entry, dict) and entry.get("id")]


class Recorder:
    """一条连接会话的落盘写入器。

    只接受调用方喂进来的成对读数，不碰串口也不碰 Qt：presenter 负责周期与取数，
    这里只负责"要不要写、写成什么样、登记在哪"。
    """

    def __init__(self, records_dir,
                 monotonic=time.monotonic,
                 flush_interval_s: float = FLUSH_INTERVAL_SECONDS):
        self.records_dir = Path(records_dir)
        self.index_path = self.records_dir / INDEX_FILE_NAME
        self._monotonic = monotonic
        self._flush_interval_s = flush_interval_s

        self.active = False
        self.failure_reason: str | None = None
        self._handle = None
        self._csv_writer = None
        self._entry: dict | None = None
        self._rows = 0
        self._next_flush = 0.0

    @property
    def session(self) -> dict | None:
        return self._entry

    @property
    def rows(self) -> int:
        """本次会话已写入的数据行数（不含列头）。"""
        return self._rows

    def start(self, port: str) -> bool:
        """建立新会话。失败时置 failure_reason 并保持不在录制状态。"""
        if self.active:
            return True
        self.failure_reason = None
        started_at = time.time()
        stem = datetime.fromtimestamp(started_at).strftime(_FILE_NAME_STEM)
        session_id = f"{stem}_{_safe(port)}"
        try:
            self.records_dir.mkdir(parents=True, exist_ok=True)
            # 同一秒内重连会让时刻前缀撞车，撞车即改写上一段数据：编号让位。
            path = _unique_path(self.records_dir, f"{session_id}.csv")
            session_id = path.stem
            handle = open(path, "x", encoding="utf-8", newline="")
            writer = csv.writer(handle)
            writer.writerow(CSV_HEADER)
            handle.flush()
        except OSError as exc:
            self.failure_reason = f"无法创建记录文件：{exc}"
            logger.error("recording cannot start: %s", self.failure_reason)
            return False

        self._handle = handle
        self._csv_writer = writer
        self._rows = 0
        self._next_flush = self._monotonic() + self._flush_interval_s
        self._entry = {
            "id": session_id,
            "file": path.name,
            "port": port,
            "started_at": _iso(started_at),
            "ended_at": None,
            "rows": 0,
            "bytes": 0,
            "status": STATUS_RECORDING,
        }
        self.active = True
        # 开始即登记：进程被强杀时至少还有一个可发现的入口。
        _upsert_session(self.index_path, self._entry)
        logger.info("recording session started: %s", path.name)
        return True

    def on_sample(self, ts_ms: int, voltage, current) -> bool:
        """写入一条成对读数；任一读数缺失就整条丢弃，绝不写半条。"""
        if not self.active:
            return False
        if voltage is None or current is None:
            logger.info("丢弃不完整采样（voltage=%r current=%r），该周期在数据中留为缺口",
                        voltage, current)
            return False

        try:
            self._csv_writer.writerow([int(ts_ms), _iso(ts_ms / 1000), voltage, current])
            self._rows += 1
            if self._monotonic() >= self._next_flush:
                self._handle.flush()
                self._next_flush = self._monotonic() + self._flush_interval_s
        except OSError as exc:
            self._fail(f"写入失败：{exc}")
            return False
        return True

    def stop(self) -> dict | None:
        """结束当前会话；一条记录都没有时不留下文件与清单条目。"""
        if not self.active:
            return None
        entry, self._entry = self._entry, None
        handle, self._handle, self._csv_writer = self._handle, None, None
        self.active = False

        path = self.records_dir / entry["file"]
        try:
            handle.close()
        except OSError as exc:
            logger.warning("failed to close record file %s (%s)", path.name, exc)

        if self._rows == 0:
            _remove_quietly(path)
            _drop_session(self.index_path, entry["id"])
            logger.info("会话 %s 未采到记录，不留空文件", entry["id"])
            return None

        entry["ended_at"] = _iso(time.time())
        entry["rows"] = self._rows
        entry["bytes"] = _size_of(path)
        entry["status"] = STATUS_CLOSED
        _upsert_session(self.index_path, entry)
        logger.info("recording session closed: %s rows=%d", path.name, self._rows)
        return entry

    def _fail(self, reason: str) -> None:
        """记录侧的故障只结束记录：采样、控制与显示必须照常。"""
        logger.error("recording stopped: %s", reason)
        self.failure_reason = reason
        entry, self._entry = self._entry, None
        handle, self._handle, self._csv_writer = self._handle, None, None
        self.active = False
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if entry is None:
            return
        if self._rows == 0:
            _remove_quietly(self.records_dir / entry["file"])
            _drop_session(self.index_path, entry["id"])
            return
        entry["ended_at"] = _iso(time.time())
        entry["rows"] = self._rows
        entry["bytes"] = _size_of(self.records_dir / entry["file"])
        entry["status"] = STATUS_INTERRUPTED
        _upsert_session(self.index_path, entry)


def _save_index(index_path, sessions: list[dict]) -> None:
    sessions.sort(key=lambda entry: entry.get("started_at") or "")
    atomic_write_json(index_path, {
        "version": INDEX_SCHEMA_VERSION,
        "sessions": sessions,
    })


def _upsert_session(index_path, entry: dict) -> None:
    """按 id 覆盖写回一条会话：清单里永远以最后一次提交的条目为准。"""
    sessions = [item for item in load_index(index_path) if item["id"] != entry["id"]]
    sessions.append(dict(entry))
    _save_index(index_path, sessions)


def _drop_session(index_path, session_id: str) -> None:
    kept = [item for item in load_index(index_path) if item["id"] != session_id]
    _save_index(index_path, kept)


def reconcile_interrupted(records_dir) -> int:
    """启动收尾：上次没走完的 recording 条目按文件实际内容改判为 interrupted。

    进程被强杀时清单里的行数与文件大小都还是启动时的旧值，这里以盘上事实为准，
    使复看列表显示的点数与真实数据一致。
    """
    index_path = Path(records_dir) / INDEX_FILE_NAME
    sessions = load_index(index_path)
    changed = 0
    for entry in sessions:
        if entry.get("status") != STATUS_RECORDING:
            continue
        path = Path(records_dir) / str(entry.get("file", ""))
        rows, last_iso = _scan_file(path)
        entry["status"] = STATUS_INTERRUPTED
        entry["rows"] = rows
        entry["bytes"] = _size_of(path)
        entry["ended_at"] = last_iso
        changed += 1
    if changed:
        _save_index(index_path, sessions)
        logger.info("已将 %d 个未收尾的会话标记为 interrupted", changed)
    return changed


def _scan_file(path: Path) -> tuple[int, str | None]:
    """数出数据行数并取最后一条的本地时刻；文件不存在时返回 (0, None)。"""
    rows = 0
    last_iso = None
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            for index, line in enumerate(handle):
                if index == 0:
                    continue
                fields = line.rstrip("\r\n").split(",")
                if len(fields) >= 2:
                    rows += 1
                    last_iso = fields[1]
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("cannot scan record file %s (%s)", path, exc)
        return 0, None
    return rows, last_iso


def _safe(name: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in str(name)) or "port"


def _unique_path(records_dir: Path, name: str) -> Path:
    """同名就让位成 _2、_3：会话文件名以秒为精度，同一秒内重连必然撞车。"""
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate = records_dir / name
    index = 2
    while candidate.exists():
        candidate = records_dir / f"{stem}_{index}{suffix}"
        index += 1
    return candidate


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _remove_quietly(path: Path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
