"""趋势检测与预警"""
from training.storage.db import init_db, get_conn


def detect_warnings() -> list[dict]:
    """检测训练预警信号"""
    init_db()
    conn = get_conn()
    warnings = []

    # 1. TSB过低 — 过度疲劳
    tsb_row = conn.execute("""
        SELECT date, tsb, atl, ctl FROM daily_load
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    if tsb_row and tsb_row['tsb'] is not None:
        if tsb_row['tsb'] < -30:
            warnings.append({
                'level': 'danger',
                'category': '过度疲劳',
                'message': f"TSB={tsb_row['tsb']:.1f} (< -30)，身体处于严重疲劳状态，建议立即减量恢复",
                'date': tsb_row['date'],
            })
        elif tsb_row['tsb'] < -20:
            warnings.append({
                'level': 'warning',
                'category': '疲劳累积',
                'message': f"TSB={tsb_row['tsb']:.1f} (< -20)，疲劳积累中，注意恢复",
                'date': tsb_row['date'],
            })

    # 2. 单调性过高 — 训练缺乏变化
    monotony_row = conn.execute("""
        SELECT date, monotony, strain FROM daily_load
        WHERE monotony IS NOT NULL
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    if monotony_row:
        if monotony_row['monotony'] > 2.0:
            warnings.append({
                'level': 'warning',
                'category': '训练单调',
                'message': f"单调性={monotony_row['monotony']:.2f} (>2.0)，训练负荷过于均匀，增加变化",
                'date': monotony_row['date'],
            })
        if monotony_row['strain'] and monotony_row['strain'] > 300:
            warnings.append({
                'level': 'danger',
                'category': '过度训练风险',
                'message': f"应变={monotony_row['strain']:.0f} (>300)，过度训练风险极高",
                'date': monotony_row['date'],
            })

    # 3. 周跑量跳增 >10%
    week_rows = conn.execute("""
        SELECT week_number, run_distance_km, distance_change_pct
        FROM weekly_summaries
        ORDER BY year DESC, week_number DESC LIMIT 1
    """).fetchone()
    if week_rows and week_rows['distance_change_pct'] is not None:
        if week_rows['distance_change_pct'] > 10:
            warnings.append({
                'level': 'warning',
                'category': '跑量跳增',
                'message': f"本周跑量增长{week_rows['distance_change_pct']:.0f}% (>10%)，注意10%递增法则",
                'date': f"W{week_rows['week_number']}",
            })

    # 4. 心率漂移过大（最近3次长跑）
    drift_rows = conn.execute("""
        SELECT filename, start_time, distance_km, hr_drift_pct
        FROM sessions
        WHERE sport='running' AND distance_km >= 8 AND hr_drift_pct IS NOT NULL
        ORDER BY start_time DESC LIMIT 3
    """).fetchall()
    high_drift = [r for r in drift_rows if r['hr_drift_pct'] > 5]
    if high_drift:
        for r in high_drift:
            warnings.append({
                'level': 'warning' if r['hr_drift_pct'] <= 10 else 'danger',
                'category': '心率漂移',
                'message': f"{r['distance_km']}km跑心率漂移{r['hr_drift_pct']:.1f}% (>5%)，有氧基础需加强",
                'date': r['start_time'][:10],
            })

    # 5. 强度分布检查（近14天）
    zone_row = conn.execute("""
        SELECT
            ROUND(AVG(h.zone1_pct + h.zone2_pct), 1) as easy_pct,
            ROUND(AVG(h.zone3_pct), 1) as tempo_pct,
            ROUND(AVG(h.zone4_pct + h.zone5_pct), 1) as hard_pct
        FROM sessions s
        JOIN hr_zone_splits h ON s.id = h.session_id
        WHERE s.sport='running'
          AND s.start_time >= DATE('now', '-14 days')
          AND h.zone1_pct IS NOT NULL
    """).fetchone()
    if zone_row and zone_row['easy_pct'] is not None:
        if zone_row['easy_pct'] < 70:
            warnings.append({
                'level': 'warning',
                'category': '强度分布失衡',
                'message': f"近14天轻松跑占比{zone_row['easy_pct']:.0f}% (<70%)，"
                           f"灰色地带{zone_row['tempo_pct']:.0f}%过多，需执行80/20极化训练",
                'date': 'recent',
            })

    conn.close()
    return warnings


def print_warnings():
    """打印所有预警"""
    warnings = detect_warnings()
    if not warnings:
        print("当前无预警信号")
        return

    print(f"\n检测到 {len(warnings)} 个预警:")
    for w in warnings:
        icon = "🔴" if w['level'] == 'danger' else "🟡"
        print(f"  {icon} [{w['category']}] {w['message']}")


if __name__ == "__main__":
    print_warnings()
