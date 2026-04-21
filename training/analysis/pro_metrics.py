"""专业训练指标 v2.0 — VO2max / ACWR / Training Status / Training Effect / Marathon Shape"""
import math
from datetime import datetime, timedelta

from training import config
from training.storage.db import get_conn, init_db


def estimate_vo2max(avg_pace_sec: float, avg_hr: float, duration_sec: float,
                    distance_km: float) -> float | None:
    """基于Jack Daniels公式估算VO2max

    前提: 跑步距离>=2km, 时长>=10分钟, 有有效心率
    公式:
      speed = distance_m / duration_min
      %VO2max = 0.8 + 0.1894393 * e^(-0.012778 * duration_min) + 0.2989558 * e^(-0.1932605 * duration_min)
      VO2 = -4.60 + 0.182258 * speed + 0.000104 * speed^2
      %HRmax = (avg_hr / MHR)
      VO2max = VO2 / %VO2max * (%HRmax / fractional_utilization_correction)

    简化版(更稳定): 使用配速-VO2max经验回归
    """
    if not avg_pace_sec or not avg_hr or not duration_sec or not distance_km:
        return None
    if distance_km < 2 or duration_sec < 600:
        return None
    if avg_hr <= config.RESTING_HEART_RATE:
        return None

    duration_min = duration_sec / 60
    speed = distance_km * 1000 / duration_min  # m/min

    # VO2 at this speed (ml/kg/min) — Jack Daniels regression
    vo2 = -4.60 + 0.182258 * speed + 0.000104 * speed ** 2

    # Fraction of VO2max based on duration
    frac_vo2max = (0.8 + 0.1894393 * math.exp(-0.012778 * duration_min)
                   + 0.2989558 * math.exp(-0.1932605 * duration_min))

    if frac_vo2max <= 0:
        return None

    # HR fraction
    hr_frac = avg_hr / config.MAX_HEART_RATE
    if hr_frac < 0.5 or hr_frac > 1.0:
        return None

    # VO2max estimate — adjust by HR utilization
    vo2max = vo2 / frac_vo2max

    # Sanity check
    if vo2max < 20 or vo2max > 90:
        return None

    return round(vo2max, 1)


def compute_acwr(daily_loads: list[dict]) -> float | None:
    """计算ACWR（急性慢性负荷比）

    ACWR = 7天平均TSS / 28天平均TSS
    安全区间: 0.8-1.3
    高风险: >1.5
    极危险: >1.8
    """
    if len(daily_loads) < 28:
        return None

    recent_7 = daily_loads[-7:]
    recent_28 = daily_loads[-28:]

    acute = sum(d.get('daily_tss', 0) for d in recent_7) / 7
    chronic = sum(d.get('daily_tss', 0) for d in recent_28) / 28

    if chronic <= 0:
        return None

    acwr = acute / chronic
    return round(acwr, 2)


def determine_training_status(ctl: float, atl: float, tsb: float,
                               ctl_7d_ago: float = None,
                               monotony: float = None) -> str:
    """判定训练状态（参考Garmin 8种状态系统）

    Returns: Peaking | Productive | Maintaining | Recovery |
             Unproductive | Detraining | Overreaching | Strained
    """
    if ctl is None or atl is None or tsb is None:
        return "Unknown"

    ctl_trend = None
    if ctl_7d_ago is not None and ctl_7d_ago > 0:
        ctl_trend = (ctl - ctl_7d_ago) / ctl_7d_ago

    # Strained: 高负荷 + 高单调性
    if monotony and monotony > 2.0 and tsb < -20:
        return "Strained"

    # Overreaching: TSB极低
    if tsb < config.TSB_OVERREACHING:
        return "Overreaching"

    # Peaking: TSB在最佳比赛区间 + CTL稳定
    if config.TSB_PEAKING_MIN <= tsb <= config.TSB_PEAKING_MAX and ctl >= 20:
        return "Peaking"

    # Detraining: CTL显著下降
    if ctl_trend is not None and ctl_trend < -0.10:
        return "Detraining"

    # Recovery: TSB正值但CTL略降
    if tsb > 0 and ctl < 15:
        return "Recovery"
    if tsb > 5 and ctl_trend is not None and ctl_trend < 0:
        return "Recovery"

    # Unproductive: 有训练但CTL下降
    if ctl_trend is not None and ctl_trend < -0.03 and atl > 10:
        return "Unproductive"

    # Maintaining: CTL平稳
    if ctl_trend is not None and abs(ctl_trend) < 0.03:
        return "Maintaining"

    # Productive: CTL上升
    if ctl_trend is not None and ctl_trend >= 0.03:
        return "Productive"

    # 默认
    if tsb > 0:
        return "Recovery"
    return "Maintaining"


