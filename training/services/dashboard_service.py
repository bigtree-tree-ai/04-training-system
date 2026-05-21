"""仪表板数据聚合服务 — 从app.py提取的裸SQL集中到此"""
from datetime import datetime

from training import config
from training.storage.db import get_conn, init_db
from training.storage.queries import get_all_sessions
from training.analysis.trend_detector import detect_warnings


def get_dashboard_data() -> dict:
    """聚合仪表板所需的全部数据"""
    init_db()
    conn = get_conn()
    try:
        week = _get_latest_week(conn)
        pmc = _get_latest_pmc(conn)
        recent = _get_recent_sessions(conn, limit=5)
        pro = _get_pro_status(conn)
        warnings = detect_warnings()
        days_to_race = _get_days_to_race()

        return {
            'week': week,
            'pmc': pmc,
            'recent_sessions': recent,
            'pro': pro,
            'warnings': warnings,
            'days_to_race': days_to_race,
        }
    finally:
        conn.close()


def _get_latest_week(conn) -> dict:
    row = conn.execute("""
        SELECT * FROM weekly_summaries ORDER BY year DESC, week_number DESC LIMIT 1
    """).fetchone()
    if row:
        return dict(row)
    return {
        'run_distance_km': 0,
        'total_hr_tss': 0,
        'total_sessions': 0,
        'run_sessions': 0,
    }


def _get_latest_pmc(conn) -> dict:
    row = conn.execute("""
        SELECT date, atl, ctl, tsb, acwr, training_status, monotony, strain
        FROM daily_load ORDER BY date DESC LIMIT 1
    """).fetchone()
    if row:
        return dict(row)
    return {
        'date': None,
        'atl': None,
        'ctl': None,
        'tsb': None,
        'acwr': None,
        'training_status': None,
        'monotony': None,
        'strain': None,
    }


def _get_recent_sessions(conn, limit: int = 5) -> list[dict]:
    rows = conn.execute("""
        SELECT id, sport, start_time, distance_km, duration_sec, avg_hr,
               avg_pace_sec, hr_tss, vo2max, training_type, training_effect_label,
               recovery_hours
        FROM sessions ORDER BY start_time DESC LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def _get_pro_status(conn) -> dict:
    """获取v3.0专业指标汇总"""
    # 最近一次跑步的VO2max
    vo2 = conn.execute("""
        SELECT vo2max FROM sessions
        WHERE sport='running' AND vo2max IS NOT NULL
        ORDER BY start_time DESC LIMIT 1
    """).fetchone()

    # 近12周跑步(marathon shape)
    shape_sessions = conn.execute("""
        SELECT distance_km FROM sessions
        WHERE sport='running' AND start_time >= DATE('now', '-84 days')
    """).fetchall()

    from training.analysis.pro_metrics import compute_marathon_shape
    marathon_shape = compute_marathon_shape([dict(s) for s in shape_sessions])

    # 恢复状态
    from training.planning.recovery import assess_recovery_status, count_consecutive_days
    pmc_row = conn.execute("""
        SELECT tsb, monotony FROM daily_load ORDER BY date DESC LIMIT 1
    """).fetchone()
    consecutive = count_consecutive_days(conn)
    tsb = pmc_row['tsb'] if pmc_row else None
    monotony = pmc_row['monotony'] if pmc_row else None
    recovery = assess_recovery_status(tsb, consecutive, 0, monotony)

    return {
        'vo2max': vo2['vo2max'] if vo2 else None,
        'marathon_shape': marathon_shape,
        'recovery': recovery,
        'consecutive_days': consecutive,
    }


def _get_days_to_race() -> int:
    race_date = datetime.strptime(config.GOBI_RACE_DATE, '%Y-%m-%d').date()
    return (race_date - datetime.now().date()).days


def get_summary_data() -> dict:
    """概览统计数据"""
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()['cnt']
        running = conn.execute("SELECT COUNT(*) as cnt FROM sessions WHERE sport='running'").fetchone()['cnt']
        total_km = conn.execute("SELECT ROUND(SUM(distance_km), 1) as km FROM sessions WHERE sport='running'").fetchone()['km']
        total_hrs = conn.execute("SELECT ROUND(SUM(duration_sec)/3600, 1) as hrs FROM sessions").fetchone()['hrs']
        return {
            'total_sessions': total,
            'running_sessions': running,
            'total_running_km': total_km or 0,
            'total_hours': total_hrs or 0,
        }
    finally:
        conn.close()
