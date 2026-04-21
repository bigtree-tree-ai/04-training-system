"""从数据库组装AI教练所需的上下文"""
import json
from pathlib import Path

from training.storage.db import get_conn
from training import config


def _load_athlete_config() -> dict:
    """从athlete_config.json加载运动员配置"""
    config_path = Path(config.PROJECT_ROOT) / "athlete_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text(encoding='utf-8'))
    return {}


def build_athlete_profile() -> str:
    """构建运动员基础信息"""
    athlete = _load_athlete_config()
    name = athlete.get('name', '运动员')
    height = athlete.get('height_cm', 173.5)
    weight = athlete.get('weight_kg', 65)
    injury = athlete.get('injury_history', '无')
    current_injury = athlete.get('current_injury', '无')
    target = athlete.get('target_race', '未设定')
    race_desc = athlete.get('race_description', '')
    pb = athlete.get('half_marathon_pb', 'N/A')

    return f"""运动员档案:
- 身高: {height}cm, 体重: {weight}kg
- 最大心率(MHR): {config.MAX_HEART_RATE} bpm
- 静息心率(RHR): {config.RESTING_HEART_RATE} bpm
- 储备心率(HRR): {config.HEART_RATE_RESERVE} bpm
- 乳酸阈心率(LTHR): {config.LACTATE_THRESHOLD_HR} bpm
- 心率分区: Z1<126 Z2:126-138 Z3:138-150 Z4:150-161 Z5>161
- 伤病史: {injury}
- 当前伤情: {current_injury}
- 目标赛事: {target}({race_desc})
- 半马PB: {pb}"""


def build_macro_context(days: int = 30) -> str:
    """构建宏观训练上下文(最近N天)"""
    conn = get_conn()
    try:
        days = int(days)

        pmc = conn.execute("""
            SELECT date, daily_tss, atl, ctl, tsb, monotony, strain
            FROM daily_load ORDER BY date DESC LIMIT 1
        """).fetchone()

        if not pmc:
            return "暂无训练负荷数据，请先运行 python3 -m training.cli analyze 计算训练指标"

        days_param = f'-{days} days'
        stats = conn.execute("""
            SELECT COUNT(*) as cnt,
                   SUM(CASE WHEN sport='running' THEN 1 ELSE 0 END) as runs,
                   ROUND(SUM(CASE WHEN sport='running' THEN distance_km ELSE 0 END), 1) as run_km,
                   ROUND(SUM(duration_sec)/3600, 1) as hours,
                   ROUND(AVG(CASE WHEN sport='running' THEN avg_hr END), 0) as avg_hr,
                   ROUND(AVG(CASE WHEN sport='running' THEN hr_tss END), 0) as avg_tss,
                   ROUND(SUM(CASE WHEN sport='running' THEN hr_tss END), 0) as total_tss
            FROM sessions
            WHERE start_time >= DATE('now', ?)
        """, (days_param,)).fetchone()

        zones = conn.execute("""
            SELECT
                ROUND(AVG(h.zone1_pct), 1) as z1, ROUND(AVG(h.zone2_pct), 1) as z2,
                ROUND(AVG(h.zone3_pct), 1) as z3, ROUND(AVG(h.zone4_pct), 1) as z4,
                ROUND(AVG(h.zone5_pct), 1) as z5
            FROM sessions s JOIN hr_zone_splits h ON s.id=h.session_id
            WHERE s.sport='running' AND s.start_time >= DATE('now', ?) AND h.zone1_pct IS NOT NULL
        """, (days_param,)).fetchone()

        weeks = conn.execute("""
            SELECT year, week_number, run_sessions, run_distance_km, total_hr_tss,
                   avg_easy_pace_sec, longest_run_km, distance_change_pct
            FROM weekly_summaries ORDER BY year DESC, week_number DESC LIMIT 3
        """).fetchall()

        from training.analysis.trend_detector import detect_warnings
        warnings = detect_warnings()
    finally:
        conn.close()

    ctx = f"""近{days}天训练数据:
- 总训练: {stats['cnt']}次, 跑步{stats['runs']}次
- 跑步总距离: {stats['run_km']}km
- 总时长: {stats['hours']}小时
- 跑步平均心率: {stats['avg_hr']}bpm
- 跑步总hrTSS: {stats['total_tss']}, 场均: {stats['avg_tss']}

当前PMC状态({pmc['date']}):
- CTL(体能): {pmc['ctl']:.1f}
- ATL(疲劳): {pmc['atl']:.1f}
- TSB(状态): {pmc['tsb']:.1f}
- 单调性: {f"{pmc['monotony']:.2f}" if pmc['monotony'] else 'N/A'}
- 应变: {f"{pmc['strain']:.0f}" if pmc['strain'] else 'N/A'}

心率分区分布(跑步平均):
- Z1(恢复): {zones['z1'] if zones and zones['z1'] else 0}%
- Z2(有氧): {zones['z2'] if zones and zones['z2'] else 0}%
- Z3(节奏): {zones['z3'] if zones and zones['z3'] else 0}%
- Z4(阈值): {zones['z4'] if zones and zones['z4'] else 0}%
- Z5(极量): {zones['z5'] if zones and zones['z5'] else 0}%
"""

    ctx += "\n最近3周:\n"
    for w in weeks:
        ctx += f"  W{w['week_number']:02d}: 跑{w['run_sessions']}次 {w['run_distance_km'] or 0:.1f}km TSS={w['total_hr_tss'] or 0:.0f} 最长{w['longest_run_km'] or 0:.1f}km"
        if w['distance_change_pct'] is not None:
            ctx += f" (变化{w['distance_change_pct']:+.0f}%)"
        ctx += "\n"

    if warnings:
        ctx += "\n预警信号:\n"
        for w in warnings:
            level = "严重" if w['level'] == 'danger' else "警告"
            ctx += f"  [{level}] {w['category']}: {w['message']}\n"

    return ctx


