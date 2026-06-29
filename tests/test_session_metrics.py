"""Tests for session_metrics sport filter.

coros sessions are stored with sport='Outdoor Run'/'Indoor Run', but the legacy
filter was WHERE sport='running', so coros sessions never got hr_tss computed.
These lock in that Outdoor/Indoor Run are analyzed while cycling/hiking are not,
and that legacy sport='running' still works (regression guard).
"""
from __future__ import annotations

from pathlib import Path

from training.storage import db
from training.storage.db import get_conn


def _use_temp_db(monkeypatch, tmp_path: Path) -> Path:
    test_db = tmp_path / "training.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(str(test_db))
    return test_db


def _insert_session(filename: str, sport: str, avg_hr: int, duration_sec: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions (filename, sport, start_time, avg_hr, duration_sec) "
            "VALUES (?,?,?,?,?)",
            (filename, sport, "2026-06-27 08:00:00", avg_hr, duration_sec),
        )
        conn.commit()
    finally:
        conn.close()


def _hr_tss(filename: str) -> float | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT hr_tss FROM sessions WHERE filename=?", (filename,)
        ).fetchone()
        return row["hr_tss"] if row else None
    finally:
        conn.close()


def test_outdoor_run_gets_hr_tss(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    _insert_session("coros_outdoor1.fit", "Outdoor Run", avg_hr=150, duration_sec=3600)

    from training.analysis.session_metrics import compute_all_session_metrics

    compute_all_session_metrics()
    assert _hr_tss("coros_outdoor1.fit") is not None


def test_indoor_run_gets_hr_tss(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    _insert_session("coros_indoor1.fit", "Indoor Run", avg_hr=140, duration_sec=3600)

    from training.analysis.session_metrics import compute_all_session_metrics

    compute_all_session_metrics()
    assert _hr_tss("coros_indoor1.fit") is not None


def test_legacy_running_still_analyzed(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    _insert_session("legacy_run.fit", "running", avg_hr=150, duration_sec=3600)

    from training.analysis.session_metrics import compute_all_session_metrics

    compute_all_session_metrics()
    assert _hr_tss("legacy_run.fit") is not None


def test_cycling_not_analyzed(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    _insert_session("ride1.fit", "cycling", avg_hr=150, duration_sec=3600)

    from training.analysis.session_metrics import compute_all_session_metrics

    compute_all_session_metrics()
    assert _hr_tss("ride1.fit") is None  # cycling excluded from run load
