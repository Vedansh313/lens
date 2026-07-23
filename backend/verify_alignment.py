"""Three-way alignment proof: FAISS position <-> DB faiss_index <-> JSON row.

    python verify_alignment.py [--samples N]

Run this after any re-seed, after rebuilding the FAISS index, or any time
search results look subtly wrong. Exits non-zero if alignment is broken.

For each sampled position p it checks:

  1. FAISS self-retrieval — reconstruct vector p, search the index with it,
     and require the hit to be p itself OR a position holding a byte-identical
     vector. This asks FAISS what actually lives at p instead of trusting the
     file order.
  2. DB <-> JSON — the row with faiss_index == p must equal df.iloc[p] field
     for field.

NOTE on criterion 1: ~780 of the 44,419 vectors (1.76%) are exact duplicates —
the dataset lists the same photographed product under multiple ids (e.g.
positions 4233 and 2615 are both "Gini and Jony Girls Printed Pink Dress",
ids 34063 and 34062). FAISS breaks such ties by returning the lowest position,
so requiring a strict self-match produces false failures. Duplicate-vector ties
are reported separately and are not errors.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
from sqlalchemy import func, select

from db import SessionLocal
from models import Product

BACKEND_DIR = Path(__file__).resolve().parent
AI_DIR = BACKEND_DIR.parent / "ai"
INDEX_PATH = AI_DIR / "models" / "product_index.faiss"
METADATA_PATH = AI_DIR / "models" / "product_metadata.json"

DEFAULT_SAMPLES = 500
SEED = 20260723


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES,
                        help=f"random positions to check (default {DEFAULT_SAMPLES})")
    args = parser.parse_args()

    index = faiss.read_index(str(INDEX_PATH))
    df = pd.read_json(METADATA_PATH)
    print(f"FAISS : {type(index).__name__} ntotal={index.ntotal:,} d={index.d}")
    print(f"JSON  : {len(df):,} rows")

    if index.ntotal != len(df):
        sys.exit(f"FATAL: FAISS ntotal {index.ntotal:,} != JSON rows {len(df):,}")

    with SessionLocal() as session:
        n_db = session.scalar(select(func.count()).select_from(Product))
    print(f"DB    : {n_db:,} rows")
    if n_db != len(df):
        sys.exit(f"FATAL: DB has {n_db:,} rows, expected {len(df):,}")

    random.seed(SEED)
    n = min(args.samples, index.ntotal)
    positions = set(random.sample(range(index.ntotal), n))
    # always include boundaries — off-by-one errors hide there
    positions.update({0, 1, len(df) // 2, index.ntotal - 2, index.ntotal - 1})
    positions = sorted(positions)
    print(f"\nChecking {len(positions)} positions (seed={SEED}, includes 0 and "
          f"{index.ntotal - 1})\n")

    with SessionLocal() as session:
        db_rows = {
            r.faiss_index: r
            for r in session.scalars(
                select(Product).where(Product.faiss_index.in_(positions))
            )
        }

    missing = [p for p in positions if p not in db_rows]
    if missing:
        sys.exit(f"FATAL: no DB row for faiss_index {missing[:10]}")

    exact, ties, self_fail, field_fail = 0, [], [], []

    def norm(v):
        return None if pd.isna(v) else str(v)

    for p in positions:
        vec = index.reconstruct(int(p)).reshape(1, -1)
        _, nn = index.search(vec, 1)
        got = int(nn[0][0])
        if got == p:
            exact += 1
        elif np.array_equal(index.reconstruct(int(p)), index.reconstruct(got)):
            ties.append((p, got))
        else:
            self_fail.append((p, got))

        src, row = df.iloc[p], db_rows[p]
        pairs = [
            ("id", int(src["id"]), row.id),
            ("productDisplayName", norm(src["productDisplayName"]), row.product_display_name),
            ("masterCategory", norm(src["masterCategory"]), row.master_category),
            ("subCategory", norm(src["subCategory"]), row.sub_category),
            ("articleType", norm(src["articleType"]), row.article_type),
            ("baseColour", norm(src["baseColour"]), row.base_colour),
            ("gender", norm(src["gender"]), row.gender),
            ("season", norm(src["season"]), row.season),
            ("usage", norm(src["usage"]), row.usage),
        ]
        for field, want, got_val in pairs:
            if want != got_val:
                field_fail.append((p, field, want, got_val))
                break

    ok_self = not self_fail
    print(f"  [{'PASS' if ok_self else 'FAIL'}] FAISS self-retrieval: "
          f"{exact} exact, {len(ties)} duplicate-vector ties, "
          f"{len(self_fail)} genuine mismatches")
    if self_fail:
        print(f"        mismatches (pos -> returned): {self_fail[:10]}")

    ok_fields = not field_fail
    print(f"  [{'PASS' if ok_fields else 'FAIL'}] DB row at faiss_index=p equals "
          f"JSON .iloc[p]: {len(positions) - len(field_fail)}/{len(positions)}")
    if field_fail:
        for p, field, want, got_val in field_fail[:10]:
            print(f"        pos {p} {field}: json={want!r} db={got_val!r}")

    print("\n  landmarks:")
    for p in (0, 1, len(df) // 2, index.ntotal - 1):
        row = db_rows[p]
        print(f"    position {p:>5} -> id={row.id:<6} {row.product_display_name}")

    if ok_self and ok_fields:
        print("\nALIGNMENT VERIFIED")
        sys.exit(0)
    print("\nALIGNMENT BROKEN")
    sys.exit(1)


if __name__ == "__main__":
    main()
