"""training/science/training/pyramid.py 单元测试"""
from training.science.training.pyramid import polarization_check


def test_polarized_distribution():
    """82% Z1+Z2，3% Z3，15% Z4+Z5 → polarized"""
    p = polarization_check(z1_sec=3000, z2_sec=4920, z3_sec=300, z4_sec=900, z5_sec=600)
    assert p.verdict == "polarized"
    assert p.easy_pct >= 80
    assert p.hard_pct >= 8


def test_threshold_heavy_distribution():
    """30%+ Z3 → threshold_heavy"""
    p = polarization_check(z1_sec=2000, z2_sec=2000, z3_sec=3000, z4_sec=500, z5_sec=500)
    assert p.verdict == "threshold_heavy"


def test_easy_heavy_distribution():
    """全 Z1+Z2，无强度 → easy_heavy"""
    p = polarization_check(z1_sec=4000, z2_sec=5000, z3_sec=100, z4_sec=0, z5_sec=0)
    assert p.verdict == "easy_heavy"


def test_no_data():
    p = polarization_check()
    assert p.verdict == "no_data"


def test_polarization_index_computed_when_z2_positive():
    p = polarization_check(z1_sec=3000, z2_sec=3000, z3_sec=300, z4_sec=600, z5_sec=200)
    assert p.polarization_index is not None
