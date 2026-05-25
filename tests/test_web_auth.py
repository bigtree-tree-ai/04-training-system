"""Web authentication tests."""
from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from training.web.app import app


def _client() -> TestClient:
    return TestClient(app)


def _auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _clear_auth_env(monkeypatch):
    for name in (
        "TRAIN_AUTH_REQUIRED",
        "TRAIN_AUTH_USER",
        "TRAIN_AUTH_PASSWORD",
        "TRAIN_AUTH_REALM",
    ):
        monkeypatch.delenv(name, raising=False)


def test_auth_disabled_by_default_allows_api_access(monkeypatch):
    _clear_auth_env(monkeypatch)

    response = _client().get("/api/summary")

    assert response.status_code == 200


def test_static_assets_bypass_required_auth(monkeypatch):
    monkeypatch.setenv("TRAIN_AUTH_REQUIRED", "1")
    monkeypatch.delenv("TRAIN_AUTH_USER", raising=False)
    monkeypatch.delenv("TRAIN_AUTH_PASSWORD", raising=False)

    response = _client().get("/static/style.css")

    assert response.status_code == 200


def test_product_routes_bypass_basic_auth_and_use_product_auth(monkeypatch):
    monkeypatch.setenv("TRAIN_AUTH_REQUIRED", "1")
    monkeypatch.delenv("TRAIN_AUTH_USER", raising=False)
    monkeypatch.delenv("TRAIN_AUTH_PASSWORD", raising=False)

    product_page = _client().get("/product")
    product_api = _client().get("/api/product/me")

    assert product_page.status_code == 200
    assert product_api.status_code == 401


def test_private_routes_fail_closed_when_auth_is_unconfigured(monkeypatch):
    monkeypatch.setenv("TRAIN_AUTH_REQUIRED", "1")
    monkeypatch.delenv("TRAIN_AUTH_USER", raising=False)
    monkeypatch.delenv("TRAIN_AUTH_PASSWORD", raising=False)

    response = _client().get("/api/summary")

    assert response.status_code == 503
    assert "TRAIN_AUTH_USER" in response.text


def test_private_routes_challenge_missing_or_bad_credentials(monkeypatch):
    monkeypatch.setenv("TRAIN_AUTH_REQUIRED", "1")
    monkeypatch.setenv("TRAIN_AUTH_USER", "runner")
    monkeypatch.setenv("TRAIN_AUTH_PASSWORD", "correct-password")

    missing = _client().get("/api/summary")
    wrong = _client().get("/api/summary", headers=_auth_header("runner", "wrong"))

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == 'Basic realm="training-system"'
    assert wrong.status_code == 401


def test_private_routes_accept_basic_credentials(monkeypatch):
    monkeypatch.setenv("TRAIN_AUTH_REQUIRED", "1")
    monkeypatch.setenv("TRAIN_AUTH_USER", "runner")
    monkeypatch.setenv("TRAIN_AUTH_PASSWORD", "correct-password")

    response = _client().get("/api/summary", headers=_auth_header("runner", "correct-password"))

    assert response.status_code == 200


def test_default_pipeline_key_is_not_an_auth_bypass(monkeypatch):
    monkeypatch.setenv("TRAIN_AUTH_REQUIRED", "1")
    monkeypatch.setenv("TRAIN_AUTH_USER", "runner")
    monkeypatch.setenv("TRAIN_AUTH_PASSWORD", "correct-password")

    response = _client().post("/api/pipeline?key=training-v3-key")

    assert response.status_code == 401
