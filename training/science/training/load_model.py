"""训练负荷模型 — Banister TRIMP / Coggan TSS / Friel PMC + 增强

新增（相比 training/analysis/pro_metrics.py）：
- 7d:28d 滚动 ACWR（取代单一 4 周窗口）
- Monotony = mean(7d_load) / std(7d_load)
- Strain = monotony × weekly_load
- 综合 verdict 决策

输入：每日负荷序列 [(date_iso, load_value), ...]，按日期升序
输出：LoadProfile dataclass

理论参考：
- Banister 1980 — Training impulse model
- Friel 2009 — The Triathlete's Training Bible (PMC)
- Foster 1998 — Monitoring training in athletes (monotony/strain)
- Hulin/Gabbett 2014 — ACWR 7d:28d
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Iterable, Optional

from training.science.common.schemas import LoadProfile


def _ewma(values: list[float], tau_days: int) -> float:
    """指数加权移动平均，最新值权重最高（与 Friel PMC 等价）"""
    if not values:
        return 0.0
    decay = math.exp(-1.0 / tau_days)
    avg = 0.0
    for v in values:
        avg = avg * decay + v * (1 - decay)
    return avg


def _series_to_map(series: Iterable[tuple[str, float]]) -> dict[date, float]:
    out: dict[date, float] = {}
    for d_iso, v in series:
        try:
            out[date.fromisoformat(d_iso[:10])] = float(v or 0.0)
        except (ValueError, TypeError):
            continue
    return out


def _window_sum(load_map: dict[date, float], anchor: date, days: int) -> float:
    return sum(load_map.get(anchor - timedelta(days=i), 0.0) for i in range(days))


def compute_acwr_7_28(load_series: Iterable[tuple[str, float]], anchor: Optional[date] = None) -> Optional[float]:
    """7 日:28 日急慢负荷比

    Hulin/Gabbett 2014：>1.5 高伤病风险，0.8-1.3 安全带
    """
    load_map = _series_to_map(load_series)
    if not load_map:
        return None
    a = anchor or max(load_map.keys())
    acute = _window_sum(load_map, a, 7)
    chronic_28 = _window_sum(load_map, a, 28)
    if chronic_28 <= 0:
        return None
    chronic_avg_per_week = chronic_28 / 4.0
    if chronic_avg_per_week <= 0:
        return None
    return round(acute / chronic_avg_per_week, 3)


def compute_monotony_strain(load_series: Iterable[tuple[str, float]], anchor: Optional[date] = None) -> tuple[Optional[float], Optional[float]]:
    """Foster monotony/strain（基于过去 7 日）"""
    load_map = _series_to_map(load_series)
    if not load_map:
        return None, None
    a = anchor or max(load_map.keys())
    last7 = [load_map.get(a - timedelta(days=i), 0.0) for i in range(7)]
    mean = sum(last7) / 7.0
    if mean <= 0:
        return None, None
    var = sum((x - mean) ** 2 for x in last7) / 7.0
    std = math.sqrt(var)
    if std <= 0:
        return None, None
    monotony = round(mean / std, 3)
    weekly_load = sum(last7)
    strain = round(monotony * weekly_load, 1)
    return monotony, strain


def _verdict(ctl: float, atl: float, tsb: float, acwr: Optional[float], monotony: Optional[float]) -> str:
    if acwr is not None and acwr >= 1.5:
        return "high_injury_risk"
    if monotony is not None and monotony >= 2.0:
        return "monotonous_overreach"
    if tsb < -30:
        return "overreach"
    if tsb < -10:
        return "build"
    if tsb <= 5:
        return "balanced"
    if tsb <= 25:
        return "peak"
    return "detrain"


def compute_load_profile(
    load_series: Iterable[tuple[str, float]],
    anchor: Optional[date] = None,
) -> LoadProfile:
    """主入口：传入每日负荷序列，输出完整 LoadProfile

    load_series 元素 (date_iso, load_value)，date_iso 形如 '2026-05-25'
    """
    load_map = _series_to_map(load_series)
    if not load_map:
        return LoadProfile(0.0, 0.0, 0.0, None, None, None, "no_data")

    a = anchor or max(load_map.keys())
    # 取从最早到 anchor 的连续序列（含空日填 0）
    earliest = min(load_map.keys())
    days = (a - earliest).days + 1
    seq = [load_map.get(earliest + timedelta(days=i), 0.0) for i in range(days)]

    ctl = round(_ewma(seq, 42), 2)
    atl = round(_ewma(seq, 7), 2)
    tsb = round(ctl - atl, 2)
    acwr = compute_acwr_7_28(load_series, a)
    monotony, strain = compute_monotony_strain(load_series, a)
    verdict = _verdict(ctl, atl, tsb, acwr, monotony)
    return LoadProfile(ctl, atl, tsb, acwr, monotony, strain, verdict)
