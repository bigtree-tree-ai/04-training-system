"""Tests for coros-collect -> training-system bridge.

Unit tests cover the JSON parsers (pure functions); integration tests build a
temporary coros-collect DB, run bridge_from_collect against a temp training DB,
and assert the coros_* tables that feed the AI coach were populated.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from training.storage import db


# Minimal but realistic snapshots of the coros-collect daily_metrics payloads.
ANALYSE_SAMPLE = {
    "dayList": {
        "count": 2,
        "sample": [
            {
                "happenDay": 20260617,
                "rhr": 49,
                "t7d": 551,
                "t28d": 2027,
                "trainingLoadRatio": 1.28,
            },
            {
                # no trainingLoadRatio -> bridge must fall back to t7d/t28d
                "happenDay": 20260618,
                "rhr": 51,
                "t7d": 600,
                "t28d": 2100,
            },
        ],
    }
}

DASHBOARD_SAMPLE = {
    "summaryInfo": {
        "recoveryPct": 98,
        "recoveryState": 4,
        "fullRecoveryHours": 9,
        "rhr": 53,
        "sleepHrvData": {
            "sleepHrvList": [
                {
                    "happenDay": 20260617,
                    "avgSleepHrv": 51,
                    "sleepHrvBase": 58,
                    "sleepHrvIntervalList": [5, 40, 49, 67],
                },
                {
                    "happenDay": 20260618,
                    "avgSleepHrv": 60,
                    "sleepHrvBase": 58,
                    "sleepHrvIntervalList": [5, 40, 49, 67],
                },
            ]
        },
    }
}


def _use_temp_db(monkeypatch, tmp_path: Path) -> Path:
    test_db = tmp_path / "training.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(str(test_db))
    return test_db


def _make_collect_db(
    tmp_path: Path, analyse: dict | None = None, dashboard: dict | None = None
) -> str:
    """Build a minimal coros-collect coros.sqlite with the given snapshots."""
    db_path = tmp_path / "coros_collect.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE daily_metrics ("
        "metric_date INTEGER, source TEXT, metric_type TEXT, "
        "values_json TEXT, updated_at TEXT, "
        "PRIMARY KEY (metric_date, source, metric_type))"
    )
    if analyse:
        conn.execute(
            "INSERT INTO daily_metrics VALUES (?,?,?,?,?)",
            (20260618, "browser", "analyse.query", json.dumps(analyse), "2026-06-18T03:33:00"),
        )
    if dashboard:
        conn.execute(
            "INSERT INTO daily_metrics VALUES (?,?,?,?,?)",
            (20260619, "browser", "dashboard.query", json.dumps(dashboard), "2026-06-18T03:33:00"),
        )
    conn.commit()
    conn.close()
    return str(db_path)


# --- unit tests: pure parsers -------------------------------------------------


def test_yyyymmdd_to_iso():
    from training.coros.collect_bridge import _yyyymmdd_to_iso

    assert _yyyymmdd_to_iso(20260318) == "2026-03-18"
    assert _yyyymmdd_to_iso("20260318") == "2026-03-18"
    assert _yyyymmdd_to_iso(None) is None
    assert _yyyymmdd_to_iso(123) is None  # too short


def test_parse_heart_rate():
    from training.coros.collect_bridge import _parse_heart_rate

    rows = _parse_heart_rate(ANALYSE_SAMPLE)
    assert {"date": "2026-06-17", "resting_hr": 49} in rows
    assert {"date": "2026-06-18", "resting_hr": 51} in rows
    assert _parse_heart_rate(None) == []


def test_parse_training_load_uses_ratio_then_fallback():
    from training.coros.collect_bridge import _parse_training_load

    rows = {r["date"]: r for r in _parse_training_load(ANALYSE_SAMPLE)}
    assert rows["2026-06-17"]["load_ratio"] == 1.28  # taken directly
    assert rows["2026-06-17"]["short_term_load"] == 551
    assert rows["2026-06-17"]["long_term_load"] == 2027
    # missing trainingLoadRatio -> computed from t7d/t28d
    assert rows["2026-06-18"]["load_ratio"] == round(600 / 2100, 2)
    assert rows["2026-06-18"]["short_term_load"] == 600


def test_parse_hrv():
    from training.coros.collect_bridge import _parse_hrv

    rows = {r["date"]: r for r in _parse_hrv(DASHBOARD_SAMPLE)}
    assert rows["2026-06-17"]["hrv_avg_ms"] == 51
    assert rows["2026-06-17"]["baseline_ms"] == 58
    assert rows["2026-06-17"]["normal_low_ms"] == 5
    assert rows["2026-06-17"]["normal_high_ms"] == 67
    assert _parse_hrv(None) == []


def test_parse_recovery():
    from training.coros.collect_bridge import _parse_recovery

    rec = _parse_recovery(DASHBOARD_SAMPLE)
    assert rec["recovery_pct"] == 98
    assert rec["estimated_full_recovery_hours"] == 9.0
    assert rec["level"] == "optimal"  # recoveryState 4 -> optimal
    assert _parse_recovery(None) is None
    assert _parse_recovery({"summaryInfo": {}}) is None  # nothing to store


# --- integration tests --------------------------------------------------------


def test_bridge_end_to_end(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    collect_db = _make_collect_db(tmp_path, ANALYSE_SAMPLE, DASHBOARD_SAMPLE)

    from training.coros.collect_bridge import bridge_from_collect

    counts = bridge_from_collect(collect_db)
    assert counts == {"heart_rate": 2, "training_load": 2, "hrv": 2, "recovery": 1}

    conn = db.get_conn()
    try:
        hr = conn.execute(
            "SELECT date, resting_hr FROM coros_heart_rate_daily ORDER BY date"
        ).fetchall()
        assert len(hr) == 2
        assert hr[-1]["resting_hr"] == 51

        rec = conn.execute(
            "SELECT recovery_pct, estimated_full_recovery_hours FROM coros_recovery_snapshots "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert rec["recovery_pct"] == 98
        assert rec["estimated_full_recovery_hours"] == 9.0

        hrv = conn.execute(
            "SELECT date, hrv_avg_ms, baseline_ms FROM coros_hrv ORDER BY date"
        ).fetchall()
        assert len(hrv) == 2
        assert hrv[-1]["hrv_avg_ms"] == 60
    finally:
        conn.close()


def test_bridge_idempotent_for_dated_tables(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    collect_db = _make_collect_db(tmp_path, ANALYSE_SAMPLE, DASHBOARD_SAMPLE)

    from training.coros.collect_bridge import bridge_from_collect

    bridge_from_collect(collect_db)
    bridge_from_collect(collect_db)  # second run must not duplicate dated rows

    conn = db.get_conn()
    try:
        assert conn.execute("SELECT COUNT(*) FROM coros_heart_rate_daily").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM coros_training_load").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM coros_hrv").fetchone()[0] == 2
    finally:
        conn.close()


def test_bridge_prunes_recovery_snapshots(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    collect_db = _make_collect_db(tmp_path, None, DASHBOARD_SAMPLE)

    from training.coros.collect_bridge import bridge_from_collect

    for _ in range(5):
        bridge_from_collect(collect_db, recovery_keep=3)

    conn = db.get_conn()
    try:
        n = conn.execute("SELECT COUNT(*) FROM coros_recovery_snapshots").fetchone()[0]
        assert n <= 3  # pruned to most recent 3
    finally:
        conn.close()


def test_bridge_missing_db_raises(tmp_path):
    from training.coros.collect_bridge import bridge_from_collect

    with pytest.raises(FileNotFoundError):
        bridge_from_collect(str(tmp_path / "does_not_exist.sqlite"))


def test_bridge_with_empty_collect_db(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    collect_db = _make_collect_db(tmp_path)  # no snapshots inserted

    from training.coros.collect_bridge import bridge_from_collect

    counts = bridge_from_collect(collect_db)
    assert counts == {"heart_rate": 0, "training_load": 0, "hrv": 0, "recovery": 0}