def build_session_context(session_id: int) -> str:
    """构建单次训练上下文"""
    conn = get_conn()
    try:
        s = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not s:
            return ""

        s = dict(s)
        laps = conn.execute("SELECT * FROM laps WHERE session_id=? ORDER BY lap_index", (session_id,)).fetchall()
        zones = conn.execute("SELECT * FROM hr_zone_splits WHERE session_id=?", (session_id,)).fetchone()
    finally:
        conn.close()

    def pace_str(sec):
        if not sec:
            return "N/A"
        return f"{int(sec//60)}:{int(sec%60):02d}"

    ctx = f"""训练详情:
- 日期: {s['start_time'][:10] if s['start_time'] else 'N/A'}
- 类型: {s['sport']}
- 距离: {s['distance_km']}km
- 时长: {s['duration_sec']/60:.0f}分钟
- 配速: {pace_str(s['avg_pace_sec'])}/km
- 平均心率: {s['avg_hr']}bpm / 最大: {s['max_hr']}bpm
- hrTSS: {s['hr_tss']}
- 心率漂移: {s['hr_drift_pct']}%
- 配速CV: {s['pace_cv']}%
- 效率因子: {s['efficiency_factor']}
- 步频: {s['avg_cadence']}spm
"""

    if zones:
        zones = dict(zones)
        easy = (zones.get('zone1_pct') or 0) + (zones.get('zone2_pct') or 0)
        ctx += f"\n心率分区: Z1={zones.get('zone1_pct',0)}% Z2={zones.get('zone2_pct',0)}% Z3={zones.get('zone3_pct',0)}% Z4={zones.get('zone4_pct',0)}% Z5={zones.get('zone5_pct',0)}% (轻松占比{easy:.0f}%)\n"

    if laps:
        ctx += f"\n分圈数据({len(laps)}圈):\n"
        for lap in laps:
            lap = dict(lap)
            ctx += f"  Lap{lap['lap_index']+1}: {lap.get('distance_km', '?')}km {pace_str(lap.get('avg_pace_sec'))}/km HR={lap.get('avg_hr', '?')}\n"

    return ctx
