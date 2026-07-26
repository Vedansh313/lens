"""add commerce columns (price, in_stock) to products

Revision ID: 9c1f7a2b5e04
Revises: a9dd71427d79
Create Date: 2026-07-26

The source fashion dataset has no price or stock. Rather than fabricate these on
the frontend (which makes cart totals meaningless and price sorting impossible),
we add real columns and backfill them DETERMINISTICALLY from the product id via
md5 — so every environment computes identical, stable values with no seed file.

    price    : $20.00 .. $499.98, from the id hash.
    in_stock : ~90% true, from an independently-salted id hash.

Sequence: add nullable price + in_stock(default true) -> backfill both ->
promote price to NOT NULL -> index price (a primary catalog sort/filter axis).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c1f7a2b5e04"
down_revision: Union[str, Sequence[str], None] = "a9dd71427d79"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Deterministic hash of id -> a non-negative 60-bit bigint. 15 hex chars = 60
# bits, which always fits a signed bigint as a positive value.
_HASH = "('x' || left(md5({expr}), 15))::bit(60)::bigint"
_PRICE_EXPR = f"round((20 + (({_HASH.format(expr='id::text')}) % 48000) / 100.0)::numeric, 2)"
_STOCK_EXPR = f"(({_HASH.format(expr=chr(39) + 'stk' + chr(39) + ' || id::text')}) % 10 <> 0)"


def upgrade() -> None:
    op.add_column("products", sa.Column("price", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "products",
        sa.Column("in_stock", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )

    # Backfill in bulk (single UPDATE each), then lock price down as NOT NULL.
    op.execute(f"UPDATE products SET price = {_PRICE_EXPR}")
    op.execute(f"UPDATE products SET in_stock = {_STOCK_EXPR}")
    op.alter_column("products", "price", nullable=False)

    op.create_index("ix_products_price", "products", ["price"])


def downgrade() -> None:
    op.drop_index("ix_products_price", table_name="products")
    op.drop_column("products", "in_stock")
    op.drop_column("products", "price")
