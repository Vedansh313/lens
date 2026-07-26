"""Verify product images: every products.id needs backend/images/<id>.jpg.

    python verify_images.py [--min-coverage 99.0] [--list N]

Run after downloading the Kaggle 'fashion-product-images-small' dataset into
backend/images/. Reports how many product ids have a matching JPG, lists a
sample of any missing ids, and flags the common mistake of leaving the images
in a nested subfolder. Exits non-zero if coverage is below --min-coverage.

The server serves images by product id (server.py: /images/<id>.jpg), so the
filenames must equal the dataset ids and sit DIRECTLY in backend/images/.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import select

from db import SessionLocal
from models import Product

BACKEND_DIR = Path(__file__).resolve().parent
IMAGES_DIR = Path(os.getenv("IMAGES_DIR", BACKEND_DIR / "images"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--min-coverage", type=float, default=99.0,
        help="minimum %% of ids that must have an image to pass (default 99.0)",
    )
    parser.add_argument(
        "--list", type=int, default=20, metavar="N",
        help="how many missing ids to print (default 20)",
    )
    args = parser.parse_args()

    if not IMAGES_DIR.exists():
        sys.exit(f"ERROR: images dir does not exist: {IMAGES_DIR}")

    with SessionLocal() as session:
        ids = [row[0] for row in session.execute(select(Product.id).order_by(Product.id)).all()]
    total = len(ids)
    print(f"DB products  : {total:,}")

    # Filenames sitting DIRECTLY in backend/images/ (stem == id, e.g. 1163.jpg).
    top_level = {p.stem for p in IMAGES_DIR.glob("*.jpg")}
    print(f"images/*.jpg : {len(top_level):,} files in {IMAGES_DIR}")

    id_strs = {str(i) for i in ids}
    present = [i for i in ids if str(i) in top_level]
    missing = [i for i in ids if str(i) not in top_level]
    extra = [s for s in top_level if s not in id_strs]
    coverage = 100.0 * len(present) / total if total else 0.0

    print(f"\n  present : {len(present):,}")
    print(f"  missing : {len(missing):,}")
    print(f"  coverage: {coverage:.2f}%")
    if extra:
        print(f"  extra   : {len(extra):,} jpg(s) with no matching product id (harmless)")

    if missing:
        sample = missing[: args.list]
        print(f"\n  missing ids (first {len(sample)}): {sample}")

    # Common mistake: the JPGs unzipped into a nested subfolder instead of here.
    if not top_level:
        nested = next(iter(IMAGES_DIR.rglob("*.jpg")), None)
        if nested is not None:
            print(
                f"\n  HINT: no *.jpg directly in {IMAGES_DIR}, but found nested ones, e.g.\n"
                f"        {nested}\n"
                f"        Flatten them so the JPGs sit directly in backend/images/."
            )
        else:
            print(f"\n  HINT: no *.jpg anywhere under {IMAGES_DIR} - did the unzip land here?")

    if coverage >= args.min_coverage:
        print(f"\nIMAGES OK ({coverage:.2f}% >= {args.min_coverage:.1f}%)")
        sys.exit(0)
    print(f"\nIMAGES INCOMPLETE ({coverage:.2f}% < {args.min_coverage:.1f}%)")
    sys.exit(1)


if __name__ == "__main__":
    main()
