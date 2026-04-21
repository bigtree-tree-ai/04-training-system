"""恢复系统测试"""
import pytest
from training.planning.recovery import assess_recovery_status, suggest_today_activity


class TestAssessRecoveryStatus:
    def test_fully_recovered(self):
        r = assess_recovery_status(tsb=20, consecutive_days=1, weekly_tss=100)
        assert r['score'] >= 70
        assert r['status'] == '充分恢复'

    def test_fatigued(self):
        r = assess_recovery_status(tsb=-25, consecutive_days=5, weekly_tss=400)
        assert r['score'] < 30

    def test_moderate(self):
        r = assess_recovery_status(tsb=0, consecutive_days=2, weekly_tss=200)
        assert 30 <= r['score'] <= 70

    def test_high_monotony(self):
        normal = assess_recovery_status(tsb=5, consecutive_days=2, weekly_tss=200, monotony=1.5)
        high = assess_recovery_status(tsb=5, consecutive_days=2, weekly_tss=200, monotony=2.5)
        assert high['score'] < normal['score']

    def test_score_bounds(self):
        r = assess_recovery_status(tsb=-50, consecutive_days=7, weekly_tss=600, monotony=3.0)
        assert r['score'] >= 0
        r = assess_recovery_status(tsb=40, consecutive_days=0, weekly_tss=0)
        assert r['score'] <= 100


class TestSuggestTodayActivity:
    def test_well_recovered(self):
        status = {'score': 80}
        activity = suggest_today_activity(status, tsb=10, consecutive_days=1)
        assert activity['activity'] == '按计划训练'

    def test_moderately_recovered(self):
        status = {'score': 55}
        activity = suggest_today_activity(status, tsb=0, consecutive_days=3)
        assert '轻松' in activity['activity'] or '恢复' in activity['activity']

    def test_severely_fatigued(self):
        status = {'score': 15}
        activity = suggest_today_activity(status, tsb=-30, consecutive_days=6)
        assert '休息' in activity['activity']
