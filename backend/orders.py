"""Order retrieval + invoice (Phase 3). Read-only, auth-protected, owner-scoped.

The invoice is returned as structured JSON; the frontend renders the printable
layout (per the Phase 3 invoice choice), so the backend needs no PDF dependency.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user, get_db
from checkout import serialize_order
from models import Order, User

router = APIRouter(tags=["orders"])

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
    }


def _latest_payment_status(order: Order) -> str:
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
            }
            for o in orders
        ]
    }


@router.get("/orders/{order_id}")
def get_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    order = _get_owned_order(order_id, user, db)
    data = serialize_order(order)
    data["payments"] = [_serialize_payment(p) for p in order.payments]
    return data


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
