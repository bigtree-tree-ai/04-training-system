"""专业文案解读测试"""
import pytest
from training.content.interpretations import (
    interpret_ctl, interpret_tsb, interpret_acwr, interpret_vo2max,
    interpret_training_status, interpret_hr_drift, interpret_marathon_shape,
    interpret_recovery_score, interpret_zone_distribution,
)


class TestInterpretCTL:
    def test_low(self):
        assert '恢复' in interpret_ctl(10)

    def test_medium(self):
        assert '中等' in interpret_ctl(35)

    def test_high(self):
        r = interpret_ctl(55)
        assert '优秀' in r or '精英' in r

    def test_none(self):
        r = interpret_ctl(None)
        assert r is not None  # returns empty or default text


class TestInterpretTSB:
    def test_overreaching(self):
        assert '过度' in interpret_tsb(-35).lower() or '过度' in interpret_tsb(-35)

    def test_peaking(self):
        r = interpret_tsb(12)
        assert '恢复' in r or '竞赛' in r or '良好' in r

    def test_detraining(self):
        r = interpret_tsb(30)
        assert '失训' in r or '训练' in r


class TestInterpretACWR:
    def test_safe(self):
        assert '安全' in interpret_acwr(1.1)

    def test_danger(self):
        r = interpret_acwr(1.6)
        assert '危险' in r or '高' in r or '风险' in r


class TestInterpretVO2max:
    def test_value(self):
        r = interpret_vo2max(48)
        assert 'VO2max' in r or 'VDOT' in r or '48' in r

    def test_none(self):
        r = interpret_vo2max(None)
        assert r is not None  # returns empty or default text


class TestInterpretTrainingStatus:
    def test_peaking(self):
        r = interpret_training_status('Peaking')
        assert '巅峰' in r or '最佳' in r or 'Peaking' in r

    def test_unknown(self):
        r = interpret_training_status('Unknown')
        assert len(r) > 0


class TestInterpretHRDrift:
    def test_excellent(self):
        r = interpret_hr_drift(2.0)
        assert '优秀' in r or '扎实' in r

    def test_poor(self):
        r = interpret_hr_drift(8.0)
        assert '不足' in r or '偏高' in r or '需要' in r


class TestInterpretMarathonShape:
    def test_low(self):
        r = interpret_marathon_shape(20)
        assert len(r) > 0

    def test_high(self):
        r = interpret_marathon_shape(85)
        assert len(r) > 0


class TestInterpretRecoveryScore:
    def test_good(self):
        r = interpret_recovery_score(75)
        assert '良好' in r or '正常' in r or '恢复' in r

    def test_bad(self):
        r = interpret_recovery_score(20)
        assert '疲劳' in r or '休息' in r or '恢复' in r


class TestInterpretZoneDistribution:
    def test_good(self):
        r = interpret_zone_distribution(82)
        assert '理想' in r or '良好' in r or '达标' in r or '优秀' in r

    def test_bad(self):
        r = interpret_zone_distribution(30)
        assert '失衡' in r or '偏高' in r or '太快' in r or '不足' in r
