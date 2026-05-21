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


def test_empty_database_pages_do_not_crash(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    monkeypatch.delenv("TRAIN_AUTH_REQUIRED", raising=False)

    from training.web.app import app

    client = TestClient(app)

    assert client.get("/").status_code == 200
    assert client.get("/dashboard").status_code == 200
    assert client.get("/api/summary").status_code == 200


def test_full_user_flow_checkin_recommendation_and_confirm(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    monkeypatch.delenv("TRAIN_AUTH_REQUIRED", raising=False)

    from training.web.app import app

    client = TestClient(app)
    today = date.today().isoformat()

    checkin_response = client.post(
        "/api/v1/checkins",
        json={
            "date": today,
            "sleep_hours": 5.8,
            "sleep_quality": 45,
            "fatigue_level": 5,
            "soreness_level": 6,
            "pain_knee": 7,
            "pain_back": 2,
            "hydration_ml": 500,
            "caffeine_mg": 120,
            "injury_notes": "膝盖刺痛，今天下楼不舒服",
            "nutrition_notes": "早上只喝咖啡",
        },
    )

    assert checkin_response.status_code == 200
    payload = checkin_response.json()
    assert payload["success"] is True
    assert payload["checkin"]["pain_knee"] == 7
    assert payload["recommendation"]["risk_level"] == "high"
    assert payload["recommendation"]["needs_confirmation"] is True

    get_checkin = client.get(f"/api/v1/checkins?date_str={today}")
    assert get_checkin.status_code == 200
    assert get_checkin.json()["checkin"]["hydration_ml"] == 500

    rec_id = payload["recommendation"]["id"]
    listed = client.get("/api/v1/coach/recommendations?limit=5")
    assert listed.status_code == 200
    assert any(item["id"] == rec_id for item in listed.json()["items"])

    confirmed = client.post(
        "/api/v1/plan/confirm",
        json={"recommendation_id": rec_id, "decision": "accept"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["decision"] == "accept"


def test_v1_api_rejects_invalid_dates_and_confirm_payloads(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    monkeypatch.delenv("TRAIN_AUTH_REQUIRED", raising=False)

    from training.web.app import app

    client = TestClient(app)

    assert client.get("/api/v1/checkins?date_str=2026-99-99").status_code == 400
    assert client.post("/api/v1/coach/recommendations", json={"date": "bad-date"}).status_code == 400
    assert client.post("/api/v1/plan/confirm", json={"recommendation_id": 1, "decision": "maybe"}).status_code == 400
    assert client.post("/api/v1/plan/confirm", json={"recommendation_id": 9999, "decision": "reject"}).status_code == 404


def test_sync_run_can_skip_coros_and_still_run_heartbeat(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    monkeypatch.delenv("TRAIN_AUTH_REQUIRED", raising=False)

    from training.web import api
    from training.web.app import app

    monkeypatch.setattr(api, "run_refresh_pipeline", lambda sync_coros, coros_days: ["mock refresh"])

    response = TestClient(app).post(
        "/api/v1/sync/run",
        json={"sync_coros": False, "coros_days": 3, "phase": "evening"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["steps"] == ["mock refresh"]
    assert payload["recommendation"]["phase"] == "evening"


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
