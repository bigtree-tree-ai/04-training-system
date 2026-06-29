"""Tests for the shared run-sport predicate.

COROS sessions are stored with sport='Outdoor Run'/'Indoor Run', but many
analysis/coach queries hardcoded sport='running', so coros runs were silently
dropped from weekly summaries, AI-coach context, VO2max, trends, and dashboard
charts. These lock in that the shared RUN_SPORT_PREDICATE classifies coros runs
as running while excluding cycling/hiking/walking/strength, and that
weekly_summary applies it (coros -> run_sessions, cycling -> cross_sessions).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from training.storage import db
from training.storage.db import get_conn


def _use_temp_db(monkeypatch, tmp_path: Path) -> Path:
    test_db = tmp_path / "training.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(str(test_db))
    return test_db


def _insert(filename, sport, distance_km=10.0, start_time="2026-06-27 08:00:00",
            avg_hr=140, duration_sec=3600):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions (filename, sport, start_time, distance_km, avg_hr, duration_sec) "
            "VALUES (?,?,?,?,?,?)",
            (filename, sport, start_time, distance_km, avg_hr, duration_sec),
        )
        conn.commit()
    finally:
        conn.close()


def test_predicate_classifies_sports_correctly():
    """RUN_SPORT_PREDICATE SQL: coros Run + legacy running -> run; others -> not."""
    from training.storage.db import RUN_SPORT_PREDICATE

    conn = sqlite3.connect(":memory:")
    cases = {
        "running": 1, "Outdoor Run": 1, "Indoor Run": 1,
        "cycling": 0, "Hiking": 0, "Walking": 0, "Strength Training": 0,
    }
    for sport, expected in cases.items():
        n = conn.execute(
            f"SELECT CASE WHEN {RUN_SPORT_PREDICATE} THEN 1 ELSE 0 END "
            f"FROM (SELECT ? AS sport)",
            (sport,),
        ).fetchone()[0]
        assert n == expected, f"{sport!r} expected {expected}, got {n}"


def test_weekly_summary_coros_counts_as_run(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    _insert("coros_out.fit", "Outdoor Run", distance_km=12.85)

    from training.analysis.weekly_summary import compute_weekly_summaries

    compute_weekly_summaries()

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT run_sessions, run_distance_km, cross_sessions "
            "FROM weekly_summaries ORDER BY year DESC, week_number DESC LIMIT 1"
        ).fetchone()
        assert row["run_sessions"] == 1
        assert row["run_distance_km"] == 12.85
        assert (row["cross_sessions"] or 0) == 0
    finally:
        conn.close()


def test_weekly_summary_indoor_run_counts_as_run(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    _insert("coros_in.fit", "Indoor Run", distance_km=11.5)

    from training.analysis.weekly_summary import compute_weekly_summaries

    compute_weekly_summaries()

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT run_sessions, run_distance_km FROM weekly_summaries "
            "ORDER BY year DESC, week_number DESC LIMIT 1"
        ).fetchone()
        assert row["run_sessions"] == 1
        assert row["run_distance_km"] == 11.5
    finally:
        conn.close()


def test_weekly_summary_cycling_is_cross_not_run(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    _insert("ride1.fit", "cycling", distance_km=50.0)

    from training.analysis.weekly_summary import compute_weekly_summaries

    compute_weekly_summaries()

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT run_sessions, run_distance_km, cross_sessions "
            "FROM weekly_summaries ORDER BY year DESC, week_number DESC LIMIT 1"
        ).fetchone()
        assert row["run_sessions"] == 0
        assert (row["run_distance_km"] or 0) == 0
        assert (row["cross_sessions"] or 0) == 1
    finally:
        conn.close()


def test_weekly_summary_legacy_running_still_counts(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    _insert("legacy.fit", "running", distance_km=8.0)

    from training.analysis.weekly_summary import compute_weekly_summaries

    compute_weekly_summaries()

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT run_sessions, run_distance_km FROM weekly_summaries "
            "ORDER BY year DESC, week_number DESC LIMIT 1"
        ).fetchone()
        assert row["run_sessions"] == 1
        assert row["run_distance_km"] == 8.0
    finally:
        conn.close()
