"""Simulated payment gateway (Phase 3). Auth-protected.

IMPORTANT: this is a demo simulation — no real funds move. Card input is
format-validated (Luhn + length) but only the last 4 digits are ever stored;
the full PAN and CVV are never persisted or logged.

On a successful payment we ATOMICALLY (one transaction): record the payment,
mark the order paid, decrement product stock, and clear the buyer's cart.

Deterministic failure hooks (for testing the decline path without randomness):
    UPI id  == "fail@test"
    card ending in 0002   (e.g. 4000 0000 0000 0002 — Luhn-valid decline)
    wallet  == "fail"
"""
from __future__ import annotations

import re
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import lifecycle
from auth import get_current_user, get_db
from checkout import serialize_order
from models import CartItem, Order, Payment, Product, User

router = APIRouter(tags=["payments"])

_UPI_RE = re.compile(r"^[a-zA-Z0-9._-]{2,}@[a-zA-Z]{2,}$")


class PaymentIn(BaseModel):
    method: Literal["upi", "card", "wallet"]
    # upi
    upi_id: Optional[str] = None
    # card
    card_number: Optional[str] = None
    expiry: Optional[str] = None
    cvv: Optional[str] = None
    card_name: Optional[str] = None
    # wallet
    wallet: Optional[str] = None


def _luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    total, parity = 0, len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _bad_request(msg: str):
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)


def _validate_and_mask(body: PaymentIn) -> tuple[dict, bool]:
    """Validate the method-specific fields. Returns (masked_detail, decline)
    where `decline` triggers the deterministic failure path."""
    if body.method == "upi":
        upi = (body.upi_id or "").strip()
        if not _UPI_RE.match(upi):
            _bad_request("Enter a valid UPI id, e.g. name@bank.")
        return {"upi_id": upi}, upi.lower() == "fail@test"

    if body.method == "card":
        digits = re.sub(r"\D", "", body.card_number or "")
        if not _luhn_ok(digits):
            _bad_request("Enter a valid card number.")
        if not re.match(r"^\d{2}/\d{2}$", (body.expiry or "").strip()):
            _bad_request("Enter expiry as MM/YY.")
        if not re.match(r"^\d{3,4}$", (body.cvv or "").strip()):
            _bad_request("Enter a valid CVV.")
        # Store ONLY the last 4 digits — never the full PAN or the CVV.
        return {"last4": digits[-4:], "name": (body.card_name or "").strip() or None}, digits.endswith("0002")

    # wallet
    wallet = (body.wallet or "").strip()
    if not wallet:
        _bad_request("Choose a wallet provider.")
    return {"wallet": wallet}, wallet.lower() == "fail"


def _serialize_payment(p: Payment) -> dict:
    return {
        "id": p.id,
        "method": p.method,
        "status": p.status,
        "amount": float(p.amount),
        "transaction_ref": p.transaction_ref,
        "detail": p.detail,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.post("/orders/{order_id}/pay")
def pay_order(
    order_id: int,
    body: PaymentIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order is not awaiting payment (status: {order.status}).",
        )

    detail, decline = _validate_and_mask(body)
    txn_ref = f"TXN-{uuid.uuid4().hex[:12].upper()}"

    # --- Declined: record the failed attempt, leave the order pending. ---
    if decline:
        db.add(Payment(
            order_id=order.id, method=body.method, status="failed",
            amount=order.total, transaction_ref=txn_ref, detail=detail,
        ))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Payment was declined. Please try another method.",
        )

    # --- Success path: everything below commits as one transaction. ---
    # Re-check + lock stock right before decrementing (guards against selling
    # out between checkout and payment).
    to_decrement = []
    for item in order.items:
        if item.product_id is None:
            continue  # product was deleted since the order was placed
        product = db.scalar(
            select(Product).where(Product.id == item.product_id).with_for_update()
        )
        if product is None:
            continue
        if product.stock_quantity < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient stock for {item.product_name}.",
            )
        to_decrement.append((product, item.quantity))

    for product, qty in to_decrement:
        product.stock_quantity -= qty
        product.in_stock = product.stock_quantity > 0

    payment = Payment(
        order_id=order.id, method=body.method, status="success",
        amount=order.total, transaction_ref=txn_ref, detail=detail,
    )
    db.add(payment)
    # Records the pending -> paid history row as well as setting the status.
    lifecycle.transition(order, "paid", note=f"Payment {txn_ref} succeeded")
    db.execute(delete(CartItem).where(CartItem.user_id == user.id))  # clear the cart
    db.commit()
    db.refresh(order)
    db.refresh(payment)

    return {"status": "success", "order": serialize_order(order), "payment": _serialize_payment(payment)}
