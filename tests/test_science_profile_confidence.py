"""athlete_profile + confidence 单元测试"""
import json
from pathlib import Path

import pytest

from training.science.common.athlete_profile import load_athlete_profile
from training.science.common.confidence import score_confidence


def test_load_profile_v2_structured(tmp_path: Path):
    cfg = {
        "_schema_version": 2,
        "name": "test",
        "height_cm": 175,
        "weight_kg": 70,
        "body_fat_pct": 14,
        "ffm_kg": 60.2,
        "pal": 1.6,
        "max_heart_rate": 185,
        "resting_heart_rate": 50,
        "lactate_threshold_hr": 168,
        "zones": {
            "z1_max": 130, "z2_max": 145, "z3_max": 158, "z4_max": 170, "z5_max": 185,
            "lt_hr": 168, "cv_pace_sec": 240,
        },
        "injuries": [
            {"site": "L_knee", "grade": "III post-op", "surgery_date": "2025-11-10", "current_stage": 4, "last_pain_vas": 1.0}
        ],
    }
    p = tmp_path / "athlete.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    profile = load_athlete_profile(p)
    assert profile.schema_version == 2
    assert profile.zones.z3_max == 158
    assert profile.zones.cv_pace_sec == 240
    assert len(profile.injuries) == 1
    assert profile.injuries[0].site == "L_knee"
    assert profile.has_active_injury is True  # vas=1 > 0 视为 active
    assert profile.days_since_surgery is not None and profile.days_since_surgery > 0


def test_load_profile_v1_falls_back_to_karvonen(tmp_path: Path):
    cfg = {
        "name": "v1user",
        "max_heart_rate": 190,
        "resting_heart_rate": 60,
        "weight_kg": 65,
        "height_cm": 173,
    }
    p = tmp_path / "old.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    profile = load_athlete_profile(p)
    assert profile.schema_version == 1
    # Karvonen: hrr = 130, z2_max = 60 + 0.7*130 = 151
    assert profile.zones.z2_max == 151


def test_confidence_full_signals_high():
    c = score_confidence(
        has_today_load=True,
        has_today_checkin=True,
        hrv_latest_date="2026-05-26",
        rhr_latest_date="2026-05-26",
        sleep_latest_date="2026-05-26",
        last_session_date="2026-05-25",
        profile_complete=True,
        injuries_structured=True,
    )
    assert c.score >= 0.8
    assert c.level == "high"
    assert c.missing == []


def test_confidence_no_signals_is_low():
    c = score_confidence()
    assert c.score < 0.5
    assert c.level == "low"
    assert "training_load" in c.missing


def test_confidence_stale_data_drops():
    c = score_confidence(
        has_today_load=True,
        hrv_latest_date="2025-01-01",  # 远古数据
        last_session_date="2025-01-01",
    )
    assert "hrv" in c.stale or "hrv" in c.missing
    assert c.level in ("low", "medium")
