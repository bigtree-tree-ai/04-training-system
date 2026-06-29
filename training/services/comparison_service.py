"""环比分析服务 — 30天/自定义周期对比"""
from datetime import datetime, timedelta

from training.storage.db import get_conn, init_db


def compare_periods(days: int = 30) -> dict:
    """当前N天 vs 上一个N天的多维度对比"""
    init_db()
    conn = get_conn()
    try:
        now = datetime.now().date()
        current_start = (now - timedelta(days=days)).strftime('%Y-%m-%d')
        previous_start = (now - timedelta(days=days * 2)).strftime('%Y-%m-%d')
        current_end = now.strftime('%Y-%m-%d')
        previous_end = current_start

        current = _get_period_stats(conn, current_start, current_end)
        previous = _get_period_stats(conn, previous_start, previous_end)

        # PMC趋势
        current_pmc = _get_pmc_at_date(conn, current_end)
        previous_pmc = _get_pmc_at_date(conn, previous_end)

        # VO2max趋势
        current_vo2 = _get_avg_vo2max(conn, current_start, current_end)
        previous_vo2 = _get_avg_vo2max(conn, previous_start, previous_end)

        # 心率分区分布
        current_zones = _get_zone_distribution(conn, current_start, current_end)
        previous_zones = _get_zone_distribution(conn, previous_start, previous_end)

        metrics = _build_comparison_metrics(
            current, previous, current_pmc, previous_pmc,
            current_vo2, previous_vo2, current_zones, previous_zones
        )

        return {
            'days': days,
            'current_period': f"{current_start} ~ {current_end}",
            'previous_period': f"{previous_start} ~ {previous_end}",
            'current': current,
            'previous': previous,
            'metrics': metrics,
            'summary': _generate_summary(metrics),
        }
    finally:
        conn.close()


def _get_period_stats(conn, start: str, end: str) -> dict:
    row = conn.execute("""
        SELECT
            COUNT(*) as session_count,
            SUM(CASE WHEN (sport='running' OR sport LIKE '%Run%') THEN 1 ELSE 0 END) as run_count,
            ROUND(COALESCE(SUM(CASE WHEN (sport='running' OR sport LIKE '%Run%') THEN distance_km END), 0), 1) as run_km,
            ROUND(COALESCE(SUM(CASE WHEN (sport='running' OR sport LIKE '%Run%') THEN hr_tss END), 0), 1) as total_tss,
            ROUND(COALESCE(AVG(CASE WHEN (sport='running' OR sport LIKE '%Run%') AND hr_tss > 0 THEN hr_tss END), 0), 1) as avg_tss,
            ROUND(COALESCE(SUM(duration_sec), 0) / 3600, 1) as total_hours,
            ROUND(COALESCE(AVG(CASE WHEN (sport='running' OR sport LIKE '%Run%') AND avg_pace_sec > 330 THEN avg_pace_sec END), 0), 1) as avg_easy_pace,
            ROUND(COALESCE(AVG(CASE WHEN (sport='running' OR sport LIKE '%Run%') AND avg_pace_sec > 330 THEN avg_hr END), 0), 1) as avg_easy_hr,
            ROUND(COALESCE(MAX(CASE WHEN (sport='running' OR sport LIKE '%Run%') THEN distance_km END), 0), 1) as longest_run
        FROM sessions
        WHERE start_time >= ? AND start_time < ?
    """, (start, end)).fetchone()
    return dict(row) if row else {}


def _get_pmc_at_date(conn, date: str) -> dict:
    row = conn.execute("""
        SELECT ctl, atl, tsb, acwr, training_status
        FROM daily_load WHERE date <= ? ORDER BY date DESC LIMIT 1
    """, (date,)).fetchone()
    return dict(row) if row else {}


def _get_avg_vo2max(conn, start: str, end: str) -> float | None:
    row = conn.execute("""
        SELECT ROUND(AVG(vo2max), 1) as avg_vo2
        FROM sessions
        WHERE (sport='running' OR sport LIKE '%Run%') AND vo2max IS NOT NULL
          AND start_time >= ? AND start_time < ?
    """, (start, end)).fetchone()
    return row['avg_vo2'] if row else None


def _get_zone_distribution(conn, start: str, end: str) -> dict:
    row = conn.execute("""
        SELECT
            COALESCE(SUM(h.zone1_sec), 0) as z1,
            COALESCE(SUM(h.zone2_sec), 0) as z2,
            COALESCE(SUM(h.zone3_sec), 0) as z3,
            COALESCE(SUM(h.zone4_sec), 0) as z4,
            COALESCE(SUM(h.zone5_sec), 0) as z5
        FROM sessions s
        JOIN hr_zone_splits h ON s.id = h.session_id
        WHERE (s.sport='running' OR s.sport LIKE '%Run%') AND s.start_time >= ? AND s.start_time < ?
    """, (start, end)).fetchone()
    if not row:
        return {}
    total = row['z1'] + row['z2'] + row['z3'] + row['z4'] + row['z5']
    if total == 0:
        return {}
    return {
        'z1_pct': round(row['z1'] / total * 100, 1),
        'z2_pct': round(row['z2'] / total * 100, 1),
        'z3_pct': round(row['z3'] / total * 100, 1),
        'z4_pct': round(row['z4'] / total * 100, 1),
        'z5_pct': round(row['z5'] / total * 100, 1),
        'easy_pct': round((row['z1'] + row['z2']) / total * 100, 1),
    }


