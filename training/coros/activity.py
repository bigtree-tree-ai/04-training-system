"""COROS Activity (session-level) sync: records + detail + laps + FIT.

4-step pipeline: querySportRecords -> getActivityDetail -> queryActivityLapData
-> queryActivityFitFileDownloadUrls (per labelId) + urllib download. Separate
from sync.py (summary statistics).
"""
from __future__ import annotations

import re
import ssl
import urllib.request
from datetime import date, datetime, timedelta, timezone

from training import config
from training.coros import storage
from training.coros.parsers import (
    extract_tool_text,
    parse_activity_detail,
    parse_activity_laps,
    parse_sport_records,
)
from training.data_import.fit_parser import parse_fit_file
from training.storage.writers import upsert_gait, upsert_track_points


class ActivitySyncService:
    """Ingest COROS training sessions (records/detail/laps/FIT) into the sessions tables."""

    def __init__(self, client=None, timezone: str = "Asia/Shanghai"):
        self.client = client
        self.timezone = timezone

    def _ensure_client(self):
        """Lazily build a real MCP client; return (client, None) or (None, token_status)."""
        if self.client is None:
            from training.coros.client import CorosMcpClient
            from training.coros.token_health import get_valid_token

            token, status = get_valid_token()
            if token is None:
                return None, status
            client = CorosMcpClient(access_token=token)
            client.initialize()
            self.client = client
        return self.client, None

    def sync(self, days: int = 7, full: bool = False, with_fit: bool = False) -> dict:
        client, token_status = self._ensure_client()
        if client is None:
            return {
                "success": False,
                "token_status": token_status,
                "persisted": {"sessions": 0, "laps": 0, "fit": 0},
                "fetched": 0,
                "failed": [],
            }

        today = date.today()
        if full:
            start = today - timedelta(days=365 * 2)
        else:
            start = today - timedelta(days=days - 1)
        sd, ed = start.strftime("%Y%m%d"), today.strftime("%Y%m%d")

        records = parse_sport_records(
            extract_tool_text(
                client.call_tool(
                    "querySportRecords",
                    {
                        "startDate": sd,
                        "endDate": ed,
                        "sportTypeCodes": [65535],
                        "limit": 500,
                        "timezone": self.timezone,
                    },
                )
            )
        )
        existing = storage.existing_coros_label_ids()
        new_records = [r for r in records if r["label_id"] not in existing]

        session_rows: list[dict] = []
        laps_to_backfill: list[tuple[str, list[dict]]] = []
        failed: list[str] = []
        for r in new_records:
            label_id, stype = r["label_id"], r["sport_type"]
            try:
                detail = parse_activity_detail(
                    extract_tool_text(
                        client.call_tool(
                            "getActivityDetail", {"labelId": label_id, "sportType": stype}
                        )
                    )
                )
                laps = parse_activity_laps(
                    extract_tool_text(
                        client.call_tool(
                            "queryActivityLapData", {"labelId": label_id, "sportType": stype}
                        )
                    )
                )
            except Exception:
                failed.append(label_id)
                continue
            focus = detail.get("training_focus")
            session_rows.append(
                {
                    "label_id": label_id,
                    "sport_type": stype,
                    "sport": r["sport"],
                    "start_time": _ts_to_local(r["start_ts"]),
                    "distance_km": detail.get("distance_km") or r["distance_km"],
                    "avg_hr": detail.get("avg_hr") or r["avg_hr"],
                    "avg_pace_sec": detail.get("avg_pace_sec") or r["avg_pace_sec"],
                    "duration_sec": r["duration_sec"],
                    "calories": detail.get("calories") or r["calories"],
                    "training_effect": detail.get("aerobic_te"),
                    "anaerobic_te": detail.get("anaerobic_te"),
                    "training_type": focus,
                    "training_effect_label": focus,
                }
            )
            laps_to_backfill.append((label_id, laps))

        n_session = storage.upsert_coros_sessions(session_rows)
        n_laps = _backfill_laps(laps_to_backfill)
        fit_count = 0
        if with_fit:
            for row in session_rows:
                try:
                    if self._download_fit(row["label_id"], row["sport_type"]) is not None:
                        if self._ingest_fit(row["label_id"]) is not None:
                            fit_count += 1
                except Exception:
                    continue

        return {
            "success": True,
            "persisted": {"sessions": n_session, "laps": n_laps, "fit": fit_count},
            "fetched": len(records),
            "failed": failed,
        }

    def _download_fit(self, label_id: str, sport_type: int):
        """Download one activity's FIT via its OSS url into config.COROS_FIT_DIR. Returns Path|None."""
        import certifi

        fit_dir = config.COROS_FIT_DIR
        fit_dir.mkdir(parents=True, exist_ok=True)
        dest = fit_dir / f"coros_{label_id}.fit"
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        result = self.client.call_tool(
            "queryActivityFitFileDownloadUrls",
            {"labelId": str(label_id), "sportType": int(sport_type)},
        )
        url = _extract_fit_url(extract_tool_text(result))
        if not url:
            return None
        ctx = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(
            url, headers={"User-Agent": "training-system-coros-sync/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            dest.write_bytes(resp.read())
        return dest

    def _ingest_fit(self, label_id: str):
        """Parse the downloaded FIT and write track_points + gait for the session. Returns sid|None."""
        from training.storage.db import get_conn

        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT id FROM sessions WHERE filename=?", (f"coros_{label_id}.fit",)
            ).fetchone()
            sid = row["id"] if row else None
        finally:
            conn.close()
        if sid is None:
            return None
        fit_path = config.COROS_FIT_DIR / f"coros_{label_id}.fit"
        result = parse_fit_file(str(fit_path))
        if not result:
            return sid
        upsert_track_points(sid, result.get("track_points", []))
        upsert_gait(sid, result.get("gait") or {})
        return sid


def _ts_to_local(ts: int) -> str:
    """Unix timestamp -> 'YYYY-MM-DD HH:MM:SS' (treated as UTC; COROS ts are UTC seconds)."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _extract_fit_url(text: str) -> str | None:
    """Pull the first https://....fit download URL out of the tool response text."""
    m = re.search(r"https://\S+?\.fit", text)
    return m.group(0) if m else None


def _backfill_laps(items: list[tuple[str, list[dict]]]) -> int:
    """Resolve session ids for each (label_id, laps) and insert the laps. Returns total inserted."""
    if not items:
        return 0
    from training.storage.db import get_conn

    conn = get_conn()
    id_map: dict[str, int] = {}
    try:
        for label_id, _ in items:
            row = conn.execute(
                "SELECT id FROM sessions WHERE filename=?", (f"coros_{label_id}.fit",)
            ).fetchone()
            if row:
                id_map[label_id] = row["id"]
    finally:
        conn.close()

    total = 0
    for label_id, laps in items:
        sid = id_map.get(label_id)
        if sid is not None and laps:
            total += storage.upsert_laps(sid, laps)
    return total
