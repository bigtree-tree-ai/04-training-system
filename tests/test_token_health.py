"""Tests for COROS OAuth token health check (non-raising)."""
from __future__ import annotations

import json
import time

import training.coros.oauth as oauth
from training.coros import token_health as th
from training.coros.token_health import get_valid_token, token_status


def _write_auth(monkeypatch, tmp_path, data):
    af = tmp_path / "auth.json"
    af.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(oauth, "AUTH_FILE", af)


def test_missing_auth_file(monkeypatch, tmp_path):
    monkeypatch.setattr(oauth, "AUTH_FILE", tmp_path / "nope.json")
    st = token_status()
    assert st["state"] == "missing"
    assert st["access_token"] is None
    assert "coros-login" in st["message"]


def test_ok_when_token_valid(monkeypatch, tmp_path):
    _write_auth(
        monkeypatch,
        tmp_path,
        {
            "access_token": "AT",
            "refresh_token": "RT",
            "client_id": "CID",
            "expires_at": time.time() + 7200,
        },
    )
    st = token_status()
    assert st["state"] == "ok"
    assert st["access_token"] == "AT"


def test_refresh_failed_returns_status_not_raise(monkeypatch, tmp_path):
    _write_auth(
        monkeypatch,
        tmp_path,
        {
            "access_token": "AT",
            "refresh_token": "RT",
            "client_id": "CID",
            "expires_at": time.time() - 10,
        },
    )

    def boom(cid, rt):
        raise RuntimeError("HTTP Error 400: invalid_grant")

    monkeypatch.setattr(th, "refresh_token", boom)
    st = token_status()
    assert st["state"] == "refresh_failed"
    assert st["access_token"] is None
    # Must NOT raise — the whole point is visibility without crashing.
    assert "coros-login" in st["message"]


def test_refresh_success_updates_auth_file(monkeypatch, tmp_path):
    _write_auth(
        monkeypatch,
        tmp_path,
        {
            "access_token": "old",
            "refresh_token": "RT",
            "client_id": "CID",
            "expires_at": time.time() - 10,
        },
    )
    monkeypatch.setattr(
        th,
        "refresh_token",
        lambda cid, rt: {"access_token": "new", "refresh_token": "RT2", "expires_in": 3600},
    )
    st = token_status()
    assert st["state"] == "ok"
    assert st["access_token"] == "new"
    data = json.loads(oauth.AUTH_FILE.read_text(encoding="utf-8"))
    assert data["access_token"] == "new"
    assert data["refresh_token"] == "RT2"


def test_get_valid_token_none_on_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(oauth, "AUTH_FILE", tmp_path / "nope.json")
    tok, st = get_valid_token()
    assert tok is None
    assert st["state"] == "missing"
