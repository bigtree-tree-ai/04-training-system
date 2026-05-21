"""Pure domain objects for the AI training coach.

These dataclasses deliberately avoid database, web, and LLM SDK dependencies so
the coaching rules can be tested without the surrounding adapters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class AthleteProfile:
    name: str
    height_cm: float | None = None
    weight_kg: float | None = None
    max_heart_rate: int | None = None
    resting_heart_rate: int | None = None
    lactate_threshold_hr: int | None = None
    injury_history: str = ""
    current_injury: str = ""
    target_race: str = ""
    race_date: str = ""
    target_pace: str = ""


@dataclass(frozen=True)
class TrainingPlanItem:
    id: int | None
    planned_date: str
    workout_type: str
    description: str = ""
    target_distance_km: float | None = None
    target_duration_min: float | None = None
    target_pace_sec: float | None = None
    target_hr_zone: str | None = None
    notes: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class ActivitySummary:
    id: int | None
    date: str
    sport: str | None
    workout_type: str | None = None
    distance_km: float | None = None
    duration_sec: float | None = None
    avg_hr: int | None = None
    avg_pace_sec: float | None = None
    hr_tss: float | None = None
    recovery_hours: float | None = None


@dataclass(frozen=True)
class SubjectiveCheckin:
    date: str
    phase: str = "morning"
    sleep_hours: float | None = None
    sleep_quality: int | None = None
    soreness_level: int | None = None
    fatigue_level: int | None = None
    mood: int | None = None
    injury_notes: str = ""
    body_weight_kg: float | None = None
    pain_knee: int | None = None
    pain_back: int | None = None
    hydration_ml: int | None = None
    caffeine_mg: int | None = None
    nutrition_notes: str = ""


@dataclass(frozen=True)
class ReadinessFeatures:
    date: str
    input_version_hash: str
    readiness_score: int
    recovery_score: int
    sleep_score: int | None
    load_risk: str
    injury_risk: str
    pain_risk: str
    training_status: str | None = None
    factors: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceDocument:
    id: int | None
    title: str
    source_type: str
    url: str
    year: int | None
    domain: str
    summary: str
    tags: tuple[str, ...] = ()
    evidence_level: str = "consensus"


@dataclass(frozen=True)
class ExpertContribution:
    expert: str
    stance: str
    rationale: str
    confidence: float = 0.75


@dataclass(frozen=True)
class CoachRecommendation:
    id: int | None
    recommendation_date: str
    phase: str
    risk_level: str
    title: str
    summary: str
    recommended_action: str
    workout_type: str | None
    needs_confirmation: bool
    input_evidence: list[str]
    evidence_refs: list[EvidenceDocument]
    expert_votes: list[ExpertContribution]
    status: str = "proposed"
    created_at: datetime | None = None


@dataclass(frozen=True)
class HeartbeatRun:
    id: int | None
    phase: str
    run_date: date
    status: str
    input_version_hash: str | None = None
    recommendation_id: int | None = None
    message: str = ""

