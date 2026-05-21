"""SQLite adapters for the agentic coach ports."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from training.domain.models import (
    ActivitySummary,
    AthleteProfile,
    CoachRecommendation,
    EvidenceDocument,
    ExpertContribution,
    ReadinessFeatures,
    SubjectiveCheckin,
    TrainingPlanItem,
)
from training.storage.db import get_conn, init_db


class SQLiteTrainingRepository:
    """Repository adapter over the existing training.db schema."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def init(self):
        init_db(self.db_path)

    def _conn(self):
        return get_conn(self.db_path)

    def load_athlete_profile(self) -> AthleteProfile:
        from training import config

        data = {}
        if config.ATHLETE_CONFIG_PATH.exists():
            data = json.loads(config.ATHLETE_CONFIG_PATH.read_text(encoding="utf-8"))

        return AthleteProfile(
            name=data.get("name", "athlete"),
            height_cm=data.get("height_cm"),
            weight_kg=data.get("weight_kg"),
            max_heart_rate=data.get("max_heart_rate"),
            resting_heart_rate=data.get("resting_heart_rate"),
            lactate_threshold_hr=data.get("lactate_threshold_hr"),
            injury_history=data.get("injury_history", ""),
            current_injury=data.get("current_injury", ""),
            target_race=data.get("target_race", ""),
            race_date=data.get("race_date", ""),
            target_pace=data.get("target_pace", ""),
        )

    def list_recent_activities(self, limit: int = 5) -> list[ActivitySummary]:
        self.init()
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT id, DATE(start_time) as date, sport, training_type, distance_km,
                       duration_sec, avg_hr, avg_pace_sec, hr_tss, recovery_hours
                FROM sessions
                ORDER BY start_time DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                ActivitySummary(
                    id=row["id"],
                    date=row["date"] or "",
                    sport=row["sport"],
                    workout_type=row["training_type"],
                    distance_km=row["distance_km"],
                    duration_sec=row["duration_sec"],
                    avg_hr=row["avg_hr"],
                    avg_pace_sec=row["avg_pace_sec"],
                    hr_tss=row["hr_tss"],
                    recovery_hours=row["recovery_hours"],
                )
                for row in rows
            ]
        finally:
            conn.close()

    def get_plan_for_date(self, day: date) -> TrainingPlanItem | None:
        self.init()
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM training_plan
                WHERE planned_date=?
                ORDER BY id DESC LIMIT 1
                """,
                (day.isoformat(),),
            ).fetchone()
            if not row:
                return None
            return TrainingPlanItem(
                id=row["id"],
                planned_date=row["planned_date"],
                workout_type=row["workout_type"] or "",
                description=row["description"] or "",
                target_distance_km=row["target_distance_km"],
                target_duration_min=row["target_duration_min"],
                target_pace_sec=row["target_pace_sec"],
                target_hr_zone=row["target_hr_zone"],
                notes=row["notes"],
                source=row["source"],
            )
        finally:
            conn.close()

    def get_checkin(self, day: date, phase: str = "morning") -> SubjectiveCheckin | None:
        self.init()
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM athlete_checkins
                WHERE date=? AND phase=?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (day.isoformat(), phase),
            ).fetchone()
            if row:
                return _checkin_from_row(row)

            fallback = conn.execute(
                "SELECT * FROM athlete_status WHERE date=?",
                (day.isoformat(),),
            ).fetchone()
            if fallback:
                return SubjectiveCheckin(
                    date=day.isoformat(),
                    phase=phase,
                    sleep_hours=fallback["sleep_hours"],
                    sleep_quality=fallback["sleep_quality"],
                    soreness_level=fallback["soreness_level"],
                    fatigue_level=fallback["fatigue_level"],
                    mood=fallback["mood"],
                    injury_notes=fallback["injury_notes"] or "",
                    body_weight_kg=fallback["body_weight_kg"],
                )
            return None
        finally:
            conn.close()

    def upsert_checkin(self, checkin: SubjectiveCheckin) -> SubjectiveCheckin:
        self.init()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO athlete_checkins (
                    date, phase, sleep_hours, sleep_quality, soreness_level,
                    fatigue_level, mood, injury_notes, body_weight_kg, pain_knee,
                    pain_back, hydration_ml, caffeine_mg, nutrition_notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, phase) DO UPDATE SET
                    sleep_hours=excluded.sleep_hours,
                    sleep_quality=excluded.sleep_quality,
                    soreness_level=excluded.soreness_level,
                    fatigue_level=excluded.fatigue_level,
                    mood=excluded.mood,
                    injury_notes=excluded.injury_notes,
                    body_weight_kg=excluded.body_weight_kg,
                    pain_knee=excluded.pain_knee,
                    pain_back=excluded.pain_back,
                    hydration_ml=excluded.hydration_ml,
                    caffeine_mg=excluded.caffeine_mg,
                    nutrition_notes=excluded.nutrition_notes,
                    updated_at=datetime('now')
                """,
                (
                    checkin.date,
                    checkin.phase,
                    checkin.sleep_hours,
                    checkin.sleep_quality,
                    checkin.soreness_level,
                    checkin.fatigue_level,
                    checkin.mood,
                    checkin.injury_notes,
                    checkin.body_weight_kg,
                    checkin.pain_knee,
                    checkin.pain_back,
                    checkin.hydration_ml,
                    checkin.caffeine_mg,
                    checkin.nutrition_notes,
                ),
            )
            conn.execute(
                """
                INSERT INTO athlete_status (
                    date, sleep_hours, sleep_quality, soreness_level,
                    fatigue_level, mood, injury_notes, body_weight_kg
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    sleep_hours=COALESCE(excluded.sleep_hours, athlete_status.sleep_hours),
                    sleep_quality=COALESCE(excluded.sleep_quality, athlete_status.sleep_quality),
                    soreness_level=COALESCE(excluded.soreness_level, athlete_status.soreness_level),
                    fatigue_level=COALESCE(excluded.fatigue_level, athlete_status.fatigue_level),
                    mood=COALESCE(excluded.mood, athlete_status.mood),
                    injury_notes=COALESCE(excluded.injury_notes, athlete_status.injury_notes),
                    body_weight_kg=COALESCE(excluded.body_weight_kg, athlete_status.body_weight_kg)
                """,
                (
                    checkin.date,
                    checkin.sleep_hours,
                    checkin.sleep_quality,
                    checkin.soreness_level,
                    checkin.fatigue_level,
                    checkin.mood,
                    checkin.injury_notes,
                    checkin.body_weight_kg,
                ),
            )
            conn.commit()
            return checkin
        finally:
            conn.close()

    def get_latest_load(self, day: date) -> dict:
        self.init()
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM daily_load
                WHERE date <= ?
                ORDER BY date DESC LIMIT 1
                """,
                (day.isoformat(),),
            ).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def get_recent_loads(self, day: date, limit: int = 28) -> list[dict]:
        self.init()
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM daily_load
                WHERE date <= ?
                ORDER BY date DESC LIMIT ?
                """,
                (day.isoformat(), limit),
            ).fetchall()
            return [dict(row) for row in reversed(rows)]
        finally:
            conn.close()

    def get_coros_daily_context(self, day: date) -> dict[str, Any]:
        self.init()
        conn = self._conn()
        try:
            date_str = day.isoformat()
            return {
                "daily_health": _one(conn, "SELECT * FROM coros_daily_health WHERE date=?", (date_str,)),
                "sleep": _one(conn, "SELECT * FROM coros_sleep WHERE date=?", (date_str,)),
                "hrv": _one(conn, "SELECT * FROM coros_hrv WHERE date=?", (date_str,)),
                "heart_rate": _one(conn, "SELECT * FROM coros_heart_rate_daily WHERE date=?", (date_str,)),
                "stress": _one(conn, "SELECT * FROM coros_stress_daily WHERE date=?", (date_str,)),
                "recovery": _one(
                    conn,
                    "SELECT * FROM coros_recovery_snapshots ORDER BY captured_at DESC, id DESC LIMIT 1",
                ),
            }
        finally:
            conn.close()

    def count_consecutive_running_days(self) -> int:
        from training.planning.recovery import count_consecutive_days

        conn = self._conn()
        try:
            return count_consecutive_days(conn)
        finally:
            conn.close()

    def save_canonical_daily_metrics(self, day: date, metrics: dict[str, Any]):
        self.init()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO canonical_daily_metrics (
                    date, sleep_hours, sleep_score, hrv_ms, resting_hr, avg_hr,
                    stress_avg, steps, calories_kcal, exercise_min, body_weight_kg,
                    soreness_level, fatigue_level, mood, pain_knee, pain_back,
                    injury_notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    sleep_hours=excluded.sleep_hours,
                    sleep_score=excluded.sleep_score,
                    hrv_ms=excluded.hrv_ms,
                    resting_hr=excluded.resting_hr,
                    avg_hr=excluded.avg_hr,
                    stress_avg=excluded.stress_avg,
                    steps=excluded.steps,
                    calories_kcal=excluded.calories_kcal,
                    exercise_min=excluded.exercise_min,
                    body_weight_kg=excluded.body_weight_kg,
                    soreness_level=excluded.soreness_level,
                    fatigue_level=excluded.fatigue_level,
                    mood=excluded.mood,
                    pain_knee=excluded.pain_knee,
                    pain_back=excluded.pain_back,
                    injury_notes=excluded.injury_notes,
                    updated_at=datetime('now')
                """,
                (
                    day.isoformat(),
                    metrics.get("sleep_hours"),
                    metrics.get("sleep_score"),
                    metrics.get("hrv_ms"),
                    metrics.get("resting_hr"),
                    metrics.get("avg_hr"),
                    metrics.get("stress_avg"),
                    metrics.get("steps"),
                    metrics.get("calories_kcal"),
                    metrics.get("exercise_min"),
                    metrics.get("body_weight_kg"),
                    metrics.get("soreness_level"),
                    metrics.get("fatigue_level"),
                    metrics.get("mood"),
                    metrics.get("pain_knee"),
                    metrics.get("pain_back"),
                    metrics.get("injury_notes"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_daily_features(self, features: ReadinessFeatures):
        self.init()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO daily_features (
                    date, input_version_hash, readiness_score, recovery_score,
                    sleep_score, load_risk, injury_risk, pain_risk,
                    training_status, factors_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    input_version_hash=excluded.input_version_hash,
                    readiness_score=excluded.readiness_score,
                    recovery_score=excluded.recovery_score,
                    sleep_score=excluded.sleep_score,
                    load_risk=excluded.load_risk,
                    injury_risk=excluded.injury_risk,
                    pain_risk=excluded.pain_risk,
                    training_status=excluded.training_status,
                    factors_json=excluded.factors_json,
                    computed_at=datetime('now')
                """,
                (
                    features.date,
                    features.input_version_hash,
                    features.readiness_score,
                    features.recovery_score,
                    features.sleep_score,
                    features.load_risk,
                    features.injury_risk,
                    features.pain_risk,
                    features.training_status,
                    json.dumps(features.factors, ensure_ascii=False, sort_keys=True),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_latest_recommendation(self, day: date, phase: str = "morning") -> CoachRecommendation | None:
        self.init()
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM coach_recommendations
                WHERE recommendation_date=? AND phase=?
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (day.isoformat(), phase),
            ).fetchone()
            return _recommendation_from_row(row) if row else None
        finally:
            conn.close()

    def list_recommendations(self, limit: int = 20) -> list[dict]:
        self.init()
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM coach_recommendations
                ORDER BY recommendation_date DESC, created_at DESC, id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [_recommendation_row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def save_recommendation(self, rec: CoachRecommendation) -> int:
        self.init()
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO coach_recommendations (
                    recommendation_date, phase, risk_level, title, summary,
                    recommended_action, workout_type, needs_confirmation,
                    input_evidence_json, evidence_refs_json, expert_votes_json,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.recommendation_date,
                    rec.phase,
                    rec.risk_level,
                    rec.title,
                    rec.summary,
                    rec.recommended_action,
                    rec.workout_type,
                    1 if rec.needs_confirmation else 0,
                    json.dumps(rec.input_evidence, ensure_ascii=False),
                    json.dumps([_evidence_to_dict(e) for e in rec.evidence_refs], ensure_ascii=False),
                    json.dumps([_expert_to_dict(v) for v in rec.expert_votes], ensure_ascii=False),
                    rec.status,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def start_heartbeat_run(self, phase: str, day: date) -> int:
        self.init()
        conn = self._conn()
        try:
            cur = conn.execute(
                "INSERT INTO heartbeat_runs (phase, run_date, status) VALUES (?, ?, 'running')",
                (phase, day.isoformat()),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def finish_heartbeat_run(
        self,
        run_id: int,
        status: str,
        input_version_hash: str | None = None,
        recommendation_id: int | None = None,
        message: str = "",
    ):
        conn = self._conn()
        try:
            conn.execute(
                """
                UPDATE heartbeat_runs
                SET status=?, input_version_hash=?, recommendation_id=?,
                    message=?, finished_at=datetime('now')
                WHERE id=?
                """,
                (status, input_version_hash, recommendation_id, message, run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def confirm_recommendation(self, recommendation_id: int, decision: str) -> bool:
        self.init()
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                UPDATE coach_recommendations
                SET user_decision=?, status=?, decided_at=datetime('now')
                WHERE id=?
                """,
                (decision, "accepted" if decision == "accept" else "rejected", recommendation_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def seed_evidence_documents(self, documents: list[EvidenceDocument]):
        self.init()
        conn = self._conn()
        try:
            for doc in documents:
                conn.execute(
                    """
                    INSERT INTO evidence_documents (
                        source_type, title, url, year, domain, summary, tags, evidence_level
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(title) DO UPDATE SET
                        source_type=excluded.source_type,
                        url=excluded.url,
                        year=excluded.year,
                        domain=excluded.domain,
                        summary=excluded.summary,
                        tags=excluded.tags,
                        evidence_level=excluded.evidence_level,
                        updated_at=datetime('now')
                    """,
                    (
                        doc.source_type,
                        doc.title,
                        doc.url,
                        doc.year,
                        doc.domain,
                        doc.summary,
                        ",".join(doc.tags),
                        doc.evidence_level,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def search_evidence(self, query: str, limit: int = 5) -> list[EvidenceDocument]:
        self.init()
        terms = [term.lower() for term in query.replace("/", " ").split() if term.strip()]
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM evidence_documents ORDER BY year DESC, id"
            ).fetchall()
            scored = []
            for row in rows:
                haystack = " ".join(
                    str(row[key] or "")
                    for key in ("title", "domain", "summary", "tags", "source_type")
                ).lower()
                score = sum(1 for term in terms if term in haystack)
                if score > 0 or not terms:
                    scored.append((score, row))
            scored.sort(key=lambda item: (-item[0], -(item[1]["year"] or 0), item[1]["id"]))
            return [_evidence_from_row(row) for _, row in scored[:limit]]
        finally:
            conn.close()


def stable_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _one(conn, sql: str, params: tuple = ()) -> dict:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else {}


def _checkin_from_row(row) -> SubjectiveCheckin:
    return SubjectiveCheckin(
        date=row["date"],
        phase=row["phase"],
        sleep_hours=row["sleep_hours"],
        sleep_quality=row["sleep_quality"],
        soreness_level=row["soreness_level"],
        fatigue_level=row["fatigue_level"],
        mood=row["mood"],
        injury_notes=row["injury_notes"] or "",
        body_weight_kg=row["body_weight_kg"],
        pain_knee=row["pain_knee"],
        pain_back=row["pain_back"],
        hydration_ml=row["hydration_ml"],
        caffeine_mg=row["caffeine_mg"],
        nutrition_notes=row["nutrition_notes"] or "",
    )


def _evidence_from_row(row) -> EvidenceDocument:
    return EvidenceDocument(
        id=row["id"],
        title=row["title"],
        source_type=row["source_type"],
        url=row["url"],
        year=row["year"],
        domain=row["domain"],
        summary=row["summary"],
        tags=tuple(tag for tag in (row["tags"] or "").split(",") if tag),
        evidence_level=row["evidence_level"],
    )


def _evidence_to_dict(doc: EvidenceDocument) -> dict:
    return {
        "id": doc.id,
        "title": doc.title,
        "source_type": doc.source_type,
        "url": doc.url,
        "year": doc.year,
        "domain": doc.domain,
        "summary": doc.summary,
        "tags": list(doc.tags),
        "evidence_level": doc.evidence_level,
    }


def _expert_to_dict(vote: ExpertContribution) -> dict:
    return {
        "expert": vote.expert,
        "stance": vote.stance,
        "rationale": vote.rationale,
        "confidence": vote.confidence,
    }


def _recommendation_from_row(row) -> CoachRecommendation:
    return CoachRecommendation(
        id=row["id"],
        recommendation_date=row["recommendation_date"],
        phase=row["phase"],
        risk_level=row["risk_level"],
        title=row["title"],
        summary=row["summary"],
        recommended_action=row["recommended_action"],
        workout_type=row["workout_type"],
        needs_confirmation=bool(row["needs_confirmation"]),
        input_evidence=json.loads(row["input_evidence_json"] or "[]"),
        evidence_refs=[
            EvidenceDocument(
                id=item.get("id"),
                title=item.get("title", ""),
                source_type=item.get("source_type", ""),
                url=item.get("url", ""),
                year=item.get("year"),
                domain=item.get("domain", ""),
                summary=item.get("summary", ""),
                tags=tuple(item.get("tags") or ()),
                evidence_level=item.get("evidence_level", ""),
            )
            for item in json.loads(row["evidence_refs_json"] or "[]")
        ],
        expert_votes=[
            ExpertContribution(
                expert=item.get("expert", ""),
                stance=item.get("stance", ""),
                rationale=item.get("rationale", ""),
                confidence=item.get("confidence", 0.0),
            )
            for item in json.loads(row["expert_votes_json"] or "[]")
        ],
        status=row["status"],
    )


def _recommendation_row_to_dict(row) -> dict:
    data = dict(row)
    data["needs_confirmation"] = bool(data.get("needs_confirmation"))
    data["input_evidence"] = json.loads(data.pop("input_evidence_json") or "[]")
    data["evidence_refs"] = json.loads(data.pop("evidence_refs_json") or "[]")
    data["expert_votes"] = json.loads(data.pop("expert_votes_json") or "[]")
    return data
