"""身体恢复计划系统 — 基于训练负荷输出恢复建议"""
from datetime import datetime, timedelta

from training import config
from training.storage.db import get_conn, init_db


def get_recovery_report() -> str:
    """输出当前恢复状态报告"""
    init_db()
    conn = get_conn()

    # 最近一次训练
    latest = conn.execute("""
        SELECT * FROM sessions WHERE sport='running' ORDER BY start_time DESC LIMIT 1
    """).fetchone()

    # 当前PMC
    pmc = conn.execute("""
        SELECT date, atl, ctl, tsb, acwr, training_status, monotony, strain
        FROM daily_load ORDER BY date DESC LIMIT 1
    """).fetchone()

    # 最近7天训练
    recent_7d = conn.execute("""
        SELECT COUNT(*) as cnt,
               SUM(COALESCE(hr_tss, 0)) as total_tss,
               SUM(COALESCE(distance_km, 0)) as total_km
        FROM sessions
        WHERE sport='running' AND start_time >= DATE('now', '-7 days')
    """).fetchone()

    # 连续训练天数
    consecutive = _count_consecutive_days(conn)

    conn.close()

    return _format_recovery_report(latest, pmc, recent_7d, consecutive)


def _count_consecutive_days(conn) -> int:
    """计算连续训练天数"""
    rows = conn.execute("""
        SELECT DISTINCT DATE(start_time) as d FROM sessions
        WHERE sport='running' ORDER BY d DESC LIMIT 14
    """).fetchall()

    if not rows:
        return 0

    dates = [datetime.strptime(r['d'], '%Y-%m-%d').date() for r in rows]
    today = datetime.now().date()

    count = 0
    for i, d in enumerate(dates):
        expected = today - timedelta(days=i)
        if d == expected:
            count += 1
        else:
            break

    return count


def assess_recovery_status(tsb: float, consecutive_days: int,
                           weekly_tss: float, monotony: float = None) -> dict:
    """评估恢复状态"""
    # 恢复指数 (0-100, 越高越恢复)
    recovery_score = 50  # 基线

    # TSB贡献 (-30~+30 → -30~+30分)
    if tsb is not None:
        recovery_score += min(max(tsb, -30), 30)

    # 连续训练天数惩罚
    if consecutive_days >= 5:
        recovery_score -= 15
    elif consecutive_days >= 3:
        recovery_score -= 5

    # 单调性惩罚
    if monotony and monotony > 2.0:
        recovery_score -= 10

    recovery_score = max(0, min(100, recovery_score))

    # 状态判定
    if recovery_score >= 70:
        status = "充分恢复"
        color = "green"
        recommendation = "可以进行高强度训练"
    elif recovery_score >= 50:
        status = "基本恢复"
        color = "yellow"
        recommendation = "建议以轻松跑或交叉训练为主"
    elif recovery_score >= 30:
        status = "疲劳累积"
        color = "orange"
        recommendation = "建议轻松恢复跑或完全休息"
    else:
        status = "严重疲劳"
        color = "red"
        recommendation = "强烈建议完全休息1-2天"

    return {
        'score': recovery_score,
        'status': status,
        'color': color,
        'recommendation': recommendation,
    }


def suggest_today_activity(recovery_status: dict, tsb: float = None,
                           consecutive_days: int = 0) -> dict:
    """建议今日训练活动"""
    score = recovery_status['score']

    if score >= 70:
        if consecutive_days < 3:
            return {
                'activity': '按计划训练',
                'detail': '身体状态良好，可以进行计划中的训练',
                'intensity': '按计划执行',
            }
        else:
            return {
                'activity': '中等强度训练',
                'detail': '虽已恢复但连续训练天数较多，建议控制强度',
                'intensity': 'Z2-Z3',
            }
    elif score >= 50:
        return {
            'activity': '轻松恢复跑',
            'detail': '30-40分钟轻松跑，心率控制在Z1-Z2',
            'intensity': 'Z1-Z2',
            'target_duration': '30-40min',
        }
    elif score >= 30:
        return {
            'activity': '积极恢复',
            'detail': '20-30分钟散步/瑜伽/拉伸，避免跑步',
            'intensity': '极低',
        }
    else:
        return {
            'activity': '完全休息',
            'detail': '充分休息、充足睡眠、营养补充',
            'intensity': '无',
        }


