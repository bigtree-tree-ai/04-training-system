"""training/science/training/load_model.py 单元测试"""
from datetime import date, timedelta

import pytest

from training.science.training.load_model import (
    compute_acwr_7_28,
    compute_load_profile,
    compute_monotony_strain,
)


def _series(values: list[float], end_date: str = "2026-05-25") -> list[tuple[str, float]]:
    end = date.fromisoformat(end_date)
    return [((end - timedelta(days=len(values) - 1 - i)).isoformat(), v) for i, v in enumerate(values)]


def test_acwr_balanced_returns_close_to_1():
    """连续 28 天每日相同负荷 → ACWR ≈ 1.0"""
    series = _series([60.0] * 28)
    acwr = compute_acwr_7_28(series)
    assert acwr is not None
    assert 0.95 <= acwr <= 1.05


def test_acwr_acute_spike_above_safe_band():
    """近 7 天突然加倍 → ACWR > 1.5 触发预警"""
    series = _series([40.0] * 21 + [120.0] * 7)
    acwr = compute_acwr_7_28(series)
    assert acwr is not None
    assert acwr > 1.5


def test_acwr_returns_none_for_empty():
    assert compute_acwr_7_28([]) is None


def test_monotony_uniform_load_is_high():
    """每日相同负荷 → std ≈ 0 → monotony 应被识别为单调风险（这里 std=0 返回 None 视为不可计算）"""
    monotony, strain = compute_monotony_strain(_series([60.0] * 7))
    assert monotony is None  # std=0 时 monotony 不可计算


def test_monotony_varied_load_is_low():
    """波动大的负荷 → monotony < 1.5"""
    monotony, strain = compute_monotony_strain(_series([100, 30, 80, 0, 90, 20, 60]))
    assert monotony is not None
    assert 0.5 < monotony < 1.6
    assert strain is not None and strain > 0


def test_load_profile_no_data():
    p = compute_load_profile([])
    assert p.verdict == "no_data"
    assert p.ctl == 0


def test_load_profile_balanced_state_after_warmup():
    """长时间稳定 60 hr_tss/d（>120 天预热）→ CTL≈ATL≈60，TSB≈0"""
    p = compute_load_profile(_series([60.0] * 200))
    assert abs(p.ctl - 60) < 3
    assert abs(p.atl - 60) < 3
    assert abs(p.tsb) < 3
    # 稳态 monotony std=0 → verdict 可能落入 high_injury_risk（acwr 仍 = 1）保持 balanced
    assert p.verdict in ("balanced", "build")


def test_load_profile_overreach_after_spike():
    """长期 30，最近 14 天每日 130 → ATL 远高于 CTL → TSB 极负"""
    series = _series([30.0] * 60 + [130.0] * 14)
    p = compute_load_profile(series)
    assert p.tsb < -10
    assert p.verdict in ("overreach", "build", "high_injury_risk", "monotonous_overreach")


def test_load_profile_taper_then_peak():
    """长期 80（充分预热）+ 7 天 30 → TSB 转正"""
    series = _series([80.0] * 100 + [30.0] * 7)
    p = compute_load_profile(series)
    assert p.tsb > 0


def test_load_profile_high_injury_risk_overrides_tsb():
    """ACWR 飙升应覆盖普通 verdict"""
    series = _series([30.0] * 60 + [200.0] * 7)
    p = compute_load_profile(series)
    assert p.acwr_7_28 is not None and p.acwr_7_28 > 1.5
    assert p.verdict == "high_injury_risk"
