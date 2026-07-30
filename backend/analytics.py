"""Admin analytics (Phase 4, step 9). Every route requires is_admin.

Read-only aggregation over orders, order_items, payments and the lifecycle
timestamps Phase 4 added. Nothing here writes, and nothing here is allowed to
invent a second definition of revenue — that lives in models.REVENUE_STATUSES
and every figure below is built on it.

Three things worth knowing before reading the queries:

* Every endpoint takes the same date window (`start`/`end`, default the last 30
  days) and filters on orders.created_at, i.e. when the order was PLACED. An
  order placed in the window and delivered after it still counts here. The
  alternative — attributing revenue to the day money moved — would make a
  completed day's figures keep changing, which is worse for a dashboard.

* Time series are gap-filled with generate_series. A day with no orders comes
  back as an explicit zero rather than a missing key, because a chart that
  silently skips empty days misreads as "flat" instead of "dead".

* Aggregation happens in Postgres, not Python. These endpoints run over every
  order in the range, and the row-by-row version would fall over as soon as the
  catalogue sees real traffic.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, literal, select, text
from sqlalchemy.orm import Session

from auth import get_db, require_admin
from models import ORDER_STATUSES, REVENUE_STATUSES, Order, OrderItem, Payment, User

router = APIRouter(
    prefix="/admin/analytics", tags=["admin", "analytics"],
    dependencies=[Depends(require_admin)],
)

DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 731  # two years; guards against a generate_series bomb


# ---------------------------------------------------------------------------
# Shared window handling
# ---------------------------------------------------------------------------
class Window:
    """A resolved [start, end) date range, plus the equal-length span before it.

    `end` is exclusive and rounded up to the start of the day after the one the
    caller asked for, so "to 2026-07-31" includes everything that happened on
    the 31st rather than only the instant at midnight — an off-by-one that would
    quietly drop the most recent day, the one anyone looking at a dashboard
    cares about most.
    """

    def __init__(self, start: date, end: date):
        self.start_date = start
        self.end_date = end
        self.start = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        self.end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        span = self.end - self.start
        # Immediately preceding window of identical length, for period-on-period
        # comparison. Same length matters: comparing a 30-day span against a
        # 31-day one produces a "trend" that is really just the calendar.
        self.prev_start = self.start - span
        self.prev_end = self.start

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def as_dict(self) -> dict:
        return {
            "start": self.start_date.isoformat(),
            "end": self.end_date.isoformat(),
            "days": self.days,
        }


def get_window(
    start: Optional[date] = Query(default=None, description="inclusive, YYYY-MM-DD"),
    end: Optional[date] = Query(default=None, description="inclusive, YYYY-MM-DD"),
) -> Window:
    """Resolve the date window shared by every endpoint here."""
    today = datetime.now(timezone.utc).date()
    end = end or today
    start = start or (end - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'start' must not be after 'end'.",
        )
    if (end - start).days + 1 > MAX_WINDOW_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Window too large: at most {MAX_WINDOW_DAYS} days.",
        )
    return Window(start, end)


def _revenue_sum():
    """SUM(total) restricted to orders that count as revenue."""
    return func.coalesce(
        func.sum(case((Order.status.in_(REVENUE_STATUSES), Order.total), else_=0)), 0
    )


def _revenue_count():
    """COUNT of orders that count as revenue (the AOV denominator)."""
    return func.count(case((Order.status.in_(REVENUE_STATUSES), Order.id)))


def _totals(db: Session, lo: datetime, hi: datetime) -> dict:
    """The headline figures for one window. Used twice per overview call."""
    row = db.execute(
        select(
            func.count(Order.id),
            _revenue_count(),
            _revenue_sum(),
            func.count(func.distinct(Order.user_id)),
            func.count(case((Order.status == "cancelled", Order.id))),
            func.count(case((Order.status.in_(("returned", "refunded")), Order.id))),
        ).where(Order.created_at >= lo, Order.created_at < hi)
    ).one()
    orders, paid_orders, revenue, customers, cancelled, returned = row
    revenue = float(revenue or 0)
    return {
        "orders": orders,
        "paid_orders": paid_orders,
        "revenue": round(revenue, 2),
        # Average order value over PAID orders only. Dividing by all orders
        # would let a pile of abandoned pending orders drag AOV toward zero.
        "average_order_value": round(revenue / paid_orders, 2) if paid_orders else 0.0,
        "customers": customers,
        "cancelled": cancelled,
        "returned": returned,
    }


def _pct_change(now: float, before: float) -> Optional[float]:
    """Percent change, or None when there is no baseline to compare against.

    None rather than 0 or 100: growth from zero is undefined, and rendering it
    as "+100%" would read as a real measurement instead of a missing one.
    """
    if not before:
        return None
    return round((now - before) / before * 100, 1)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/overview")
def overview(window: Window = Depends(get_window), db: Session = Depends(get_db)) -> dict:
    """Headline KPIs for the window, each against the preceding window."""
    current = _totals(db, window.start, window.end)
    previous = _totals(db, window.prev_start, window.prev_end)

    comparable = ("orders", "paid_orders", "revenue", "average_order_value", "customers")
    return {
        "window": window.as_dict(),
        "current": current,
        "previous": previous,
        "change_pct": {k: _pct_change(current[k], previous[k]) for k in comparable},
        # Rates over all orders placed, which is the question being asked:
        # "of what we took, how much came back?"
        "rates": {
            "cancellation_pct": round(current["cancelled"] / current["orders"] * 100, 1)
            if current["orders"] else 0.0,
            "return_pct": round(current["returned"] / current["orders"] * 100, 1)
            if current["orders"] else 0.0,
            "conversion_to_paid_pct": round(current["paid_orders"] / current["orders"] * 100, 1)
            if current["orders"] else 0.0,
        },
    }


@router.get("/revenue")
def revenue_series(
    bucket: Literal["day", "week", "month"] = Query(default="day"),
    window: Window = Depends(get_window),
    db: Session = Depends(get_db),
) -> dict:
    """Revenue and order counts over time, gap-filled.

    The LEFT JOIN onto generate_series is what produces zero rows for quiet
    days. Doing it in SQL rather than patching holes in Python keeps one
    definition of "which bucket does this order fall in" — date_trunc's — for
    both the data and the axis.
    """
    # Series bounds come from the INCLUSIVE last day, not window.end (which is
    # exclusive). Using the exclusive end emits one bucket past the window —
    # a trailing empty day, or a whole spurious month on a month bucket.
    last_day = datetime.combine(window.end_date, datetime.min.time(), tzinfo=timezone.utc)
    buckets = (
        select(
            func.generate_series(
                func.date_trunc(bucket, literal(window.start, type_=Order.created_at.type)),
                func.date_trunc(bucket, literal(last_day, type_=Order.created_at.type)),
                text(f"'1 {bucket}'::interval"),
            ).label("bucket")
        )
        .subquery()
    )

    ordered = (
        select(
            func.date_trunc(bucket, Order.created_at).label("bucket"),
            func.count(Order.id).label("orders"),
            _revenue_count().label("paid_orders"),
            _revenue_sum().label("revenue"),
        )
        .where(Order.created_at >= window.start, Order.created_at < window.end)
        .group_by(text("1"))
        .subquery()
    )

    rows = db.execute(
        select(
            buckets.c.bucket,
            func.coalesce(ordered.c.orders, 0),
            func.coalesce(ordered.c.paid_orders, 0),
            func.coalesce(ordered.c.revenue, 0),
        )
        .select_from(buckets.outerjoin(ordered, ordered.c.bucket == buckets.c.bucket))
        .order_by(buckets.c.bucket)
    ).all()

    points = [
        {
            "bucket": b.date().isoformat(),
            "orders": o,
            "paid_orders": p,
            "revenue": round(float(r or 0), 2),
        }
        for b, o, p, r in rows
    ]
    return {
        "window": window.as_dict(),
        "bucket": bucket,
        "points": points,
        "totals": {
            "orders": sum(p["orders"] for p in points),
            "paid_orders": sum(p["paid_orders"] for p in points),
            "revenue": round(sum(p["revenue"] for p in points), 2),
        },
    }


@router.get("/orders")
def order_breakdown(
    window: Window = Depends(get_window), db: Session = Depends(get_db)
) -> dict:
    """Where orders placed in this window currently stand, plus payment mix.

    A snapshot of CURRENT status, not a funnel over time: an order counted under
    'delivered' also passed through paid and shipped. order_status_history holds
    the timeline if a true funnel is ever needed.
    """
    by_status = dict(
        db.execute(
            select(Order.status, func.count(Order.id))
            .where(Order.created_at >= window.start, Order.created_at < window.end)
            .group_by(Order.status)
        ).all()
    )
    # Every status present, so a chart's categories do not shift as states
    # empty out between refreshes.
    statuses = {s: by_status.get(s, 0) for s in ORDER_STATUSES}

    by_method = db.execute(
        select(
            Payment.method,
            func.count(Payment.id),
            func.count(case((Payment.status == "success", Payment.id))),
            func.count(case((Payment.status == "failed", Payment.id))),
            func.count(case((Payment.status == "refunded", Payment.id))),
            func.coalesce(
                func.sum(case((Payment.status == "success", Payment.amount), else_=0)), 0
            ),
        )
        .join(Order, Order.id == Payment.order_id)
        .where(Order.created_at >= window.start, Order.created_at < window.end)
        .group_by(Payment.method)
        .order_by(func.count(Payment.id).desc())
    ).all()

    return {
        "window": window.as_dict(),
        "by_status": statuses,
        "total": sum(statuses.values()),
        "payments": [
            {
                "method": m,
                "attempts": n,
                "successful": ok,
                "failed": bad,
                "refunded": ref,
                "collected": round(float(amt or 0), 2),
                "success_rate_pct": round(ok / n * 100, 1) if n else 0.0,
            }
            for m, n, ok, bad, ref, amt in by_method
        ],
    }


@router.get("/products")
def top_products(
    metric: Literal["revenue", "units"] = Query(default="revenue"),
    limit: int = Query(default=20, ge=1, le=100),
    window: Window = Depends(get_window),
    db: Session = Depends(get_db),
) -> dict:
    """Best sellers by revenue or units, over revenue-counting orders only.

    Grouped by the order line's product_name snapshot as well as product_id, so
    a line whose product was deleted (product_id NULL) still reports under the
    name it sold as instead of vanishing from the totals.
    """
    units = func.sum(OrderItem.quantity).label("units")
    revenue = func.sum(OrderItem.line_total).label("revenue")

    rows = db.execute(
        select(
            OrderItem.product_id,
            OrderItem.product_name,
            units,
            revenue,
            func.count(func.distinct(OrderItem.order_id)).label("orders"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.created_at >= window.start,
            Order.created_at < window.end,
            Order.status.in_(REVENUE_STATUSES),
        )
        .group_by(OrderItem.product_id, OrderItem.product_name)
        .order_by((revenue if metric == "revenue" else units).desc())
        .limit(limit)
    ).all()

    return {
        "window": window.as_dict(),
        "metric": metric,
        "products": [
            {
                "product_id": pid,
                "name": name,
                "units": int(u or 0),
                "revenue": round(float(r or 0), 2),
                "orders": n,
                # False for a line whose product row is gone; the sale still
                # counts, but there is nothing left to link to.
                "product_exists": pid is not None,
            }
            for pid, name, u, r, n in rows
        ],
    }


@router.get("/fulfilment")
def fulfilment(window: Window = Depends(get_window), db: Session = Depends(get_db)) -> dict:
    """How long orders take to ship and arrive, from the Phase 4 timestamps.

    Averages are over orders that actually reached the milestone, so an order
    still in transit does not count as a fast delivery. Both figures are in
    hours; EXTRACT(EPOCH) / 3600 rather than a Python loop over every order.
    """
    hours = lambda a, b: func.avg(func.extract("epoch", a - b) / 3600.0)  # noqa: E731

    row = db.execute(
        select(
            func.count(case((Order.shipped_at.isnot(None), Order.id))),
            func.count(case((Order.delivered_at.isnot(None), Order.id))),
            hours(Order.shipped_at, Order.created_at),
            hours(Order.delivered_at, Order.shipped_at),
            hours(Order.delivered_at, Order.created_at),
            func.count(
                case((and_(Order.status.in_(REVENUE_STATUSES), Order.shipped_at.is_(None)), Order.id))
            ),
        ).where(Order.created_at >= window.start, Order.created_at < window.end)
    ).one()
    shipped, delivered, to_ship, ship_to_deliver, end_to_end, awaiting = row

    def h(v):
        return round(float(v), 1) if v is not None else None

    return {
        "window": window.as_dict(),
        "shipped_orders": shipped,
        "delivered_orders": delivered,
        # None, not 0, when nothing has reached the milestone yet — "no data"
        # and "instant" must not look the same.
        "avg_hours_to_ship": h(to_ship),
        "avg_hours_ship_to_deliver": h(ship_to_deliver),
        "avg_hours_end_to_end": h(end_to_end),
        # Paid but not yet shipped: the admin's actual work queue.
        "awaiting_shipment": awaiting,
    }


@router.get("/customers")
def customers(window: Window = Depends(get_window), db: Session = Depends(get_db)) -> dict:
    """New vs returning buyers, and who spends the most.

    "New" means the customer's FIRST EVER order falls in this window — computed
    against all of history, not just the window, so someone who bought last year
    and again today is correctly counted as returning rather than new.
    """
    first_order = (
        select(Order.user_id, func.min(Order.created_at).label("first_at"))
        .group_by(Order.user_id)
        .subquery()
    )

    new_customers, returning = db.execute(
        select(
            func.count(
                func.distinct(
                    case(
                        (
                            and_(
                                first_order.c.first_at >= window.start,
                                first_order.c.first_at < window.end,
                            ),
                            Order.user_id,
                        )
                    )
                )
            ),
            func.count(
                func.distinct(
                    case((first_order.c.first_at < window.start, Order.user_id))
                )
            ),
        )
        .select_from(Order)
        .join(first_order, first_order.c.user_id == Order.user_id)
        .where(Order.created_at >= window.start, Order.created_at < window.end)
    ).one()

    spend = _revenue_sum().label("spent")
    top = db.execute(
        select(User.id, User.email, User.name, func.count(Order.id), spend)
        .join(Order, Order.user_id == User.id)
        .where(Order.created_at >= window.start, Order.created_at < window.end)
        .group_by(User.id)
        .order_by(spend.desc())
        .limit(10)
    ).all()

    return {
        "window": window.as_dict(),
        "new_customers": new_customers,
        "returning_customers": returning,
        "total_customers": new_customers + returning,
        "top_customers": [
            {
                "user_id": uid,
                "email": email,
                "name": name,
                "orders": n,
                "spent": round(float(s or 0), 2),
            }
            for uid, email, name, n, s in top
        ],
    }