def generate_weekly_recovery_strategy(conn=None) -> dict:
    """生成周恢复策略"""
    should_close = False
    if conn is None:
        init_db()
        conn = get_conn()
        should_close = True

    try:
        # 获取本周训练负荷
        week_data = conn.execute("""
            SELECT COUNT(*) as cnt,
                   SUM(COALESCE(hr_tss, 0)) as total_tss,
                   SUM(COALESCE(distance_km, 0)) as total_km,
                   AVG(CASE WHEN hr_tss > 0 THEN hr_tss END) as avg_tss
            FROM sessions
            WHERE sport='running' AND start_time >= DATE('now', '-7 days')
        """).fetchone()

        # 上周数据
        prev_week = conn.execute("""
            SELECT SUM(COALESCE(hr_tss, 0)) as total_tss,
                   SUM(COALESCE(distance_km, 0)) as total_km
            FROM sessions
            WHERE sport='running'
              AND start_time >= DATE('now', '-14 days')
              AND start_time < DATE('now', '-7 days')
        """).fetchone()

        current_tss = week_data['total_tss'] or 0
        prev_tss = prev_week['total_tss'] or 0 if prev_week else 0

        # 判断是否需要减量周
        needs_deload = False
        reasons = []

        if current_tss > prev_tss * 1.15 and prev_tss > 0:
            needs_deload = True
            reasons.append(f"周TSS增长{((current_tss/prev_tss)-1)*100:.0f}%(>15%)")

        pmc = conn.execute("""
            SELECT tsb, monotony FROM daily_load ORDER BY date DESC LIMIT 1
        """).fetchone()

        if pmc and pmc['tsb'] and pmc['tsb'] < -25:
            needs_deload = True
            reasons.append(f"TSB={pmc['tsb']:.1f}(<-25)")

        if pmc and pmc['monotony'] and pmc['monotony'] > 2.0:
            needs_deload = True
            reasons.append(f"单调性={pmc['monotony']:.2f}(>2.0)")

        strategy = {
            'needs_deload': needs_deload,
            'reasons': reasons,
            'current_week_tss': round(current_tss, 1),
            'previous_week_tss': round(prev_tss, 1),
        }

        if needs_deload:
            strategy['recommendation'] = (
                "建议下周减量:\n"
                "  - 总跑量降至本周65-70%\n"
                "  - 取消间歇/阈值训练，仅保留轻松跑\n"
                "  - 增加1-2天完全休息\n"
                "  - 重视睡眠(≥7.5小时)和营养补充"
            )
        else:
            strategy['recommendation'] = "当前负荷在可控范围内，可按计划继续训练"

        return strategy
    finally:
        if should_close:
            conn.close()


def _format_recovery_report(latest, pmc, recent_7d, consecutive) -> str:
    """格式化恢复报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("  身体恢复状态报告")
    lines.append("=" * 60)

    # 最近训练
    if latest:
        latest = dict(latest)
        def pace_str(sec):
            if not sec: return "N/A"
            return f"{int(sec//60)}:{int(sec%60):02d}"

        lines.append(f"\n最近一次训练:")
        lines.append(f"  日期: {latest.get('start_time', 'N/A')[:10]}")
        lines.append(f"  类型: {latest.get('training_type', 'N/A')}")
        lines.append(f"  距离: {latest.get('distance_km', 0):.1f}km")
        lines.append(f"  hrTSS: {latest.get('hr_tss', 'N/A')}")
        recovery_h = latest.get('recovery_hours')
        if recovery_h:
            lines.append(f"  建议恢复: {int(recovery_h)}小时")

    # 恢复状态评估
    pmc_dict = dict(pmc) if pmc else {}
    tsb = pmc_dict.get('tsb')
    monotony = pmc_dict.get('monotony')
    weekly_tss = recent_7d['total_tss'] if recent_7d else 0

    status = assess_recovery_status(tsb, consecutive, weekly_tss, monotony)

    lines.append(f"\n恢复评估:")
    lines.append(f"  恢复指数: {status['score']}/100")
    lines.append(f"  状态: {status['status']}")
    lines.append(f"  建议: {status['recommendation']}")

    # 详细指标
    lines.append(f"\n详细指标:")
    if tsb is not None:
        lines.append(f"  TSB(训练平衡): {tsb:.1f}")
    lines.append(f"  连续训练天数: {consecutive}天")
    if recent_7d:
        total_tss = recent_7d['total_tss'] or 0
        total_km = recent_7d['total_km'] or 0
        lines.append(f"  近7天: {recent_7d['cnt']}次训练, TSS={total_tss:.0f}, {total_km:.1f}km")
    if pmc_dict.get('training_status'):
        lines.append(f"  训练状态: {pmc_dict['training_status']}")
    if pmc_dict.get('acwr'):
        lines.append(f"  ACWR: {pmc_dict['acwr']:.2f}")

    # 今日建议
    activity = suggest_today_activity(status, tsb, consecutive)
    lines.append(f"\n今日活动建议:")
    lines.append(f"  推荐: {activity['activity']}")
    lines.append(f"  详情: {activity['detail']}")
    lines.append(f"  强度: {activity['intensity']}")

    # 周恢复策略
    weekly = generate_weekly_recovery_strategy()
    lines.append(f"\n周恢复策略:")
    if weekly['needs_deload']:
        lines.append(f"  需要减量! 原因: {', '.join(weekly['reasons'])}")
    lines.append(f"  {weekly['recommendation']}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)
