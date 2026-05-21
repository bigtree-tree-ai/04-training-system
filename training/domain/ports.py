"""Ports for the agentic coach architecture."""
from __future__ import annotations

from datetime import date
from typing import Protocol

from training.domain.models import (
    ActivitySummary,
    CoachRecommendation,
    EvidenceDocument,
    ReadinessFeatures,
    SubjectiveCheckin,
    TrainingPlanItem,
)


class DataSourcePort(Protocol):
    def sync(self, days: int = 14) -> dict:
        """Pull raw data from an external source and persist it through an adapter."""


class ActivityRepository(Protocol):
    def list_recent_activities(self, limit: int = 5) -> list[ActivitySummary]:
        """Return recent normalized activity summaries."""


class HealthMetricRepository(Protocol):
    def get_checkin(self, day: date, phase: str = "morning") -> SubjectiveCheckin | None:
        """Return a subjective athlete check-in for a phase."""

    def upsert_checkin(self, checkin: SubjectiveCheckin) -> SubjectiveCheckin:
        """Persist a subjective check-in."""


class FeaturePipeline(Protocol):
    def compute_for_date(self, day: date) -> ReadinessFeatures:
        """Transform raw/canonical data into daily coaching features."""


class EvidenceRetriever(Protocol):
    def search(self, query: str, limit: int = 5) -> list[EvidenceDocument]:
        """Return curated evidence documents relevant to a coaching decision."""


class CoachAgentPort(Protocol):
    def recommend(
        self,
        features: ReadinessFeatures,
        plan_item: TrainingPlanItem | None,
        checkin: SubjectiveCheckin | None,
        evidence: list[EvidenceDocument],
    ) -> CoachRecommendation:
        """Generate a traceable training recommendation."""


class NotifierPort(Protocol):
    def notify(self, recommendation: CoachRecommendation) -> dict:
        """Deliver or queue a notification."""


class HeartbeatScheduler(Protocol):
    def run(self, phase: str = "morning", day: date | None = None) -> CoachRecommendation:
        """Run one scheduled coaching heartbeat."""

