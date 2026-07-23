"""Database engine and session management for the Lens backend.

Reads DATABASE_URL from backend/.env (see .env.example). Kept separate from
models.py so Alembic's env.py can import metadata without opening connections
at import time.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy backend/.env.example to backend/.env "
        "and fill in the connection string."
    )

# pool_pre_ping avoids handing out connections the server has already dropped
# (common when Postgres restarts under a long-lived uvicorn process).
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
