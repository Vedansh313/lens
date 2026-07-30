"""Admin user management (Phase 4, step 8). Every route requires is_admin.

What an admin can do here: find accounts, see what each one is worth and has
ordered, and disable or re-enable one.

What an admin deliberately CANNOT do here: grant or remove admin rights. That
stays in promote_admin.py, a shell tool on the machine running the database.
The reasoning is in that file's docstring and has not changed just because
there is now an admin API to hang it off — a privilege-escalation route is
exactly the thing not to expose over the network, and an admin panel is the
most attractive place to attack for it. Nothing here can raise anyone's
privileges, including the caller's.

Disabling is not deleting. Orders, payments and history must survive an account
being shut off, the email must stay taken, and users.id is referenced by half
the schema. So is_active is flipped and auth.py refuses the account from then
on; there is no user-delete endpoint and there should not be one.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from auth import get_db, require_admin
from models import Address, CartItem, Order, User, WishlistItem

router = APIRouter(
    prefix="/admin/users", tags=["admin", "users"],
    dependencies=[Depends(require_admin)],
)

# Order statuses that represent money the business actually kept. Excludes
# pending (never paid) and the three unwound states, so "total spent" matches
# what a refund report would say rather than counting cancelled orders as
# revenue.
REVENUE_STATUSES = ("paid", "shipped", "delivered")


def _revenue_case():
    """SUM(total) but only over orders that count as revenue."""
    return func.coalesce(
        func.sum(case((Order.status.in_(REVENUE_STATUSES), Order.total), else_=0)), 0
    )


def _user_row(u: User, orders: int, spent, last_order) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "is_admin": u.is_admin,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "order_count": int(orders or 0),
        "total_spent": float(spent or 0),
        "last_order_at": last_order.isoformat() if last_order else None,
        # Only meaningful while disabled; all three are cleared on re-enable.
        "deactivated_at": u.deactivated_at.isoformat() if u.deactivated_at else None,
        "deactivated_by_user_id": u.deactivated_by_user_id,
        "deactivation_reason": u.deactivation_reason,
    }


@router.get("")
def list_users(
    q: Optional[str] = Query(default=None, min_length=1, description="email or name"),
    is_admin: Optional[bool] = Query(default=None),
    active: Optional[bool] = Query(default=None),
    sort: Literal["created", "spent", "orders", "email"] = Query(default="created"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Accounts with their order counts and lifetime value.

    The aggregates come from one LEFT JOIN + GROUP BY rather than a query per
    user — this is the list view, so the per-row version would be 50 queries a
    page. LEFT so an account that has never ordered still appears, which is
    precisely who you are looking for when auditing signups.
    """
    filters = []
    if q:
        term = f"%{q}%"
        filters.append(User.email.ilike(term) | User.name.ilike(term))
    if is_admin is not None:
        filters.append(User.is_admin.is_(is_admin))
    if active is not None:
        filters.append(User.is_active.is_(active))

    order_count = func.count(Order.id)
    spent = _revenue_case()
    last_order = func.max(Order.created_at)

    sort_by = {
        "created": User.created_at.desc(),
        "email": User.email.asc(),
        "spent": spent.desc(),
        "orders": order_count.desc(),
    }[sort]

    total = db.scalar(select(func.count(User.id)).where(*filters))
    rows = db.execute(
        select(User, order_count, spent, last_order)
        .outerjoin(Order, Order.user_id == User.id)
        .where(*filters)
        .group_by(User.id)
        .order_by(sort_by, User.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "users": [_user_row(u, n, s, last) for u, n, s, last in rows],
    }


@router.get("/summary")
def users_summary(db: Session = Depends(get_db)) -> dict:
    """Headline account counts for the dashboard."""
    total, admins, disabled = db.execute(
        select(
            func.count(User.id),
            func.count(case((User.is_admin, 1))),
            func.count(case((User.is_active.is_(False), 1))),
        )
    ).one()
    with_orders = db.scalar(select(func.count(func.distinct(Order.user_id))))
    return {
        "total_users": total,
        "admins": admins,
        "disabled": disabled,
        "active": total - disabled,
        "with_orders": with_orders,
    }


@router.get("/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)) -> dict:
    """One account in full: totals, recent orders and what it has saved.

    password_hash is never returned — not to an admin either. There is nothing
    an admin can do with it that is not either useless or an attack.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    n, spent, last = db.execute(
        select(func.count(Order.id), _revenue_case(), func.max(Order.created_at))
        .where(Order.user_id == user_id)
    ).one()

    recent = db.scalars(
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(10)
    ).all()

    by_status = dict(
        db.execute(
            select(Order.status, func.count(Order.id))
            .where(Order.user_id == user_id)
            .group_by(Order.status)
        ).all()
    )

    return {
        **_user_row(user, n, spent, last),
        "orders_by_status": by_status,
        "recent_orders": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "status": o.status,
                "total": float(o.total),
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in recent
        ],
        # Engagement counts, the cheap version: how much is parked in this
        # account right now. Useful for spotting an abandoned cart worth
        # chasing, and for telling a real signup from a throwaway.
        "saved": {
            "addresses": db.scalar(
                select(func.count(Address.id)).where(Address.user_id == user_id)
            ),
            "cart_items": db.scalar(
                select(func.count(CartItem.id)).where(CartItem.user_id == user_id)
            ),
            "wishlist_items": db.scalar(
                select(func.count(WishlistItem.id)).where(WishlistItem.user_id == user_id)
            ),
        },
    }


class ActiveIn(BaseModel):
    """Note what is absent: there is no is_admin here, and no route that takes
    one. Privileges are not editable over HTTP — see the module docstring."""

    is_active: bool
    # Recorded on the user row when disabling; ignored (and cleared) when
    # re-enabling, since it would describe a state the account is leaving.
    reason: Optional[str] = Field(default=None, max_length=255)


@router.post("/{user_id}/active")
def set_user_active(
    user_id: int,
    body: ActiveIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Disable or re-enable an account.

    Two refusals, both mirroring promote_admin.py's refusal to strip the last
    admin — an admin panel must not be able to lock everyone out of itself:

      * you cannot disable your own account (immediate self-lockout), and
      * you cannot disable the last active admin (lockout for everyone, fixable
        only by someone with shell access remembering this tool exists).

    Disabling takes effect on the account's very next request, because
    auth.get_current_user re-reads the flag rather than trusting the token.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_active == body.is_active:
        return {
            "user": _summary_after_change(db, user),
            "changed": False,
            "message": f"{user.email} was already {'active' if body.is_active else 'disabled'}.",
        }

    if not body.is_active:
        if user.id == admin.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You cannot disable your own account.",
            )
        if user.is_admin:
            others = db.scalar(
                select(func.count(User.id)).where(
                    User.is_admin, User.is_active, User.id != user.id
                )
            )
            if not others:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Refusing to disable {user.email}: they are the only active "
                        "admin. Promote someone else first (promote_admin.py)."
                    ),
                )

    user.is_active = body.is_active
    if body.is_active:
        # Cleared on re-enable so a stale reason can never be read as describing
        # a live account.
        user.deactivated_at = None
        user.deactivated_by_user_id = None
        user.deactivation_reason = None
    else:
        user.deactivated_at = func.now()
        user.deactivated_by_user_id = admin.id
        user.deactivation_reason = body.reason

    db.commit()
    db.refresh(user)
    return {
        "user": _summary_after_change(db, user),
        "changed": True,
        "message": f"{user.email} is now {'active' if user.is_active else 'disabled'}.",
    }


def _summary_after_change(db: Session, user: User) -> dict:
    """The user row as the list view would show it, for the response body."""
    n, spent, last = db.execute(
        select(func.count(Order.id), _revenue_case(), func.max(Order.created_at))
        .where(Order.user_id == user.id)
    ).one()
    return _user_row(user, n, spent, last)
