"""负荷-疼痛 2D 决策矩阵

x = 当日训练负荷（hr_tss 或周相对值），y = 24h 后疼痛 VAS 变化
落点决定"keep / back-off / escalate / stop"。
"""
from __future__ import annotations

from typing import Literal

Quadrant = Literal["safe", "load_only", "pain_only", "danger", "neutral"]


def classify_load_pain(today_load: float, vas_delta_24h: float, *, weekly_avg_load: float = 0.0) -> Quadrant:
    """简单 2x2 + 中性区

    high load = today_load > 1.2 × weekly_avg（或绝对值 > 100 hr_tss）
    high pain = vas_delta_24h ≥ 2（24 小时内 VAS 上升 ≥2 分）
    """
    if weekly_avg_load > 0:
        high_load = today_load > 1.2 * weekly_avg_load
    else:
        high_load = today_load > 100
    high_pain = vas_delta_24h >= 2

    if high_load and high_pain:
        return "danger"
    if high_load and not high_pain:
        return "load_only"
    if not high_load and high_pain:
        return "pain_only"
    if today_load == 0 and vas_delta_24h == 0:
        return "neutral"
    return "safe"
