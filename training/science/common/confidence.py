"""数据置信度评分 — 给每条建议附 0-1 可信度

输入：信号字典（每个键的存在与新鲜度），输出综合置信度 + 缺口清单。
用于 UI 顶栏色点（绿>0.8 / 黄 0.5-0.8 / 红<0.5）和 LLM 输入元数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class DataConfidence:
    score: float                    # 0.0-1.0
    level: str                      # high / medium / low
    missing: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)


# 各信号源的权重（总和 1.0）
WEIGHTS = {
    "training_load": 0.20,   # daily_load
    "checkin_today": 0.15,    # 当日 morning checkin
    "hrv": 0.15,              # coros_hrv 或 canonical
    "rhr": 0.10,              # resting_heart_rate
    "sleep": 0.10,            # coros_sleep / checkin
    "session_recent": 0.15,   # 最近 7 天有 sessions
    "athlete_profile": 0.10,  # athlete_config 完整
    "injuries_known": 0.05,   # 伤病已结构化
}


def _stale(latest: Optional[str], max_days: int) -> bool:
    if not latest:
        return True
    try:
        d = date.fromisoformat(latest[:10])
    except ValueError:
        try:
            d = datetime.fromisoformat(latest).date()
        except ValueError:
            return True
    return (date.today() - d).days > max_days


def score_confidence(
    *,
    has_today_load: bool = False,
    has_today_checkin: bool = False,
    hrv_latest_date: Optional[str] = None,
    rhr_latest_date: Optional[str] = None,
    sleep_latest_date: Optional[str] = None,
    last_session_date: Optional[str] = None,
    profile_complete: bool = True,
    injuries_structured: bool = False,
) -> DataConfidence:
    score = 0.0
    missing: list[str] = []
    stale: list[str] = []

    if has_today_load:
        score += WEIGHTS["training_load"]
    else:
        missing.append("training_load")

    if has_today_checkin:
        score += WEIGHTS["checkin_today"]
    else:
        missing.append("morning_checkin")

    if hrv_latest_date and not _stale(hrv_latest_date, 3):
        score += WEIGHTS["hrv"]
    else:
        (stale if hrv_latest_date else missing).append("hrv")

    if rhr_latest_date and not _stale(rhr_latest_date, 3):
        score += WEIGHTS["rhr"]
    else:
        (stale if rhr_latest_date else missing).append("rhr")

    if sleep_latest_date and not _stale(sleep_latest_date, 2):
        score += WEIGHTS["sleep"]
    else:
        (stale if sleep_latest_date else missing).append("sleep")

    if last_session_date and not _stale(last_session_date, 7):
        score += WEIGHTS["session_recent"]
    else:
        (stale if last_session_date else missing).append("session")

    if profile_complete:
        score += WEIGHTS["athlete_profile"]
    else:
        missing.append("athlete_profile")

    if injuries_structured:
        score += WEIGHTS["injuries_known"]
    else:
        missing.append("injuries_structured")

    score = round(min(score, 1.0), 3)
    level = "high" if score >= 0.8 else "medium" if score >= 0.5 else "low"
    return DataConfidence(score=score, level=level, missing=missing, stale=stale)
