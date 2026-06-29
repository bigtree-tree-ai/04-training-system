"""从现有all_sessions.csv冷启动导入数据到SQLite"""
import csv
import sys
from pathlib import Path

from training import config
from training.storage.db import init_db, get_conn


def parse_pace_to_sec(pace_str: str) -> float | None:
    """将 '5:27' 格式配速转为秒数 327"""
    if not pace_str or pace_str == '':
        return None
    try:
        parts = pace_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


def import_csv(csv_path: str = None):
    if csv_path is None:
        csv_path = str(config.CSV_PATH)

    init_db()
    conn = get_conn()

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        count = 0
        skipped = 0
        for row in reader:
            # 过滤异常数据（速度异常值65.535是COROS哨兵值）
            avg_speed = float(row['avg_speed_mps']) if row.get('avg_speed_mps') else None
            if avg_speed and avg_speed > 20:  # >20 m/s = >72 km/h，不可能的跑步速度
                avg_speed = None

            pace_sec = parse_pace_to_sec(row.get('avg_pace'))
            # 过滤异常配速（<2min/km 或 >30min/km）
            if pace_sec and (pace_sec < 120 or pace_sec > 1800):
                pace_sec = None

            distance = float(row['total_distance_km']) if row.get('total_distance_km') else None

            conn.execute("""
                INSERT INTO sessions (filename, sport, sub_sport, start_time,
                    duration_sec, distance_km, total_calories, avg_hr, max_hr,
                    avg_speed_mps, avg_pace_sec, avg_cadence, max_cadence,
                    total_ascent, total_descent, training_effect, anaerobic_te,
                    avg_temperature, total_strides)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(filename) DO UPDATE SET updated_at=datetime('now')
            """, (
                row['filename'],
                row.get('sport') or None,
                row.get('sub_sport') or None,
                row['start_time'],
                float(row['total_timer_time_sec']) if row.get('total_timer_time_sec') else None,
                distance,
                int(row['total_calories']) if row.get('total_calories') else None,
                int(row['avg_heart_rate']) if row.get('avg_heart_rate') else None,
                int(row['max_heart_rate']) if row.get('max_heart_rate') else None,
                avg_speed,
                pace_sec,
                float(row['avg_cadence']) if row.get('avg_cadence') else None,
                int(row['max_cadence']) if row.get('max_cadence') else None,
                int(row['total_ascent']) if row.get('total_ascent') else None,
                int(row['total_descent']) if row.get('total_descent') else None,
                float(row['total_training_effect']) if row.get('total_training_effect') else None,
                float(row['total_anaerobic_training_effect']) if row.get('total_anaerobic_training_effect') else None,
                float(row['avg_temperature']) if row.get('avg_temperature') else None,
                int(row['total_strides']) if row.get('total_strides') else None,
            ))
            count += 1

    conn.commit()

    # 验证
    total = conn.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()['cnt']
    running = conn.execute("SELECT COUNT(*) as cnt FROM sessions WHERE (sport='running' OR sport LIKE '%Run%')").fetchone()['cnt']
    conn.close()

    print(f"CSV导入完成: {count}条记录已导入")
    print(f"数据库总计: {total}条session")
    print(f"  跑步: {running}条")
    print(f"  其他: {total - running}条")
    return count


if __name__ == "__main__":
    import_csv()
