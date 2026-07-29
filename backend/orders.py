"""Order retrieval + invoice (Phase 3). Read-only, auth-protected, owner-scoped.

The invoice is returned as structured JSON; the frontend renders the printable
layout (per the Phase 3 invoice choice), so the backend needs no PDF dependency.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import lifecycle
from auth import get_current_user, get_db
from checkout import serialize_order
from models import Order, User

router = APIRouter(tags=["orders"])


class LifecycleActionIn(BaseModel):
    """Body for cancel/return. The reason is optional and free-text; it is
    stored on the order and echoed into the status-history note."""

    reason: str | None = Field(default=None, max_length=255)

SELLER = {
    "name": "Lens",
    "email": "orders@lens.app",
    "note": "Thank you for shopping with Lens.",
}


def _serialize_payment(p) -> dict:
    return {
        "id": p.id,
        "method": p.method,
        "status": p.status,
        "amount": float(p.amount),
        "transaction_ref": p.transaction_ref,
        "detail": p.detail,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        # Refund bookkeeping (Phase 4); both null unless status == 'refunded'.
        "refunded_at": p.refunded_at.isoformat() if p.refunded_at else None,
        "refund_ref": p.refund_ref,
    }


def _serialize_history(h) -> dict:
    return {
        "from_status": h.from_status,
        "to_status": h.to_status,
        "note": h.note,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


def _latest_payment_status(order: Order) -> str:
    """One word for 'where is the money'. Checked most-decisive first: a refund
    supersedes the success it reverses, and a success supersedes earlier
    declines (a failed attempt can be retried, so it is never the last word
    while a later attempt worked)."""
    if any(p.status == "refunded" for p in order.payments):
        return "refunded"
    if any(p.status == "success" for p in order.payments):
        return "success"
    if order.payments:
        return order.payments[-1].status
    return "unpaid"


def _get_owned_order(order_id: int, user: User, db: Session) -> Order:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.get("/orders")
def list_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    orders = db.scalars(
        select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc(), Order.id.desc())
    ).all()
    return {
        "orders": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "status": o.status,
                "total": float(o.total),
                "item_count": sum(i.quantity for i in o.items),
                "payment_status": _latest_payment_status(o),
                "created_at": o.created_at.isoformat() if o.created_at else None,
                # Same rules as the detail view, so the list can render the
                # right action without fetching each order first.
                "can_cancel": o.status in ("pending", "paid"),
                "can_return": o.status == "delivered",
            }
            for o in orders
        ]
    }


@router.get("/orders/{order_id}")
def get_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    order = _get_owned_order(order_id, user, db)
    data = serialize_order(order)
    data["payments"] = [_serialize_payment(p) for p in order.payments]
    data["history"] = [_serialize_history(h) for h in order.status_history]
    # What the customer may do next, resolved server-side so the UI does not
    # have to re-implement the transition rules to decide which buttons to show.
    data["can_cancel"] = order.status in ("pending", "paid")
    data["can_return"] = order.status == "delivered"
    return data


# ---------------------------------------------------------------------------
# Customer lifecycle actions
# ---------------------------------------------------------------------------
@router.post("/orders/{order_id}/cancel")
def cancel_order(
    order_id: int,
    body: LifecycleActionIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Cancel an order that has not shipped yet.

    Legal from 'pending' (nothing was charged) and 'paid' (stock and money are
    returned). Once shipped, cancelling is no longer possible — that is a
    return. Stock, refund and status all commit as one transaction.
    """
    order = _get_owned_order(order_id, user, db)
    reason = (body.reason if body else None) or None

    # transition() would reject an illegal move anyway; this check exists to
    # give the customer a sentence about *their* order rather than a rules dump.
    if order.status not in ("pending", "paid"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This order has already shipped and can no longer be cancelled."
                if order.status in ("shipped", "delivered")
                else f"This order cannot be cancelled (status: {order.status})."
            ),
        )

    lifecycle.transition(order, "cancelled", note=reason or "Cancelled by customer")
    order.cancel_reason = reason
    # Unpaid orders stop here; paid ones continue to 'refunded' with stock returned.
    lifecycle.unwind(db, order, note="Refund issued for cancelled order")

    db.commit()
    db.refresh(order)
    return get_order(order_id, user=user, db=db)


@router.post("/orders/{order_id}/return")
def request_return(
    order_id: int,
    body: LifecycleActionIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Request a return on a delivered order.

    Records the request (time + reason) and, since a delivered order was
    necessarily paid, returns the stock and refunds the payment in the same
    transaction. A real store would hold the refund until the goods are
    inspected; that approval gate is an admin concern and is not modelled here.
    """
    order = _get_owned_order(order_id, user, db)
    reason = (body.reason if body else None) or None

    if order.status != "delivered":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Only delivered orders can be returned (status: {order.status})."
            ),
        )

    order.return_requested_at = func.now()
    order.return_reason = reason
    lifecycle.transition(order, "returned", note=reason or "Return requested by customer")
    lifecycle.unwind(db, order, note="Refund issued for returned order")

    db.commit()
    db.refresh(order)
    return get_order(order_id, user=user, db=db)


@router.get("/orders/{order_id}/invoice")
def get_invoice(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    order = _get_owned_order(order_id, user, db)
    paid = next((p for p in order.payments if p.status == "success"), None)
    return {
        "invoice_number": order.order_number,
        "issued_at": order.created_at.isoformat() if order.created_at else None,
        "status": order.status,
        "seller": SELLER,
        "bill_to": order.shipping_address,
        "items": [
            {
                "name": i.product_name,
                "unit_price": float(i.unit_price),
                "quantity": i.quantity,
                "line_total": float(i.line_total),
            }
            for i in order.items
        ],
        "totals": {
            "subtotal": float(order.subtotal),
            "discount": float(order.discount),
            "tax": float(order.tax),
            "shipping": float(order.shipping),
            "total": float(order.total),
        },
        "coupon_code": order.coupon_code,
        "payment": _serialize_payment(paid) if paid else None,
    }
