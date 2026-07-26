"""add full-text + trigram search to products

Revision ID: d3e8f1a2b6c7
Revises: 9c1f7a2b5e04
Create Date: 2026-07-26

Adds a STORED generated tsvector column (name + article type + colour) with a
GIN index for full-text search, plus the pg_trgm extension and a trigram GIN
index on the product name for fuzzy/typo matching. Powers GET /products?q= and
GET /autocomplete.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d3e8f1a2b6c7"
down_revision: Union[str, Sequence[str], None] = "9c1f7a2b5e04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TSVECTOR = (
    "to_tsvector('english'::regconfig, "
    "coalesce(product_display_name, '') || ' ' || "
    "coalesce(article_type, '') || ' ' || "
    "coalesce(base_colour, ''))"
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column(
        "products",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(_TSVECTOR, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_products_search_vector", "products", ["search_vector"], postgresql_using="gin"
    )
    op.create_index(
        "ix_products_name_trgm",
        "products",
        ["product_display_name"],
        postgresql_using="gin",
        postgresql_ops={"product_display_name": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_products_name_trgm", table_name="products")
    op.drop_index("ix_products_search_vector", table_name="products")
    op.drop_column("products", "search_vector")
    # pg_trgm is left installed — dropping an extension other objects may use is
    # riskier than leaving it; remove manually if truly unwanted.
