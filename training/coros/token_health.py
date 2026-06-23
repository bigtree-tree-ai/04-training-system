"""COROS MCP OAuth token health check — non-raising.

Centralises token validity + refresh so callers (coros-sync, the daily cron)
can detect a broken OAuth chain WITHOUT crashing silently.

Background: the daily `coros-sync` cron failed invisibly for 11+ days because
`CorosMcpClient.__init__` raised on a dead refresh_token, and nothing surfaced
that the body-data dimension (sleep/stress/heart-rate) had stopped flowing.
This module returns a structured status instead of raising, so the sync run
can be closed as ``token_expired`` and the breakage becomes visible.
"""
from __future__ import annotations

import time

from training.coros.oauth import _read_auth, _write_auth, refresh_token


def token_status() -> dict:
    """Return token health without raising.

    Keys: ``state`` (ok|expired|refresh_failed|missing),
    ``expires_in_days``, ``access_token``, ``message``.
    """
    data = _read_auth()
    if not data or not data.get("access_token"):
        return {
            "state": "missing",
            "expires_in_days": None,
            "access_token": None,
            "message": "无 COROS 授权(.coros_auth.json 缺失),需运行 coros-login",
        }

    now = time.time()
    exp = float(data.get("expires_at") or 0)
    days_left = (exp - now) / 86400

    if exp - now > 120:
        return {
            "state": "ok",
            "expires_in_days": round(days_left, 2),
            "access_token": data["access_token"],
            "message": "access_token 有效",
        }

    # Expired or within 2 minutes of expiry → try to refresh.
    if not (data.get("refresh_token") and data.get("client_id")):
        return {
            "state": "expired",
            "expires_in_days": round(days_left, 2),
            "access_token": None,
            "message": "token 过期且无 refresh_token,需重新 coros-login",
        }

    try:
        new = refresh_token(data["client_id"], data["refresh_token"])
    except Exception as exc:  # noqa: BLE001 — surfaced into sync_run, not raised
        return {
            "state": "refresh_failed",
            "expires_in_days": round(days_left, 2),
            "access_token": None,
            "message": f"refresh 失败({exc}),refresh_token 可能已过期,需重新 coros-login",
        }

    if "access_token" not in new:
        return {
            "state": "refresh_failed",
            "expires_in_days": round(days_left, 2),
            "access_token": None,
            "message": f"refresh 返回异常: {new}",
        }

    data.update(new)
    data["expires_at"] = now + int(new.get("expires_in", 3600))
    _write_auth(data)
    return {
        "state": "ok",
        "expires_in_days": round((data["expires_at"] - now) / 86400, 2),
        "access_token": data["access_token"],
        "message": "refresh 成功",
    }


def get_valid_token() -> tuple[str | None, dict]:
    """Return ``(token, status)``. ``token`` is None when unusable."""
    status = token_status()
    return status["access_token"], status