def _build_comparison_metrics(current, previous, cur_pmc, prev_pmc,
                               cur_vo2, prev_vo2, cur_zones, prev_zones) -> list[dict]:
    metrics = []

    def add(name, cur_val, prev_val, unit, higher_is_better=True, format_fn=None):
        if cur_val is None or prev_val is None:
            return
        diff = cur_val - prev_val
        pct = (diff / prev_val * 100) if prev_val != 0 else 0
        if higher_is_better:
            trend = 'better' if diff > 0 else ('worse' if diff < 0 else 'same')
        else:
            trend = 'better' if diff < 0 else ('worse' if diff > 0 else 'same')

        metrics.append({
            'name': name,
            'current': format_fn(cur_val) if format_fn else cur_val,
            'previous': format_fn(prev_val) if format_fn else prev_val,
            'diff': round(diff, 1),
            'diff_pct': round(pct, 1),
            'trend': trend,
            'unit': unit,
        })

    def pace_fmt(sec):
        if not sec: return "N/A"
        return f"{int(sec // 60)}:{int(sec % 60):02d}"

    # 跑量
    add('跑步次数', current.get('run_count', 0), previous.get('run_count', 0), '次', True)
    add('总跑量', current.get('run_km', 0), previous.get('run_km', 0), 'km', True)
    add('总训练时长', current.get('total_hours', 0), previous.get('total_hours', 0), '小时', True)
    add('总训练负荷(TSS)', current.get('total_tss', 0), previous.get('total_tss', 0), '', True)
    add('平均单次TSS', current.get('avg_tss', 0), previous.get('avg_tss', 0), '', True)
    add('最长单次距离', current.get('longest_run', 0), previous.get('longest_run', 0), 'km', True)

    # 轻松跑效率（配速低=更快=更好）
    add('轻松跑平均配速', current.get('avg_easy_pace', 0), previous.get('avg_easy_pace', 0),
        '/km', False, pace_fmt)
    # 同配速心率降低=更好
    add('轻松跑平均心率', current.get('avg_easy_hr', 0), previous.get('avg_easy_hr', 0),
        'bpm', False)

    # CTL（体能）
    add('CTL(体能)', cur_pmc.get('ctl'), prev_pmc.get('ctl'), '', True)

    # VO2max
    add('VO2max均值', cur_vo2, prev_vo2, 'ml/kg/min', True)

    # 极化训练(Z1+Z2占比)
    add('低强度占比(Z1+Z2)', cur_zones.get('easy_pct'), prev_zones.get('easy_pct'), '%', True)

    return metrics


def _generate_summary(metrics: list[dict]) -> str:
    better = [m for m in metrics if m['trend'] == 'better']
    worse = [m for m in metrics if m['trend'] == 'worse']

    lines = []
    if better:
        items = '、'.join(m['name'] for m in better[:3])
        lines.append(f"进步指标({len(better)}项): {items}")
    if worse:
        items = '、'.join(m['name'] for m in worse[:3])
        lines.append(f"退步指标({len(worse)}项): {items}")

    if len(better) > len(worse):
        lines.append("总体趋势: 训练效果正向发展，保持当前训练节奏")
    elif len(worse) > len(better):
        lines.append("总体趋势: 需要关注训练质量和恢复状况")
    else:
        lines.append("总体趋势: 训练状态稳定")

    return '\n'.join(lines)


def format_comparison_report(data: dict) -> str:
    """格式化环比报告（CLI输出用）"""
    lines = []
    lines.append("=" * 70)
    lines.append(f"  {data['days']}天训练环比分析")
    lines.append(f"  当前: {data['current_period']}")
    lines.append(f"  对比: {data['previous_period']}")
    lines.append("=" * 70)

    for m in data['metrics']:
        arrow = '↑' if m['diff'] > 0 else ('↓' if m['diff'] < 0 else '→')
        color_tag = '✓' if m['trend'] == 'better' else ('✗' if m['trend'] == 'worse' else '→')
        cur = m['current']
        prev = m['previous']

        lines.append(f"\n  {m['name']}:")
        lines.append(f"    当前: {cur} {m['unit']}  |  上期: {prev} {m['unit']}")
        lines.append(f"    变化: {arrow} {m['diff']:+.1f} ({m['diff_pct']:+.1f}%) {color_tag}")

    lines.append(f"\n{'─' * 70}")
    lines.append(f"  {data['summary']}")
    lines.append("=" * 70)
    return '\n'.join(lines)
