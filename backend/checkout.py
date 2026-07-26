"""Checkout API: saved addresses, a price quote, and order creation from the
cart. All routes require auth.

Creating an order does NOT decrement stock or clear the cart — that happens on
successful payment (see payments module). Line prices and the shipping address
are snapshotted so a placed order is immutable.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

import pricing
from auth import get_current_user, get_db
from models import Address, CartItem, Order, OrderItem, Product, User

router = APIRouter(tags=["checkout"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AddressIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=32)
    line1: str = Field(min_length=1, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=128)
    state: str = Field(min_length=1, max_length=128)
    postal_code: str = Field(min_length=1, max_length=32)
    country: str = Field(default="US", max_length=64)


class AddressOut(AddressIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_default: bool


class CheckoutIn(BaseModel):
    address_id: int | None = None       # a saved address...
    address: AddressIn | None = None    # ...or a one-off inline address
    coupon_code: str | None = None


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def _address_snapshot(a) -> dict:
    # Works for both an Address model and an AddressIn (attribute access).
    return {
        "full_name": a.full_name,
        "phone": a.phone,
        "line1": a.line1,
        "line2": a.line2,
        "city": a.city,
        "state": a.state,
        "postal_code": a.postal_code,
        "country": a.country,
    }


def serialize_order(order: Order) -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "shipping_address": order.shipping_address,
        "subtotal": float(order.subtotal),
        "discount": float(order.discount),
        "tax": float(order.tax),
        "shipping": float(order.shipping),
        "total": float(order.total),
        "coupon_code": order.coupon_code,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "product_id": i.product_id,
                "name": i.product_name,
                "unit_price": float(i.unit_price),
                "quantity": i.quantity,
                "line_total": float(i.line_total),
            }
            for i in order.items
        ],
    }


def _cart_rows(db: Session, user_id: int):
    """The user's cart joined to products, oldest first."""
    return db.execute(
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.user_id == user_id)
        .order_by(CartItem.created_at, CartItem.id)
    ).all()


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------
@router.get("/addresses", response_model=list[AddressOut])
def list_addresses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Address).where(Address.user_id == user.id).order_by(Address.is_default.desc(), Address.id)
    ).all()


@router.post("/addresses", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
def create_address(body: AddressIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # The first address a user saves becomes their default.
    has_any = db.scalar(select(Address.id).where(Address.user_id == user.id).limit(1)) is not None
    address = Address(user_id=user.id, is_default=not has_any, **body.model_dump())
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


# ---------------------------------------------------------------------------
# Quote (dry-run price preview for the current cart)
# ---------------------------------------------------------------------------
@router.get("/checkout/quote")
def checkout_quote(
    coupon_code: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = _cart_rows(db, user.id)
    subtotal = sum((p.price * ci.quantity for ci, p in rows), Decimal("0"))
    q = pricing.quote(subtotal, coupon_code)
    return {
        "item_count": sum(ci.quantity for ci, _ in rows),
        "subtotal": float(q.subtotal),
        "discount": float(q.discount),
        "tax": float(q.tax),
        "shipping": float(q.shipping),
        "total": float(q.total),
        "coupon_code": q.coupon_code,
        "coupon_error": q.coupon_error,
    }


# ---------------------------------------------------------------------------
# Create order from cart
# ---------------------------------------------------------------------------
def _generate_order_number() -> str:
    return f"LENS-{uuid.uuid4().hex[:10].upper()}"


@router.post("/checkout", status_code=status.HTTP_201_CREATED)
def checkout(body: CheckoutIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = _cart_rows(db, user.id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your cart is empty.")

    # Resolve the shipping address (saved id or inline), snapshot it.
    if body.address_id is not None:
        address = db.scalar(
            select(Address).where(Address.id == body.address_id, Address.user_id == user.id)
        )
        if address is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
        snapshot = _address_snapshot(address)
    elif body.address is not None:
        snapshot = _address_snapshot(body.address)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A shipping address is required."
        )

    # Guard: everything must be in stock now (authoritative decrement is at payment).
    short = [
        p.product_display_name
        for ci, p in rows
        if not p.in_stock or p.stock_quantity < ci.quantity
    ]
    if short:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Insufficient stock for: {', '.join(short[:5])}",
        )

    subtotal = sum((p.price * ci.quantity for ci, p in rows), Decimal("0"))
    q = pricing.quote(subtotal, body.coupon_code)
    if body.coupon_code and q.coupon_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=q.coupon_error)

    order = Order(
        order_number=_generate_order_number(),
        user_id=user.id,
        status="pending",
        shipping_address=snapshot,
        subtotal=q.subtotal,
        discount=q.discount,
        tax=q.tax,
        shipping=q.shipping,
        total=q.total,
        coupon_code=q.coupon_code,
    )
    for ci, p in rows:
        order.items.append(
            OrderItem(
                product_id=p.id,
                product_name=p.product_display_name,
                unit_price=pricing.money(p.price),
                quantity=ci.quantity,
                line_total=pricing.money(p.price * ci.quantity),
            )
        )
    db.add(order)
    db.commit()
    db.refresh(order)
    return serialize_order(order)
