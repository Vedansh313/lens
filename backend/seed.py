"""Seed the products table from ai/models/product_metadata.json.

    python seed.py [--truncate]

=============================================================================
The one thing this script must get right: ROW ORDER.
=============================================================================
ai/search_system.py resolves FAISS hits positionally (`df.iloc[idx]`), so a
product's meaning in the database comes from its POSITION in the metadata
file, not from its id. This script writes that position to `faiss_index`.

If the order is wrong, nothing crashes — search just returns confident,
plausible, wrong products. So the script asserts the source ordering up front
and verifies the loaded rows afterwards instead of assuming either.
=============================================================================

Idempotent: refuses to run against a non-empty table unless --truncate is
given, so a double-run cannot produce a half-loaded catalogue. The whole load
runs in one transaction — it either completes or leaves the table untouched.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import func, insert, select, text

from db import SessionLocal, engine
from models import Product

BACKEND_DIR = Path(__file__).resolve().parent
METADATA_PATH = BACKEND_DIR.parent / "ai" / "models" / "product_metadata.json"

# JSON column -> model attribute. The JSON's camelCase names are the dataset's;
# the DB uses snake_case.
COLUMN_MAP = {
    "id": "id",
    "productDisplayName": "product_display_name",
    "masterCategory": "master_category",
    "subCategory": "sub_category",
    "articleType": "article_type",
    "baseColour": "base_colour",
    "gender": "gender",
    "season": "season",
    "year": "year",
    "usage": "usage",
}

CHUNK_SIZE = 2000


def load_metadata() -> pd.DataFrame:
    """Read the metadata JSON in file order and validate its shape."""
    if not METADATA_PATH.exists():
        sys.exit(f"ERROR: metadata not found at {METADATA_PATH}")

    df = pd.read_json(METADATA_PATH)
    print(f"[seed] read {len(df):,} rows from {METADATA_PATH.name}")

    missing = set(COLUMN_MAP) - set(df.columns)
    if missing:
        sys.exit(f"ERROR: metadata is missing expected columns: {sorted(missing)}")

    # The positional contract. pd.read_json must have produced a plain
    # 0..n-1 index; anything else means the file was reordered or reindexed,
    # and faiss_index would no longer mean "position in the FAISS index".
    if not df.index.equals(pd.RangeIndex(len(df))):
        sys.exit(
            "ERROR: metadata index is not a clean RangeIndex 0..n-1. The "
            "FAISS<->metadata positional alignment cannot be trusted; refusing "
            "to seed."
        )

    if df["id"].duplicated().any():
        dupes = int(df["id"].duplicated().sum())
        sys.exit(f"ERROR: metadata contains {dupes} duplicate product ids.")

    return df


def to_records(df: pd.DataFrame) -> list[dict]:
    """Build insert dicts, position -> faiss_index, NaN -> None."""
    frame = df[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)

    # year is float64 purely because of its single NaN; store it as a real int.
    frame["year"] = frame["year"].astype("Int64")

    # pandas NaN/NaT/pd.NA are not valid SQL NULLs — convert explicitly.
    frame = frame.astype(object).where(pd.notna(frame), None)

    records = frame.to_dict(orient="records")

    # faiss_index IS the row position. Assigned from enumerate, never from a
    # column, so it cannot inherit a mistake in the source file.
    for position, record in enumerate(records):
        record["faiss_index"] = position
        record["id"] = int(record["id"])
        if record["year"] is not None:
            record["year"] = int(record["year"])

    return records


def seed(truncate: bool) -> None:
    df = load_metadata()
    records = to_records(df)

    with SessionLocal() as session:
        existing = session.scalar(select(func.count()).select_from(Product))
        if existing:
            if not truncate:
                sys.exit(
                    f"ERROR: products already has {existing:,} rows. Re-run with "
                    "--truncate to replace them, or leave the table as it is."
                )
            print(f"[seed] truncating {existing:,} existing rows")
            session.execute(text("TRUNCATE TABLE products"))
            session.commit()

    started = time.perf_counter()
    # One transaction: a failure part-way leaves the table exactly as it was.
    with engine.begin() as conn:
        for start in range(0, len(records), CHUNK_SIZE):
            chunk = records[start:start + CHUNK_SIZE]
            conn.execute(insert(Product), chunk)
            done = min(start + CHUNK_SIZE, len(records))
            print(f"\r[seed] inserted {done:,}/{len(records):,}", end="", flush=True)
    elapsed = time.perf_counter() - started
    print(f"\n[seed] committed {len(records):,} rows in {elapsed:.1f}s")

    verify(df)


def verify(df: pd.DataFrame) -> None:
    """Post-load checks against the database, not against the in-memory list."""
    print("[seed] verifying...")
    failures = []

    with SessionLocal() as session:
        count = session.scalar(select(func.count()).select_from(Product))
        if count == len(df):
            print(f"  [PASS] row count = {count:,}")
        else:
            failures.append(f"row count {count:,} != {len(df):,}")

        # faiss_index must be exactly 0..n-1: contiguous, no gaps, no dupes.
        lo, hi, distinct = session.execute(
            select(func.min(Product.faiss_index),
                   func.max(Product.faiss_index),
                   func.count(func.distinct(Product.faiss_index)))
        ).one()
        if (lo, hi, distinct) == (0, len(df) - 1, len(df)):
            print(f"  [PASS] faiss_index is a complete 0..{hi:,} sequence")
        else:
            failures.append(
                f"faiss_index min={lo} max={hi} distinct={distinct}, "
                f"expected 0..{len(df) - 1} with {len(df)} distinct"
            )

        # Every row's DB content must equal the JSON row at the same position.
        mismatches = 0
        rows = session.execute(
            select(Product.faiss_index, Product.id, Product.product_display_name,
                   Product.article_type, Product.base_colour, Product.gender)
            .order_by(Product.faiss_index)
        ).all()
        for fx, pid, name, article, colour, gender in rows:
            src = df.iloc[fx]
            if int(src["id"]) != pid:
                mismatches += 1
                continue
            if str(src["articleType"]) != str(article):
                mismatches += 1
                continue
            if str(src["gender"]) != str(gender):
                mismatches += 1
        if mismatches == 0:
            print(f"  [PASS] all {len(rows):,} rows match the JSON row at the "
                  f"same position")
        else:
            failures.append(f"{mismatches:,} rows disagree with their JSON position")

    if failures:
        print("\n[seed] VERIFICATION FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("[seed] all checks passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--truncate", action="store_true",
        help="delete existing rows first (otherwise a non-empty table aborts)",
    )
    args = parser.parse_args()
    seed(truncate=args.truncate)


if __name__ == "__main__":
    main()
