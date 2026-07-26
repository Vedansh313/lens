"""Password hashing (bcrypt) and JWT creation/verification.

Deliberately free of FastAPI and database imports so it can be unit-tested in
isolation and reused from anywhere. Routes (auth.py) translate the TokenError
raised here into HTTP 401s; this module never speaks HTTP.

Config comes from backend/.env:
    JWT_SECRET                    required — no insecure default (see .env.example)
    ACCESS_TOKEN_EXPIRE_MINUTES   default 15  (short-lived access token)
    REFRESH_TOKEN_EXPIRE_DAYS     default 7   (longer-lived refresh token)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
from dotenv import load_dotenv

# db.py also loads this, but security.py may be imported on its own (tests);
# load_dotenv defaults to override=False so it never clobbers a real env var.
load_dotenv(Path(__file__).resolve().parent / ".env")

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
# bcrypt hashes at most 72 bytes and (as of 5.x) raises on longer input instead
# of truncating. We truncate identically on hash and verify so the two always
# agree; splitting a multibyte char at the boundary is harmless because bcrypt
# hashes raw bytes, never decoded text.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """Return a bcrypt hash ($2b$, cost 12) of the password."""
    pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """True if password matches the stored bcrypt hash. Never raises."""
    pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(pw, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed / non-bcrypt hash in the column — treat as a failed login.
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not set. Add it to backend/.env (see .env.example); "
        "generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

ACCESS_TOKEN = "access"
REFRESH_TOKEN = "refresh"


class TokenError(Exception):
    """A JWT was missing, malformed, expired, or of the wrong type."""


def _create_token(subject: int | str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),   # JWT 'sub' must be a string
        "type": token_type,    # guards against using a refresh token as access
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(subject: int | str) -> str:
    return _create_token(subject, ACCESS_TOKEN, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(subject: int | str) -> str:
    return _create_token(subject, REFRESH_TOKEN, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str, expected_type: str) -> dict:
    """Verify signature + expiry, require the token's `type`, return the payload.

    Raises TokenError on any failure, including an access token presented where a
    refresh token is required (or vice versa).
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(f"invalid token: {exc}") from exc
    if payload.get("type") != expected_type:
        raise TokenError(
            f"expected a {expected_type} token, got {payload.get('type')!r}"
        )
    return payload
