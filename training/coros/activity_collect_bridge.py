"""Bridge coros-collect activities -> training-system sessions + track_points.

coros-collect (/opt/coros-collect) ingests the COROS Training Hub via a browser
session and stores activities + per-second samples in a separate SQLite DB
(data/coros.sqlite). The MCP querySportRecords path (training/coros/activity.py)
returns empty for recent activities, so recent runs never reach sessions and the
decision dashboard's training load goes stale. This bridge reads coros-collect's
activities + activity_samples read-only and upserts them into training-system's
sessions + session_track_points, keyed by the same coros_<labelId>.fit filename
so it stays dedup-consistent with the MCP path.

Field reliability (verified on server):
- reliable: activities.distance_cm (cm), activities.avg_hr,
  activity_samples.timestamp (centiseconds; adjacent samples differ by 100 = 1/s),
  heart_rate, cadence, altitude, gps_lat_e7/gps_lon_e7 (deg*1e7; 0 = indoor/no fix)
- unreliable/unused: samples.distance_cm, pace, speed, calories_kcal, workout_time_s

Not written here: laps (coros-collect has no reliable lap data; synthesizing laps
would corrupt pace_cv/hr_drift). hr_tss only needs avg_hr + duration_sec.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

from training.coros import storage
from training.coros.activity import _ts_to_local
from training.storage.db import get_conn
from training.storage.writers import upsert_track_points


SPORT_MAP = {
    100: "Outdoor Run",
    101: "Indoor Run",
    104: "Hiking",
    200: "Outdoor Cycling",
    201: "Indoor Cycling",
    402: "Strength Training",
    900: "Walking",
}


def _compute_session_fields(activity: dict, samples: list[dict]) -> dict:
    """Derive session-level fields from one activity + its samples.

    duration comes from sample timestamps (centiseconds), NOT workout_time_s
    (which is sometimes corrupt). distance from activities.distance_cm (cm).
    avg_hr prefers the activity top-level value, falling back to the sample mean.
    """
    timestamps = [s["ts"] for s in samples]
    min_ts, max_ts = min(timestamps), max(timestamps)
    duration_sec = (max_ts - min_ts) / 100
    distance_km = (activity.get("distance_cm") or 0) / 100000

    avg_hr = activity.get("avg_hr")
    if not avg_hr:
        hrs = [s["hr"] for s in samples if s.get("hr")]
        avg_hr = round(mean(hrs)) if hrs else None

    avg_pace_sec = round(duration_sec / distance_km) if distance_km > 0 else None

    return {
        "label_id": activity["label_id"],
        "sport": SPORT_MAP.get(activity["sport_type"]),
        "start_time": _ts_to_local(min_ts / 100),
        "duration_sec": duration_sec,
        "distance_km": distance_km,
        "avg_hr": avg_hr,
        "avg_pace_sec": avg_pace_sec,
        "calories": None,  # coros-collect calories_kcal is unreliable
        "training_effect": None,
        "anaerobic_te": None,
        "training_type": None,
        "training_effect_label": None,
    }


def _build_track_points(samples: list[dict], min_ts: int) -> list[dict]:
    """Map per-second samples -> track_point dicts. Indoor GPS (e7=0) -> NULL lat/lon.

    speed_mps / distance_m are left out: coros-collect's speed/distance fields are
    unreliable, and the session page renders HR/cadence/altitude/GPS from the
    other columns.
    """
    points = []
    for s in samples:
        lat_e7 = s.get("lat_e7")
        lon_e7 = s.get("lon_e7")
        points.append({
            "t_offset_s": (s["ts"] - min_ts) / 100,
            "lat": (lat_e7 / 1e7) if lat_e7 else None,
            "lon": (lon_e7 / 1e7) if lon_e7 else None,
            "altitude_m": s.get("alt"),
            "hr": s.get("hr"),
            "cadence": s.get("cad"),
        })
    return points


def sync_activities_from_collect(
    collect_db_path: str, *, days: int = 7, sport_types: tuple = (100, 101)
) -> dict:
    """Read activities + samples from coros-collect DB; upsert sessions + track_points.

    Read-only on the collect DB. Idempotent via existing_coros_label_ids() dedup
    (filename = coros_<labelId>.fit). Returns
    {"sessions": n, "track_points": total_pts, "laps": 0, "skipped": [...]}.
    """
    if not Path(collect_db_path).exists():
        raise FileNotFoundError(f"coros-collect DB not found: {collect_db_path}")

    cutoff = int((date.today() - timedelta(days=days - 1)).strftime("%Y%m%d"))
    placeholders = ",".join("?" * len(sport_types))

    conn = sqlite3.connect(f"file:{collect_db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        activities = [
            dict(r)
            for r in conn.execute(
                f"SELECT label_id, sport_type, distance_cm, avg_hr, start_day "
                f"FROM activities WHERE start_day IS NOT NULL AND start_day >= ? "
                f"AND sport_type IN ({placeholders}) ORDER BY start_day DESC",
                (cutoff, *sport_types),
            ).fetchall()
        ]
        existing = storage.existing_coros_label_ids()

        n_sessions = 0
        total_pts = 0
        skipped: list[dict] = []
        for a in activities:
            if a["label_id"] in existing:
                skipped.append({"label_id": a["label_id"], "reason": "already_exists"})
                continue
            raw = conn.execute(
                "SELECT timestamp, heart_rate, cadence, altitude, gps_lat_e7, gps_lon_e7 "
                "FROM activity_samples WHERE label_id=? ORDER BY timestamp",
                (a["label_id"],),
            ).fetchall()
            samples = [
                {
                    "ts": r["timestamp"],
                    "hr": r["heart_rate"],
                    "cad": r["cadence"],
                    "alt": r["altitude"],
                    "lat_e7": r["gps_lat_e7"],
                    "lon_e7": r["gps_lon_e7"],
                }
                for r in raw
            ]

            if len(samples) < 2:
                skipped.append({"label_id": a["label_id"], "reason": "empty_or_single_sample"})
                continue

            fields = _compute_session_fields(a, samples)
            min_ts = min(s["ts"] for s in samples)
            n_sessions += storage.upsert_coros_sessions([fields])

            tconn = get_conn()
            try:
                row = tconn.execute(
                    "SELECT id FROM sessions WHERE filename=?",
                    (f"coros_{a['label_id']}.fit",),
                ).fetchone()
            finally:
                tconn.close()
            sid = row["id"] if row else None
            if sid is None:
                skipped.append({"label_id": a["label_id"], "reason": "session_id_not_found"})
                continue

            points = _build_track_points(samples, min_ts)
            if points:
                upsert_track_points(sid, points)
                storage.mark_session_has_track_points(sid)
                total_pts += len(points)
    finally:
        conn.close()

    return {"sessions": n_sessions, "track_points": total_pts, "laps": 0, "skipped": skipped}
