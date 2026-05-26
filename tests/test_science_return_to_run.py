"""training/science/rehab/return_to_run.py 单元测试"""
from datetime import date, timedelta

from training.science.common.athlete_profile import Injury
from training.science.rehab.return_to_run import assess_return_to_run


def _surgery_days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def test_no_injury_returns_full_stage5():
    r = assess_return_to_run(None, today_vas=0)
    assert r.stage == 5
    assert r.today_action == "keep"


def test_high_pain_triggers_back_off():
    inj = Injury(site="L_knee", grade="II", current_stage=4, last_pain_vas=2, capacity_pct=70)
    r = assess_return_to_run(inj, today_vas=5)
    assert r.today_action == "back-off"
    assert r.stage <= 4
    assert "cross-training" in " ".join(r.do)


def test_postop_under_6mo_blocks_high_intensity():
    inj = Injury(
        site="L_knee", grade="III post-op",
        surgery_date=_surgery_days_ago(120),  # 4 个月前手术
        current_stage=4, last_pain_vas=1, capacity_pct=80,
    )
    r = assess_return_to_run(inj, today_vas=1, weekly_hard_min=30)
    assert r.today_action == "back-off"
    assert "Z4" in " ".join(r.avoid + r.do).upper() or "节奏" in " ".join(r.avoid)


def test_advance_when_three_low_vas_sessions():
    inj = Injury(
        site="L_knee", grade="II",
        current_stage=3, last_pain_vas=1, capacity_pct=85,
    )
    # 最近三课 VAS 都 ≤ 2
    r = assess_return_to_run(inj, today_vas=1, recent_vas=[1, 1, 2])
    assert r.today_action == "advance"
    assert r.stage == 4


def test_postop_advance_blocked_by_min_days():
    """术后 30 天的 stage 1 → 不允许进 stage 2（要求 60 天）"""
    inj = Injury(
        site="L_knee", grade="III post-op",
        surgery_date=_surgery_days_ago(30),
        current_stage=1, last_pain_vas=1, capacity_pct=60,
    )
    r = assess_return_to_run(inj, today_vas=1, recent_vas=[1, 1, 1])
    assert r.today_action == "keep"
    assert r.stage == 1


def test_recent_high_vas_blocks_advance():
    """近 7 天有 VAS>4 事件 → 不能进阶"""
    inj = Injury(site="L_knee", grade="II", current_stage=3, last_pain_vas=1, capacity_pct=80)
    r = assess_return_to_run(inj, today_vas=1, recent_vas=[1, 1, 5, 2])
    assert r.today_action == "keep"
