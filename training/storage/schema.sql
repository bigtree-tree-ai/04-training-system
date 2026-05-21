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

-- coros_sync_runs: COROS MCP每日同步运行记录
CREATE TABLE IF NOT EXISTS coros_sync_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at          TEXT DEFAULT (datetime('now')),
    finished_at         TEXT,
    status              TEXT NOT NULL DEFAULT 'running',
    days                INTEGER,
    message             TEXT,
    tool_results        TEXT
);

-- coros_profile: COROS用户基础信息（单行快照）
CREATE TABLE IF NOT EXISTS coros_profile (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    nickname            TEXT,
    height_cm           REAL,
    weight_kg           REAL,
    birthday            TEXT,
    age                 INTEGER,
    gender              TEXT,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- coros_devices: COROS绑定设备
CREATE TABLE IF NOT EXISTS coros_devices (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bluetooth_id        TEXT UNIQUE,
    name                TEXT,
    model_name          TEXT,
    serial_number       TEXT,
    warranty_expires    TEXT,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- coros_recovery_snapshots: 恢复状态快照
CREATE TABLE IF NOT EXISTS coros_recovery_snapshots (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at                     TEXT NOT NULL DEFAULT (datetime('now')),
    recovery_pct                    INTEGER,
    level                           TEXT,
    estimated_full_recovery_hours   REAL,
    raw_text                        TEXT
);
CREATE INDEX IF NOT EXISTS idx_coros_recovery_captured ON coros_recovery_snapshots(captured_at);

-- coros_fitness_snapshots: 跑力评估快照
CREATE TABLE IF NOT EXISTS coros_fitness_snapshots (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at                 TEXT NOT NULL DEFAULT (datetime('now')),
    vo2max                      REAL,
    running_level               REAL,
    threshold_pace_sec          INTEGER,
    five_k_prediction_sec       INTEGER,
    ten_k_prediction_sec        INTEGER,
    half_marathon_prediction_sec INTEGER,
    marathon_prediction_sec     INTEGER,
    raw_text                    TEXT
);
CREATE INDEX IF NOT EXISTS idx_coros_fitness_captured ON coros_fitness_snapshots(captured_at);

-- coros_training_load: COROS训练负荷评估
CREATE TABLE IF NOT EXISTS coros_training_load (
    date                TEXT PRIMARY KEY,
    comment             TEXT,
    short_term_load     REAL,
    long_term_load      REAL,
    load_ratio          REAL,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- coros_daily_health: 日常非运动健康汇总
CREATE TABLE IF NOT EXISTS coros_daily_health (
    date                TEXT PRIMARY KEY,
    steps               INTEGER,
    calories_kcal       INTEGER,
    exercise_min        INTEGER,
    stress_avg          INTEGER,
    sleep_score         INTEGER,
    sleep_total_min     INTEGER,
    sleep_awake_min     INTEGER,
    sleep_deep_min      INTEGER,
    sleep_light_min     INTEGER,
    sleep_rem_min       INTEGER,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- coros_sleep: 睡眠明细
CREATE TABLE IF NOT EXISTS coros_sleep (
    date                TEXT PRIMARY KEY,
    sleep_score         INTEGER,
    main_sleep_min      INTEGER,
    deep_sleep_pct      INTEGER,
    light_sleep_pct     INTEGER,
    rem_pct             INTEGER,
    awake_pct           INTEGER,
    awake_min           INTEGER,
    awake_count         INTEGER,
    sleep_window        TEXT,
    naps_total_min      INTEGER,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- coros_hrv: HRV评估
CREATE TABLE IF NOT EXISTS coros_hrv (
    date                TEXT PRIMARY KEY,
    hrv_avg_ms          INTEGER,
    evaluation          TEXT,
    normal_low_ms       INTEGER,
    normal_high_ms      INTEGER,
    baseline_ms         INTEGER,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- coros_heart_rate_daily: 每日心率
CREATE TABLE IF NOT EXISTS coros_heart_rate_daily (
    date                TEXT PRIMARY KEY,
    avg_hr              INTEGER,
    min_hr              INTEGER,
    max_hr              INTEGER,
    resting_hr          INTEGER,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- coros_stress_daily: 每日压力
CREATE TABLE IF NOT EXISTS coros_stress_daily (
    date                TEXT PRIMARY KEY,
    stress_avg          INTEGER,
    level               TEXT,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- coros_training_schedule: COROS训练计划
CREATE TABLE IF NOT EXISTS coros_training_schedule (
    date                TEXT PRIMARY KEY,
    title               TEXT,
    distance_km         REAL,
    estimated_time_min  REAL,
    load_tl             REAL,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- coros_sport_records: COROS运动记录列表（MCP接口可用时写入）
CREATE TABLE IF NOT EXISTS coros_sport_records (
    label_id            TEXT PRIMARY KEY,
    date                TEXT,
    sport_type          INTEGER,
    title               TEXT,
    distance_km         REAL,
    duration_min        REAL,
    avg_pace_sec        INTEGER,
    avg_speed           REAL,
    location            TEXT,
    raw_text            TEXT,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- raw_ingest_events: raw layer for device/app payload lineage
CREATE TABLE IF NOT EXISTS raw_ingest_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT NOT NULL,
    external_id         TEXT,
    occurred_at         TEXT,
    captured_at         TEXT DEFAULT (datetime('now')),
    payload_hash        TEXT,
    payload_json        TEXT NOT NULL,
    status              TEXT DEFAULT 'stored',
    UNIQUE(source, payload_hash)
);
CREATE INDEX IF NOT EXISTS idx_raw_ingest_source_time ON raw_ingest_events(source, captured_at);

-- athlete_checkins: subjective state and future nutrition/hydration inputs
CREATE TABLE IF NOT EXISTS athlete_checkins (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL,
    phase               TEXT NOT NULL DEFAULT 'morning',
    sleep_hours         REAL,
    sleep_quality       INTEGER,
    soreness_level      INTEGER,
    fatigue_level       INTEGER,
    mood                INTEGER,
    injury_notes        TEXT,
    body_weight_kg      REAL,
    pain_knee           INTEGER,
    pain_back           INTEGER,
    hydration_ml        INTEGER,
    caffeine_mg         INTEGER,
    nutrition_notes     TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now')),
    UNIQUE(date, phase)
);
CREATE INDEX IF NOT EXISTS idx_athlete_checkins_date ON athlete_checkins(date, phase);

-- canonical_daily_metrics: canonical layer across COROS/FIT/subjective/HealthKit later
CREATE TABLE IF NOT EXISTS canonical_daily_metrics (
    date                TEXT PRIMARY KEY,
    sleep_hours         REAL,
    sleep_score         INTEGER,
    hrv_ms              INTEGER,
    resting_hr          INTEGER,
    avg_hr              INTEGER,
    stress_avg          INTEGER,
    steps               INTEGER,
    calories_kcal       INTEGER,
    exercise_min        INTEGER,
    body_weight_kg      REAL,
    soreness_level      INTEGER,
    fatigue_level       INTEGER,
    mood                INTEGER,
    pain_knee           INTEGER,
    pain_back           INTEGER,
    injury_notes        TEXT,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- daily_features: feature layer consumed by the coach agents
CREATE TABLE IF NOT EXISTS daily_features (
    date                TEXT PRIMARY KEY,
    input_version_hash  TEXT NOT NULL,
    readiness_score     INTEGER NOT NULL,
    recovery_score      INTEGER NOT NULL,
    sleep_score         INTEGER,
    load_risk           TEXT NOT NULL,
    injury_risk         TEXT NOT NULL,
    pain_risk           TEXT NOT NULL,
    training_status     TEXT,
    factors_json        TEXT,
    computed_at         TEXT DEFAULT (datetime('now'))
);

-- evidence_documents: curated RAG-lite seed corpus
CREATE TABLE IF NOT EXISTS evidence_documents (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type         TEXT NOT NULL,
    title               TEXT NOT NULL UNIQUE,
    url                 TEXT NOT NULL,
    year                INTEGER,
    domain              TEXT NOT NULL,
    summary             TEXT NOT NULL,
    tags                TEXT,
    evidence_level      TEXT DEFAULT 'consensus',
    updated_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_evidence_domain ON evidence_documents(domain);

-- coach_recommendations: agent outputs with traceable inputs and evidence
CREATE TABLE IF NOT EXISTS coach_recommendations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_date TEXT NOT NULL,
    phase               TEXT NOT NULL,
    risk_level          TEXT NOT NULL,
    title               TEXT NOT NULL,
    summary             TEXT NOT NULL,
    recommended_action  TEXT NOT NULL,
    workout_type        TEXT,
    needs_confirmation  INTEGER NOT NULL DEFAULT 0,
    input_evidence_json TEXT,
    evidence_refs_json  TEXT,
    expert_votes_json   TEXT,
    status              TEXT DEFAULT 'proposed',
    user_decision       TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    decided_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_coach_recommendations_date ON coach_recommendations(recommendation_date, phase, created_at);

-- heartbeat_runs: autonomous coach heartbeat audit log
CREATE TABLE IF NOT EXISTS heartbeat_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    phase               TEXT NOT NULL,
    run_date            TEXT NOT NULL,
    started_at          TEXT DEFAULT (datetime('now')),
    finished_at         TEXT,
    status              TEXT NOT NULL DEFAULT 'running',
    input_version_hash  TEXT,
    recommendation_id   INTEGER REFERENCES coach_recommendations(id),
    message             TEXT
);
CREATE INDEX IF NOT EXISTS idx_heartbeat_runs_date ON heartbeat_runs(run_date, phase, started_at);