def classify_training_type(avg_hr: float, avg_pace_sec: float,
                           duration_sec: float, distance_km: float,
                           hr_zones: dict = None) -> str:
    """自动分类训练类型

    Returns: Easy Run | Tempo | Threshold | Interval | Long Run | Recovery | Cross Training
    """
    if not avg_hr:
        return "Unknown"

    hrr = (avg_hr - config.RESTING_HEART_RATE) / config.HEART_RATE_RESERVE

    # 基于心率储备比判断
    if hrr < 0.60:
        if distance_km and distance_km >= 15:
            return "Long Run"
        return "Recovery"
    elif hrr < 0.70:
        if distance_km and distance_km >= 15:
            return "Long Run"
        return "Easy Run"
    elif hrr < 0.80:
        return "Tempo"
    elif hrr < 0.90:
        return "Threshold"
    else:
        return "Interval"


def classify_training_effect(training_type: str, hr_tss: float = None,
                              duration_sec: float = None) -> str:
    """分类训练效果标签（参考Garmin Training Effect）

    Returns: Recovery | Base | Tempo | Threshold | VO2max | Anaerobic
    """
    effect_map = {
        "Recovery": "Recovery",
        "Easy Run": "Base",
        "Long Run": "Base",
        "Tempo": "Tempo",
        "Threshold": "Threshold",
        "Interval": "VO2max",
    }
    return effect_map.get(training_type, "Base")


def estimate_recovery_hours(hr_tss: float, training_type: str,
                            tsb: float = None) -> float:
    """估算恢复时间（小时）

    基于hrTSS和训练类型，参考EPOC原理
    """
    if not hr_tss:
        return 12

    # 基础恢复时间 = hrTSS映射
    if hr_tss < 30:
        base_hours = 12
    elif hr_tss < 60:
        base_hours = 24
    elif hr_tss < 100:
        base_hours = 36
    elif hr_tss < 150:
        base_hours = 48
    else:
        base_hours = 72

    # 高强度训练额外恢复
    intensity_factor = {
        "Recovery": 0.7,
        "Easy Run": 0.8,
        "Long Run": 1.2,
        "Tempo": 1.1,
        "Threshold": 1.3,
        "Interval": 1.4,
    }
    factor = intensity_factor.get(training_type, 1.0)

    # TSB低时恢复更慢
    if tsb is not None and tsb < -20:
        factor *= 1.3

    return round(base_hours * factor, 0)


def predict_race_time(vo2max: float, distance_km: float) -> float | None:
    """基于VO2max预测比赛成绩（秒）

    使用Jack Daniels VDOT表的逆向推算 + Riegel修正
    """
    if not vo2max or vo2max < 25 or vo2max > 85:
        return None

    # VDOT参考配速（简化回归）
    # 5K基准时间 from VDOT
    vdot_5k_sec = 30 * 60 * math.exp(-0.0435 * (vo2max - 30))

    # Riegel公式: T2 = T1 * (D2/D1)^1.06
    base_dist = 5.0
    predicted = vdot_5k_sec * (distance_km / base_dist) ** 1.06

    return round(predicted, 0)


