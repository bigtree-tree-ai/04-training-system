"""COROS MCP sync tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from training.storage import db


def _use_temp_db(monkeypatch, tmp_path: Path):
    test_db = tmp_path / "training.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(str(test_db))
    return test_db


def test_parse_coros_health_texts():
    from training.coros.parsers import (
        parse_daily_health,
        parse_fitness,
        parse_hrv,
        parse_recovery,
        parse_sleep,
        parse_stress,
        parse_training_load,
    )

    assert parse_recovery("Recovery: 99%\nLevel: Heavy training allowed\nEstimated Full Recovery: 5h") == {
        "recovery_pct": 99,
        "level": "Heavy training allowed",
        "estimated_full_recovery_hours": 5.0,
    }

    fitness = parse_fitness(
        "VO2max: 56\nRunning Level: 89\nThreshold Pace: 4:11 /km\n"
        "5 km Prediction: 19:58\n10 km Prediction: 41:17\n"
        "Half Marathon Prediction: 1:31:47\nMarathon Prediction: 3:12:07"
    )
    assert fitness["vo2max"] == 56
    assert fitness["threshold_pace_sec"] == 251
    assert fitness["marathon_prediction_sec"] == 11527

    sleep = parse_sleep(
        "2026-05-11\nSleep Score: 58\nMain Sleep: 8h 19min\n"
        "Deep Sleep Ratio: 22%\nLight Sleep Ratio: 48%\nREM Ratio: 19%\n"
        "Awake Time: 1h 0min\nAwake Count (>5 min): 1\n"
        "Main Sleep Window: 22:23 - 07:42"
    )
    assert sleep[0]["date"] == "2026-05-11"
    assert sleep[0]["main_sleep_min"] == 499
    assert sleep[0]["awake_min"] == 60

    daily = parse_daily_health(
        "--- 20260511 ---\nSteps: 2,351 | Calories: 103 kcal | Exercise: 1 min\n"
        "Stress: Avg 19\nSleep Summary: (Score: 64)\n"
        "  Total: 8h 19min | Awake: 1h 0min\n"
        "  Deep: 2h 1min | Light: 4h 29min | REM: 1h 49min"
    )
    assert daily[0]["steps"] == 2351
    assert daily[0]["sleep_score"] == 64
    assert daily[0]["sleep_total_min"] == 499

    hrv = parse_hrv("Normal Range: 48 - 74 ms\nBaseline: 61 ms\n2026-05-09:\n  HRV Avg: 35 ms — Below normal")
    assert hrv[0]["date"] == "2026-05-09"
    assert hrv[0]["hrv_avg_ms"] == 35
    assert hrv[0]["evaluation"] == "Below normal"
    assert hrv[0]["baseline_ms"] == 61

    load = parse_training_load(
        "2026-05-11\nComment: Optimized\nShort-Term Load: 111\n"
        "Long-Term Load: 102\nLoad Ratio: 1.08"
    )
    assert load[0]["short_term_load"] == 111
    assert load[0]["load_ratio"] == 1.08

    stress = parse_stress("2026-05-11:\nAverage Stress: 19 (Relaxed)")
    assert stress == [{"date": "2026-05-11", "stress_avg": 19, "level": "Relaxed"}]


def test_coros_sync_persists_structured_data(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    from training.coros.sync import CorosSyncService
    from training.coros.storage import get_coros_overview

    class FakeClient:
        def call_tool(self, name, arguments=None):
            payloads = {
                "queryRecoveryStatus": "Recovery: 99%\nLevel: Heavy training allowed\nEstimated Full Recovery: 5h",
                "queryFitnessAssessmentOverview": "VO2max: 56\nRunning Level: 89\nThreshold Pace: 4:11 /km\nMarathon Prediction: 3:12:07",
                "queryTrainingLoadAssessment": "2026-05-11\nComment: Optimized\nShort-Term Load: 111\nLong-Term Load: 102\nLoad Ratio: 1.08",
                "queryDailyHealthData": "--- 20260511 ---\nSteps: 2,351 | Calories: 103 kcal | Exercise: 1 min\nStress: Avg 19",
                "querySleepData": "2026-05-11\nSleep Score: 58\nMain Sleep: 8h 19min\nAwake Time: 1h 0min\nAwake Count (>5 min): 1",
                "queryHrvAssessment": "Normal Range: 48 - 74 ms\nBaseline: 61 ms\n2026-05-11:\n  HRV Avg: 68 ms — Normal",
                "queryRestingHeartRate": "2026-05-11: 53 bpm",
                "queryAvgHeartRate": "2026-05-11: 60 bpm (Min: 44, Max: 88)",
                "queryStressLevel": "2026-05-11:\nAverage Stress: 19 (Relaxed)",
                "queryTrainingSchedule": "2026-05-11\n(恢复)有氧跑5km\nDistance: 5.29 km\nEstimated Time: 30:00\nLoad: 50 TL",
                "queryDevices": "Bound Devices (1)\n1. COROS PACE 4\n   Bluetooth ID: B7F09E\n   Model Name: COROS R4\n   Serial Number: W35B003815",
                "queryUserInfo": "Height: 174.0 cm\nWeight: 64.4 kg\nBirthday: 1990-12-17 (Age: 35)\nGender: Male\nNickname: 田大树路跑跑",
            }
            return {"content": [{"type": "text", "text": payloads[name]}], "isError": False}

    summary = CorosSyncService(FakeClient()).sync(days=14)
    assert summary["success"] is True
    assert summary["persisted"]["daily_health"] == 1
    assert summary["persisted"]["devices"] == 1

    overview = get_coros_overview()
    assert overview["profile"]["weight_kg"] == 64.4
    assert overview["recovery"]["recovery_pct"] == 99
    assert overview["fitness"]["vo2max"] == 56
    assert overview["daily_health"][0]["steps"] == 2351
    assert overview["sleep"][0]["awake_min"] == 60
    assert overview["devices"][0]["name"] == "COROS PACE 4"


def test_coros_sync_degrades_gracefully_when_token_expired(monkeypatch, tmp_path):
    """A dead refresh_token must NOT crash the daily cron — it closes the run
    as token_expired and returns success=False (the 11-day blackout fix)."""
    _use_temp_db(monkeypatch, tmp_path)

    from training.coros import sync, token_health

    broken = {
        "state": "refresh_failed",
        "expires_in_days": -0.5,
        "access_token": None,
        "message": "refresh 失败,需重新 coros-login",
    }
    monkeypatch.setattr(token_health, "get_valid_token", lambda: (None, broken))

    result = sync.CorosSyncService().sync(days=14)

    assert result["success"] is False
    assert result["token_status"]["state"] == "refresh_failed"

    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT status, message FROM coros_sync_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    assert row["status"] == "token_expired"
    assert "coros-login" in row["message"]


def test_coros_sync_records_client_failure_when_token_valid(monkeypatch, tmp_path):
    """When the token is fine but CorosMcpClient itself blows up, sync still
    raises and records status=failed (the original fail-loud path)."""
    _use_temp_db(monkeypatch, tmp_path)

    from training.coros import sync, token_health

    ok = {"state": "ok", "access_token": "AT", "expires_in_days": 30.0, "message": "ok"}
    monkeypatch.setattr(token_health, "get_valid_token", lambda: ("AT", ok))

    class BrokenClient:
        def __init__(self, access_token=None):
            raise RuntimeError("client init boom")

    monkeypatch.setattr(sync, "CorosMcpClient", BrokenClient)

    with pytest.raises(RuntimeError, match="client init boom"):
        sync.CorosSyncService().sync(days=14)

    conn = db.get_conn()
    try:
        row = conn.execute("SELECT status FROM coros_sync_runs ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()

    assert row["status"] == "failed"


def test_coros_overview_has_four_structured_sections(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    from training.coros.storage import (
        get_coros_overview,
        upsert_daily_health,
        upsert_fitness,
        upsert_recovery,
        upsert_training_load,
    )
    from training.services.coros_service import get_coros_dashboard_data

    upsert_recovery({"recovery_pct": 99, "level": "Heavy training allowed"})
    upsert_fitness({"vo2max": 56, "running_level": 89})
    upsert_training_load([{"date": "2026-05-11", "comment": "Optimized", "load_ratio": 1.08}])
    upsert_daily_health([{"date": "2026-05-11", "steps": 2351, "stress_avg": 19}])

    overview = get_coros_overview()
    assert "training" in get_coros_dashboard_data(overview)
    assert "daily_life" in get_coros_dashboard_data(overview)
    assert "health_recovery" in get_coros_dashboard_data(overview)
    assert "planning_devices" in get_coros_dashboard_data(overview)
