"""宏观指标: 每日训练负荷 + ATL/CTL/TSB (PMC)"""
from datetime import datetime, timedelta

from training.storage.db import init_db, get_conn
from training.storage.writers import upsert_daily_load


def compute_daily_load():
    """计算每日训练负荷及ATL/CTL/TSB"""
    init_db()
    conn = get_conn()

    # 获取所有有hrTSS的跑步session，按日期聚合
    rows = conn.execute("""
        SELECT DATE(start_time) as date,
               SUM(COALESCE(hr_tss, 0)) as daily_tss,
               SUM(COALESCE(distance_km, 0)) as daily_distance_km,
               SUM(COALESCE(duration_sec, 0)) as daily_duration_sec,
               COUNT(*) as session_count
        FROM sessions
        WHERE hr_tss IS NOT NULL
        GROUP BY DATE(start_time)
        ORDER BY date
    """).fetchall()

    if not rows:
        print("没有hrTSS数据，请先运行session_metrics")
        conn.close()
        return 0

    # 获取日期范围（从第一次训练到今天）
    first_date = datetime.strptime(rows[0]['date'], '%Y-%m-%d').date()
    today = datetime.now().date()

    # 构建日期->TSS映射
    daily_data = {}
    for r in rows:
        daily_data[r['date']] = {
            'daily_tss': r['daily_tss'],
            'daily_distance_km': r['daily_distance_km'],
            'daily_duration_sec': r['daily_duration_sec'],
            'session_count': r['session_count'],
        }

    # 按日期序列计算 EMA
    atl = 0.0
    ctl = 0.0
    count = 0
    current = first_date

    while current <= today:
        date_str = current.strftime('%Y-%m-%d')
        info = daily_data.get(date_str, {})
        tss = info.get('daily_tss', 0)

        # EMA更新
        atl = atl + (tss - atl) / 7
        ctl = ctl + (tss - ctl) / 42
        tsb = round(ctl - atl, 1)

        upsert_daily_load({
            'date': date_str,
            'daily_tss': round(tss, 1),
            'daily_distance_km': round(info.get('daily_distance_km', 0), 2),
            'daily_duration_sec': round(info.get('daily_duration_sec', 0), 1),
            'session_count': info.get('session_count', 0),
            'atl': round(atl, 1),
            'ctl': round(ctl, 1),
            'tsb': round(tsb, 1),
        })
        count += 1
        current += timedelta(days=1)

    # 计算单调性和应变（7天滚动窗口）
    compute_monotony_strain(conn, first_date, today)

    conn.close()
    print(f"每日负荷计算完成: {count} 天")

    # 打印最近7天PMC
    conn2 = get_conn()
    recent = conn2.execute("""
        SELECT date, daily_tss, atl, ctl, tsb
        FROM daily_load ORDER BY date DESC LIMIT 7
    """).fetchall()
    print("\n最近7天PMC:")
    print(f"  {'日期':>12s} {'TSS':>6s} {'ATL':>6s} {'CTL':>6s} {'TSB':>6s}")
    for r in reversed(list(recent)):
        print(f"  {r['date']:>12s} {r['daily_tss']:6.1f} {r['atl']:6.1f} {r['ctl']:6.1f} {r['tsb']:6.1f}")
    conn2.close()

    return count


def compute_monotony_strain(conn, first_date, last_date):
    """计算7天滚动窗口的单调性和应变"""
    current = first_date + timedelta(days=6)  # 需要7天窗口

    while current <= last_date:
        window_start = (current - timedelta(days=6)).strftime('%Y-%m-%d')
        window_end = current.strftime('%Y-%m-%d')

        rows = conn.execute("""
            SELECT daily_tss FROM daily_load
            WHERE date BETWEEN ? AND ?
            ORDER BY date
        """, (window_start, window_end)).fetchall()

        tss_values = [r['daily_tss'] for r in rows]
        if len(tss_values) == 7:
            mean_tss = sum(tss_values) / 7
            if mean_tss > 0:
                variance = sum((t - mean_tss) ** 2 for t in tss_values) / 7
                std_tss = variance ** 0.5
                monotony = mean_tss / std_tss if std_tss > 0 else 0
                strain = sum(tss_values) * monotony
            else:
                monotony = 0
                strain = 0

            conn.execute("""
                UPDATE daily_load SET monotony=?, strain=?
                WHERE date=?
            """, (round(monotony, 2), round(strain, 1), window_end))

        current += timedelta(days=1)

    conn.commit()


if __name__ == "__main__":
    compute_daily_load()
