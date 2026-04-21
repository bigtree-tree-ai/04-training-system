"""数据写入函数"""
from training.storage.db import get_conn


def upsert_session(data: dict) -> int:
    conn = get_conn()
    try:
        cols = [
            'filename', 'fit_file_hash', 'sport', 'sub_sport', 'start_time',
            'duration_sec', 'distance_km', 'total_calories', 'avg_hr', 'max_hr',
            'avg_speed_mps', 'avg_pace_sec', 'avg_cadence', 'max_cadence',
            'total_ascent', 'total_descent', 'training_effect', 'anaerobic_te',
            'avg_temperature', 'total_strides'
        ]
        present = {k: data[k] for k in cols if k in data}
        placeholders = ', '.join(['?'] * len(present))
        col_names = ', '.join(present.keys())
        update_cols = [k for k in present.keys() if k != 'filename']
        if update_cols:
            update_clause = ', '.join(f"{k}=excluded.{k}" for k in update_cols)
            sql = f"""INSERT INTO sessions ({col_names})
                      VALUES ({placeholders})
                      ON CONFLICT(filename) DO UPDATE SET {update_clause}, updated_at=datetime('now')"""
        else:
            sql = f"""INSERT INTO sessions ({col_names})
                      VALUES ({placeholders})
                      ON CONFLICT(filename) DO UPDATE SET updated_at=datetime('now')"""
        conn.execute(sql, list(present.values()))
        conn.commit()
        row = conn.execute("SELECT id FROM sessions WHERE filename=?", (data['filename'],)).fetchone()
        return row['id']
    finally:
        conn.close()


def upsert_laps(session_id: int, laps: list[dict]):
    conn = get_conn()
    try:
        for lap in laps:
            conn.execute("""
                INSERT INTO laps (session_id, lap_index, start_time, duration_sec,
                                distance_km, avg_hr, max_hr, avg_speed_mps, avg_pace_sec,
                                avg_cadence, total_ascent, total_descent, total_calories)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, lap_index) DO UPDATE SET
                    duration_sec=excluded.duration_sec, distance_km=excluded.distance_km,
                    avg_hr=excluded.avg_hr, max_hr=excluded.max_hr,
                    avg_speed_mps=excluded.avg_speed_mps, avg_pace_sec=excluded.avg_pace_sec,
                    avg_cadence=excluded.avg_cadence, total_ascent=excluded.total_ascent,
                    total_descent=excluded.total_descent, total_calories=excluded.total_calories
            """, (
                session_id, lap['lap_index'], lap.get('start_time'),
                lap.get('duration_sec'), lap.get('distance_km'),
                lap.get('avg_hr'), lap.get('max_hr'),
                lap.get('avg_speed_mps'), lap.get('avg_pace_sec'),
                lap.get('avg_cadence'), lap.get('total_ascent'),
                lap.get('total_descent'), lap.get('total_calories'),
            ))
        conn.commit()
    finally:
        conn.close()


