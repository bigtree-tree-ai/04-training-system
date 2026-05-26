"""api_v2 路由 — 给 professional_v2_* 页面提供数据

只读，不写入。命名空间 /api/v2/* 与现有 /api/* 隔离。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException

from training.application.science_today import build_today
from training.science.common.athlete_profile import load_athlete_profile
from training.storage.db import get_conn

router = APIRouter()


@router.get("/today")
def today():
    """SciencePrescription 聚合产出（一级决策台数据源）"""
    rx = build_today()
    return rx.to_dict()


@router.get("/session/{session_id}/full")
def session_full(session_id: int):
    """单次训练全息数据（三级页面数据源）

    包含：
    - meta（sport/distance/duration/avg_hr/training_type/...）
    - track（GPS+海拔+HR+speed+cadence 时间序列，按 30s 抽样以控制载荷）
    - laps
    - hr_zones
    - gait
    """
    conn = get_conn()
    try:
        meta = conn.execute(
            """SELECT id, filename, sport, sub_sport, start_time, duration_sec, distance_km,
                      total_calories, avg_hr, max_hr, avg_pace_sec, avg_cadence,
                      total_ascent, total_descent, training_effect, anaerobic_te,
                      vo2max, training_type, recovery_hours, hr_tss, hr_drift_pct,
                      pace_cv, efficiency_factor, has_track_points, has_gait
               FROM sessions WHERE id=?""",
            (session_id,),
        ).fetchone()
        if not meta:
            raise HTTPException(status_code=404, detail="session not found")

        # 抽样轨迹：每 ~10s 取一点（避免 3000+ 点全部传给前端）
        # 取个粗粒度：duration / 300 步进，至少每 5s 一点
        duration = meta["duration_sec"] or 3600
        step = max(int(duration / 300), 1)
        track_rows = conn.execute(
            """SELECT t_offset_s, lat, lon, altitude_m, hr, speed_mps, cadence, distance_m
               FROM session_track_points
               WHERE session_id=? AND CAST(t_offset_s AS INTEGER) % ? = 0
               ORDER BY t_offset_s""",
            (session_id, step),
        ).fetchall()
        track = [dict(r) for r in track_rows]

        laps = [dict(r) for r in conn.execute(
            "SELECT * FROM laps WHERE session_id=? ORDER BY lap_index", (session_id,)
        ).fetchall()]

        zone = conn.execute(
            "SELECT * FROM hr_zone_splits WHERE session_id=?", (session_id,)
        ).fetchone()

        gait = conn.execute(
            "SELECT * FROM session_gait WHERE session_id=?", (session_id,)
        ).fetchone()
    finally:
        conn.close()

    return {
        "meta": dict(meta),
        "track_sample_step_s": step,
        "track": track,
        "laps": laps,
        "hr_zones": dict(zone) if zone else None,
        "gait": dict(gait) if gait else None,
    }


@router.get("/trends/load")
def trends_load(days: int = 90):
    """CTL/ATL/TSB/ACWR 时间序列（二级趋势页数据源）"""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT date, daily_tss, ctl, atl, tsb, acwr, monotony, strain
               FROM daily_load
               WHERE date >= ?
               ORDER BY date""",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    return {"days": days, "series": [dict(r) for r in rows]}


@router.get("/trends/zones")
def trends_zones(weeks: int = 12):
    """周心率分区堆叠数据（二级趋势页数据源）"""
    cutoff = (date.today() - timedelta(weeks=weeks)).isoformat()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT
                strftime('%Y-W%W', s.start_time) AS week_key,
                SUM(z.zone1_sec) AS z1, SUM(z.zone2_sec) AS z2,
                SUM(z.zone3_sec) AS z3, SUM(z.zone4_sec) AS z4,
                SUM(z.zone5_sec) AS z5
               FROM hr_zone_splits z JOIN sessions s ON z.session_id = s.id
               WHERE s.start_time >= ?
               GROUP BY week_key
               ORDER BY week_key""",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    return {"weeks": weeks, "series": [dict(r) for r in rows]}


@router.get("/sessions/recent")
def sessions_recent(limit: int = 7):
    """最近 N 场训练摘要（决策台课卡墙）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, start_time, sport, distance_km, duration_sec, avg_hr,
                      avg_pace_sec, hr_tss, training_type, has_track_points, has_gait
               FROM sessions
               ORDER BY start_time DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return {"sessions": [dict(r) for r in rows]}
