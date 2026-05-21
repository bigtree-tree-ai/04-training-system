"""HTTP Basic authentication for the training dashboard."""
from __future__ import annotations

import base64
import binascii
import hmac
import os

from starlette.requests import Request
from starlette.responses import Response


STATIC_PREFIXES = ("/static/",)
PUBLIC_PATHS = {"/favicon.ico"}


def require_basic_auth(request: Request) -> Response | None:
    """Return an auth failure response when the request is not authenticated."""
    if not _auth_required() or _is_public_path(request.url.path):
        return None

    username = os.getenv("TRAIN_AUTH_USER", "")
    password = os.getenv("TRAIN_AUTH_PASSWORD", "")
    if not username or not password:
        return Response(
            "Training dashboard auth is required but TRAIN_AUTH_USER/TRAIN_AUTH_PASSWORD are not configured.",
            status_code=503,
            media_type="text/plain",
        )

    supplied = _decode_basic_auth(request.headers.get("Authorization", ""))
    if supplied is None:
        return _auth_challenge()

    supplied_user, supplied_password = supplied
    if _matches(supplied_user, username) and _matches(supplied_password, password):
        return None
    return _auth_challenge()


def _auth_required() -> bool:
    return os.getenv("TRAIN_AUTH_REQUIRED", "").strip().lower() in {"1", "true", "yes", "on"}


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in STATIC_PREFIXES)


def _decode_basic_auth(header: str) -> tuple[str, str] | None:
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "basic" or not value:
        return None
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    username, sep, password = decoded.partition(":")
    if not sep:
        return None
    return username, password


def _matches(supplied: str, expected: str) -> bool:
    return hmac.compare_digest(supplied, expected)


def _auth_challenge() -> Response:
    realm = os.getenv("TRAIN_AUTH_REALM", "training-system").replace('"', "")
    return Response(
        "Authentication required.",
        status_code=401,
        headers={"WWW-Authenticate": f'Basic realm="{realm}"'},
        media_type="text/plain",
    )
