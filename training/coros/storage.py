"""Persistence helpers for COROS MCP structured data."""
from __future__ import annotations

import json
from typing import Any

from training.storage.db import get_conn, init_db


def start_sync_run(days: int) -> int:
    init_db()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO coros_sync_runs (days, status) VALUES (?, 'running')",
            (days,),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def finish_sync_run(run_id: int, status: str, message: str = "", tool_results: dict | None = None):
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE coros_sync_runs
            SET status=?, message=?, tool_results=?, finished_at=datetime('now')
            WHERE id=?
            """,
            (status, message, json.dumps(tool_results or {}, ensure_ascii=False), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_profile(data: dict):
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO coros_profile (id, nickname, height_cm, weight_kg, birthday, age, gender)
            VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                nickname=excluded.nickname,
                height_cm=excluded.height_cm,
                weight_kg=excluded.weight_kg,
                birthday=excluded.birthday,
                age=excluded.age,
                gender=excluded.gender,
                updated_at=datetime('now')
            """,
            (
                data.get("nickname"),
                data.get("height_cm"),
                data.get("weight_kg"),
                data.get("birthday"),
                data.get("age"),
                data.get("gender"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_devices(rows: list[dict]) -> int:
    conn = get_conn()
    try:
        for row in rows:
            conn.execute(
                """
                INSERT INTO coros_devices
                    (bluetooth_id, name, model_name, serial_number, warranty_expires)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(bluetooth_id) DO UPDATE SET
                    name=excluded.name,
                    model_name=excluded.model_name,
                    serial_number=excluded.serial_number,
                    warranty_expires=excluded.warranty_expires,
                    updated_at=datetime('now')
                """,
                (
                    row.get("bluetooth_id"),
                    row.get("name"),
                    row.get("model_name"),
                    row.get("serial_number"),
                    row.get("warranty_expires"),
                ),
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def upsert_recovery(data: dict) -> int:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO coros_recovery_snapshots
                (recovery_pct, level, estimated_full_recovery_hours, raw_text)
            VALUES (?, ?, ?, ?)
            """,
            (
                data.get("recovery_pct"),
                data.get("level"),
                data.get("estimated_full_recovery_hours"),
                data.get("raw_text"),
            ),
        )
        conn.commit()
        return 1
    finally:
        conn.close()


def upsert_fitness(data: dict) -> int:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO coros_fitness_snapshots
                (vo2max, running_level, threshold_pace_sec, five_k_prediction_sec,
                 ten_k_prediction_sec, half_marathon_prediction_sec,
                 marathon_prediction_sec, raw_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("vo2max"),
                data.get("running_level"),
                data.get("threshold_pace_sec"),
                data.get("five_k_prediction_sec"),
                data.get("ten_k_prediction_sec"),
                data.get("half_marathon_prediction_sec"),
                data.get("marathon_prediction_sec"),
                data.get("raw_text"),
            ),
        )
        conn.commit()
        return 1
    finally:
        conn.close()


def upsert_training_load(rows: list[dict]) -> int:
    return _upsert_rows(
        "coros_training_load",
        ("date", "comment", "short_term_load", "long_term_load", "load_ratio"),
        rows,
    )


def upsert_daily_health(rows: list[dict]) -> int:
    count = _upsert_rows(
        "coros_daily_health",
        (
            "date",
            "steps",
            "calories_kcal",
            "exercise_min",
            "stress_avg",
            "sleep_score",
            "sleep_total_min",
            "sleep_awake_min",
            "sleep_deep_min",
            "sleep_light_min",
            "sleep_rem_min",
        ),
        rows,
    )
    _sync_athlete_status(rows)
    return count


def upsert_sleep(rows: list[dict]) -> int:
    return _upsert_rows(
        "coros_sleep",
        (
            "date",
            "sleep_score",
            "main_sleep_min",
            "deep_sleep_pct",
            "light_sleep_pct",
            "rem_pct",
            "awake_pct",
            "awake_min",
            "awake_count",
            "sleep_window",
            "naps_total_min",
        ),
        rows,
    )


def upsert_hrv(rows: list[dict]) -> int:
    return _upsert_rows(
        "coros_hrv",
        ("date", "hrv_avg_ms", "evaluation", "normal_low_ms", "normal_high_ms", "baseline_ms"),
        rows,
    )


def upsert_resting_hr(rows: list[dict]) -> int:
    return _upsert_rows("coros_heart_rate_daily", ("date", "resting_hr"), rows)


def upsert_avg_hr(rows: list[dict]) -> int:
    return _upsert_rows("coros_heart_rate_daily", ("date", "avg_hr", "min_hr", "max_hr"), rows)


def upsert_stress(rows: list[dict]) -> int:
    return _upsert_rows("coros_stress_daily", ("date", "stress_avg", "level"), rows)


def upsert_training_schedule(rows: list[dict]) -> int:
    return _upsert_rows(
        "coros_training_schedule",
        ("date", "title", "distance_km", "estimated_time_min", "load_tl"),
        rows,
    )


def get_coros_overview(days: int = 14) -> dict[str, Any]:
    init_db()
    conn = get_conn()
    try:
        return {
            "profile": _one(conn, "SELECT * FROM coros_profile WHERE id=1"),
            "recovery": _one(
                conn,
                "SELECT * FROM coros_recovery_snapshots ORDER BY captured_at DESC, id DESC LIMIT 1",
            ),
            "fitness": _one(
                conn,
                "SELECT * FROM coros_fitness_snapshots ORDER BY captured_at DESC, id DESC LIMIT 1",
            ),
            "training_load": _many(
                conn,
                "SELECT * FROM coros_training_load ORDER BY date DESC LIMIT ?",
                (days,),
            ),
            "daily_health": _many(
                conn,
                "SELECT * FROM coros_daily_health ORDER BY date DESC LIMIT ?",
                (days,),
            ),
            "sleep": _many(conn, "SELECT * FROM coros_sleep ORDER BY date DESC LIMIT ?", (days,)),
            "hrv": _many(conn, "SELECT * FROM coros_hrv ORDER BY date DESC LIMIT ?", (days,)),
            "heart_rate": _many(
                conn,
                "SELECT * FROM coros_heart_rate_daily ORDER BY date DESC LIMIT ?",
                (days,),
            ),
            "stress": _many(conn, "SELECT * FROM coros_stress_daily ORDER BY date DESC LIMIT ?", (days,)),
            "schedule": _many(
                conn,
                "SELECT * FROM coros_training_schedule ORDER BY date LIMIT 14",
            ),
            "devices": _many(conn, "SELECT * FROM coros_devices ORDER BY name"),
            "sync_runs": _many(
                conn,
                "SELECT * FROM coros_sync_runs ORDER BY started_at DESC, id DESC LIMIT 5",
            ),
        }
    finally:
        conn.close()


def _upsert_rows(table: str, columns: tuple[str, ...], rows: list[dict]) -> int:
    if not rows:
        return 0
    conn = get_conn()
    try:
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)
        update_cols = [col for col in columns if col != "date"]
        update_clause = ", ".join(f"{col}=excluded.{col}" for col in update_cols)
        if update_clause:
            update_clause += ", updated_at=datetime('now')"
        else:
            update_clause = "updated_at=datetime('now')"
        sql = f"""
            INSERT INTO {table} ({col_names})
            VALUES ({placeholders})
            ON CONFLICT(date) DO UPDATE SET {update_clause}
        """
        for row in rows:
            conn.execute(sql, [row.get(col) for col in columns])
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def _sync_athlete_status(rows: list[dict]):
    conn = get_conn()
    try:
        for row in rows:
            if not row.get("date"):
                continue
            conn.execute(
                """
                INSERT INTO athlete_status (date, sleep_hours, sleep_quality, resting_hr)
                VALUES (?, ?, ?, NULL)
                ON CONFLICT(date) DO UPDATE SET
                    sleep_hours=COALESCE(excluded.sleep_hours, athlete_status.sleep_hours),
                    sleep_quality=COALESCE(excluded.sleep_quality, athlete_status.sleep_quality)
                """,
                (
                    row.get("date"),
                    round(row["sleep_total_min"] / 60, 2) if row.get("sleep_total_min") else None,
                    row.get("sleep_score"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _one(conn, sql: str, params: tuple = ()) -> dict:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else {}


def _many(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


# --- Activity (session-level) sync ------------------------------------------


def existing_coros_label_ids() -> set[str]:
    """Return labelIds already ingested. Matches both 'coros_<id>.fit' (new) and
    bare '<id>.fit' (legacy COROS exports) so backfill won't duplicate history."""
    init_db()
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT filename FROM sessions WHERE filename LIKE '%.fit'"
        ).fetchall()
    finally:
        conn.close()
    out: set[str] = set()
    for r in rows:
        name = r["filename"]
        stem = name[:-4] if name.endswith(".fit") else name
        if stem.startswith("coros_"):
            stem = stem[len("coros_") :]
        if stem.isdigit():
            out.add(stem)
    return out


def upsert_coros_sessions(rows: list[dict]) -> int:
    """Insert COROS sessions keyed by filename=coros_<labelId>.fit. Idempotent (IGNORE on dup)."""
    if not rows:
        return 0
    conn = get_conn()
    n = 0
    try:
        for r in rows:
            filename = f"coros_{r['label_id']}.fit"
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO sessions
                    (filename, sport, start_time, duration_sec, distance_km,
                     total_calories, avg_hr, avg_pace_sec, training_effect,
                     anaerobic_te, training_type, training_effect_label)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    filename,
                    r.get("sport"),
                    r["start_time"],
                    r.get("duration_sec"),
                    r.get("distance_km"),
                    r.get("calories"),
                    r.get("avg_hr"),
                    r.get("avg_pace_sec"),
                    r.get("training_effect"),
                    r.get("anaerobic_te"),
                    r.get("training_type"),
                    r.get("training_effect_label"),
                ),
            )
            n += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return n


def mark_session_has_track_points(session_id: int) -> None:
    """Flag that a session now has track_points.

    upsert_coros_sessions does not touch has_track_points (schema default 0);
    bridges that write session_track_points must set this so the session page
    renders the HR/GPS track.
    """
    conn = get_conn()
    try:
        conn.execute("UPDATE sessions SET has_track_points=1 WHERE id=?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def upsert_laps(session_id: int, laps: list[dict]) -> int:
    """Insert laps for a session. lap distance_m -> distance_km. UNIQUE(session_id, lap_index)."""
    if not laps:
        return 0
    conn = get_conn()
    n = 0
    try:
        for lap in laps:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO laps
                    (session_id, lap_index, distance_km, avg_hr, max_hr,
                     avg_pace_sec, avg_cadence)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    session_id,
                    lap.get("lap_index"),
                    (lap.get("distance_m") or 0) / 1000.0,
                    lap.get("avg_hr"),
                    lap.get("max_hr"),
                    lap.get("avg_pace_sec"),
                    lap.get("avg_cadence"),
                ),
            )
            n += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return n
