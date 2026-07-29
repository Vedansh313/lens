"""Order lifecycle: transition rules, history recording, restock, refunds (Phase 4).

Every status change in the system goes through transition() so that no path can
move an order without leaving an order_status_history row behind. checkout.py
records the order's creation, payments.py records pending -> paid, and the
customer-facing cancel/return endpoints live in orders.py.

The legal moves are declared once, below. Statuses themselves come from
models.ORDER_STATUSES, which also backs the ck_orders_status_valid CHECK, so an
illegal status cannot reach the database even if a caller bypasses this module.

Money and stock are simulated exactly as the original charge is (see
payments.py): no funds move, but refunds get a traceable reference and stock is
genuinely returned to products.stock_quantity.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Order, OrderStatusHistory, Payment, Product

# from_status -> the statuses it may move to. A status absent from a value set
# is unreachable from that state; 'refunded' is terminal.
#
# Deliberately NOT allowed: shipped -> cancelled (it has already left the
# warehouse; that path is a return), and any move out of 'refunded'.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"paid", "cancelled"},
    "paid": {"shipped", "cancelled"},
    "shipped": {"delivered"},
    "delivered": {"returned"},
    "cancelled": {"refunded"},
    "returned": {"refunded"},
    "refunded": set(),
}

# Statuses that stamp a one-time timestamp column on the order.
_TIMESTAMP_COLUMN = {
    "shipped": "shipped_at",
    "delivered": "delivered_at",
    "cancelled": "cancelled_at",
}


def record_creation(order: Order) -> None:
    """Append the genesis history row for a newly created order.

    from_status is NULL here and only here — it marks the start of the trail.
    Called by checkout.py before the order is committed, so the history exists
    from the order's first moment rather than being inferred later.
    """
    order.status_history.append(
        OrderStatusHistory(from_status=None, to_status=order.status, note="Order placed")
    )


def transition(
    order: Order,
    to_status: str,
    *,
    note: str | None = None,
    actor_id: int | None = None,
) -> None:
    """Move `order` to `to_status`, recording it. Raises 409 if the move is illegal.

    Does not commit — the caller owns the transaction, so a transition always
    lands atomically with whatever else it implies (stock, refunds, cart).

    actor_id is the admin who acted, or None when the change came from the
    customer or the system.
    """
    allowed = ALLOWED_TRANSITIONS.get(order.status, set())
    if to_status not in allowed:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot move an order from '{order.status}' to '{to_status}'."
                + (f" Allowed from here: {', '.join(sorted(allowed))}." if allowed else
                   f" '{order.status}' is final.")
            ),
        )

    order.status_history.append(
        OrderStatusHistory(
            from_status=order.status,
            to_status=to_status,
            note=note,
            changed_by_user_id=actor_id,
        )
    )

    column = _TIMESTAMP_COLUMN.get(to_status)
    # Set once: a status is only entered once, but guarding keeps the first
    # occurrence authoritative if that ever stops being true.
    if column and getattr(order, column) is None:
        setattr(order, column, func.now())

    order.status = to_status


def stock_was_taken(order: Order) -> bool:
    """True if this order's stock has been decremented and not yet returned.

    Stock comes off at payment (payments.py), so it is exactly the orders that
    reached a successful payment. A payment refunded by this module has already
    had its stock returned, hence 'success' only.
    """
    return any(p.status == "success" for p in order.payments)


def restock(db: Session, order: Order) -> list[tuple[int, int]]:
    """Return this order's quantities to product stock. Returns (product_id, qty).

    Rows are locked before update for the same reason payments.py locks them on
    the way down — two concurrent cancels must not interleave a read-modify-write.
    Lines whose product was deleted since the order (product_id NULL) are skipped.
    """
    restocked: list[tuple[int, int]] = []
    for item in order.items:
        if item.product_id is None:
            continue
        product = db.scalar(
            select(Product).where(Product.id == item.product_id).with_for_update()
        )
        if product is None:
            continue
        product.stock_quantity += item.quantity
        product.in_stock = product.stock_quantity > 0
        restocked.append((product.id, item.quantity))
    return restocked


def refund(order: Order) -> Payment | None:
    """Mark this order's successful payment refunded. Returns it, or None.

    The successful payment row is flipped in place rather than a second row
    being written, so an order never has two payments that look like money
    received (orders.py:_latest_payment_status depends on this).
    """
    paid = next((p for p in order.payments if p.status == "success"), None)
    if paid is None:
        return None
    paid.status = "refunded"
    paid.refunded_at = func.now()
    paid.refund_ref = f"RFND-{uuid.uuid4().hex[:12].upper()}"
    return paid


def unwind(
    db: Session,
    order: Order,
    *,
    note: str | None = None,
    actor_id: int | None = None,
) -> Payment | None:
    """Return stock and money for an order leaving the fulfilment path.

    Shared by cancel and return: both need the same two things to happen, and
    both then move the order to 'refunded' if money had actually been taken.
    An unpaid order stops at cancelled — there is nothing to refund.
    """
    if not stock_was_taken(order):
        return None
    restock(db, order)
    refunded = refund(order)
    if refunded is not None:
        transition(order, "refunded", note=note, actor_id=actor_id)
    return refunded
