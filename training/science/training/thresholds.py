"""LT/CV 阈值动态学习 — 基于 EF 漂移 + 圈段拐点

理论参考：
- Conconi 1996 / Magness 2014 — LT 检测：心率-速度回归在拐点处发生斜率变化
- Galan-Rioja 2020 — Critical Speed 模型：3 分钟全力跑 + 12 分钟全力跑差值法
- 简化版：从近 N 周高强度 session 中找"配速最快但可持续 ≥ 20 min"的 LT 估计

输入：sessions 历史
输出：LT_HR / CV_pace_sec 估计 + 写入 thresholds_history 表
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from training.storage.db import get_conn


def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None


def estimate_lt_hr_from_recent(weeks: int = 8) -> Optional[int]:
    """从最近 N 周的 tempo / threshold 跑中估计 LT_HR

    取符合条件的 session：
      - duration_sec >= 1200（≥ 20 分钟持续努力）
      - avg_hr 在 0.85 × maxHR 附近（典型阈值区）
      - (sport='running' OR sport LIKE '%Run%')
    返回这些 session avg_hr 的中位数。
    """
    cutoff = (date.today() - timedelta(weeks=weeks)).isoformat()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT avg_hr FROM sessions
               WHERE (sport='running' OR sport LIKE '%Run%')
                 AND duration_sec >= 1200
                 AND avg_hr IS NOT NULL
                 AND start_time >= ?
                 AND (workout_type IN ('Tempo','Threshold') OR avg_hr >= 145)
               ORDER BY avg_hr DESC""",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    hrs = sorted([r["avg_hr"] for r in rows])
    mid = hrs[len(hrs) // 2]
    return int(mid)


def estimate_critical_speed(weeks: int = 8) -> Optional[float]:
    """估计临界速度（CV）— 取最近 N 周内 5-15 km 持续努力的最快平均配速（秒/km）"""
    cutoff = (date.today() - timedelta(weeks=weeks)).isoformat()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT avg_pace_sec FROM sessions
               WHERE (sport='running' OR sport LIKE '%Run%')
                 AND distance_km BETWEEN 5 AND 15
                 AND avg_pace_sec IS NOT NULL
                 AND start_time >= ?
               ORDER BY avg_pace_sec ASC
               LIMIT 5""",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    paces = [r["avg_pace_sec"] for r in rows]
    return round(sum(paces) / len(paces), 1)


def record_threshold(kind: str, value: float, source: str = "auto", note: str = "") -> int:
    """写入 thresholds_history"""
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO thresholds_history (kind, value, learned_on, source, note)
               VALUES (?, ?, ?, ?, ?)""",
            (kind, value, date.today().isoformat(), source, note),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def learn_and_record(weeks: int = 8) -> dict:
    """主入口：跑一次学习 + 落库 + 返回结果"""
    lt_hr = estimate_lt_hr_from_recent(weeks)
    cv = estimate_critical_speed(weeks)
    out: dict = {"weeks": weeks}
    if lt_hr:
        record_threshold("LT_HR", float(lt_hr), source="auto", note=f"from last {weeks}w tempo/threshold")
        out["lt_hr"] = lt_hr
    if cv:
        record_threshold("CV_pace_sec", cv, source="auto", note=f"from last {weeks}w 5-15km efforts")
        out["cv_pace_sec"] = cv
    return out


def latest(kind: str) -> Optional[float]:
    """读取最新一次某 kind 的阈值"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM thresholds_history WHERE kind=? ORDER BY learned_on DESC, id DESC LIMIT 1",
            (kind,),
        ).fetchone()
    finally:
        conn.close()
    return float(row["value"]) if row else None
