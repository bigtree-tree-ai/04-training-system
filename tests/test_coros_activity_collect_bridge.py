"""Tests for coros-collect activities -> training-system sessions bridge.

Unit tests cover the pure conversion helpers (sport mapping, unit conversions,
GPS-NULL handling, pace divide-by-zero guard). Integration tests build a
temporary coros-collect DB with activities + activity_samples, run
sync_activities_from_collect against a temp training DB, and assert the
sessions / session_track_points tables were populated correctly.

coros-collect field semantics (verified on server):
- activity_samples.timestamp : centiseconds (adjacent samples differ by 100 = 1s)
- activities.distance_cm     : centimeters (top-level total, reliable)
- gps_lat_e7/gps_lon_e7      : degrees * 1e7; 0 means indoor (no fix) -> must NULL
- pace/speed/distance_cm(samples)/calories_kcal/workout_time_s : unreliable, unused
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from training.storage import db


# Real 06-27 outdoor-run timestamp magnitude (centiseconds).
BASE_TS = 178252131000  # -> 2026-06-27 00:48:30 UTC when /100


def _use_temp_db(monkeypatch, tmp_path: Path) -> Path:
    test_db = tmp_path / "training.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(str(test_db))
    return test_db


def _s(ts, hr=140, cad=190, alt=20.0, lat_e7=303007757, lon_e7=1202318846):
    """One activity_sample row (only fields the bridge reads)."""
    return {"ts": ts, "hr": hr, "cad": cad, "alt": alt, "lat_e7": lat_e7, "lon_e7": lon_e7}


def _make_collect_db_with_activities(
    tmp_path: Path, activities: list[dict], samples_by_label: dict[str, list[dict]]
) -> str:
    """Build a coros-collect coros.sqlite with activities + activity_samples tables."""
    db_path = tmp_path / "coros_collect.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE activities ("
        "label_id TEXT PRIMARY KEY, sport_type INTEGER NOT NULL, name TEXT, "
        "sport_name TEXT, start_time INTEGER, start_day INTEGER, timezone INTEGER, "
        "distance_cm INTEGER, workout_time_s INTEGER, total_time_s INTEGER, "
        "avg_speed REAL, avg_hr INTEGER, avg_power INTEGER, training_load INTEGER, "
        "calories_kcal INTEGER, device_id TEXT, location_name TEXT, "
        "start_lat_e7 INTEGER, start_lon_e7 INTEGER, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE activity_samples ("
        "label_id TEXT NOT NULL, timestamp INTEGER NOT NULL, sport_type INTEGER, "
        "distance_cm INTEGER, heart_rate INTEGER, pace REAL, speed REAL, power INTEGER, "
        "cadence INTEGER, altitude REAL, gps_lat_e7 INTEGER, gps_lon_e7 INTEGER, "
        "raw_index INTEGER, PRIMARY KEY (label_id, timestamp))"
    )
    for a in activities:
        conn.execute(
            "INSERT INTO activities (label_id, sport_type, name, start_day, timezone, "
            "distance_cm, workout_time_s, avg_hr, calories_kcal, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                a["label_id"], a["sport_type"], a.get("name"), a.get("start_day"),
                a.get("timezone", 32), a.get("distance_cm"), a.get("workout_time_s"),
                a.get("avg_hr"), a.get("calories_kcal"), "2026-06-28T00:00:00",
            ),
        )
    for label_id, samples in samples_by_label.items():
        for i, s in enumerate(samples):
            conn.execute(
                "INSERT INTO activity_samples (label_id, timestamp, heart_rate, cadence, "
                "altitude, gps_lat_e7, gps_lon_e7, raw_index) VALUES (?,?,?,?,?,?,?,?)",
                (label_id, s["ts"], s.get("hr"), s.get("cad"), s.get("alt"),
                 s.get("lat_e7"), s.get("lon_e7"), i),
            )
    conn.commit()
    conn.close()
    return str(db_path)


def _outdoor_activity(label_id="478492964937564262", **kw):
    base = dict(label_id=label_id, sport_type=100, start_day=20260627,
                distance_cm=1285000, avg_hr=144, workout_time_s=3874, calories_kcal=907751)
    base.update(kw)
    return base


# --- unit tests: pure helpers -------------------------------------------------


def test_sport_map_covers_known_types():
    from training.coros.activity_collect_bridge import SPORT_MAP

    assert SPORT_MAP[100] == "Outdoor Run"
    assert SPORT_MAP[101] == "Indoor Run"
    for code in (104, 200, 201, 402, 900):
        assert SPORT_MAP[code]


def test_compute_session_fields_unit_conversions():
    from training.coros.activity_collect_bridge import _compute_session_fields

    activity = {"label_id": "L1", "sport_type": 100, "distance_cm": 1285000, "avg_hr": 144}
    # two samples 387400 centiseconds apart -> 3874 s
    samples = [{"ts": 100000, "hr": 140}, {"ts": 487400, "hr": 150}]

    f = _compute_session_fields(activity, samples)

    assert f["sport"] == "Outdoor Run"
    assert f["distance_km"] == 12.85
    assert f["duration_sec"] == 3874
    assert f["avg_hr"] == 144
    assert f["avg_pace_sec"] == 301  # round(3874 / 12.85)
    assert f["calories"] is None  # unreliable field, never written


def test_compute_session_fields_zero_distance_no_pace():
    from training.coros.activity_collect_bridge import _compute_session_fields

    activity = {"label_id": "L1", "sport_type": 101, "distance_cm": 0, "avg_hr": None}
    samples = [{"ts": 100000, "hr": 130}, {"ts": 160000, "hr": 136}]

    f = _compute_session_fields(activity, samples)

    assert f["distance_km"] == 0
    assert f["avg_pace_sec"] is None  # divide-by-zero guard
    assert f["avg_hr"] == 133  # falls back to mean(samples.hr) when activity avg missing


def test_compute_session_fields_start_time_utc_basis():
    from training.coros.activity_collect_bridge import _compute_session_fields

    activity = {"label_id": "L1", "sport_type": 100, "distance_cm": 100000, "avg_hr": 140}
    samples = [{"ts": BASE_TS, "hr": 140}, {"ts": BASE_TS + 100, "hr": 141}]

    f = _compute_session_fields(activity, samples)
    assert f["start_time"].startswith("2026-06-27")  # min_ts/100 -> UTC date


def test_build_track_points_drops_zero_gps():
    from training.coros.activity_collect_bridge import _build_track_points

    samples = [{"ts": 1000, "hr": 140, "cad": 190, "alt": 20.0, "lat_e7": 0, "lon_e7": 0}]
    pts = _build_track_points(samples, min_ts=1000)
    assert len(pts) == 1
    assert pts[0]["lat"] is None  # indoor GPS=0 -> NULL, never 0.0
    assert pts[0]["lon"] is None
    assert pts[0]["hr"] == 140
    assert pts[0]["cadence"] == 190
    assert pts[0]["altitude_m"] == 20.0


def test_build_track_points_offset_and_gps_scale():
    from training.coros.activity_collect_bridge import _build_track_points

    samples = [
        {"ts": 1000, "hr": 140, "lat_e7": 303007757, "lon_e7": 1202318846},
        {"ts": 1100, "hr": 142, "lat_e7": 303007760, "lon_e7": 1202318850},
    ]
    pts = _build_track_points(samples, min_ts=1000)
    assert pts[0]["t_offset_s"] == 0.0
    assert pts[1]["t_offset_s"] == 1.0  # (1100-1000)/100
    assert pts[0]["lat"] == pytest.approx(30.3007757, abs=1e-6)
    assert pts[0]["lon"] == pytest.approx(120.2318846, abs=1e-6)


# --- integration tests --------------------------------------------------------


def test_sync_outdoor_run_end_to_end(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    samples = [_s(BASE_TS + i * 100, hr=140 + i) for i in range(100)]
    collect_db = _make_collect_db_with_activities(
        tmp_path, [_outdoor_activity()], {"478492964937564262": samples}
    )

    from training.coros.activity_collect_bridge import sync_activities_from_collect

    result = sync_activities_from_collect(collect_db, days=3650)
    assert result["sessions"] == 1
    assert result["track_points"] == 100
    assert result["laps"] == 0
    assert result["skipped"] == []

    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT sport, distance_km, avg_hr, has_track_points, start_time "
            "FROM sessions WHERE filename='coros_478492964937564262.fit'"
        ).fetchone()
        assert row["sport"] == "Outdoor Run"
        assert row["distance_km"] == 12.85
        assert row["avg_hr"] == 144
        assert row["has_track_points"] == 1  # must be set explicitly
        assert row["start_time"].startswith("2026-06-27")

        sid = conn.execute(
            "SELECT id FROM sessions WHERE filename='coros_478492964937564262.fit'"
        ).fetchone()[0]
        n_pts = conn.execute(
            "SELECT COUNT(*) FROM session_track_points WHERE session_id=?", (sid,)
        ).fetchone()[0]
        assert n_pts == 100
        gps_pts = conn.execute(
            "SELECT COUNT(*) FROM session_track_points WHERE session_id=? AND lat IS NOT NULL",
            (sid,),
        ).fetchone()[0]
        assert gps_pts == 100  # outdoor: every point has GPS
    finally:
        conn.close()


def test_sync_indoor_run_gps_is_null(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    samples = [_s(BASE_TS + i * 100, lat_e7=0, lon_e7=0) for i in range(20)]
    collect_db = _make_collect_db_with_activities(
        tmp_path,
        [_outdoor_activity(label_id="478500000000000001", sport_type=101)],
        {"478500000000000001": samples},
    )

    from training.coros.activity_collect_bridge import sync_activities_from_collect

    result = sync_activities_from_collect(collect_db, days=3650)
    assert result["sessions"] == 1

    conn = db.get_conn()
    try:
        sid = conn.execute(
            "SELECT id FROM sessions WHERE filename='coros_478500000000000001.fit'"
        ).fetchone()[0]
        row = conn.execute(
            "SELECT COUNT(*) c, COUNT(lat) gps FROM session_track_points WHERE session_id=?",
            (sid,),
        ).fetchone()
        assert row["c"] == 20
        assert row["gps"] == 0  # indoor: lat/lon all NULL
    finally:
        conn.close()


def test_sync_dedup_skips_existing_label(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    # pre-insert the coros session as if MCP had already synced it
    from training.coros.storage import upsert_coros_sessions

    upsert_coros_sessions([{
        "label_id": "478492964937564262", "sport": "Outdoor Run",
        "start_time": "2026-06-27 00:48:30", "duration_sec": 3874,
        "distance_km": 12.85, "avg_hr": 144, "avg_pace_sec": 301,
    }])

    samples = [_s(BASE_TS + i * 100) for i in range(10)]
    collect_db = _make_collect_db_with_activities(
        tmp_path, [_outdoor_activity()], {"478492964937564262": samples}
    )

    from training.coros.activity_collect_bridge import sync_activities_from_collect

    result = sync_activities_from_collect(collect_db, days=3650)
    assert result["sessions"] == 0
    skipped_ids = [s["label_id"] for s in result["skipped"]]
    assert "478492964937564262" in skipped_ids


def test_sync_empty_samples_activity_skipped(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    collect_db = _make_collect_db_with_activities(
        tmp_path, [_outdoor_activity()], {"478492964937564262": []}
    )

    from training.coros.activity_collect_bridge import sync_activities_from_collect

    result = sync_activities_from_collect(collect_db, days=3650)
    assert result["sessions"] == 0
    assert any(s["reason"] == "empty_or_single_sample" for s in result["skipped"])


def test_sync_single_sample_skipped_no_div_by_zero(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    collect_db = _make_collect_db_with_activities(
        tmp_path, [_outdoor_activity()], {"478492964937564262": [_s(BASE_TS)]}
    )

    from training.coros.activity_collect_bridge import sync_activities_from_collect

    result = sync_activities_from_collect(collect_db, days=3650)  # must not raise
    assert result["sessions"] == 0
    assert any(s["label_id"] == "478492964937564262" for s in result["skipped"])


def test_sync_filters_by_sport_type(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    activities = [
        _outdoor_activity(label_id="478600000000000001", sport_type=100),  # run
        {"label_id": "478600000000000002", "sport_type": 402, "start_day": 20260627,
         "distance_cm": 0, "avg_hr": 110},  # strength training
    ]
    samples = {
        "478600000000000001": [_s(BASE_TS + i * 100) for i in range(5)],
        "478600000000000002": [_s(BASE_TS + i * 100, hr=110) for i in range(5)],
    }
    collect_db = _make_collect_db_with_activities(tmp_path, activities, samples)

    from training.coros.activity_collect_bridge import sync_activities_from_collect

    result = sync_activities_from_collect(collect_db, days=3650)  # default sport_types=(100,101)
    assert result["sessions"] == 1
    conn = db.get_conn()
    try:
        sports = [r[0] for r in conn.execute(
            "SELECT sport FROM sessions WHERE filename LIKE 'coros_4786%'")]
        assert sports == ["Outdoor Run"]  # strength (402) excluded
    finally:
        conn.close()


def test_sync_days_window(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    today = int(date.today().strftime("%Y%m%d"))
    recent_day = int((date.today() - timedelta(days=1)).strftime("%Y%m%d"))
    old_day = int((date.today() - timedelta(days=10)).strftime("%Y%m%d"))
    activities = [
        _outdoor_activity(label_id="478700000000000001", start_day=recent_day),
        _outdoor_activity(label_id="478700000000000002", start_day=old_day),
    ]
    samples = {
        "478700000000000001": [_s(BASE_TS + i * 100) for i in range(5)],
        "478700000000000002": [_s(BASE_TS + i * 100) for i in range(5)],
    }
    collect_db = _make_collect_db_with_activities(tmp_path, activities, samples)

    from training.coros.activity_collect_bridge import sync_activities_from_collect

    result = sync_activities_from_collect(collect_db, days=7)
    assert result["sessions"] == 1  # only the recent (1-day-old) activity


def test_sync_missing_db_raises(tmp_path):
    from training.coros.activity_collect_bridge import sync_activities_from_collect

    with pytest.raises(FileNotFoundError):
        sync_activities_from_collect(str(tmp_path / "does_not_exist.sqlite"))


def test_sync_read_only_does_not_write_collect_db(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    samples = [_s(BASE_TS + i * 100) for i in range(10)]
    collect_db = _make_collect_db_with_activities(
        tmp_path, [_outdoor_activity()], {"478492964937564262": samples}
    )

    from training.coros.activity_collect_bridge import sync_activities_from_collect

    sync_activities_from_collect(collect_db, days=3650)

    conn = sqlite3.connect(f"file:{collect_db}?mode=ro", uri=True)
    try:
        n = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        assert n == 1  # collect DB untouched
    finally:
        conn.close()


def test_sync_idempotent_rerun(tmp_path, monkeypatch):
    _use_temp_db(monkeypatch, tmp_path)
    samples = [_s(BASE_TS + i * 100) for i in range(10)]
    collect_db = _make_collect_db_with_activities(
        tmp_path, [_outdoor_activity()], {"478492964937564262": samples}
    )

    from training.coros.activity_collect_bridge import sync_activities_from_collect

    first = sync_activities_from_collect(collect_db, days=3650)
    second = sync_activities_from_collect(collect_db, days=3650)
    assert first["sessions"] == 1
    assert second["sessions"] == 0  # dedup
    conn = db.get_conn()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM session_track_points p "
            "JOIN sessions s ON s.id=p.session_id "
            "WHERE s.filename='coros_478492964937564262.fit'"
        ).fetchone()[0]
        assert n == 10  # not doubled
    finally:
        conn.close()
