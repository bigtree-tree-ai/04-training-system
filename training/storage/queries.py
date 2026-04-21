"""数据读取查询函数 — 所有函数使用try/finally防止连接泄漏"""
from training.storage.db import get_conn


def get_all_sessions(sport=None, limit=None, offset=0):
    conn = get_conn()
    try:
        sql = "SELECT * FROM sessions"
        params = []
        if sport:
            sql += " WHERE sport=?"
            params.append(sport)
        sql += " ORDER BY start_time DESC"
        if limit:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_session_by_id(session_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_session_by_filename(filename: str):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE filename=?", (filename,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_laps_for_session(session_id: int):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM laps WHERE session_id=? ORDER BY lap_index", (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_hr_zones_for_session(session_id: int):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM hr_zone_splits WHERE session_id=?", (session_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_daily_load(from_date=None, to_date=None):
    conn = get_conn()
    try:
        sql = "SELECT * FROM daily_load"
        params = []
        conditions = []
        if from_date:
            conditions.append("date >= ?")
            params.append(from_date)
        if to_date:
            conditions.append("date <= ?")
            params.append(to_date)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY date"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_weekly_summaries(limit=None):
    conn = get_conn()
    try:
        sql = "SELECT * FROM weekly_summaries ORDER BY year DESC, week_number DESC"
        params = []
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_ai_reports(report_type=None, limit=20):
    conn = get_conn()
    try:
        sql = "SELECT * FROM ai_reports"
        params = []
        if report_type:
            sql += " WHERE report_type=?"
            params.append(report_type)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_session_count():
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()
        return row['cnt']
    finally:
        conn.close()


def get_running_sessions(from_date=None, to_date=None):
    conn = get_conn()
    try:
        sql = "SELECT * FROM sessions WHERE sport='running'"
        params = []
        if from_date:
            sql += " AND start_time >= ?"
            params.append(from_date)
        if to_date:
            sql += " AND start_time <= ?"
            params.append(to_date)
        sql += " ORDER BY start_time"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_imported_filenames():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT filename FROM sessions").fetchall()
        return {r['filename'] for r in rows}
    finally:
        conn.close()


def get_similar_sessions(session_id: int, sport: str = 'running',
                         distance_range: tuple | float = 2.0, limit: int = 10):
    """获取与指定session同类型、相近距离的历史训练

    distance_range: float(正负范围) 或 tuple(min_km, max_km)
    """
    conn = get_conn()
    try:
        session = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not session:
            return []

        dist = session['distance_km'] or 0
        if isinstance(distance_range, tuple):
            min_dist, max_dist = distance_range
        else:
            min_dist = dist - distance_range
            max_dist = dist + distance_range

        rows = conn.execute("""
            SELECT * FROM sessions
            WHERE sport=? AND id != ?
              AND distance_km BETWEEN ? AND ?
              AND hr_tss IS NOT NULL
            ORDER BY start_time DESC LIMIT ?
        """, (sport, session_id, min_dist, max_dist, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
