"""单次训练指标计算: hrTSS, 配速CV, 心率漂移, 效率因子"""
import math

from training import config
from training.storage.db import init_db, get_conn
from training.storage.writers import update_session_metrics


def compute_hr_tss(avg_hr: float, duration_sec: float) -> float | None:
    """计算心率训练压力分数 (hrTSS)

    公式:
      HRR = (avg_hr - RHR) / (MHR - RHR)
      TRIMP = duration_min * HRR * 0.64 * e^(1.92 * HRR)
      hrTSS = TRIMP / LT_TRIMP_per_hour * 100
    """
    if not avg_hr or not duration_sec or duration_sec <= 0:
        return None
    if avg_hr <= config.RESTING_HEART_RATE:
        return None

    hrr = (avg_hr - config.RESTING_HEART_RATE) / config.HEART_RATE_RESERVE
    hrr = max(0.0, min(hrr, 1.0))

    duration_min = duration_sec / 60
    trimp = duration_min * hrr * 0.64 * math.exp(1.92 * hrr)

    # LT TRIMP per hour (at lactate threshold HR)
    lt_hrr = (config.LACTATE_THRESHOLD_HR - config.RESTING_HEART_RATE) / config.HEART_RATE_RESERVE
    lt_trimp_per_hour = 60 * lt_hrr * 0.64 * math.exp(1.92 * lt_hrr)

    if lt_trimp_per_hour == 0:
        return None

    tss = trimp / lt_trimp_per_hour * 100
    return round(tss, 1)


def compute_pace_cv(laps: list[dict]) -> float | None:
    """计算配速变异系数 (CV%)，衡量配速一致性

    CV = std(pace) / mean(pace) * 100
    仅使用距离 >= 0.5km 的完整圈
    """
    paces = []
    for lap in laps:
        pace = lap.get('avg_pace_sec')
        dist = lap.get('distance_km')
        if pace and dist and dist >= 0.5 and 120 < pace < 1800:
            paces.append(pace)

    if len(paces) < 2:
        return None

    mean_pace = sum(paces) / len(paces)
    variance = sum((p - mean_pace) ** 2 for p in paces) / len(paces)
    std_pace = math.sqrt(variance)

    cv = std_pace / mean_pace * 100
    return round(cv, 1)


def compute_hr_drift(laps: list[dict]) -> float | None:
    """计算心率漂移%: 后半程 vs 前半程心率变化

    drift = (后半程平均HR - 前半程平均HR) / 前半程平均HR * 100
    < 3% 优秀 | 3-5% 正常 | > 5% 有氧不足 | > 10% 危险
    """
    valid_laps = [l for l in laps if l.get('avg_hr') and l.get('duration_sec') and l['duration_sec'] > 0]
    if len(valid_laps) < 2:
        return None

    total_time = sum(l['duration_sec'] for l in valid_laps)
    half_time = total_time / 2

    first_hr_sum = 0.0
    first_time = 0.0
    second_hr_sum = 0.0
    second_time = 0.0

    elapsed = 0.0
    for lap in valid_laps:
        lap_dur = lap['duration_sec']
        lap_hr = lap['avg_hr']

        if elapsed + lap_dur <= half_time:
            first_hr_sum += lap_hr * lap_dur
            first_time += lap_dur
        elif elapsed >= half_time:
            second_hr_sum += lap_hr * lap_dur
            second_time += lap_dur
        else:
            # 跨越中点的圈
            first_part = half_time - elapsed
            second_part = lap_dur - first_part
            first_hr_sum += lap_hr * first_part
            first_time += first_part
            second_hr_sum += lap_hr * second_part
            second_time += second_part
        elapsed += lap_dur

    if first_time == 0 or second_time == 0:
        return None

    first_avg = first_hr_sum / first_time
    second_avg = second_hr_sum / second_time

    drift = (second_avg - first_avg) / first_avg * 100
    return round(drift, 1)


def compute_efficiency_factor(avg_speed_mps: float, avg_hr: float) -> float | None:
    """效率因子 = 速度 / 心率 * 1000

    更高 = 更有效率（同心率下跑得更快）
    趋势上升 = 有氧能力进步
    """
    if not avg_speed_mps or not avg_hr or avg_hr <= 0:
        return None
    ef = avg_speed_mps / avg_hr * 1000
    return round(ef, 2)


def compute_all_session_metrics():
    """为所有session计算指标并写入数据库"""
    init_db()
    conn = get_conn()

    # Include both legacy 'running' and COROS 'Outdoor Run'/'Indoor Run'. Exclude
    # Hiking/Walking/Cycling (no 'Run' in name). SQLite LIKE is case-insensitive
    # for ASCII but 'running' has no capital 'Run', so it needs the explicit OR.
    sessions = conn.execute("""
        SELECT id, avg_hr, duration_sec, avg_speed_mps, sport
        FROM sessions WHERE sport='running' OR sport LIKE '%Run%'
    """).fetchall()

    updated = 0
    for s in sessions:
        sid = s['id']

        # hrTSS
        hr_tss = compute_hr_tss(s['avg_hr'], s['duration_sec'])

        # 获取分圈数据
        laps = conn.execute(
            "SELECT avg_pace_sec, distance_km, avg_hr, duration_sec FROM laps WHERE session_id=?",
            (sid,)
        ).fetchall()
        laps = [dict(l) for l in laps]

        pace_cv = compute_pace_cv(laps)
        hr_drift = compute_hr_drift(laps)
        ef = compute_efficiency_factor(s['avg_speed_mps'], s['avg_hr'])

        metrics = {}
        if hr_tss is not None:
            metrics['hr_tss'] = hr_tss
        if pace_cv is not None:
            metrics['pace_cv'] = pace_cv
        if hr_drift is not None:
            metrics['hr_drift_pct'] = hr_drift
        if ef is not None:
            metrics['efficiency_factor'] = ef

        if metrics:
            update_session_metrics(sid, metrics)
            updated += 1

    conn.close()
    print(f"Session指标计算完成: {updated}/{len(sessions)} 条跑步已更新")
    return updated


if __name__ == "__main__":
    compute_all_session_metrics()
