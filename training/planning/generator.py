"""AI课表计划生成系统 — 基于当前体能状态自动编排训练计划"""
from datetime import datetime, timedelta
import json

from training import config
from training.storage.db import get_conn, init_db


def generate_plan(weeks: int = 4) -> str:
    """生成未来N周训练计划"""
    init_db()
    context = _gather_context()
    plan = _create_plan(context, weeks)
    _save_plan(plan)
    return _format_plan(plan, context)


def _gather_context() -> dict:
    """收集生成计划所需的上下文"""
    conn = get_conn()

    # 当前PMC状态
    pmc = conn.execute("""
        SELECT date, atl, ctl, tsb, acwr, training_status, monotony
        FROM daily_load ORDER BY date DESC LIMIT 1
    """).fetchone()

    # 最近4周汇总
    weeks = conn.execute("""
        SELECT week_number, run_sessions, run_distance_km, total_hr_tss,
               avg_easy_pace_sec, longest_run_km
        FROM weekly_summaries ORDER BY year DESC, week_number DESC LIMIT 4
    """).fetchall()

    # 赛事倒计时
    race_date = datetime.strptime(config.GOBI_RACE_DATE, '%Y-%m-%d').date()
    days_to_race = (race_date - datetime.now().date()).days

    conn.close()

    return {
        'pmc': dict(pmc) if pmc else {},
        'recent_weeks': [dict(w) for w in weeks],
        'days_to_race': days_to_race,
        'weeks_to_race': days_to_race // 7,
    }


def _determine_phase(weeks_to_race: int) -> str:
    """确定训练周期"""
    if weeks_to_race > 20:
        return "基础期"
    elif weeks_to_race > 12:
        return "提升期"
    elif weeks_to_race > 4:
        return "竞赛准备期"
    elif weeks_to_race > 1:
        return "赛前减量期"
    else:
        return "比赛周"


def _create_plan(context: dict, num_weeks: int) -> list[dict]:
    """基于上下文创建训练计划"""
    pmc = context.get('pmc', {})
    recent = context.get('recent_weeks', [])

    # 基准参数
    current_ctl = pmc.get('ctl', 20)
    current_tsb = pmc.get('tsb', 0)
    current_acwr = pmc.get('acwr', 1.0)

    # 最近周均跑量
    recent_km = [w.get('run_distance_km', 0) or 0 for w in recent[:4]]
    avg_weekly_km = sum(recent_km) / len(recent_km) if recent_km else 20

    # 最近轻松配速
    easy_paces = [w.get('avg_easy_pace_sec') for w in recent if w.get('avg_easy_pace_sec')]
    easy_pace = sum(easy_paces) / len(easy_paces) if easy_paces else 390

    phase = _determine_phase(context.get('weeks_to_race', 30))

    plan = []
    today = datetime.now().date()
    # 从下周一开始
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    start_date = today + timedelta(days=days_until_monday)

    for week in range(num_weeks):
        week_start = start_date + timedelta(weeks=week)

        # 每4周第4周为减量周
        is_recovery_week = (week + 1) % 4 == 0

        # 周目标跑量（渐进+减量）
        if is_recovery_week:
            target_km = avg_weekly_km * 0.65
        else:
            growth = 1.0 + min(0.08 * (week + 1), 0.25)  # 最多增长25%
            target_km = avg_weekly_km * growth

        # TSB过低时自动降量
        if current_tsb and current_tsb < -25:
            target_km *= 0.8

        week_plan = _plan_week(
            week_start, week + 1, target_km, easy_pace,
            phase, is_recovery_week
        )
        plan.extend(week_plan)

    return plan


