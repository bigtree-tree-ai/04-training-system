"""数据库连接管理"""
import sqlite3
from pathlib import Path

from training.config import DB_PATH


# SQL predicate matching running sessions: legacy 'running' + COROS 'Outdoor/Indoor Run'.
# Excludes Hiking/Walking/Cycling/Strength Training (no 'Run' in name). SQLite LIKE is
# case-insensitive for ASCII, but 'running' has no capital 'Run', so it needs the OR.
# Use inside WHERE / CASE WHEN via f-string:   WHERE {RUN_SPORT_PREDICATE}
# For table-aliased queries use the inlined  (s.sport='running' OR s.sport LIKE '%Run%').
RUN_SPORT_PREDICATE = "(sport='running' OR sport LIKE '%Run%')"


def get_conn(db_path: str = None) -> sqlite3.Connection:
    path = db_path or str(DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str = None):
    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    conn = get_conn(db_path)
    conn.executescript(schema_sql)
    conn.commit()
    _migrate(conn)
    conn.close()


def _migrate(conn: sqlite3.Connection):
    """自动添加v2.0新增字段（幂等）"""
    migrations = [
        ("sessions", "vo2max", "REAL"),
        ("sessions", "training_type", "TEXT"),
        ("sessions", "training_effect_label", "TEXT"),
        ("sessions", "recovery_hours", "REAL"),
        ("sessions", "owner_user_id", "INTEGER"),
        ("daily_load", "acwr", "REAL"),
        ("daily_load", "training_status", "TEXT"),
        ("raw_ingest_events", "owner_user_id", "INTEGER"),
        ("athlete_checkins", "owner_user_id", "INTEGER"),
        ("canonical_daily_metrics", "owner_user_id", "INTEGER"),
        ("daily_features", "owner_user_id", "INTEGER"),
        ("coach_recommendations", "owner_user_id", "INTEGER"),
        ("heartbeat_runs", "owner_user_id", "INTEGER"),
        # science v2 增量字段（feature/science-viz-stage-a）
        ("athlete_checkins", "session_rpe", "INTEGER"),
        ("athlete_checkins", "session_id", "INTEGER"),
        ("sessions", "rpe", "INTEGER"),
        ("sessions", "has_track_points", "INTEGER DEFAULT 0"),
        ("sessions", "has_gait", "INTEGER DEFAULT 0"),
    ]
    for table, col, dtype in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError:
            pass
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_sessions_owner_start ON sessions(owner_user_id, start_time)",
        "CREATE INDEX IF NOT EXISTS idx_raw_ingest_owner_time ON raw_ingest_events(owner_user_id, captured_at)",
        "CREATE INDEX IF NOT EXISTS idx_athlete_checkins_owner_date ON athlete_checkins(owner_user_id, date, phase)",
        "CREATE INDEX IF NOT EXISTS idx_coach_recommendations_owner_date ON coach_recommendations(owner_user_id, recommendation_date, phase, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_heartbeat_runs_owner_date ON heartbeat_runs(owner_user_id, run_date, phase, started_at)",
    ]
    for sql in indexes:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass
    conn.commit()
