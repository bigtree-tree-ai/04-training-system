"""数据库连接管理"""
import sqlite3
from pathlib import Path

from training.config import DB_PATH


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
        ("daily_load", "acwr", "REAL"),
        ("daily_load", "training_status", "TEXT"),
    ]
    for table, col, dtype in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
