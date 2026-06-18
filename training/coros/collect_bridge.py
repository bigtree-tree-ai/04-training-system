"""Bridge COROS collect (Training Hub) data into training-system coros_* tables.

coros-collect (`/opt/coros-collect`) stores daily Training Hub snapshots in a
separate SQLite DB (`data/coros.sqlite`), in an EAV-style `daily_metrics` table
keyed by `metric_type`. This module reads the latest snapshots, parses the
payloads, and upserts them into training-system's `coros_*` tables — which are
the source of truth that `DailyFeaturePipeline.compute_for_date` reads to feed
the AI coach's ReadinessFeatures.

This replaces the broken MCP `coros-sync` path (COROS upgraded the MCP protocol
and the old client now returns `Session not found 404`). coros-collect pulls the
same athlete data via the Training Hub browser session instead.

Mapped dimensions (the ones that actually move readiness):
- analyse.query  -> coros_heart_rate_daily.resting_hr, coros_training_load
- dashboard.query summaryInfo.recoveryPct        -> coros_recovery_snapshots.recovery_pct  (drives recovery_score)
- dashboard.query summaryInfo.sleepHrvData        -> coros_hrv.hrv_avg_ms / baseline_ms
- dashboard.query summaryInfo.fullRecoveryHours   -> coros_recovery_snapshots.estimated_full_recovery_hours

Not covered (coros-collect does not collect daily sleep/stress/daily-health
detail): coros_sleep, coros_stress_daily, coros_daily_health. Those still need
the MCP path to be repaired, which is out of scope here.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from training.coros import storage
from training.storage.db import get_conn


ANALYSE = "analyse.query"
DASHBOARD = "dashboard.query"

# recoveryState is COROS's 1-5 ordinal; map to a coarse label for display only.
_RECOVERY_LABELS = {1: "low", 2: "fair", 3: "good", 4: "optimal", 5: "peak"}


def bridge_from_collect(collect_db_path: str, *, recovery_keep: int = 60) -> dict[str, int]:
    """Read latest metrics from coros-collect DB and upsert into training-system.

    Idempotent: re-running only updates existing rows (ON CONFLICT(date)). The
    recovery snapshot table is pruned to the most recent `recovery_keep` rows so
    daily runs do not accumulate unbounded history (it has no date column).

    Returns per-table upsert counts, e.g.
    {"heart_rate": 3, "training_load": 3, "hrv": 6, "recovery": 1}.
    """
    if not Path(collect_db_path).exists():
        raise FileNotFoundError(f"coros-collect DB not found: {collect_db_path}")

    latest = _load_latest_metrics(collect_db_path)

    heart_rate_rows = _parse_heart_rate(latest.get(ANALYSE))
    load_rows = _parse_training_load(latest.get(ANALYSE))
    hrv_rows = _parse_hrv(latest.get(DASHBOARD))
    recovery = _parse_recovery(latest.get(DASHBOARD))

    counts = {
        "heart_rate": storage.upsert_resting_hr(heart_rate_rows),
        "training_load": storage.upsert_training_load(load_rows),
        "hrv": storage.upsert_hrv(hrv_rows),
        "recovery": storage.upsert_recovery(recovery) if recovery else 0,
    }
    if recovery:
        _prune_recovery_snapshots(recovery_keep)
    return counts


def _load_latest_metrics(collect_db_path: str) -> dict[str, dict]:
    """Load the newest non-null values_json per relevant metric_type.

    metric_date can be NULL for some snapshot types, so order by rowid (insertion
    order) rather than metric_date to reliably get the latest.
    """
    out: dict[str, dict] = {}
    # Open read-only: this DB belongs to coros-collect, we must never write it.
    conn = sqlite3.connect(f"file:{collect_db_path}?mode=ro", uri=True)
    try:
        for metric_type in (ANALYSE, DASHBOARD):
            row = conn.execute(
                "SELECT values_json FROM daily_metrics "
                "WHERE metric_type = ? AND values_json IS NOT NULL "
                "ORDER BY rowid DESC LIMIT 1",
                (metric_type,),
            ).fetchone()
            if row and row[0]:
                try:
                    out[metric_type] = json.loads(row[0])
                except json.JSONDecodeError:
                    continue
    finally:
        conn.close()
    return out


def _parse_heart_rate(analyse: dict | None) -> list[dict]:
    """analyse.query.dayList.sample[].rhr -> [{date, resting_hr}, ...]."""
    if not analyse:
        return []
    rows: list[dict] = []
    for sample in analyse.get("dayList", {}).get("sample", []):
        date = _yyyymmdd_to_iso(sample.get("happenDay"))
        rhr = sample.get("rhr")
        if date and rhr is not None:
            rows.append({"date": date, "resting_hr": int(rhr)})
    return rows


def _parse_training_load(analyse: dict | None) -> list[dict]:
    """analyse.query.dayList.sample[] -> [{date, short_term_load, long_term_load, load_ratio}].

    COROS exposes trainingLoadRatio directly; fall back to t7d/t28d if absent.
    """
    if not analyse:
        return []
    rows: list[dict] = []
    for sample in analyse.get("dayList", {}).get("sample", []):
        date = _yyyymmdd_to_iso(sample.get("happenDay"))
        t7d = sample.get("t7d")
        t28d = sample.get("t28d")
        ratio = sample.get("trainingLoadRatio")
        if not date or (t7d is None and t28d is None and ratio is None):
            continue
        if ratio is None and t7d is not None and t28d:
            ratio = round(t7d / t28d, 2)
        rows.append(
            {
                "date": date,
                "short_term_load": t7d,
                "long_term_load": t28d,
                "load_ratio": ratio,
            }
        )
    return rows


def _parse_hrv(dashboard: dict | None) -> list[dict]:
    """dashboard.query.summaryInfo.sleepHrvData.sleepHrvList[]
    -> [{date, hrv_avg_ms, baseline_ms, normal_low_ms, normal_high_ms}, ...].

    sleepHrvIntervalList is [low, q1, q3, high]; we use the bounds as the
    normal range. avgSleepHrv is RMSSD-like in ms.
    """
    if not dashboard:
        return []
    hrv_list = (
        dashboard.get("summaryInfo", {}).get("sleepHrvData", {}).get("sleepHrvList", [])
    )
    rows: list[dict] = []
    for item in hrv_list:
        date = _yyyymmdd_to_iso(item.get("happenDay"))
        avg = item.get("avgSleepHrv")
        if not date or avg is None:
            continue
        intervals = item.get("sleepHrvIntervalList") or []
        rows.append(
            {
                "date": date,
                "hrv_avg_ms": int(avg),
                "baseline_ms": item.get("sleepHrvBase"),
                "normal_low_ms": intervals[0] if intervals else None,
                "normal_high_ms": intervals[-1] if intervals else None,
            }
        )
    return rows


def _parse_recovery(dashboard: dict | None) -> dict | None:
    """dashboard.query.summaryInfo -> recovery snapshot dict (current state).

    Recovery is a point-in-time value (not per-day), so it is appended as a new
    snapshot row each run and pruned by bridge_from_collect.
    """
    if not dashboard:
        return None
    info = dashboard.get("summaryInfo", {})
    pct = info.get("recoveryPct")
    hours = info.get("fullRecoveryHours")
    if pct is None and hours is None:
        return None
    state = info.get("recoveryState")
    return {
        "recovery_pct": int(pct) if pct is not None else None,
        "level": _RECOVERY_LABELS.get(state) if state is not None else None,
        "estimated_full_recovery_hours": float(hours) if hours is not None else None,
        "raw_text": json.dumps(
            {"recoveryPct": pct, "recoveryState": state, "fullRecoveryHours": hours},
            ensure_ascii=False,
        ),
    }


def _prune_recovery_snapshots(keep: int) -> None:
    """Keep only the most recent `keep` recovery snapshots (no date column)."""
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM coros_recovery_snapshots WHERE id NOT IN ("
            "SELECT id FROM coros_recovery_snapshots "
            "ORDER BY captured_at DESC, id DESC LIMIT ?)",
            (keep,),
        )
        conn.commit()
    finally:
        conn.close()


def _yyyymmdd_to_iso(day) -> str | None:
    """20260318 (int) -> '2026-03-18'. Returns None if not parseable."""
    if day is None:
        return None
    text = str(day)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return None
