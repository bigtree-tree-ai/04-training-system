"""增强FIT文件解析 — 提取session + laps + 心率分区"""
import hashlib
import sys
from pathlib import Path

from garmin_fit_sdk import Decoder, Stream

from training import config


def file_hash(fpath: str) -> str:
    h = hashlib.sha256()
    with open(fpath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()[:16]


def parse_fit_file(fpath: str) -> dict | None:
    """解析单个FIT文件，返回 {session, laps, hr_zones} 或 None"""
    try:
        stream = Stream.from_file(fpath)
        decoder = Decoder(stream)
        messages, errs = decoder.read()
    except Exception as e:
        print(f"  FIT解析失败 {Path(fpath).name}: {e}", file=sys.stderr)
        return None

    session_mesgs = messages.get('session_mesgs', [])
    if not session_mesgs:
        return None

    msg = session_mesgs[0]
    fname = Path(fpath).name

    # --- Session ---
    avg_spd = msg.get('enhanced_avg_speed') or msg.get('avg_speed')
    # 过滤COROS哨兵值
    if avg_spd and avg_spd > 20:
        avg_spd = None

    pace_sec = None
    if avg_spd and avg_spd > 0:
        pace_sec = round(1000 / avg_spd, 1)
        if pace_sec < 120 or pace_sec > 1800:
            pace_sec = None

    dist = msg.get('total_distance')
    distance_km = round(dist / 1000, 2) if dist else None

    dur = msg.get('total_timer_time')
    duration_sec = round(dur, 1) if dur else None

    session = {
        'filename': fname,
        'fit_file_hash': file_hash(fpath),
        'sport': str(msg.get('sport', '')).lower() if msg.get('sport') else None,
        'sub_sport': str(msg.get('sub_sport', '')).lower() if msg.get('sub_sport') else None,
        'start_time': str(msg.get('start_time', '')),
        'duration_sec': duration_sec,
        'distance_km': distance_km,
        'total_calories': msg.get('total_calories'),
        'avg_hr': msg.get('avg_heart_rate'),
        'max_hr': msg.get('max_heart_rate'),
        'avg_speed_mps': round(avg_spd, 3) if avg_spd else None,
        'avg_pace_sec': pace_sec,
        'avg_cadence': msg.get('avg_running_cadence') or msg.get('avg_cadence'),
        'max_cadence': msg.get('max_running_cadence') or msg.get('max_cadence'),
        'total_ascent': msg.get('total_ascent'),
        'total_descent': msg.get('total_descent'),
        'training_effect': msg.get('total_training_effect'),
        'anaerobic_te': msg.get('total_anaerobic_training_effect'),
        'avg_temperature': msg.get('avg_temperature'),
        'total_strides': msg.get('total_strides'),
    }

    # --- Laps ---
    laps = []
    for i, lap_msg in enumerate(messages.get('lap_mesgs', [])):
        lap_spd = lap_msg.get('enhanced_avg_speed') or lap_msg.get('avg_speed')
        if lap_spd and lap_spd > 20:
            lap_spd = None
        lap_pace = None
        if lap_spd and lap_spd > 0:
            lap_pace = round(1000 / lap_spd, 1)

        lap_dist = lap_msg.get('total_distance')
        laps.append({
            'lap_index': i,
            'start_time': str(lap_msg.get('start_time', '')),
            'duration_sec': round(lap_msg['total_timer_time'], 1) if lap_msg.get('total_timer_time') else None,
            'distance_km': round(lap_dist / 1000, 2) if lap_dist else None,
            'avg_hr': lap_msg.get('avg_heart_rate'),
            'max_hr': lap_msg.get('max_heart_rate'),
            'avg_speed_mps': round(lap_spd, 3) if lap_spd else None,
            'avg_pace_sec': lap_pace,
            'avg_cadence': lap_msg.get('avg_running_cadence') or lap_msg.get('avg_cadence'),
            'total_ascent': lap_msg.get('total_ascent'),
            'total_descent': lap_msg.get('total_descent'),
            'total_calories': lap_msg.get('total_calories'),
        })

    # --- HR Zone Splits (从record_mesgs计算) ---
    hr_zones = compute_hr_zones(messages.get('record_mesgs', []))

    return {'session': session, 'laps': laps, 'hr_zones': hr_zones}


def compute_hr_zones(record_mesgs: list) -> dict:
    """从逐秒record数据计算心率分区时间"""
    zone_secs = [0.0] * 5  # Z1-Z5
    zone_boundaries = [
        config.HR_ZONES['Z1']['max'],  # 126
        config.HR_ZONES['Z2']['max'],  # 138
        config.HR_ZONES['Z3']['max'],  # 150
        config.HR_ZONES['Z4']['max'],  # 161
    ]

    prev_ts = None
    for rec in record_mesgs:
        hr = rec.get('heart_rate')
        ts = rec.get('timestamp')
        if hr is None or ts is None:
            continue

        if prev_ts is not None:
            dt = (ts - prev_ts).total_seconds()
            if dt <= 0 or dt > 30:  # 跳过异常间隔
                prev_ts = ts
                continue

            if hr < zone_boundaries[0]:
                zone_secs[0] += dt
            elif hr < zone_boundaries[1]:
                zone_secs[1] += dt
            elif hr < zone_boundaries[2]:
                zone_secs[2] += dt
            elif hr < zone_boundaries[3]:
                zone_secs[3] += dt
            else:
                zone_secs[4] += dt

        prev_ts = ts

    total = sum(zone_secs)
    if total == 0:
        return {
            'zone1_sec': 0, 'zone2_sec': 0, 'zone3_sec': 0, 'zone4_sec': 0, 'zone5_sec': 0,
            'zone1_pct': None, 'zone2_pct': None, 'zone3_pct': None, 'zone4_pct': None, 'zone5_pct': None,
        }

    return {
        'zone1_sec': round(zone_secs[0], 1),
        'zone2_sec': round(zone_secs[1], 1),
        'zone3_sec': round(zone_secs[2], 1),
        'zone4_sec': round(zone_secs[3], 1),
        'zone5_sec': round(zone_secs[4], 1),
        'zone1_pct': round(zone_secs[0] / total * 100, 1),
        'zone2_pct': round(zone_secs[1] / total * 100, 1),
        'zone3_pct': round(zone_secs[2] / total * 100, 1),
        'zone4_pct': round(zone_secs[3] / total * 100, 1),
        'zone5_pct': round(zone_secs[4] / total * 100, 1),
    }
