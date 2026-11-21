"""发现盘上的会话、整读记录并按采样时刻切成连续段。

复看的访问模式是"整读一个会话"，没有按条件筛选，因此分块读取 + 让出事件循环
就够用，不引入线程也不引入数据库。缺口不写占位行，改由读取侧按相邻记录的时间
间隔断段，使中断在图上表现为空洞而不是被直线连起来。
"""

import asyncio
import itertools
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .recorder import INDEX_FILE_NAME, load_index

logger = logging.getLogger(__name__)

# 相邻记录间隔超过标称周期的这个倍数即视为缺口。
GAP_FACTOR = 2.5

# 每解析这么多行让出一次事件循环：载入 24 小时的会话期间界面还得画得动进度条。
READ_CHUNK_ROWS = 20000

_HEADER_TOKEN = "ts_ms"


@dataclass
class LoadResult:
    """一次会话载入的产出：可用样本与坏行计数。

    坏行只跳过不致命：手工编辑过或被截断的文件里，能画出来的部分仍然要画出来。
    """

    samples: list[tuple[int, float, float]] = field(default_factory=list)
    skipped: int = 0


def list_sessions(records_dir) -> list[dict]:
    """按开始时刻倒序列出会话，并标注数据文件是否还在。

    文件缺失的条目留在列表里标记为不可用：清单是这段数据存在过的唯一凭据，
    悄悄删掉等于告诉用户"从来没录过"。
    """
    root = Path(records_dir)
    entries = load_index(root / INDEX_FILE_NAME)
    for entry in entries:
        entry["available"] = (root / str(entry.get("file", ""))).is_file()
        entry["duration_s"] = duration_seconds(entry)
    entries.sort(key=lambda entry: entry.get("started_at") or "", reverse=True)
    return entries


def duration_seconds(entry: dict):
    """会话时长（秒）；缺结束时间或时间戳不可解析时返回 None，不拿现在凑。

    时长是复看列表要显示的第三项事实，但清单里的时间戳可能来自被手工编辑过或
    跨时区改过时的文件，凑一个数比承认不知道更容易骗人。
    """
    start = _parse_iso(entry.get("started_at"))
    end = _parse_iso(entry.get("ended_at"))
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds())


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def storage_summary(records_dir) -> dict:
    """记录目录的体积与会话数：容量提示用，不提供任何清理动作。"""
    root = Path(records_dir)
    files = [path for path in root.glob("*.csv") if path.is_file()] if root.is_dir() else []
    return {
        "dir": str(root),
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
    }


async def load_session(path, chunk_rows: int = READ_CHUNK_ROWS, on_progress=None) -> LoadResult:
    """整读一份会话 CSV，每 chunk_rows 行让出一次事件循环。

    读的是本地小文件（24 小时约 7 MB），同步读加解析即已满足复看的耗时要求；
    线程池会让"载入中被再次点击"变成竞态，这里用让出循环的协作式分块代替。
    """
    result = LoadResult()
    path = Path(path)
    with open(path, "r", encoding="utf-8", newline="") as handle:
        first = handle.readline()
        if not first.startswith(_HEADER_TOKEN):
            handle.seek(0)
        # islice 而不是 readlines(hint)：后者的参数按字节近似，一次交出的行数说不准，
        # 进度条也就跟着忽快忽慢。
        while True:
            lines = list(itertools.islice(handle, chunk_rows))
            if not lines:
                break
            for line in lines:
                if not line.strip():
                    continue
                sample = _parse_row(line)
                if sample is None:
                    result.skipped += 1
                    continue
                result.samples.append(sample)
            if on_progress is not None:
                on_progress(len(result.samples), result.skipped)
            await asyncio.sleep(0)

    if result.skipped:
        logger.warning("%s 有 %d 行无法解析，已跳过", path.name, result.skipped)
    # 手工改时或 NTP 回拨会写出乱序行：绘制侧用 bisect 按时刻取窗，进来时必须有序。
    if len(result.samples) > 1:
        result.samples.sort(key=lambda sample: sample[0])
    return result


def _parse_row(line: str):
    """解析一行成 (ts_ms, voltage, current)；不完整或非数值一律判为坏行。"""
    fields = line.rstrip("\r\n").split(",")
    if len(fields) < 4:
        return None
    try:
        return int(fields[0]), float(fields[2]), float(fields[3])
    except ValueError:
        return None


def split_by_gaps(samples, nominal_interval_ms: int, factor: float = GAP_FACTOR) -> list[list]:
    """按相邻记录的时间间隔把一段会话切成连续段，缺口两侧分属不同段。

    记录侧不为失败周期写占位行，所以图上必须靠分段来表现中断：整段一次画完会把
    掉线前后的两点连成一条直线，把事故画成渐变。
    """
    if not samples:
        return []
    limit = nominal_interval_ms * factor
    segments: list[list] = []
    current = [samples[0]]
    for previous, sample in zip(samples, samples[1:]):
        if sample[0] - previous[0] > limit:
            segments.append(current)
            current = [sample]
        else:
            current.append(sample)
    segments.append(current)
    return segments