def upsert_hr_zones(session_id: int, zones: dict):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO hr_zone_splits (session_id, zone1_sec, zone2_sec, zone3_sec, zone4_sec, zone5_sec,
                                         zone1_pct, zone2_pct, zone3_pct, zone4_pct, zone5_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                zone1_sec=excluded.zone1_sec, zone2_sec=excluded.zone2_sec,
                zone3_sec=excluded.zone3_sec, zone4_sec=excluded.zone4_sec,
                zone5_sec=excluded.zone5_sec, zone1_pct=excluded.zone1_pct,
                zone2_pct=excluded.zone2_pct, zone3_pct=excluded.zone3_pct,
                zone4_pct=excluded.zone4_pct, zone5_pct=excluded.zone5_pct
        """, (
            session_id,
            zones.get('zone1_sec', 0), zones.get('zone2_sec', 0),
            zones.get('zone3_sec', 0), zones.get('zone4_sec', 0),
            zones.get('zone5_sec', 0), zones.get('zone1_pct'),
            zones.get('zone2_pct'), zones.get('zone3_pct'),
            zones.get('zone4_pct'), zones.get('zone5_pct'),
        ))
        conn.commit()
    finally:
        conn.close()


def update_session_metrics(session_id: int, metrics: dict):
    conn = get_conn()
    try:
        allowed = (
            'hr_tss', 'pace_cv', 'hr_drift_pct', 'efficiency_factor',
            'vo2max', 'training_type', 'training_effect_label', 'recovery_hours',
            'ai_summary', 'ai_analyzed_at',
        )
        sets = []
        vals = []
        for k in allowed:
            if k in metrics:
                sets.append(f"{k}=?")
                vals.append(metrics[k])
        if sets:
            sets.append("updated_at=datetime('now')")
            vals.append(session_id)
            conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id=?", vals)
            conn.commit()
    finally:
        conn.close()


def upsert_daily_load(data: dict):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO daily_load (date, daily_tss, daily_distance_km, daily_duration_sec,
                                   session_count, atl, ctl, tsb, monotony, strain, acwr,
                                   training_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                daily_tss=excluded.daily_tss, daily_distance_km=excluded.daily_distance_km,
                daily_duration_sec=excluded.daily_duration_sec, session_count=excluded.session_count,
                atl=excluded.atl, ctl=excluded.ctl, tsb=excluded.tsb,
                monotony=excluded.monotony, strain=excluded.strain,
                acwr=excluded.acwr, training_status=excluded.training_status,
                computed_at=datetime('now')
        """, (
            data['date'], data.get('daily_tss', 0), data.get('daily_distance_km', 0),
            data.get('daily_duration_sec', 0), data.get('session_count', 0),
            data.get('atl'), data.get('ctl'), data.get('tsb'),
            data.get('monotony'), data.get('strain'),
            data.get('acwr'), data.get('training_status'),
        ))
        conn.commit()
    finally:
        conn.close()


def upsert_weekly_summary(data: dict):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO weekly_summaries (year, week_number, week_start, week_end,
                total_sessions, run_sessions, cross_sessions, total_distance_km,
                run_distance_km, total_duration_sec, total_calories, total_hr_tss,
                avg_hr, max_hr_of_week, avg_easy_pace_sec, longest_run_km,
                distance_change_pct, planned_distance_km, plan_adherence_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(year, week_number) DO UPDATE SET
                total_sessions=excluded.total_sessions, run_sessions=excluded.run_sessions,
                cross_sessions=excluded.cross_sessions, total_distance_km=excluded.total_distance_km,
                run_distance_km=excluded.run_distance_km, total_duration_sec=excluded.total_duration_sec,
                total_calories=excluded.total_calories, total_hr_tss=excluded.total_hr_tss,
                avg_hr=excluded.avg_hr, max_hr_of_week=excluded.max_hr_of_week,
                avg_easy_pace_sec=excluded.avg_easy_pace_sec, longest_run_km=excluded.longest_run_km,
                distance_change_pct=excluded.distance_change_pct,
                planned_distance_km=excluded.planned_distance_km,
                plan_adherence_pct=excluded.plan_adherence_pct,
                computed_at=datetime('now')
        """, (
            data['year'], data['week_number'], data['week_start'], data['week_end'],
            data.get('total_sessions', 0), data.get('run_sessions', 0),
            data.get('cross_sessions', 0), data.get('total_distance_km', 0),
            data.get('run_distance_km', 0), data.get('total_duration_sec', 0),
            data.get('total_calories', 0), data.get('total_hr_tss', 0),
            data.get('avg_hr'), data.get('max_hr_of_week'),
            data.get('avg_easy_pace_sec'), data.get('longest_run_km'),
            data.get('distance_change_pct'), data.get('planned_distance_km'),
            data.get('plan_adherence_pct'),
        ))
        conn.commit()
    finally:
        conn.close()
