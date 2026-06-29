"""周汇总统计"""
from datetime import datetime

from training.storage.db import init_db, get_conn, RUN_SPORT_PREDICATE
from training.storage.writers import upsert_weekly_summary


def compute_weekly_summaries():
    """按ISO周聚合训练数据"""
    init_db()
    conn = get_conn()

    rows = conn.execute(f"""
        SELECT
            strftime('%Y', start_time) as year,
            strftime('%W', start_time) as week_number,
            MIN(DATE(start_time)) as week_start,
            MAX(DATE(start_time)) as week_end,
            COUNT(*) as total_sessions,
            SUM(CASE WHEN {RUN_SPORT_PREDICATE} THEN 1 ELSE 0 END) as run_sessions,
            SUM(CASE WHEN NOT {RUN_SPORT_PREDICATE} THEN 1 ELSE 0 END) as cross_sessions,
            ROUND(SUM(COALESCE(distance_km, 0)), 2) as total_distance_km,
            ROUND(SUM(CASE WHEN {RUN_SPORT_PREDICATE} THEN COALESCE(distance_km, 0) ELSE 0 END), 2) as run_distance_km,
            ROUND(SUM(COALESCE(duration_sec, 0)), 1) as total_duration_sec,
            SUM(COALESCE(total_calories, 0)) as total_calories,
            ROUND(SUM(COALESCE(hr_tss, 0)), 1) as total_hr_tss,
            ROUND(AVG(CASE WHEN {RUN_SPORT_PREDICATE} AND avg_hr IS NOT NULL THEN avg_hr END), 0) as avg_hr,
            MAX(CASE WHEN {RUN_SPORT_PREDICATE} THEN max_hr END) as max_hr_of_week,
            ROUND(AVG(CASE WHEN {RUN_SPORT_PREDICATE} AND avg_pace_sec IS NOT NULL
                       AND avg_pace_sec > 330 THEN avg_pace_sec END), 1) as avg_easy_pace_sec,
            ROUND(MAX(CASE WHEN {RUN_SPORT_PREDICATE} THEN distance_km END), 2) as longest_run_km
        FROM sessions
        GROUP BY year, week_number
        ORDER BY year, week_number
    """).fetchall()

    # 计算周间距离变化率
    prev_dist = None
    count = 0
    for r in rows:
        data = dict(r)
        data['year'] = int(data['year'])
        data['week_number'] = int(data['week_number'])

        # 距离变化率
        cur_dist = data['run_distance_km'] or 0
        if prev_dist and prev_dist > 0:
            change = (cur_dist - prev_dist) / prev_dist * 100
            data['distance_change_pct'] = round(change, 1)
        else:
            data['distance_change_pct'] = None
        prev_dist = cur_dist

        upsert_weekly_summary(data)
        count += 1

    conn.close()

    print(f"周汇总计算完成: {count} 周")

    # 打印最近4周
    conn2 = get_conn()
    recent = conn2.execute("""
        SELECT year, week_number, week_start, week_end,
               run_sessions, run_distance_km, total_hr_tss,
               avg_easy_pace_sec, longest_run_km, distance_change_pct
        FROM weekly_summaries ORDER BY year DESC, week_number DESC LIMIT 4
    """).fetchall()

    print("\n最近4周汇总:")
    print(f"  {'周':>8s} {'跑步次':>6s} {'跑量km':>8s} {'hrTSS':>7s} {'轻松配速':>8s} {'最长km':>7s} {'变化%':>7s}")
    for r in reversed(list(recent)):
        pace_str = ""
        if r['avg_easy_pace_sec']:
            m = int(r['avg_easy_pace_sec'] // 60)
            s = int(r['avg_easy_pace_sec'] % 60)
            pace_str = f"{m}:{s:02d}"
        chg = f"{r['distance_change_pct']:+.0f}%" if r['distance_change_pct'] is not None else "-"
        print(f"  W{r['week_number']:02d}     {r['run_sessions'] or 0:>4d}   {r['run_distance_km'] or 0:>7.1f}  {r['total_hr_tss'] or 0:>6.1f}    {pace_str:>6s}  {r['longest_run_km'] or 0:>6.1f}  {chg:>6s}")
    conn2.close()

    return count


if __name__ == "__main__":
    compute_weekly_summaries()
