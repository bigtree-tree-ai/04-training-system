"""Password and cookie-session auth for product users."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, Response

from training.storage.db import get_conn, init_db


SESSION_COOKIE = "training_product_session"
HASH_ALGORITHM = "pbkdf2_sha256"
HASH_ITERATIONS = 210_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ProductAuthService:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def init(self):
        init_db(self.db_path)

    def register(self, email: str, password: str, display_name: str = "") -> dict[str, Any]:
        self.init()
        email = normalize_email(email)
        _validate_email(email)
        _validate_password(password)
        role = "admin" if self._user_count() == 0 else "user"
        conn = get_conn(self.db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO product_users (email, password_hash, display_name, role)
                VALUES (?, ?, ?, ?)
                """,
                (email, hash_password(password), display_name.strip() or email.split("@")[0], role),
            )
            conn.commit()
            return self.get_user_by_id(int(cur.lastrowid)) or {}
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise HTTPException(status_code=409, detail="Email already registered") from exc
            raise
        finally:
            conn.close()

    def login(self, email: str, password: str) -> tuple[dict[str, Any], str]:
        self.init()
        conn = get_conn(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM product_users WHERE email=? AND status='active'",
                (normalize_email(email),),
            ).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                raise HTTPException(status_code=401, detail="Invalid email or password")
            token = self.create_session(int(row["id"]))
            return _user_from_row(row), token
        finally:
            conn.close()

    def create_session(self, user_id: int, days: int = 30) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = token_digest(token)
        expires_at = (
            datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days)
        ).isoformat(timespec="seconds")
        conn = get_conn(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO product_auth_sessions (user_id, token_hash, expires_at)
                VALUES (?, ?, ?)
                """,
                (user_id, token_hash, expires_at),
            )
            conn.commit()
            return token
        finally:
            conn.close()

    def get_current_user(self, request: Request) -> dict[str, Any] | None:
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            return None
        conn = get_conn(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT u.*
                FROM product_auth_sessions s
                JOIN product_users u ON u.id=s.user_id
                WHERE s.token_hash=? AND datetime(s.expires_at) > datetime('now') AND u.status='active'
                """,
                (token_digest(token),),
            ).fetchone()
            return _user_from_row(row) if row else None
        finally:
            conn.close()

    def require_user(self, request: Request) -> dict[str, Any]:
        user = self.get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Login required")
        return user

    def require_admin(self, request: Request) -> dict[str, Any]:
        user = self.require_user(request)
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")
        return user

    def logout(self, request: Request, response: Response):
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            conn = get_conn(self.db_path)
            try:
                conn.execute("DELETE FROM product_auth_sessions WHERE token_hash=?", (token_digest(token),))
                conn.commit()
            finally:
                conn.close()
        clear_session_cookie(response)

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        self.init()
        conn = get_conn(self.db_path)
        try:
            row = conn.execute("SELECT * FROM product_users WHERE id=?", (user_id,)).fetchone()
            return _user_from_row(row) if row else None
        finally:
            conn.close()

    def ensure_bootstrap_admin(self):
        email = os.getenv("TRAIN_PRODUCT_ADMIN_EMAIL", "").strip()
        password = os.getenv("TRAIN_PRODUCT_ADMIN_PASSWORD", "")
        if not email or not password or self._user_count() > 0:
            return
        user = self.register(email, password, os.getenv("TRAIN_PRODUCT_ADMIN_NAME", "Admin"))
        conn = get_conn(self.db_path)
        try:
            conn.execute("UPDATE product_users SET role='admin' WHERE id=?", (user["id"],))
            conn.commit()
        finally:
            conn.close()

    def _user_count(self) -> int:
        conn = get_conn(self.db_path)
        try:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM product_users").fetchone()
            return int(row["cnt"])
        finally:
            conn.close()


def set_session_cookie(response: Response, token: str):
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=os.getenv("TRAIN_PRODUCT_COOKIE_SECURE", "").lower() in {"1", "true", "yes", "on"},
        max_age=30 * 24 * 3600,
        path="/",
    )


def clear_session_cookie(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)
    return "$".join(
        [
            HASH_ALGORITHM,
            str(HASH_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != HASH_ALGORITHM:
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _validate_email(email: str):
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email")


def _validate_password(password: str):
    if len(password or "") < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")


def _user_from_row(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "status": row["status"],
        "onboarding_completed": bool(row["onboarding_completed"]),
        "accepted_terms_at": row["accepted_terms_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
