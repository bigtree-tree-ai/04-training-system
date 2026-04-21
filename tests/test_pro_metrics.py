"""专业指标计算函数测试"""
import pytest
from training.analysis.pro_metrics import (
    estimate_vo2max, compute_acwr, determine_training_status,
    classify_training_type, classify_training_effect,
    estimate_recovery_hours, predict_race_time, compute_marathon_shape,
)


class TestEstimateVO2max:
    def test_normal_run(self):
        # 10km, 50min, 5:00/km, HR=145
        vo2 = estimate_vo2max(avg_pace_sec=300, avg_hr=145, duration_sec=3000, distance_km=10)
        assert vo2 is not None
        assert 30 < vo2 < 70

    def test_too_short_distance(self):
        assert estimate_vo2max(300, 145, 600, 1.5) is None

    def test_too_short_duration(self):
        assert estimate_vo2max(300, 145, 500, 3) is None

    def test_no_hr(self):
        assert estimate_vo2max(300, None, 3000, 10) is None

    def test_low_hr(self):
        # HR below resting
        assert estimate_vo2max(300, 50, 3000, 10) is None

    def test_extreme_hr(self):
        # HR above max → hr_frac > 1.0
        assert estimate_vo2max(300, 200, 3000, 10) is None


class TestComputeACWR:
    def test_normal(self):
        loads = [{'daily_tss': 50}] * 28
        acwr = compute_acwr(loads)
        assert acwr == 1.0

    def test_acute_spike(self):
        loads = [{'daily_tss': 30}] * 21 + [{'daily_tss': 100}] * 7
        acwr = compute_acwr(loads)
        assert acwr > 1.0

    def test_insufficient_data(self):
        loads = [{'daily_tss': 50}] * 20
        assert compute_acwr(loads) is None

    def test_zero_chronic(self):
        loads = [{'daily_tss': 0}] * 28
        assert compute_acwr(loads) is None


class TestDetermineTrainingStatus:
    def test_peaking(self):
        assert determine_training_status(ctl=30, atl=20, tsb=15) == "Peaking"

    def test_overreaching(self):
        assert determine_training_status(ctl=40, atl=70, tsb=-35) == "Overreaching"

    def test_strained(self):
        assert determine_training_status(ctl=40, atl=60, tsb=-25, monotony=2.5) == "Strained"

    def test_recovery(self):
        assert determine_training_status(ctl=10, atl=5, tsb=5) == "Recovery"

    def test_unknown(self):
        assert determine_training_status(None, None, None) == "Unknown"


class TestClassifyTrainingType:
    def test_easy_run(self):
        # HRR = (130-56)/117 = 0.63 → Easy Run
        assert classify_training_type(130, 360, 2400, 8) == "Easy Run"

    def test_long_run(self):
        # HRR = 0.63 but distance >= 15
        assert classify_training_type(130, 380, 6000, 18) == "Long Run"

    def test_tempo(self):
        # HRR = (148-56)/117 = 0.79 → Tempo
        assert classify_training_type(148, 300, 2400, 8) == "Tempo"

    def test_threshold(self):
        # HRR = (158-56)/117 = 0.87 → Threshold
        assert classify_training_type(158, 280, 2400, 8) == "Threshold"

    def test_interval(self):
        # HRR = (165-56)/117 = 0.93 → Interval
        assert classify_training_type(165, 260, 1800, 6) == "Interval"

    def test_recovery(self):
        # HRR = (110-56)/117 = 0.46 → Recovery
        assert classify_training_type(110, 420, 1800, 5) == "Recovery"

    def test_no_hr(self):
        assert classify_training_type(None, 300, 2400, 8) == "Unknown"


class TestClassifyTrainingEffect:
    def test_easy(self):
        assert classify_training_effect("Easy Run") == "Base"

    def test_interval(self):
        assert classify_training_effect("Interval") == "VO2max"


class TestEstimateRecoveryHours:
    def test_easy_low_tss(self):
        hrs = estimate_recovery_hours(25, "Easy Run")
        assert hrs < 20

    def test_hard_high_tss(self):
        hrs = estimate_recovery_hours(120, "Interval")
        assert hrs > 40

    def test_no_tss(self):
        assert estimate_recovery_hours(None, "Easy Run") == 12

    def test_fatigue_penalty(self):
        normal = estimate_recovery_hours(80, "Tempo", tsb=0)
        fatigued = estimate_recovery_hours(80, "Tempo", tsb=-25)
        assert fatigued > normal


class TestPredictRaceTime:
    def test_normal(self):
        t = predict_race_time(50, 42.195)
        assert t is not None
        assert 5000 < t < 25000  # reasonable marathon range

    def test_5k(self):
        t = predict_race_time(50, 5.0)
        assert t is not None
        assert 600 < t < 2400  # 10min ~ 40min

    def test_invalid_vo2(self):
        assert predict_race_time(None, 42.195) is None
        assert predict_race_time(20, 42.195) is None


class TestComputeMarathonShape:
    def test_empty(self):
        assert compute_marathon_shape([]) == 0.0

    def test_good_preparation(self):
        sessions = [
            {'distance_km': 25}, {'distance_km': 20}, {'distance_km': 18},
            {'distance_km': 22}, {'distance_km': 30}, {'distance_km': 15},
        ]
        score = compute_marathon_shape(sessions)
        assert score > 50

    def test_short_runs_only(self):
        sessions = [{'distance_km': 5}] * 10
        score = compute_marathon_shape(sessions)
        assert score < 30
