"""Daily feature pipeline for the agentic coach."""
from __future__ import annotations

from datetime import date
from typing import Any

from training.adapters.sqlite_repositories import SQLiteTrainingRepository, stable_hash
from training.domain.models import ReadinessFeatures
from training.planning.recovery import assess_recovery_status


class DailyFeaturePipeline:
    """Build canonical daily metrics and coach-ready features.

    This is intentionally deterministic and idempotent. Re-running it for a day
    rewrites the canonical/feature rows from the latest source tables.
    """

    def __init__(self, repository: SQLiteTrainingRepository | None = None):
        self.repository = repository or SQLiteTrainingRepository()

    def compute_for_date(self, day: date) -> ReadinessFeatures:
        checkin = self.repository.get_checkin(day)
        load = self.repository.get_latest_load(day)
        coros = self.repository.get_coros_daily_context(day)
        consecutive_days = self.repository.count_consecutive_running_days()

        canonical = _canonical_metrics(checkin, coros)
        self.repository.save_canonical_daily_metrics(day, canonical)

        recovery_score = _recovery_score(load, coros, consecutive_days)
        sleep_score = _sleep_score(canonical)
        pain_risk, pain_score = _pain_risk(checkin)
        load_risk = _load_risk(load)
        injury_risk = _injury_risk(load_risk, pain_risk, checkin)

        readiness_score = _readiness_score(
            recovery_score=recovery_score,
            sleep_score=sleep_score,
            load_risk=load_risk,
            pain_score=pain_score,
            fatigue_level=checkin.fatigue_level if checkin else None,
        )

        factors: dict[str, Any] = {
            "canonical": canonical,
            "latest_load": {
                "date": load.get("date"),
                "ctl": load.get("ctl"),
                "atl": load.get("atl"),
                "tsb": load.get("tsb"),
                "acwr": load.get("acwr"),
                "monotony": load.get("monotony"),
                "training_status": load.get("training_status"),
            },
            "consecutive_running_days": consecutive_days,
            "pain_score": pain_score,
            "recovery_source": "coros" if coros.get("recovery", {}).get("recovery_pct") is not None else "pmc",
        }
        version = stable_hash(factors)
        features = ReadinessFeatures(
            date=day.isoformat(),
            input_version_hash=version,
            readiness_score=readiness_score,
            recovery_score=recovery_score,
            sleep_score=sleep_score,
            load_risk=load_risk,
            injury_risk=injury_risk,
            pain_risk=pain_risk,
            training_status=load.get("training_status"),
            factors=factors,
        )
        self.repository.save_daily_features(features)
        return features


def _canonical_metrics(checkin, coros: dict[str, Any]) -> dict[str, Any]:
    daily = coros.get("daily_health", {})
    sleep = coros.get("sleep", {})
    hrv = coros.get("hrv", {})
    heart = coros.get("heart_rate", {})
    stress = coros.get("stress", {})

    sleep_hours = None
    if sleep.get("main_sleep_min") is not None:
        sleep_hours = round(sleep["main_sleep_min"] / 60, 2)
    elif daily.get("sleep_total_min") is not None:
        sleep_hours = round(daily["sleep_total_min"] / 60, 2)
    elif checkin and checkin.sleep_hours is not None:
        sleep_hours = checkin.sleep_hours

    return {
        "sleep_hours": sleep_hours,
        "sleep_score": sleep.get("sleep_score") or daily.get("sleep_score") or _quality_to_score(checkin.sleep_quality if checkin else None),
        "hrv_ms": hrv.get("hrv_avg_ms"),
        "resting_hr": heart.get("resting_hr"),
        "avg_hr": heart.get("avg_hr"),
        "stress_avg": stress.get("stress_avg") or daily.get("stress_avg"),
        "steps": daily.get("steps"),
        "calories_kcal": daily.get("calories_kcal"),
        "exercise_min": daily.get("exercise_min"),
        "body_weight_kg": checkin.body_weight_kg if checkin else None,
        "soreness_level": checkin.soreness_level if checkin else None,
        "fatigue_level": checkin.fatigue_level if checkin else None,
        "mood": checkin.mood if checkin else None,
        "pain_knee": checkin.pain_knee if checkin else None,
        "pain_back": checkin.pain_back if checkin else None,
        "injury_notes": checkin.injury_notes if checkin else "",
    }


def _quality_to_score(value: int | None) -> int | None:
    if value is None:
        return None
    if value > 5:
        return min(max(int(value), 0), 100)
    return int(min(max(value, 1), 5) / 5 * 100)


def _recovery_score(load: dict, coros: dict[str, Any], consecutive_days: int) -> int:
    coros_recovery = coros.get("recovery", {}).get("recovery_pct")
    if coros_recovery is not None:
        return int(min(max(coros_recovery, 0), 100))
    status = assess_recovery_status(
        tsb=load.get("tsb"),
        consecutive_days=consecutive_days,
        weekly_tss=0,
        monotony=load.get("monotony"),
    )
    return int(status["score"])


def _sleep_score(canonical: dict[str, Any]) -> int | None:
    score = canonical.get("sleep_score")
    if score is not None:
        return int(min(max(score, 0), 100))
    hours = canonical.get("sleep_hours")
    if hours is None:
        return None
    if hours >= 8:
        return 90
    if hours >= 7:
        return 78
    if hours >= 6:
        return 62
    return 40


def _pain_risk(checkin) -> tuple[str, int]:
    if not checkin:
        return "unknown", 0
    pain_score = max(
        checkin.pain_knee or 0,
        checkin.pain_back or 0,
        checkin.soreness_level or 0,
    )
    notes = (checkin.injury_notes or "").lower()
    red_flags = ("刺痛", "跛", "肿", "无法", "sharp", "swelling", "limp", "numb")
    if pain_score >= 7 or any(flag in notes for flag in red_flags):
        return "high", pain_score
    if pain_score >= 4:
        return "moderate", pain_score
    if pain_score > 0:
        return "low", pain_score
    return "none", 0


def _load_risk(load: dict[str, Any]) -> str:
    acwr = load.get("acwr")
    tsb = load.get("tsb")
    monotony = load.get("monotony")
    if (acwr is not None and acwr >= 1.5) or (tsb is not None and tsb <= -30):
        return "high"
    if monotony is not None and monotony >= 2.0 and tsb is not None and tsb <= -20:
        return "high"
    if (acwr is not None and acwr > 1.3) or (tsb is not None and tsb < -20):
        return "moderate"
    if acwr is not None and acwr < 0.8:
        return "detraining"
    return "low"


def _injury_risk(load_risk: str, pain_risk: str, checkin) -> str:
    if pain_risk == "high":
        return "high"
    if load_risk == "high" and pain_risk in {"moderate", "low"}:
        return "high"
    if load_risk == "high":
        return "moderate"
    if pain_risk == "moderate":
        return "moderate"
    fatigue = checkin.fatigue_level if checkin else None
    if fatigue is not None and fatigue >= 4 and load_risk in {"moderate", "low"}:
        return "moderate"
    return "low"


def _readiness_score(
    recovery_score: int,
    sleep_score: int | None,
    load_risk: str,
    pain_score: int,
    fatigue_level: int | None,
) -> int:
    score = recovery_score
    if sleep_score is not None:
        score = round(score * 0.65 + sleep_score * 0.35)
    if load_risk == "high":
        score -= 22
    elif load_risk == "moderate":
        score -= 10
    elif load_risk == "detraining":
        score -= 4
    score -= pain_score * 4
    if fatigue_level is not None:
        score -= max(fatigue_level - 2, 0) * 6
    return int(min(max(score, 0), 100))
