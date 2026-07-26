"""Cart API: per-user cart, persisted in cart_items. All routes require auth.

Every endpoint returns the full updated cart (items + totals) so the frontend
never needs a follow-up GET. Products are enriched through catalog's
serialize_product for a consistent shape across the storefront.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auth import get_current_user, get_db
from catalog import serialize_product
from models import CartItem, Product, User

router = APIRouter(prefix="/cart", tags=["cart"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AddToCartIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class UpdateQtyIn(BaseModel):
    # 0 is allowed and means "remove this line".
    quantity: int = Field(ge=0, le=99)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _serialize_cart(db: Session, user_id: int) -> dict:
    """The user's cart: enriched line items (with quantity + subtotal) + totals,
    ordered oldest-first for a stable display."""
    rows = db.execute(
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.user_id == user_id)
        .order_by(CartItem.created_at, CartItem.id)
    ).all()

    items = []
    total = Decimal("0")
    item_count = 0
    for cart_item, product in rows:
        subtotal = product.price * cart_item.quantity
        total += subtotal
        item_count += cart_item.quantity
        items.append(
            {
                **serialize_product(product),
                "quantity": cart_item.quantity,
                "subtotal": float(subtotal),
            }
        )
    return {"items": items, "item_count": item_count, "total": float(total)}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("")
def get_cart(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _serialize_cart(db, user.id)


@router.post("")
def add_to_cart(
    body: AddToCartIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if db.get(Product, body.product_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    existing = db.scalar(
        select(CartItem).where(
            CartItem.user_id == user.id, CartItem.product_id == body.product_id
        )
    )
    if existing is not None:
        # Increment rather than adding a second row (unique constraint anyway).
        existing.quantity = min(existing.quantity + body.quantity, 99)
    else:
        db.add(CartItem(user_id=user.id, product_id=body.product_id, quantity=body.quantity))
    db.commit()
    return _serialize_cart(db, user.id)


@router.patch("/{product_id}")
def update_quantity(
    product_id: int,
    body: UpdateQtyIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    item = db.scalar(
        select(CartItem).where(
            CartItem.user_id == user.id, CartItem.product_id == product_id
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not in cart")

    if body.quantity == 0:
        db.delete(item)  # setting quantity to 0 removes the line
    else:
        item.quantity = body.quantity
    db.commit()
    return _serialize_cart(db, user.id)


@router.delete("/{product_id}")
def remove_item(
    product_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # Idempotent: removing a line that isn't there still returns the cart.
    db.execute(
        delete(CartItem).where(
            CartItem.user_id == user.id, CartItem.product_id == product_id
        )
    )
    db.commit()
    return _serialize_cart(db, user.id)


@router.delete("")
def clear_cart(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    db.execute(delete(CartItem).where(CartItem.user_id == user.id))
    db.commit()
    return _serialize_cart(db, user.id)
