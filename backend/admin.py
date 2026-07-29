"""Admin order management (Phase 4, step 5). Every route requires is_admin.

The gate is attached to the router itself rather than to individual routes, so
a future endpoint added here cannot be left ungated by forgetting a dependency.
Routes that need the acting admin re-declare Depends(require_admin) to get the
User object; FastAPI caches the dependency per request, so it resolves once.

Unlike the customer endpoints in orders.py, nothing here is owner-scoped — an
admin acts on any user's order. Status changes still go through lifecycle.py,
so admin actions are validated and audited exactly like customer ones, with
changed_by_user_id recording who acted.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from decimal import Decimal

import lifecycle
from auth import get_db, require_admin
from catalog import serialize_product_detail
from checkout import serialize_order
from models import ORDER_STATUSES, Order, Product, User

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class StatusChangeIn(BaseModel):
    to_status: str
    note: Optional[str] = Field(default=None, max_length=255)

    @field_validator("to_status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        if v not in ORDER_STATUSES:
            raise ValueError(f"Unknown status. Expected one of: {', '.join(ORDER_STATUSES)}")
        return v


@router.get("/orders")
def list_all_orders(
    order_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Every order in the system, newest first, with the buyer's identity.

    Exists so an admin can find the order they need to act on; the richer
    reporting views come with the analytics endpoints.
    """
    if order_status is not None and order_status not in ORDER_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown status. Expected one of: {', '.join(ORDER_STATUSES)}",
        )

    where = [Order.status == order_status] if order_status else []
    total = db.scalar(select(func.count()).select_from(Order).where(*where))
    # Joined rather than looked up per order — this list is the admin's entry
    # point and would otherwise issue a query per row.
    rows = db.execute(
        select(Order, User)
        .join(User, User.id == Order.user_id)
        .where(*where)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "orders": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "status": o.status,
                "total": float(o.total),
                "item_count": sum(i.quantity for i in o.items),
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "user": {"id": u.id, "email": u.email, "name": u.name},
                # The moves this order can actually make from where it is.
                "next_statuses": sorted(lifecycle.ALLOWED_TRANSITIONS.get(o.status, set())),
            }
            for o, u in rows
        ],
    }


