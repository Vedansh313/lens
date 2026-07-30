"""Inventory management (Phase 4, step 7). Every route requires is_admin.

Two things live here:

1. `adjust_stock` — the ONLY supported way to change products.stock_quantity.
   It locks the row, moves the number, keeps in_stock in sync and writes the
   StockAdjustment ledger row. payments.py and lifecycle.py call it too, so the
   ledger explains every unit that moves, not just the ones an admin typed in.
   Assigning to product.stock_quantity directly bypasses the audit and is a bug.

2. The admin-facing stock views: what is running out, what is gone, and the
   history behind any one product's number.

Stock timing is set by the payment path and is not re-litigated here: units come
off at a successful charge, not when the order is placed (see payments.py). That
means an unpaid order reserves nothing, so two customers can both check out the
last unit and the second one is refused at payment with a 409. That is a
deliberate trade — it can disappoint late, but it can never oversell, because
the decrement re-reads the row under FOR UPDATE. True reservations would need a
holds table with expiry and are not part of this step.

The router carries the is_admin gate itself, the same as admin.py's, so a route
added here cannot be left ungated by forgetting a dependency.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from auth import get_db, require_admin
from models import Product, StockAdjustment, User

router = APIRouter(
    prefix="/admin/inventory", tags=["admin", "inventory"],
    dependencies=[Depends(require_admin)],
)

# A product at or below this many units is "low". Not a column: it is a
# reporting threshold, not a property of any one product, and every endpoint
# here lets the caller override it per request.
DEFAULT_LOW_STOCK_THRESHOLD = 5


# ---------------------------------------------------------------------------
# The write path
# ---------------------------------------------------------------------------
def adjust_stock(
    db: Session,
    product_id: int,
    delta: int,
    *,
    source: str,
    reason: str | None = None,
    actor_id: int | None = None,
    order_id: int | None = None,
) -> tuple[Product, StockAdjustment] | None:
    """Move one product's stock by `delta` and record why. Returns None if the
    product no longer exists (order lines outlive deleted products).

    Locks the row with FOR UPDATE before the read-modify-write, for the same
    reason the payment path does: two concurrent adjustments must not both read
    the old value and write back a number that loses one of them.

    Raises 409 rather than clamping when a delta would take stock below zero.
    Clamping would silently invent units and leave the ledger unable to
    reconcile against the column.

    Does NOT commit — the caller owns the transaction, so a stock move and the
    payment or status change it belongs to succeed or fail together.
    """
    if delta == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A stock adjustment must change the quantity.",
        )

    product = db.scalar(select(Product).where(Product.id == product_id).with_for_update())
    if product is None:
        return None

    before = product.stock_quantity
    after = before + delta
    if after < 0:
        wanted = abs(delta)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot remove {wanted} unit{'' if wanted == 1 else 's'} from "
                f"{product.product_display_name!r}: only {before} in stock."
            ),
        )

    product.stock_quantity = after
    product.in_stock = after > 0

    entry = StockAdjustment(
        product_id=product.id,
        delta=delta,
        quantity_before=before,
        quantity_after=after,
        source=source,
        reason=reason,
        changed_by_user_id=actor_id,
        order_id=order_id,
    )
    db.add(entry)
    return product, entry


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def _stock_row(p: Product, threshold: int) -> dict:
    """A product as the inventory screen sees it: identity plus stock state."""
    return {
        "id": p.id,
        "name": p.product_display_name,
        "category": p.master_category,
        "article_type": p.article_type,
        "price": float(p.price),
        "stock_quantity": p.stock_quantity,
        "in_stock": p.in_stock,
        "is_active": p.is_active,
        # Derived, not stored: the threshold is a per-request question.
        "stock_state": (
            "out" if p.stock_quantity == 0
            else "low" if p.stock_quantity <= threshold
            else "ok"
        ),
    }


def _adjustment_row(a: StockAdjustment) -> dict:
    return {
        "id": a.id,
        "delta": a.delta,
        "quantity_before": a.quantity_before,
        "quantity_after": a.quantity_after,
        "source": a.source,
        "reason": a.reason,
        "changed_by_user_id": a.changed_by_user_id,
        "order_id": a.order_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------
@router.get("")
def list_inventory(
    state: Literal["all", "low", "out", "ok"] = Query(default="all"),
    threshold: int = Query(default=DEFAULT_LOW_STOCK_THRESHOLD, ge=0, le=1000),
    q: Optional[str] = Query(default=None, min_length=1),
    active: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Products ordered by how urgently they need restocking.

    Sorted by stock ascending — the default view is a worklist, so the thing
    most needing attention is first, unlike /admin/products which sorts by id.
    'low' means 1..threshold and deliberately EXCLUDES 0, so the two states
    partition the shelf instead of overlapping; use state=out for the empties.
    """
    filters = []
    if q:
        filters.append(Product.product_display_name.ilike(f"%{q}%"))
    if active is not None:
        filters.append(Product.is_active.is_(active))
    if state == "out":
        filters.append(Product.stock_quantity == 0)
    elif state == "low":
        filters.append(Product.stock_quantity > 0)
        filters.append(Product.stock_quantity <= threshold)
    elif state == "ok":
        filters.append(Product.stock_quantity > threshold)

    total = db.scalar(select(func.count(Product.id)).where(*filters))
    rows = db.scalars(
        select(Product)
        .where(*filters)
        .order_by(Product.stock_quantity.asc(), Product.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "threshold": threshold,
        "products": [_stock_row(p, threshold) for p in rows],
    }


@router.get("/summary")
def inventory_summary(
    threshold: int = Query(default=DEFAULT_LOW_STOCK_THRESHOLD, ge=0, le=1000),
    db: Session = Depends(get_db),
) -> dict:
    """Counts per stock state plus total units on hand.

    One aggregate query rather than four counts: this is the top of the admin
    dashboard and runs over all 44k rows.
    """
    counted = db.execute(
        select(
            func.count(Product.id),
            func.count(case((Product.stock_quantity == 0, 1))),
            func.count(
                case(
                    ((Product.stock_quantity > 0) & (Product.stock_quantity <= threshold), 1)
                )
            ),
            func.coalesce(func.sum(Product.stock_quantity), 0),
        ).where(Product.is_active.is_(True))
    ).one()
    total, out, low, units = counted
    return {
        "threshold": threshold,
        # Active products only — a soft-deleted product is off the shelf, so
        # counting it as "out of stock" would pad the worklist with noise.
        "active_products": total,
        "out_of_stock": out,
        "low_stock": low,
        "healthy": total - out - low,
        "total_units": int(units),
    }


@router.get("/{product_id}/history")
def stock_history(
    product_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """The ledger for one product, newest first.

    Returns 404 for an unknown product rather than an empty list, so a typo in
    the id is distinguishable from a product that has genuinely never moved.
    """
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    total = db.scalar(
        select(func.count(StockAdjustment.id)).where(StockAdjustment.product_id == product_id)
    )
    rows = db.scalars(
        select(StockAdjustment)
        .where(StockAdjustment.product_id == product_id)
        .order_by(StockAdjustment.created_at.desc(), StockAdjustment.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "product_id": product_id,
        "name": product.product_display_name,
        "stock_quantity": product.stock_quantity,
        "total": total,
        "limit": limit,
        "offset": offset,
        "adjustments": [_adjustment_row(a) for a in rows],
    }


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------
class AdjustIn(BaseModel):
    """Either a relative `delta` or an absolute `set_to`, never both.

    delta is the safer of the two and the one to prefer: "+20 arrived" survives
    a concurrent sale, whereas set_to overwrites whatever the number became
    between the admin reading the screen and pressing the button.
    """

    delta: Optional[int] = None
    set_to: Optional[int] = Field(default=None, ge=0)
    reason: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def _exactly_one(self) -> "AdjustIn":
        if (self.delta is None) == (self.set_to is None):
            raise ValueError("Provide exactly one of 'delta' or 'set_to'.")
        if self.delta == 0:
            raise ValueError("'delta' must not be zero.")
        return self


@router.post("/{product_id}/adjust")
def adjust_one(
    product_id: int,
    body: AdjustIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Adjust one product's stock and record the reason.

    `reason` is required, which is the whole point of routing stock changes
    through here rather than through PATCH /admin/products.
    """
    # set_to is resolved to a delta under the same lock that applies it, so the
    # ledger only ever stores movements and the row cannot shift in between.
    if body.set_to is not None:
        product = db.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
            )
        delta = body.set_to - product.stock_quantity
        if delta == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Stock is already {body.set_to}.",
            )
    else:
        delta = body.delta

    result = adjust_stock(
        db, product_id, delta,
        source="manual", reason=body.reason, actor_id=admin.id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product, entry = result
    db.commit()
    db.refresh(product)
    db.refresh(entry)
    return {"product": _stock_row(product, DEFAULT_LOW_STOCK_THRESHOLD),
            "adjustment": _adjustment_row(entry)}


class BulkLineIn(BaseModel):
    product_id: int
    delta: int = Field(description="Signed change; must not be zero.")

    @model_validator(mode="after")
    def _nonzero(self) -> "BulkLineIn":
        if self.delta == 0:
            raise ValueError("'delta' must not be zero.")
        return self


class BulkAdjustIn(BaseModel):
    reason: str = Field(min_length=1, max_length=255)
    lines: list[BulkLineIn] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _no_duplicate_products(self) -> "BulkAdjustIn":
        ids = [line.product_id for line in self.lines]
        if len(set(ids)) != len(ids):
            raise ValueError("Each product may appear at most once per request.")
        return self


@router.post("/bulk-adjust")
def adjust_bulk(
    body: BulkAdjustIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Apply many adjustments as ONE transaction — a delivery arriving, or a
    stocktake correcting a shelf.

    All-or-nothing on purpose: a partial bulk restock is worse than none,
    because the admin cannot tell which half applied. Any unknown product or
    any line that would go negative fails the whole request.

    Products are locked in ascending id order (the validator rejects duplicates,
    so the order is total) to keep two overlapping bulk requests from deadlocking
    by grabbing the same rows in opposite orders.
    """
    applied = []
    for line in sorted(body.lines, key=lambda l: l.product_id):
        result = adjust_stock(
            db, line.product_id, line.delta,
            source="manual", reason=body.reason, actor_id=admin.id,
        )
        if result is None:
            # Nothing is committed yet, so returning here discards every line.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {line.product_id} not found; no changes were applied.",
            )
        applied.append(result)

    db.commit()
    return {
        "reason": body.reason,
        "applied": len(applied),
        "products": [
            {
                **_stock_row(p, DEFAULT_LOW_STOCK_THRESHOLD),
                "delta": e.delta,
                "quantity_before": e.quantity_before,
            }
            for p, e in applied
        ],
    }
