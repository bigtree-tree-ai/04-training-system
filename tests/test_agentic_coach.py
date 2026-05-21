"""Agentic coach v1 tests."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from training.storage import db


def _use_temp_db(monkeypatch, tmp_path: Path):
    test_db = tmp_path / "training.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(str(test_db))
    return test_db


def test_heartbeat_high_pain_blocks_intensity_and_requires_confirmation(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    from training.adapters.sqlite_repositories import SQLiteTrainingRepository
    from training.application.heartbeat import AgenticHeartbeatScheduler
    from training.domain.models import SubjectiveCheckin

    today = date.today()
    repo = SQLiteTrainingRepository()
    repo.upsert_checkin(
        SubjectiveCheckin(
            date=today.isoformat(),
            pain_knee=8,
            soreness_level=6,
            fatigue_level=4,
            injury_notes="膝盖刺痛，跑步落地不舒服",
        )
    )

    conn = db.get_conn()
    try:
        conn.execute(
            """
            INSERT INTO daily_load (date, daily_tss, atl, ctl, tsb, acwr, monotony, training_status)
            VALUES (?, 90, 70, 38, -32, 1.62, 2.3, 'Overreaching')
            """,
            (today.isoformat(),),
        )
        conn.execute(
            """
            INSERT INTO training_plan (planned_date, workout_type, description, target_distance_km, target_hr_zone)
            VALUES (?, 'Interval', '6x800m', 9.0, 'Z4-Z5')
            """,
            (today.isoformat(),),
        )
        conn.commit()
    finally:
        conn.close()

    rec = AgenticHeartbeatScheduler(repository=repo).run(day=today)

    assert rec.risk_level == "high"
    assert rec.needs_confirmation is True
    assert "取消高强度" in rec.recommended_action
    assert rec.evidence_refs


def test_evidence_search_returns_seeded_sources(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    from training.evidence.retriever import CuratedEvidenceRetriever

    results = CuratedEvidenceRetriever().search("load injury ACWR", limit=3)

    assert results
    assert any("Load" in item.title or "load" in item.summary for item in results)
    assert all(item.url.startswith("https://") for item in results)


def test_today_api_returns_agentic_contract(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    monkeypatch.delenv("TRAIN_AUTH_REQUIRED", raising=False)

    from training.web.app import app

    response = TestClient(app).get("/api/v1/today")

    assert response.status_code == 200
    payload = response.json()
    assert "features" in payload
    assert "recommendation" in payload
    assert "expert_votes" in payload["recommendation"]
    assert "evidence_refs" in payload["recommendation"]


def test_raw_ingest_events_are_idempotent(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    from training.storage.writers import store_raw_ingest_event

    first = store_raw_ingest_event("fit_file", {"filename": "a.fit", "hash": "abc"}, external_id="a.fit")
    second = store_raw_ingest_event("fit_file", {"filename": "a.fit", "hash": "abc"}, external_id="a.fit")

    conn = db.get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) as cnt FROM raw_ingest_events").fetchone()["cnt"]
    finally:
        conn.close()

    assert first == second
    assert count == 1