@router.post("/orders/{order_id}/status")
def set_order_status(
    order_id: int,
    body: StatusChangeIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Move an order to `to_status`, recording the acting admin.

    This is how an order reaches shipped/delivered — the customer endpoints
    only ever move an order *out* of the fulfilment path. Illegal moves are
    rejected by lifecycle.transition with a 409.

    Moving to cancelled or returned returns stock and refunds the payment, the
    same as the customer-facing routes, so an admin cancellation cannot leave
    stock or money stranded.
    """
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    # 'refunded' is legal from cancelled/returned, but refunding an order that
    # was never paid would record money moving that never did.
    if body.to_status == "refunded" and not lifecycle.stock_was_taken(order):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order has no successful payment to refund.",
        )

    lifecycle.transition(order, body.to_status, note=body.note, actor_id=admin.id)

    if body.to_status in ("cancelled", "returned"):
        lifecycle.unwind(
            db,
            order,
            note=f"Refund issued by admin for {body.to_status} order",
            actor_id=admin.id,
        )

    db.commit()
    db.refresh(order)

    data = serialize_order(order)
    data["history"] = [
        {
            "from_status": h.from_status,
            "to_status": h.to_status,
            "note": h.note,
            "changed_by_user_id": h.changed_by_user_id,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in order.status_history
    ]
    data["next_statuses"] = sorted(lifecycle.ALLOWED_TRANSITIONS.get(order.status, set()))
    return data


# ---------------------------------------------------------------------------
# Product management
#
# READ THIS BEFORE CHANGING ANYTHING HERE.
#
# products.faiss_index must stay a contiguous 0..n-1 sequence whose order
# matches product_index.faiss, because ai/search_system.py resolves FAISS hits
# by ROW POSITION (df.iloc[idx]). server.py re-checks this at every boot and
# refuses to start otherwise.
#
# Therefore:
#   * DELETE is soft. Clearing is_active leaves the row, and the position, in
#     place. A hard delete shifts every later row and breaks image search.
#   * CREATE appends at faiss_index = max + 1, keeping the sequence contiguous.
#     The new product has NO CLIP vector, so FAISS can never return it — it is
#     findable by text/catalog only. That is a deliberate, accepted limitation:
#     generating a vector would mean touching the AI pipeline.
#   * EDIT is unrestricted for catalogue and commerce fields, and must never
#     touch faiss_index.
# ---------------------------------------------------------------------------
def _admin_product(p: Product) -> dict:
    """Detail view plus the admin-only fields the storefront never shows."""
    return {
        **serialize_product_detail(p),
        "is_active": p.is_active,
        "stock_quantity": p.stock_quantity,
        "faiss_index": p.faiss_index,
        # False for admin-created products: no CLIP vector exists for them.
        "image_searchable": p.faiss_index < _faiss_vector_count(),
    }


_VECTOR_COUNT: int | None = None


def _faiss_vector_count() -> int:
    """How many products came from the seeded dataset, i.e. have a CLIP vector.

    Read once from server.index.ntotal when available. Imported lazily because
    admin.py is imported *by* server.py — a module-level import would be
    circular.
    """
    global _VECTOR_COUNT
    if _VECTOR_COUNT is None:
        try:
            import server  # noqa: PLC0415 - lazy by necessity, see docstring

            _VECTOR_COUNT = int(server.index.ntotal)
        except Exception:
            # Admin routes must not fall over because the search stack is not
            # loaded (e.g. under tests); treat every seeded row as searchable.
            _VECTOR_COUNT = 2**31
    return _VECTOR_COUNT


class ProductIn(BaseModel):
    """Create payload. faiss_index is intentionally absent — it is assigned by
    the server and is never client-supplied."""

    product_display_name: str = Field(min_length=1, max_length=255)
    master_category: str = Field(min_length=1, max_length=64)
    sub_category: str = Field(min_length=1, max_length=64)
    article_type: str = Field(min_length=1, max_length=64)
    gender: str = Field(min_length=1, max_length=32)
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    base_colour: Optional[str] = Field(default=None, max_length=64)
    season: Optional[str] = Field(default=None, max_length=32)
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    usage: Optional[str] = Field(default=None, max_length=32)
    stock_quantity: int = Field(default=0, ge=0)


class ProductPatch(BaseModel):
    """Partial update. Every field optional; only what is sent is changed."""

    product_display_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    master_category: Optional[str] = Field(default=None, min_length=1, max_length=64)
    sub_category: Optional[str] = Field(default=None, min_length=1, max_length=64)
    article_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    gender: Optional[str] = Field(default=None, min_length=1, max_length=32)
    price: Optional[Decimal] = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    base_colour: Optional[str] = Field(default=None, max_length=64)
    season: Optional[str] = Field(default=None, max_length=32)
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    usage: Optional[str] = Field(default=None, max_length=32)
    stock_quantity: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


@router.get("/products")
def list_products_admin(
    q: Optional[str] = Query(default=None, min_length=1),
    active: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Admin product list. Unlike the storefront this shows inactive products
    too — they are what an admin needs to find in order to restore them."""
    filters = []
    if q:
        filters.append(Product.product_display_name.ilike(f"%{q}%"))
    if active is not None:
        filters.append(Product.is_active.is_(active))

    total = db.scalar(select(func.count(Product.id)).where(*filters))
    rows = db.scalars(
        select(Product).where(*filters).order_by(Product.id).limit(limit).offset(offset)
    ).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "products": [_admin_product(p) for p in rows],
    }


@router.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(body: ProductIn, db: Session = Depends(get_db)) -> dict:
    """Create a product.

    id and faiss_index are both assigned server-side as max + 1. The id is not
    autoincrementing (the seeded ids are real, sparse dataset ids), and
    faiss_index must extend the sequence by exactly one to stay contiguous.

    The result is text- and catalog-searchable but NOT image-searchable: no
    CLIP vector exists for it, so FAISS cannot return it. See the block comment
    above.
    """
    next_id = (db.scalar(select(func.max(Product.id))) or 0) + 1
    next_faiss = (db.scalar(select(func.max(Product.faiss_index))) or -1) + 1

    product = Product(
        id=next_id,
        faiss_index=next_faiss,
        in_stock=body.stock_quantity > 0,
        is_active=True,
        **body.model_dump(),
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return _admin_product(product)


@router.patch("/products/{product_id}")
def update_product(product_id: int, body: ProductPatch, db: Session = Depends(get_db)) -> dict:
    """Update catalogue/commerce fields. faiss_index and id are not editable."""
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(product, field, value)
    # Keep the two stock fields consistent, exactly as the payment path does.
    if "stock_quantity" in changes:
        product.in_stock = product.stock_quantity > 0

    db.commit()
    db.refresh(product)
    return _admin_product(product)


@router.delete("/products/{product_id}")
def deactivate_product(product_id: int, db: Session = Depends(get_db)) -> dict:
    """SOFT delete: clears is_active. The row is never removed.

    DELETE is the honest verb for what this means to a storefront — the product
    disappears from the catalog and from search — but the row must survive to
    hold its FAISS position. Reversible via PATCH is_active=true.
    """
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product.is_active = False
    db.commit()
    db.refresh(product)
    return _admin_product(product)
