"""把长序列变成画得动的短序列：滚动窗口裁剪与分桶极值抽稀。

两个入口都不依赖 Qt，输入输出为 (x, y) 二元组序列，可以直接断言。抽稀按像素列分桶
取 min/max 包络，使单点毛刺不会因为等间隔取点而被抽掉——电源曲线要看的正是毛刺。
"""

import logging

logger = logging.getLogger(__name__)

# 每桶输出最小值与最大值两点，桶数由绘图宽度决定。
POINTS_PER_BUCKET = 2


def trim_to_window(samples, limit: int) -> list:
    """返回样本序列的最后 limit 个，把滚动窗口维持在固定宽度。"""
    if limit <= 0:
        raise ValueError(f"窗口宽度必须为正数，收到 {limit}")
    return list(samples)[-limit:]


def decimate_min_max(samples, buckets: int) -> list:
    """按横向桶位抽稀：每桶只输出该桶的最小值点与最大值点。

    等间隔跳点会让只持续一个采样的毛刺整段消失，包络法则保证它必然可见。桶内保持
    原始先后顺序输出极值点，使折线不会在桶内倒退。
    """
    if buckets <= 0:
        raise ValueError(f"桶数必须为正数，收到 {buckets}")
    points = list(samples)
    if len(points) <= buckets * POINTS_PER_BUCKET:
        return points

    span = len(points) / buckets
    result: list[tuple[float, float]] = []
    for index in range(buckets):
        start = int(index * span)
        stop = int((index + 1) * span) if index + 1 < buckets else len(points)
        chunk = points[start:stop]
        if not chunk:
            continue
        low_i = min(range(len(chunk)), key=lambda i: chunk[i][1])
        high_i = max(range(len(chunk)), key=lambda i: chunk[i][1])
        # 同一桶内先出现的先输出，避免出现往回走的折线。
        if low_i == high_i:
            result.append(chunk[low_i])
        elif low_i < high_i:
            result.append(chunk[low_i])
            result.append(chunk[high_i])
        else:
            result.append(chunk[high_i])
            result.append(chunk[low_i])
    return result
