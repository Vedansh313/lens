"""Authentication API: register / login / refresh / logout + current-user dep.

Mounted onto the main app in server.py via app.include_router(router). Keeps all
auth concerns out of server.py (which owns the CLIP+FAISS search pipeline) — the
only change there is the include_router line.

Tokens are stateless JWTs (see security.py). Because there is no server-side
token store, /auth/logout is a client-side discard: it authenticates the caller
and returns 200, but cannot revoke an already-issued token. Server-side
revocation (a denylist) is deferred.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import SessionLocal
from models import User
from security import (
    ACCESS_TOKEN,
    REFRESH_TOKEN,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# auto_error=False so a missing/invalid header yields our own 401 (with a
# WWW-Authenticate: Bearer challenge) rather than HTTPBearer's default 403.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = {
    "status_code": status.HTTP_401_UNAUTHORIZED,
    "headers": {"WWW-Authenticate": "Bearer"},
}


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def get_db() -> Session:
    """Request-scoped SQLAlchemy session, closed when the request ends."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the caller from a Bearer *access* token, or raise 401.

    Use as a route dependency to protect endpoints:
        @router.get("/thing")
        def thing(user: User = Depends(get_current_user)): ...
    """
    if creds is None:
        raise HTTPException(detail="Not authenticated", **_UNAUTHORIZED)
    try:
        payload = decode_token(creds.credentials, ACCESS_TOKEN)
    except TokenError as exc:
        raise HTTPException(detail=str(exc), **_UNAUTHORIZED) from exc

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(detail="User no longer exists", **_UNAUTHORIZED)
    return user


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    # 8-char floor; 128 ceiling keeps requests sane (bcrypt itself only reads
    # the first 72 bytes — see security.py).
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # allow returning the ORM row

    id: int
    email: EmailStr
    name: str
    is_admin: bool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def _normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> User:
    email = _normalize_email(body.email)
    user = User(email=email, password_hash=hash_password(body.password), name=body.name.strip())
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Unique-constraint violation on email — also covers the race where two
        # requests pass the pre-check and both try to insert.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    email = _normalize_email(body.email)
    user = db.scalar(select(User).where(User.email == email))
    # Verify even when the user is missing would be ideal for timing, but a
    # dummy hash adds complexity; bad email and bad password both return the
    # same 401 so the response doesn't reveal which was wrong.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(detail="Incorrect email or password.", **_UNAUTHORIZED)
    return TokenOut(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=AccessTokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)) -> AccessTokenOut:
    try:
        payload = decode_token(body.refresh_token, REFRESH_TOKEN)
    except TokenError as exc:
        raise HTTPException(detail=str(exc), **_UNAUTHORIZED) from exc

    # The account must still exist to mint a fresh access token for it.
    if db.get(User, int(payload["sub"])) is None:
        raise HTTPException(detail="User no longer exists", **_UNAUTHORIZED)
    return AccessTokenOut(access_token=create_access_token(payload["sub"]))


@router.post("/logout")
def logout(user: User = Depends(get_current_user)) -> dict:
    # Stateless: authenticate the caller and acknowledge. The client discards
    # its tokens; the server holds no session to invalidate (see module docs).
    return {"message": "Logged out. Discard your tokens."}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