def _plan_week(week_start, week_num: int, target_km: float,
               easy_pace: float, phase: str, is_recovery: bool) -> list[dict]:
    """编排单周课表"""
    days = []

    if is_recovery:
        # 减量周: 3次轻松跑 + 1次短节奏
        templates = [
            ("Monday", "Rest", None, None),
            ("Tuesday", "Easy Run", target_km * 0.2, "Z2"),
            ("Wednesday", "Rest", None, None),
            ("Thursday", "Tempo", target_km * 0.15, "Z3"),
            ("Friday", "Rest", None, None),
            ("Saturday", "Easy Run", target_km * 0.25, "Z2"),
            ("Sunday", "Rest", None, None),
        ]
    elif phase in ("基础期", "提升期"):
        templates = [
            ("Monday", "Rest", None, None),
            ("Tuesday", "Easy Run", target_km * 0.18, "Z2"),
            ("Wednesday", "Tempo", target_km * 0.15, "Z3-Z4"),
            ("Thursday", "Easy Run", target_km * 0.15, "Z1-Z2"),
            ("Friday", "Rest", None, None),
            ("Saturday", "Interval", target_km * 0.12, "Z4-Z5"),
            ("Sunday", "Long Run", target_km * 0.30, "Z2"),
        ]
    elif phase == "竞赛准备期":
        templates = [
            ("Monday", "Rest", None, None),
            ("Tuesday", "Threshold", target_km * 0.15, "Z4"),
            ("Wednesday", "Easy Run", target_km * 0.15, "Z2"),
            ("Thursday", "Interval", target_km * 0.12, "Z4-Z5"),
            ("Friday", "Rest", None, None),
            ("Saturday", "Easy Run", target_km * 0.13, "Z2"),
            ("Sunday", "Long Run", target_km * 0.35, "Z2-Z3"),
        ]
    else:  # 赛前减量
        templates = [
            ("Monday", "Rest", None, None),
            ("Tuesday", "Easy Run", target_km * 0.20, "Z2"),
            ("Wednesday", "Tempo", target_km * 0.10, "Z3"),
            ("Thursday", "Rest", None, None),
            ("Friday", "Easy Run", target_km * 0.15, "Z1-Z2"),
            ("Saturday", "Rest", None, None),
            ("Sunday", "Easy Run", target_km * 0.15, "Z2"),
        ]

    workout_descriptions = {
        "Rest": "休息日 — 完全休息或轻度拉伸",
        "Easy Run": "轻松跑 — 保持对话配速，心率Z2区间",
        "Tempo": "节奏跑 — 2km热身 + 目标配速段 + 2km放松",
        "Threshold": "阈值跑 — 2km热身 + 4x1km@乳酸阈值配速 r=400m慢跑 + 2km放松",
        "Interval": "间歇训练 — 2km热身 + 6x800m@Z4-Z5 r=400m慢跑 + 2km放松",
        "Long Run": "长距离跑 — 匀速为主，后段可渐加速，心率Z2为主",
    }

    pace_targets = {
        "Easy Run": easy_pace,
        "Long Run": easy_pace + 10,
        "Tempo": easy_pace - 30,
        "Threshold": easy_pace - 45,
        "Interval": easy_pace - 60,
    }

    for i, (day_name, workout_type, dist, hr_zone) in enumerate(templates):
        date = week_start + timedelta(days=i)

        target_pace = pace_targets.get(workout_type)
        duration_min = None
        if dist and target_pace:
            duration_min = round(dist * target_pace / 60, 0)

        # 估算TSS
        tss_per_km = {"Easy Run": 4, "Long Run": 4.5, "Tempo": 7, "Threshold": 8, "Interval": 9}
        est_tss = round(dist * tss_per_km.get(workout_type, 5), 0) if dist else 0

        days.append({
            'plan_week': f"W{week_num}",
            'planned_date': date.strftime('%Y-%m-%d'),
            'workout_type': workout_type,
            'description': workout_descriptions.get(workout_type, ""),
            'target_distance_km': round(dist, 1) if dist else None,
            'target_duration_min': duration_min,
            'target_pace_sec': target_pace,
            'target_hr_zone': hr_zone,
            'notes': f"预估TSS: {est_tss}" if est_tss else None,
            'source': 'auto_v2',
        })

    return days


def _save_plan(plan: list[dict]):
    """保存计划到数据库"""
    conn = get_conn()
    for p in plan:
        conn.execute("""
            INSERT INTO training_plan (plan_week, planned_date, workout_type, description,
                target_distance_km, target_duration_min, target_pace_sec, target_hr_zone,
                notes, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
        """, (
            p['plan_week'], p['planned_date'], p['workout_type'], p['description'],
            p.get('target_distance_km'), p.get('target_duration_min'),
            p.get('target_pace_sec'), p.get('target_hr_zone'),
            p.get('notes'), p.get('source', 'auto_v2'),
        ))
    conn.commit()
    conn.close()


def _format_plan(plan: list[dict], context: dict) -> str:
    """格式化输出训练计划"""
    phase = _determine_phase(context.get('weeks_to_race', 30))

    def pace_str(sec):
        if not sec: return "-"
        return f"{int(sec//60)}:{int(sec%60):02d}"

    lines = []
    lines.append("=" * 70)
    lines.append(f"  训练计划 — {phase}")
    lines.append(f"  距离戈21: {context.get('days_to_race', '?')}天 ({context.get('weeks_to_race', '?')}周)")

    pmc = context.get('pmc', {})
    if pmc.get('ctl'):
        lines.append(f"  当前体能: CTL={pmc['ctl']:.1f} TSB={pmc.get('tsb','N/A')}")
    if pmc.get('training_status'):
        lines.append(f"  训练状态: {pmc['training_status']}")
    lines.append("=" * 70)

    current_week = None
    week_km = 0

    for p in plan:
        if p['plan_week'] != current_week:
            if current_week:
                lines.append(f"  {'周总距离':>42s}: {week_km:.1f}km")
                lines.append("")
            current_week = p['plan_week']
            week_km = 0
            lines.append(f"\n  ── {current_week} ({p['planned_date']}起) ──")

        dist = p.get('target_distance_km')
        if dist:
            week_km += dist

        date_obj = datetime.strptime(p['planned_date'], '%Y-%m-%d')
        weekday_cn = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        day_cn = weekday_cn[date_obj.weekday()]

        if p['workout_type'] == 'Rest':
            lines.append(f"  {day_cn} {p['planned_date']}: 休息")
        else:
            pace = pace_str(p.get('target_pace_sec'))
            lines.append(f"  {day_cn} {p['planned_date']}: {p['workout_type']}")
            lines.append(f"      距离: {dist:.1f}km | 目标配速: {pace}/km | 心率: {p.get('target_hr_zone', '-')}")
            if p.get('description'):
                lines.append(f"      {p['description']}")

    if current_week:
        lines.append(f"  {'周总距离':>42s}: {week_km:.1f}km")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)
