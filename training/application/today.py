"""Application service for the PWA Today surface."""
from __future__ import annotations

from datetime import date

from training.adapters.sqlite_repositories import SQLiteTrainingRepository
from training.application.features import DailyFeaturePipeline
from training.application.heartbeat import AgenticHeartbeatScheduler
from training.application.serializers import to_plain
from training.evidence.retriever import CuratedEvidenceRetriever


class TodayService:
    def __init__(self, repository: SQLiteTrainingRepository | None = None):
        self.repository = repository or SQLiteTrainingRepository()
        self.features = DailyFeaturePipeline(self.repository)
        self.heartbeat = AgenticHeartbeatScheduler(repository=self.repository, feature_pipeline=self.features)
        self.evidence = CuratedEvidenceRetriever(self.repository)

    def get_today(self, day: date | None = None, phase: str = "morning", refresh: bool = False) -> dict:
        day = day or date.today()
        self.evidence.ensure_seeded()
        features = self.features.compute_for_date(day)
        recommendation = self.repository.get_latest_recommendation(day, phase)
        if refresh or recommendation is None:
            recommendation = self.heartbeat.run(phase=phase, day=day)
        return {
            "date": day.isoformat(),
            "phase": phase,
            "athlete": to_plain(self.repository.load_athlete_profile()),
            "features": to_plain(features),
            "plan": to_plain(self.repository.get_plan_for_date(day)),
            "checkin": to_plain(self.repository.get_checkin(day, phase="morning")),
            "recommendation": to_plain(recommendation),
            "recent_activities": to_plain(self.repository.list_recent_activities(limit=5)),
        }


def build_today_service() -> TodayService:
    return TodayService()