def compute_marathon_shape(sessions: list[dict], weeks: int = 12) -> float:
    """计算马拉松专项准备度（0-100%）参考Runalyze Marathon Shape

    基于近N周的长距离训练完成度:
    - 长距离跑次数和距离
    - 20km+跑的完成质量
    - 连续长跑周的持续性
    """
    if not sessions:
        return 0.0

    long_runs = [s for s in sessions if s.get('distance_km', 0) >= 15]
    very_long = [s for s in sessions if s.get('distance_km', 0) >= 20]

    # 长跑次数得分 (0-30)
    count_score = min(len(long_runs) * 5, 30)

    # 最长距离得分 (0-30)
    max_dist = max((s.get('distance_km', 0) for s in sessions), default=0)
    dist_score = min(max_dist / 35 * 30, 30)  # 35km=满分

    # 20km+跑次数得分 (0-20)
    very_long_score = min(len(very_long) * 7, 20)

    # 总跑量得分 (0-20)
    total_km = sum(s.get('distance_km', 0) for s in sessions)
    volume_score = min(total_km / 500 * 20, 20)  # 500km=满分

    shape = count_score + dist_score + very_long_score + volume_score
    return round(min(shape, 100), 1)


def compute_all_pro_metrics():
    """为所有session计算专业指标并写入数据库"""
    init_db()
    conn = get_conn()

    sessions = conn.execute("""
        SELECT id, avg_hr, duration_sec, avg_speed_mps, avg_pace_sec,
               distance_km, sport, hr_tss
        FROM sessions WHERE sport='running' AND avg_hr IS NOT NULL
    """).fetchall()

    # 获取最新TSB
    latest_load = conn.execute("""
        SELECT tsb FROM daily_load ORDER BY date DESC LIMIT 1
    """).fetchone()
    current_tsb = latest_load['tsb'] if latest_load else None

    updated = 0
    for s in sessions:
        sid = s['id']

        # VO2max
        vo2max = estimate_vo2max(s['avg_pace_sec'], s['avg_hr'],
                                  s['duration_sec'], s['distance_km'])

        # 训练类型分类
        training_type = classify_training_type(
            s['avg_hr'], s['avg_pace_sec'], s['duration_sec'], s['distance_km'])

        # 训练效果标签
        effect_label = classify_training_effect(training_type, s['hr_tss'])

        # 恢复时间
        recovery = estimate_recovery_hours(s['hr_tss'], training_type, current_tsb)

        updates = {}
        if vo2max is not None:
            updates['vo2max'] = vo2max
        updates['training_type'] = training_type
        updates['training_effect_label'] = effect_label
        updates['recovery_hours'] = recovery

        if updates:
            sets = ', '.join(f"{k}=?" for k in updates)
            vals = list(updates.values()) + [sid]
            conn.execute(f"UPDATE sessions SET {sets}, updated_at=datetime('now') WHERE id=?", vals)
            updated += 1

    conn.commit()

    # 计算ACWR和Training Status
    _compute_daily_pro_metrics(conn)

    conn.close()
    print(f"专业指标计算完成: {updated}/{len(sessions)} 条跑步已更新")
    return updated


def _compute_daily_pro_metrics(conn):
    """为daily_load计算ACWR和Training Status"""
    rows = conn.execute("""
        SELECT date, daily_tss, atl, ctl, tsb, monotony
        FROM daily_load ORDER BY date
    """).fetchall()

    if len(rows) < 28:
        return

    rows_list = [dict(r) for r in rows]

    for i in range(27, len(rows_list)):
        row = rows_list[i]
        window_28 = rows_list[max(0, i-27):i+1]

        # ACWR
        acwr = compute_acwr(window_28)

        # Training Status
        ctl_7d_ago = rows_list[i-7]['ctl'] if i >= 7 else None
        status = determine_training_status(
            row['ctl'], row['atl'], row['tsb'],
            ctl_7d_ago=ctl_7d_ago, monotony=row['monotony'])

        conn.execute("""
            UPDATE daily_load SET acwr=?, training_status=?
            WHERE date=?
        """, (acwr, status, row['date']))

    conn.commit()
    print(f"ACWR和Training Status计算完成: {len(rows_list)-27} 天已更新")
