"""Order pricing rules: tax, shipping, coupons. Pure functions — no DB or HTTP,
so they're trivially testable and the knobs live in one place.

Money is Decimal throughout, quantized to cents with ROUND_HALF_UP.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

TAX_RATE = Decimal("0.08")            # 8% sales tax on the post-discount subtotal
SHIPPING_FLAT = Decimal("5.99")       # flat shipping...
FREE_SHIPPING_OVER = Decimal("75")    # ...waived once subtotal reaches this

# Coupon config (not a DB table — Phase 3 keeps these as server config).
#   percent  : value is a fraction off the subtotal
#   flat     : value is a dollar amount off the subtotal
#   freeship : waives shipping
COUPONS = {
    "SAVE10": {"kind": "percent", "value": Decimal("0.10"), "min_subtotal": Decimal("0")},
    "WELCOME50": {"kind": "flat", "value": Decimal("50"), "min_subtotal": Decimal("100")},
    "FREESHIP": {"kind": "freeship", "value": Decimal("0"), "min_subtotal": Decimal("0")},
}


def money(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def apply_coupon(subtotal: Decimal, code: str | None):
    """Return (discount, free_shipping, error). An unknown or ineligible code
    yields a zero effect plus an error message; None/blank is simply no coupon."""
    if not code or not code.strip():
        return money(0), False, None
    coupon = COUPONS.get(code.strip().upper())
    if coupon is None:
        return money(0), False, "Invalid coupon code."
    if subtotal < coupon["min_subtotal"]:
        return money(0), False, f"Coupon requires a minimum subtotal of ${coupon['min_subtotal']}."

    kind = coupon["kind"]
    if kind == "percent":
        return money(subtotal * coupon["value"]), False, None
    if kind == "flat":
        return money(min(coupon["value"], subtotal)), False, None
    # freeship
    return money(0), True, None


@dataclass
class Quote:
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    shipping: Decimal
    total: Decimal
    coupon_code: str | None  # normalized applied code, or None if not applied
    coupon_error: str | None


def quote(subtotal, coupon_code: str | None = None) -> Quote:
    """Full price breakdown for a given subtotal. Tax applies to the
    post-discount amount; shipping is free over the threshold or with FREESHIP."""
    subtotal = money(subtotal)
    discount, free_shipping, error = apply_coupon(subtotal, coupon_code)

    taxable = subtotal - discount
    tax = money(taxable * TAX_RATE)
    if subtotal <= 0 or free_shipping or subtotal >= FREE_SHIPPING_OVER:
        shipping = money(0)
    else:
        shipping = SHIPPING_FLAT
    total = money(taxable + tax + shipping)

    applied = coupon_code.strip().upper() if (coupon_code and coupon_code.strip() and error is None) else None
    return Quote(subtotal, discount, tax, shipping, total, applied, error)
