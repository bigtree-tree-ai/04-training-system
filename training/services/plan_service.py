"""训练计划服务 — 协调课表生成和恢复计划"""
from training.storage.db import get_conn, init_db
from training.planning.generator import generate_plan
from training.planning.recovery import get_recovery_report, generate_weekly_recovery_strategy


def get_training_plan(weeks: int = 4) -> str:
    """生成训练计划"""
    return generate_plan(weeks=weeks)


def get_recovery_status() -> str:
    """获取恢复状态报告"""
    return get_recovery_report()


def get_plan_calendar() -> list[dict]:
    """获取课表日历数据（Web展示用）"""
    init_db()
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT tp.*, s.distance_km as actual_distance, s.avg_pace_sec as actual_pace,
                   s.hr_tss as actual_tss
            FROM training_plan tp
            LEFT JOIN sessions s ON tp.actual_session_id = s.id
            ORDER BY tp.planned_date
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def match_plan_to_actual():
    """将实际训练匹配到计划（按日期+类型最近匹配）"""
    init_db()
    conn = get_conn()
    try:
        plans = conn.execute("""
            SELECT id, planned_date, workout_type, target_distance_km
            FROM training_plan WHERE actual_session_id IS NULL AND workout_type != 'Rest'
        """).fetchall()

        matched = 0
        for plan in plans:
            # 查找当天的实际训练
            session = conn.execute("""
                SELECT id, distance_km FROM sessions
                WHERE (sport='running' OR sport LIKE '%Run%') AND DATE(start_time) = ?
                ORDER BY start_time LIMIT 1
            """, (plan['planned_date'],)).fetchone()

            if session:
                # 计算完成度
                target = plan['target_distance_km'] or 0
                actual = session['distance_km'] or 0
                adherence = round(min(actual / target, 1.5) * 100, 0) if target > 0 else 0

                conn.execute("""
                    UPDATE training_plan SET actual_session_id=?, adherence_score=?
                    WHERE id=?
                """, (session['id'], adherence, plan['id']))
                matched += 1

        conn.commit()
        return matched
    finally:
        conn.close()
