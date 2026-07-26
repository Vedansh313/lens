"""Wishlist + recently-viewed API (Phase 2). All routes require auth.

Both lists return products through catalog's serialize_product for a consistent
shape. Recently-viewed uses an upsert so re-viewing a product bumps it to the
top instead of duplicating.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from auth import get_current_user, get_db
from catalog import serialize_product
from models import Product, RecentlyViewed, User, WishlistItem

router = APIRouter(tags=["engagement"])

RECENTLY_VIEWED_LIMIT = 12


class ProductRef(BaseModel):
    product_id: int


def _ensure_product(db: Session, product_id: int) -> None:
    if db.get(Product, product_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")


# ---------------------------------------------------------------------------
# Wishlist
# ---------------------------------------------------------------------------
@router.get("/wishlist")
def get_wishlist(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    rows = db.execute(
        select(Product)
        .join(WishlistItem, WishlistItem.product_id == Product.id)
        .where(WishlistItem.user_id == user.id)
        .order_by(WishlistItem.created_at.desc(), WishlistItem.id.desc())
    ).scalars().all()
    return {"items": [serialize_product(p) for p in rows]}


@router.post("/wishlist", status_code=status.HTTP_201_CREATED)
def add_to_wishlist(
    body: ProductRef,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_product(db, body.product_id)
    # Idempotent: a duplicate save is a no-op thanks to the unique constraint.
    stmt = (
        pg_insert(WishlistItem)
        .values(user_id=user.id, product_id=body.product_id)
        .on_conflict_do_nothing(constraint="uq_wishlist_items_user_product")
    )
    db.execute(stmt)
    db.commit()
    return get_wishlist(user, db)


@router.delete("/wishlist/{product_id}")
def remove_from_wishlist(
    product_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # Idempotent: removing something not saved still returns the wishlist.
    db.execute(
        delete(WishlistItem).where(
            WishlistItem.user_id == user.id, WishlistItem.product_id == product_id
        )
    )
    db.commit()
    return get_wishlist(user, db)


# ---------------------------------------------------------------------------
# Recently viewed
# ---------------------------------------------------------------------------
@router.get("/recently-viewed")
def get_recently_viewed(
    limit: int = Query(RECENTLY_VIEWED_LIMIT, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.execute(
        select(Product)
        .join(RecentlyViewed, RecentlyViewed.product_id == Product.id)
        .where(RecentlyViewed.user_id == user.id)
        .order_by(RecentlyViewed.viewed_at.desc(), RecentlyViewed.id.desc())
        .limit(limit)
    ).scalars().all()
    return {"items": [serialize_product(p) for p in rows]}


@router.post("/recently-viewed", status_code=status.HTTP_201_CREATED)
def record_view(
    body: ProductRef,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_product(db, body.product_id)
    # Upsert: re-viewing bumps viewed_at to now() rather than adding a duplicate.
    stmt = (
        pg_insert(RecentlyViewed)
        .values(user_id=user.id, product_id=body.product_id)
        .on_conflict_do_update(
            constraint="uq_recently_viewed_user_product",
            set_={"viewed_at": func.now()},
        )
    )
    db.execute(stmt)
    db.commit()
    return get_recently_viewed(RECENTLY_VIEWED_LIMIT, user, db)
