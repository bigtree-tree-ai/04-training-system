"""增量回填 GPS 轨迹 + 步态参数（science v2）

不破坏现有 sessions/laps/hr_zones，只对 has_track_points=0 或 has_gait=0 的会话重解析。

用法：
  python -m scripts.reparse_fit_v2                       # 全量
  python -m scripts.reparse_fit_v2 --since 2025-04-01    # 指定日期之后
  python -m scripts.reparse_fit_v2 --limit 5             # 仅前 5 场（dry test）
  python -m scripts.reparse_fit_v2 --dry-run             # 仅打印
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training import config
from training.data_import.fit_parser import parse_fit_file
from training.storage.db import get_conn, init_db
from training.storage.writers import upsert_track_points, upsert_gait


def find_fit(filename: str) -> Path | None:
    for d in (config.COROS_FIT_DIR, config.EXTRA_FIT_DIR, config.USER_UPLOAD_DIR):
        if d and Path(d).exists():
            p = Path(d) / filename
            if p.exists():
                return p
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", help="YYYY-MM-DD 起始日期")
    parser.add_argument("--limit", type=int, help="最多处理 N 场")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reparse-all", action="store_true", help="忽略 has_* 标志，强制重跑")
    args = parser.parse_args()

    init_db()
    conn = get_conn()
    try:
        sql = "SELECT id, filename, start_time, has_track_points, has_gait FROM sessions"
        cond = []
        params: list = []
        if not args.reparse_all:
            cond.append("(COALESCE(has_track_points,0)=0 OR COALESCE(has_gait,0)=0)")
        if args.since:
            cond.append("start_time >= ?")
            params.append(args.since)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY start_time DESC"
        if args.limit:
            sql += f" LIMIT {int(args.limit)}"

        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    print(f"待处理 sessions: {len(rows)}", flush=True)
    track_ok = gait_ok = miss = errs = 0

    for r in rows:
        fit_path = find_fit(r["filename"])
        if not fit_path:
            miss += 1
            continue
        result = parse_fit_file(str(fit_path))
        if not result:
            errs += 1
            continue
        track = result.get("track_points") or []
        gait = result.get("gait") or {}

        if args.dry_run:
            print(f"[dry] {r['filename']:40s} track={len(track):5d} gait_samples={gait.get('sample_count',0):5d}")
            continue

        if track:
            upsert_track_points(r["id"], track)
            track_ok += 1
        if gait and gait.get("sample_count"):
            upsert_gait(r["id"], gait)
            gait_ok += 1

        # 更新 has_* 标志
        c2 = get_conn()
        try:
            c2.execute(
                "UPDATE sessions SET has_track_points=?, has_gait=?, updated_at=datetime('now') WHERE id=?",
                (1 if track else 0, 1 if gait.get("sample_count") else 0, r["id"]),
            )
            c2.commit()
        finally:
            c2.close()

    print(f"\n回填完成：track_ok={track_ok} gait_ok={gait_ok} 文件缺失={miss} 错误={errs}")


if __name__ == "__main__":
    main()
