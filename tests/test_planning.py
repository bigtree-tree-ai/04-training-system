"""训练计划生成测试"""
import pytest
from training.planning.generator import _determine_phase, _plan_week
from datetime import date


class TestDeterminePhase:
    def test_base_phase(self):
        assert _determine_phase(25) == "基础期"

    def test_build_phase(self):
        assert _determine_phase(15) == "提升期"

    def test_race_prep(self):
        assert _determine_phase(8) == "竞赛准备期"

    def test_taper(self):
        assert _determine_phase(3) == "赛前减量期"

    def test_race_week(self):
        assert _determine_phase(0) == "比赛周"


class TestPlanWeek:
    def test_normal_week_has_7_days(self):
        days = _plan_week(date(2026, 5, 4), 1, 40.0, 390, "基础期", False)
        assert len(days) == 7

    def test_recovery_week_has_7_days(self):
        days = _plan_week(date(2026, 5, 4), 4, 26.0, 390, "基础期", True)
        assert len(days) == 7

    def test_rest_days_have_no_distance(self):
        days = _plan_week(date(2026, 5, 4), 1, 40.0, 390, "基础期", False)
        rest_days = [d for d in days if d['workout_type'] == 'Rest']
        assert len(rest_days) >= 2
        for d in rest_days:
            assert d['target_distance_km'] is None

    def test_workout_days_have_distance(self):
        days = _plan_week(date(2026, 5, 4), 1, 40.0, 390, "基础期", False)
        workout_days = [d for d in days if d['workout_type'] != 'Rest']
        for d in workout_days:
            assert d['target_distance_km'] is not None
            assert d['target_distance_km'] > 0

    def test_long_run_on_sunday(self):
        days = _plan_week(date(2026, 5, 4), 1, 40.0, 390, "基础期", False)
        sunday = days[6]  # Monday=0, Sunday=6
        assert sunday['workout_type'] == 'Long Run'
