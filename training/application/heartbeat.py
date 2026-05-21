"""Autonomous heartbeat orchestration for the coach team."""
from __future__ import annotations

from datetime import date

from training.adapters.sqlite_repositories import SQLiteTrainingRepository
from training.application.coach import AgenticCoachTeam
from training.application.features import DailyFeaturePipeline
from training.evidence.retriever import CuratedEvidenceRetriever


class AgenticHeartbeatScheduler:
    def __init__(
        self,
        repository: SQLiteTrainingRepository | None = None,
        feature_pipeline: DailyFeaturePipeline | None = None,
        coach=None,
        evidence_retriever: CuratedEvidenceRetriever | None = None,
    ):
        self.repository = repository or SQLiteTrainingRepository()
        self.feature_pipeline = feature_pipeline or DailyFeaturePipeline(self.repository)
        self.coach = coach or AgenticCoachTeam()
        self.evidence_retriever = evidence_retriever or CuratedEvidenceRetriever(self.repository)

    def run(self, phase: str = "morning", day: date | None = None):
        day = day or date.today()
        run_id = self.repository.start_heartbeat_run(phase=phase, day=day)
        recommendation_id = None
        try:
            features = self.feature_pipeline.compute_for_date(day)
            plan = self.repository.get_plan_for_date(day)
            checkin = self.repository.get_checkin(day, phase="morning")
            evidence = self.evidence_retriever.search(_evidence_query(features), limit=5)
            recommendation = self.coach.recommend(
                features=features,
                plan_item=plan,
                checkin=checkin,
                evidence=evidence,
                phase=phase,
            )
            recommendation_id = self.repository.save_recommendation(recommendation)
            self.repository.finish_heartbeat_run(
                run_id=run_id,
                status="success",
                input_version_hash=features.input_version_hash,
                recommendation_id=recommendation_id,
                message=recommendation.title,
            )
            return self.repository.get_latest_recommendation(day, phase) or recommendation
        except Exception as exc:
            self.repository.finish_heartbeat_run(
                run_id=run_id,
                status="failed",
                recommendation_id=recommendation_id,
                message=str(exc),
            )
            raise


def _evidence_query(features) -> str:
    parts = ["load injury recovery"]
    if features.pain_risk in {"moderate", "high"} or features.injury_risk in {"moderate", "high"}:
        parts.append("pain rehabilitation overuse")
    if features.load_risk in {"moderate", "high"}:
        parts.append("ACWR fatigue training load")
    if features.sleep_score is not None and features.sleep_score < 65:
        parts.append("sleep recovery")
    parts.append("ultramarathon nutrition resistance")
    return " ".join(parts)

