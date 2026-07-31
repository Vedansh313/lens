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
from ratelimit import (
    check_login_email,
    clear_login_email,
    limit_login_ip,
    limit_register_ip,
)
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

# Shown wherever a disabled account is turned away (Phase 4, step 8). 401 and
# not 403, so the frontend's existing "session ended" handling takes over and
# clears the tokens instead of leaving a dead session on screen.
_DISABLED_DETAIL = "This account has been disabled. Contact support."


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
    # Checked on every request, not just at login: tokens are stateless and
    # cannot be revoked, so this is what makes disabling an account take effect
    # immediately rather than whenever the access token happens to expire.
    if not user.is_active:
        raise HTTPException(detail=_DISABLED_DETAIL, **_UNAUTHORIZED)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Resolve the caller and require users.is_admin, or raise 403 (Phase 4).

    403, not 401: the caller proved who they are, they simply are not allowed.
    Returning 401 here would tell the frontend to try refreshing its token,
    which would loop without ever fixing anything.

    Attach to a whole router so nothing behind it can be left ungated by
    accident:
        APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required for this action.",
        )
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


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_register_ip)],
)
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


@router.post("/login", response_model=TokenOut, dependencies=[Depends(limit_login_ip)])
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    email = _normalize_email(body.email)
    # Second limiter, keyed by the account rather than the caller: a botnet
    # guessing one password from many addresses stays under every per-IP limit.
    # Checked before the password is verified, so being over the limit costs an
    # attacker a bcrypt comparison they never get.
    check_login_email(email)

    user = db.scalar(select(User).where(User.email == email))
    # Verify even when the user is missing would be ideal for timing, but a
    # dummy hash adds complexity; bad email and bad password both return the
    # same 401 so the response doesn't reveal which was wrong.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(detail="Incorrect email or password.", **_UNAUTHORIZED)
    # Only after the password checks out: saying "disabled" to anyone who types
    # the address would confirm the account exists to someone who cannot log in.
    if not user.is_active:
        raise HTTPException(detail=_DISABLED_DETAIL, **_UNAUTHORIZED)
    # Correct credentials: forget the failures so an honest user who mistyped a
    # few times does not carry a lockout around for the rest of the window.
    clear_login_email(email)
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
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(detail="User no longer exists", **_UNAUTHORIZED)
    # A refresh token outlives an access token, so without this a disabled
    # account could keep minting working access tokens until the refresh
    # expires. bcd6880 made the frontend end the session on a rejected refresh,
    # so this logs them out rather than looping.
    if not user.is_active:
        raise HTTPException(detail=_DISABLED_DETAIL, **_UNAUTHORIZED)
    return AccessTokenOut(access_token=create_access_token(payload["sub"]))


@router.post("/logout")
def logout(user: User = Depends(get_current_user)) -> dict:
    # Stateless: authenticate the caller and acknowledge. The client discards
    # its tokens; the server holds no session to invalidate (see module docs).
    return {"message": "Logged out. Discard your tokens."}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
