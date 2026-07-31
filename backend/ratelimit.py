"""In-process rate limiting for the auth endpoints (Phase 5, step 1).

No dependency and no Redis: the deploy target is a single VPS running a single
uvicorn process, and a sliding window of timestamps in a dict is enough for
endpoints that should see a handful of requests per minute.

TWO LIMITATIONS THAT MUST BE UNDERSTOOD BEFORE DEPLOYING
--------------------------------------------------------
1. State is per-process. `uvicorn --workers N` gives each worker its own
   counters, so the effective limit becomes N x the configured one. Run a single
   worker, or move this to Redis. It is not a bug that can be fixed in here.
2. State is in memory. A restart forgets every window, so a restart loop would
   also reset an attacker's budget. Acceptable for the threat this addresses
   (online password guessing), not for anything that needs durable accounting.

The window is a sliding log rather than a fixed window: a fixed window lets a
caller spend its whole budget in the last second of one window and again in the
first second of the next, which is double the intended rate at the boundary —
exactly when it matters for password guessing.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional

from fastapi import HTTPException, Request, status

# Escape hatch for test suites that would otherwise trip the limiter. Never set
# this in a deployed environment.
ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() not in {"0", "false", "no"}

# request.client.host is the address of whatever opened the TCP connection. Behind
# nginx that is always 127.0.0.1, which would put every user in one bucket and
# let one attacker lock out the whole world. X-Forwarded-For fixes that, but it
# is a client-supplied header: trusting it when there is NO proxy in front lets
# anyone set it per request and never hit a limit at all. So it is opt-in, and
# must only be enabled when a trusted proxy is actually terminating connections.
TRUST_PROXY_HEADER = os.getenv("TRUST_PROXY_HEADER", "").strip().lower() in {"1", "true", "yes"}


def client_ip(request: Request) -> str:
    if TRUST_PROXY_HEADER:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Left-most entry is the original client; the rest are proxy hops.
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding-window limiter: at most `limit` hits per `window` seconds per key."""

    def __init__(self, limit: int, window: int, name: str) -> None:
        self.limit = limit
        self.window = window
        self.name = name
        self._hits: Dict[str, Deque[float]] = {}
        # auth.py's routes are `def`, not `async def`, so FastAPI runs them in a
        # threadpool and two requests really can touch this dict at once.
        self._lock = threading.Lock()

    def _prune(self, log: Deque[float], now: float) -> None:
        cutoff = now - self.window
        while log and log[0] <= cutoff:
            log.popleft()

    def retry_after(self, key: str) -> Optional[int]:
        """Seconds to wait if `key` is over its limit, else None. Records the hit."""
        if not ENABLED:
            return None
        now = time.monotonic()
        with self._lock:
            log = self._hits.setdefault(key, deque())
            self._prune(log, now)
            if len(log) >= self.limit:
                # Oldest hit in the window decides when a slot frees up.
                return max(1, int(log[0] + self.window - now) + 1)
            log.append(now)
            # Opportunistic sweep so idle keys do not accumulate forever. Cheap
            # because it only runs when the table is already large.
            if len(self._hits) > 2048:
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
                    del self._hits[k]
            return None

    def reset(self, key: str) -> None:
        """Forget a key's history — used to clear failures after a real success."""
        with self._lock:
            self._hits.pop(key, None)


def _limit(limiter: RateLimiter, key: str) -> None:
    wait = limiter.retry_after(key)
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many {limiter.name} attempts. Try again in {wait}s.",
            headers={"Retry-After": str(wait)},
        )


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


# Per-IP on login: stops one host hammering many accounts.
LOGIN_IP = RateLimiter(_int_env("RATE_LIMIT_LOGIN_PER_MIN", 5), 60, "sign-in")
# Per-email on login: stops a botnet spreading guesses at ONE account across many
# IPs, which the per-IP limit alone cannot see. Every attempt is recorded but a
# success clears the key, so what actually accumulates is CONSECUTIVE failures —
# someone signing in correctly all day never approaches the limit.
LOGIN_EMAIL = RateLimiter(_int_env("RATE_LIMIT_LOGIN_PER_EMAIL", 5), 300, "sign-in")
# Registration is public, so it is a spam and enumeration surface as well as a
# load one. Hourly, because no human needs four accounts in an hour.
REGISTER_IP = RateLimiter(_int_env("RATE_LIMIT_REGISTER_PER_HOUR", 3), 3600, "sign-up")


def limit_login_ip(request: Request) -> None:
    """FastAPI dependency: throttle sign-in attempts by source address."""
    _limit(LOGIN_IP, client_ip(request))


def limit_register_ip(request: Request) -> None:
    """FastAPI dependency: throttle account creation by source address."""
    _limit(REGISTER_IP, client_ip(request))


def check_login_email(email: str) -> None:
    """Raise 429 if this address has failed too often. Call before verifying."""
    _limit(LOGIN_EMAIL, f"email:{email}")


def clear_login_email(email: str) -> None:
    """Call after a successful sign-in so honest users never accumulate a lockout."""
    LOGIN_EMAIL.reset(f"email:{email}")
