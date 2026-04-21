"""对比分析测试"""
import pytest
from training.services.comparison_service import compare_periods
from training.services.session_service import get_session_detail


class TestComparePeriods:
    def test_30day_comparison(self):
        data = compare_periods(days=30)
        assert 'current_period' in data
        assert 'previous_period' in data
        assert 'metrics' in data
        assert len(data['metrics']) > 0
        assert 'summary' in data

    def test_metrics_structure(self):
        data = compare_periods(days=30)
        for m in data['metrics']:
            assert 'name' in m
            assert 'current' in m
            assert 'previous' in m
            assert 'trend' in m
            assert m['trend'] in ('better', 'worse', 'same')


class TestSessionComparison:
    def test_with_valid_session(self):
        # Use session 324 (latest running)
        data = get_session_detail(324)
        assert data is not None
        assert 'session' in data
        assert 'laps' in data

    def test_with_invalid_session(self):
        data = get_session_detail(99999)
        assert data is None

    def test_comparison_data(self):
        data = get_session_detail(324)
        if data and data.get('comparison'):
            comp = data['comparison']
            assert 'metrics' in comp
            assert 'overall' in comp
            assert comp['overall'] in ('improving', 'declining', 'stable')
