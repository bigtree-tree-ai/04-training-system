"""统一配置管理 — 所有可配置项集中在此，支持环境变量覆盖"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_ROOT = PROJECT_ROOT.parent  # 06-运动数据AI化/

# ---------- 数据库 ----------
DB_PATH = Path(os.getenv("TRAIN_DB_PATH", str(PROJECT_ROOT / "training.db")))

# ---------- FIT 文件目录 ----------
COROS_FIT_DIR = Path(os.getenv("TRAIN_FIT_DIR", str(DATA_ROOT / "高驰的运动数据导出")))
EXTRA_FIT_DIR = DATA_ROOT
CSV_PATH = DATA_ROOT / "all_sessions.csv"

# ---------- Web 服务 ----------
WEB_HOST = os.getenv("TRAIN_WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("TRAIN_WEB_PORT", "8080"))

# ---------- AI ----------
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("TRAIN_CLAUDE_MODEL", "claude-sonnet-4-20250514")

# ---------- 运动员参数 ----------
MAX_HEART_RATE = 173
RESTING_HEART_RATE = 56
HEART_RATE_RESERVE = MAX_HEART_RATE - RESTING_HEART_RATE  # 117
LACTATE_THRESHOLD_HR = int(RESTING_HEART_RATE + 0.88 * HEART_RATE_RESERVE)  # ~159

# 心率分区（Karvonen法）
HR_ZONES = {
    "Z1": {"name": "恢复", "min": 0,   "max": int(RESTING_HEART_RATE + 0.60 * HEART_RATE_RESERVE)},
    "Z2": {"name": "有氧", "min": 126,  "max": int(RESTING_HEART_RATE + 0.70 * HEART_RATE_RESERVE)},
    "Z3": {"name": "节奏", "min": 138,  "max": int(RESTING_HEART_RATE + 0.80 * HEART_RATE_RESERVE)},
    "Z4": {"name": "阈值", "min": 150,  "max": int(RESTING_HEART_RATE + 0.90 * HEART_RATE_RESERVE)},
    "Z5": {"name": "极量", "min": 161,  "max": 185},
}

# ---------- 赛事 ----------
GOBI_RACE_DATE = "2026-10-15"  # 戈21正赛（预估）

# ---------- 专业指标阈值 ----------
# ACWR安全区间
ACWR_SAFE_LOW = 0.8
ACWR_SAFE_HIGH = 1.3
ACWR_DANGER = 1.5

# Training Status 阈值
TSB_PEAKING_MIN = 10
TSB_PEAKING_MAX = 25
TSB_OVERREACHING = -30
TSB_FATIGUED = -20

# 心率漂移评级
HR_DRIFT_EXCELLENT = 3.0  # <3% 优秀
HR_DRIFT_NORMAL = 5.0     # 3-5% 正常
HR_DRIFT_POOR = 10.0      # 5-10% 有氧不足

# 80/20极化训练目标
EASY_ZONE_TARGET = 80  # Z1+Z2应占80%
