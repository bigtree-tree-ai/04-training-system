"""Productized multi-user flow tests."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from training import config
from training.storage import db


def _use_temp_product_env(monkeypatch, tmp_path: Path):
    test_db = tmp_path / "training.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(config, "USER_UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1024 * 1024)
    monkeypatch.setattr("training.product.accounts.HASH_ITERATIONS", 1)
    monkeypatch.delenv("TRAIN_AUTH_REQUIRED", raising=False)
    db.init_db(str(test_db))
    return test_db


def _client() -> TestClient:
    from training.web.app import app

    return TestClient(app)


def _register(client: TestClient, email: str, password: str = "password123") -> dict:
    response = client.post(
        "/api/product/auth/register",
        json={"email": email, "password": password, "display_name": email.split("@")[0]},
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _onboard(client: TestClient):
    response = client.post(
        "/api/product/onboarding",
        json={
            "goal_type": "马拉松能力",
            "target_race": "戈21",
            "race_date": "2026-10-15",
            "running_level": "小白",
            "weekly_availability": "每周 4 天",
            "current_injury": "无明显疼痛",
            "accepted_terms": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _mock_fit_parser(monkeypatch):
    def fake_parse(_path: str):
        return {
            "session": {
                "filename": "sample.fit",
                "fit_file_hash": "abc123",
                "sport": "running",
                "start_time": "2026-05-20T08:00:00",
                "duration_sec": 3600,
                "distance_km": 8.2,
                "avg_hr": 145,
                "max_hr": 164,
                "avg_speed_mps": 2.278,
                "avg_pace_sec": 439.0,
                "total_ascent": 60,
                "total_descent": 55,
            },
            "laps": [
                {"lap_index": 0, "duration_sec": 1800, "distance_km": 4.1, "avg_hr": 140, "avg_pace_sec": 440},
                {"lap_index": 1, "duration_sec": 1800, "distance_km": 4.1, "avg_hr": 150, "avg_pace_sec": 438},
            ],
            "hr_zones": {
                "zone1_sec": 900,
                "zone2_sec": 1800,
                "zone3_sec": 700,
                "zone4_sec": 200,
                "zone5_sec": 0,
                "zone1_pct": 25.0,
                "zone2_pct": 50.0,
                "zone3_pct": 19.4,
                "zone4_pct": 5.6,
                "zone5_pct": 0.0,
            },
        }

    monkeypatch.setattr("training.product.uploads.parse_fit_file", fake_parse)


def test_product_register_login_duplicate_and_onboarding(monkeypatch, tmp_path):
    _use_temp_product_env(monkeypatch, tmp_path)
    client = _client()

    user = _register(client, "runner@example.com")
    assert user["role"] == "admin"
    assert user["onboarding_completed"] is False

    duplicate = client.post(
        "/api/product/auth/register",
        json={"email": "runner@example.com", "password": "password123"},
    )
    assert duplicate.status_code == 409

    rejected = client.post("/api/product/onboarding", json={"accepted_terms": False})
    assert rejected.status_code == 400

    payload = _onboard(client)
    assert payload["user"]["onboarding_completed"] is True
    assert payload["profile"]["goal_type"] == "马拉松能力"
    today = client.get("/api/product/today/simple").json()
    assert not any("当前伤痛" in reason for reason in today["risk_reasons"])

    me = client.get("/api/product/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "runner@example.com"


def test_fit_upload_first_report_and_user_data_isolation(monkeypatch, tmp_path):
    _use_temp_product_env(monkeypatch, tmp_path)
    _mock_fit_parser(monkeypatch)

    user_a = _client()
    _register(user_a, "a@example.com")
    _onboard(user_a)

    bad_ext = user_a.post(
        "/api/product/fit/upload",
        content=b"not-fit",
        headers={"X-Filename": "bad.txt", "Content-Type": "application/octet-stream"},
    )
    assert bad_ext.status_code == 400

    uploaded = user_a.post(
        "/api/product/fit/upload",
        content=b"fake-fit-bytes",
        headers={"X-Filename": quote("有氧跑步.fit"), "Content-Type": "application/octet-stream"},
    )
    assert uploaded.status_code == 200, uploaded.text
    upload_payload = uploaded.json()
    assert upload_payload["first_report"]["title"].startswith("首份")
    assert upload_payload["upload"]["filename"].endswith(".fit")
    assert "%" not in upload_payload["upload"]["filename"]
    assert upload_payload["first_report"]["metrics"]["distance_km"] == 8.2
    assert not upload_payload["first_report"]["risk_flags"]

    today_a = user_a.get("/api/product/today/simple")
    assert today_a.status_code == 200
    assert today_a.json()["has_fit"] is True
    assert today_a.json()["recent_sessions"][0]["distance_km"] == 8.2

    user_b = _client()
    _register(user_b, "b@example.com")
    _onboard(user_b)
    today_b = user_b.get("/api/product/today/simple")
    assert today_b.status_code == 200
    assert today_b.json()["has_fit"] is False
    assert today_b.json()["recent_sessions"] == []


def test_privacy_export_delete_admin_and_notifications(monkeypatch, tmp_path):
    _use_temp_product_env(monkeypatch, tmp_path)
    _mock_fit_parser(monkeypatch)

    admin = _client()
    _register(admin, "admin@example.com")
    _onboard(admin)
    upload = admin.post(
        "/api/product/fit/upload",
        content=b"fake-fit-bytes",
        headers={"X-Filename": "run.fit", "Content-Type": "application/octet-stream"},
    )
    assert upload.status_code == 200

    subscription = admin.post(
        "/api/product/notifications/subscribe",
        json={"endpoint": "local-notification:test", "keys": {"p256dh": "p", "auth": "a"}},
    )
    assert subscription.status_code == 200
    notification = admin.post("/api/product/notifications/test")
    assert notification.status_code == 200
    assert notification.json()["notification"]["status"] == "queued"

    export = admin.get("/api/product/privacy/export")
    assert export.status_code == 200
    data = export.json()["data"]
    assert data["user"]["email"] == "admin@example.com"
    assert len(data["sessions"]) == 1
    assert data["notification_subscriptions"][0]["endpoint"] == "local-notification:test"

    users = admin.get("/api/product/admin/users")
    assert users.status_code == 200
    assert users.json()["items"][0]["email"] == "admin@example.com"

    normal = _client()
    _register(normal, "normal@example.com")
    _onboard(normal)
    denied = normal.get("/api/product/admin/users")
    assert denied.status_code == 403

    missing_confirmation = normal.request("DELETE", "/api/product/privacy/account", json={})
    assert missing_confirmation.status_code == 400
    deleted = normal.request(
        "DELETE",
        "/api/product/privacy/account",
        json={"confirmation": "DELETE_MY_DATA"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"]["product_users"] == 1
    assert normal.get("/api/product/me").status_code == 401
