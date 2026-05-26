"""长距离补给方案 — Jeukendrup multi-transportable CHO

时长 < 75 min：通常无需补碳水
75-120 min：30-60 g/h
> 2.5h：60-90 g/h（葡萄糖+果糖混合）

电解质：Na 出汗率 × 汗钠浓度（默认 800-1200 mg/L）
"""
from __future__ import annotations

from typing import Optional


def fueling_plan(
    duration_min: float,
    sweat_rate_ml_per_h: float = 800.0,
    sweat_na_mg_per_l: float = 1000.0,
    gi_tolerance_max: int = 60,
) -> dict:
    if duration_min < 75:
        cho_per_h = 0
    elif duration_min < 150:
        cho_per_h = min(45, gi_tolerance_max)
    else:
        cho_per_h = min(80, gi_tolerance_max)

    fluid_per_h = round(sweat_rate_ml_per_h * 0.7, 0)  # 替代 70% 汗液
    na_per_h = round(sweat_rate_ml_per_h / 1000 * sweat_na_mg_per_l * 0.7, 0)

    return {
        "duration_min": duration_min,
        "cho_g_per_h": cho_per_h,
        "fluid_ml_per_h": fluid_per_h,
        "na_mg_per_h": na_per_h,
        "advice": _advice(duration_min, cho_per_h),
    }


def _advice(duration_min: float, cho_per_h: int) -> list[str]:
    out: list[str] = []
    if duration_min >= 90 and cho_per_h < 30:
        out.append("长课>90分钟但 CHO 摄入<30g/h — 低糖训练状态风险")
    if duration_min >= 150:
        out.append("使用葡萄糖+果糖（2:1 比例）混合补给以提高吸收上限")
    if duration_min >= 180:
        out.append("赛前 24h 完成糖原装载（CHO ≥ 8 g/kg）")
    return out
