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

import lifecycle
from auth import get_db, require_admin
from checkout import serialize_order
from models import ORDER_STATUSES, Order, User

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
