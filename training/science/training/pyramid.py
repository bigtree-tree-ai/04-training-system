"""80/20 极化训练检查 — Seiler 2009/2014 + Treff 2019 PI

输入：心率分区时间分布（z1..z5 秒数）
输出：PolarizationCheck dataclass
"""
from __future__ import annotations

import math
from typing import Optional

from training.science.common.schemas import PolarizationCheck


def polarization_check(
    z1_sec: float = 0.0,
    z2_sec: float = 0.0,
    z3_sec: float = 0.0,
    z4_sec: float = 0.0,
    z5_sec: float = 0.0,
    days_window: int = 7,
) -> PolarizationCheck:
    total = z1_sec + z2_sec + z3_sec + z4_sec + z5_sec
    if total <= 0:
        return PolarizationCheck(0, 0, 0, None, "no_data", days_window)

    easy = (z1_sec + z2_sec) / total * 100
    moderate = z3_sec / total * 100
    hard = (z4_sec + z5_sec) / total * 100

    pi: Optional[float] = None
    if z2_sec > 0 and z1_sec > 0 and z3_sec > 0:
        pi = round(math.log10((z1_sec * z3_sec) / (z2_sec ** 2)) if z2_sec else 0, 3)

    if easy >= 80 and hard >= 8:
        verdict = "polarized"
    elif moderate >= 30:
        verdict = "threshold_heavy"
    elif easy >= 90 and hard < 5:
        verdict = "easy_heavy"
    else:
        verdict = "balanced"
    return PolarizationCheck(
        easy_pct=round(easy, 1),
        moderate_pct=round(moderate, 1),
        hard_pct=round(hard, 1),
        polarization_index=pi,
        verdict=verdict,
        days_window=days_window,
    )
