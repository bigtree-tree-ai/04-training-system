-- 运动数据AI分析系统 v2.0 — 数据库表结构

-- sessions: 每次训练汇总
CREATE TABLE IF NOT EXISTS sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    filename            TEXT NOT NULL UNIQUE,
    fit_file_hash       TEXT,
    sport               TEXT,
    sub_sport           TEXT,
    start_time          TEXT NOT NULL,
    duration_sec        REAL,
    distance_km         REAL,
    total_calories      INTEGER,
    avg_hr              INTEGER,
    max_hr              INTEGER,
    avg_speed_mps       REAL,
    avg_pace_sec        REAL,
    avg_cadence         REAL,
    max_cadence         INTEGER,
    total_ascent        INTEGER,
    total_descent       INTEGER,
    training_effect     REAL,
    anaerobic_te        REAL,
    avg_temperature     REAL,
    total_strides       INTEGER,
    -- v2.0 新增字段
    vo2max              REAL,
    training_type       TEXT,
    training_effect_label TEXT,
    recovery_hours      REAL,
    -- 计算字段（由analysis模块填充）
    hr_tss              REAL,
    pace_cv             REAL,
    hr_drift_pct        REAL,
    efficiency_factor   REAL,
    session_rpe         INTEGER,
    ai_summary          TEXT,
    ai_analyzed_at      TEXT,
    imported_at         TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_time);
CREATE INDEX IF NOT EXISTS idx_sessions_sport ON sessions(sport);

-- laps: 分圈数据
CREATE TABLE IF NOT EXISTS laps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id),
    lap_index       INTEGER NOT NULL,
    start_time      TEXT,
    duration_sec    REAL,
    distance_km     REAL,
    avg_hr          INTEGER,
    max_hr          INTEGER,
    avg_speed_mps   REAL,
    avg_pace_sec    REAL,
    avg_cadence     REAL,
    total_ascent    INTEGER,
    total_descent   INTEGER,
    total_calories  INTEGER,
    UNIQUE(session_id, lap_index)
);

-- hr_zone_splits: 每次训练的心率分区时间
CREATE TABLE IF NOT EXISTS hr_zone_splits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id) UNIQUE,
    zone1_sec       REAL DEFAULT 0,
    zone2_sec       REAL DEFAULT 0,
    zone3_sec       REAL DEFAULT 0,
    zone4_sec       REAL DEFAULT 0,
    zone5_sec       REAL DEFAULT 0,
    zone1_pct       REAL,
    zone2_pct       REAL,
    zone3_pct       REAL,
    zone4_pct       REAL,
    zone5_pct       REAL
);

-- daily_load: 每日训练负荷 + PMC
CREATE TABLE IF NOT EXISTS daily_load (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL UNIQUE,
    daily_tss           REAL DEFAULT 0,
    daily_distance_km   REAL DEFAULT 0,
    daily_duration_sec  REAL DEFAULT 0,
    session_count       INTEGER DEFAULT 0,
    atl                 REAL,
    ctl                 REAL,
    tsb                 REAL,
    monotony            REAL,
    strain              REAL,
    -- v2.0 新增字段
    acwr                REAL,
    training_status     TEXT,
    computed_at         TEXT DEFAULT (datetime('now'))
);

-- weekly_summaries: 周汇总
CREATE TABLE IF NOT EXISTS weekly_summaries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    year                INTEGER NOT NULL,
    week_number         INTEGER NOT NULL,
    week_start          TEXT NOT NULL,
    week_end            TEXT NOT NULL,
    total_sessions      INTEGER DEFAULT 0,
    run_sessions        INTEGER DEFAULT 0,
    cross_sessions      INTEGER DEFAULT 0,
    total_distance_km   REAL DEFAULT 0,
    run_distance_km     REAL DEFAULT 0,
    total_duration_sec  REAL DEFAULT 0,
    total_calories      INTEGER DEFAULT 0,
    total_hr_tss        REAL DEFAULT 0,
    avg_hr              REAL,
    max_hr_of_week      INTEGER,
    avg_easy_pace_sec   REAL,
    longest_run_km      REAL,
    distance_change_pct REAL,
    planned_distance_km REAL,
    plan_adherence_pct  REAL,
    computed_at         TEXT DEFAULT (datetime('now')),
    UNIQUE(year, week_number)
);

-- training_plan: 训练计划
CREATE TABLE IF NOT EXISTS training_plan (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_week           TEXT,
    planned_date        TEXT NOT NULL,
    workout_type        TEXT,
    description         TEXT,
    target_distance_km  REAL,
    target_duration_min REAL,
    target_pace_sec     REAL,
    target_hr_zone      TEXT,
    actual_session_id   INTEGER REFERENCES sessions(id),
    adherence_score     REAL,
    notes               TEXT,
    source              TEXT DEFAULT 'manual',
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_plan_date ON training_plan(planned_date);

-- ai_reports: AI分析报告
CREATE TABLE IF NOT EXISTS ai_reports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type         TEXT NOT NULL,
    reference_id        TEXT,
    reference_date      TEXT,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    model_used          TEXT,
    input_context       TEXT,
    ai_response         TEXT NOT NULL,
    structured_data     TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_reports_type ON ai_reports(report_type, reference_date);

-- athlete_status: 每日主观状态
CREATE TABLE IF NOT EXISTS athlete_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL UNIQUE,
    sleep_hours     REAL,
    sleep_quality   INTEGER,
    resting_hr      INTEGER,
    soreness_level  INTEGER,
    fatigue_level   INTEGER,
    mood            INTEGER,
    injury_notes    TEXT,
    body_weight_kg  REAL,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- athlete_status 默认数据（无记录时的基线值）
INSERT OR IGNORE INTO athlete_status (date, sleep_hours, sleep_quality, resting_hr, soreness_level, fatigue_level, mood)
VALUES ('default', 7.0, 3, 60, 2, 2, 3);
