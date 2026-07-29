"""Catalog API: product listing/detail + facet lists. Read-only, no auth.

Mounted in server.py via include_router. The product serialization here is the
single shape returned across the storefront (catalog, and later cart/wishlist),
so all product payloads stay consistent. AI search pipeline is untouched.
"""
from __future__ import annotations

import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from auth import get_db  # reuse the request-scoped session dependency
from models import Product

# Same base URL server.py uses to build image links (backend/images/{id}.jpg).
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "http://localhost:8000")

router = APIRouter(tags=["catalog"])


# ---------------------------------------------------------------------------
# Serialization (shared shape for every product payload)
# ---------------------------------------------------------------------------
def _image_url(product_id: int) -> str:
    return f"{IMAGE_BASE_URL}/images/{product_id}.jpg"


def serialize_product(p: Product) -> dict:
    """Card-level fields, camelCase to match the frontend components."""
    return {
        "id": p.id,
        "name": p.product_display_name,
        "category": p.master_category,   # API "category" == masterCategory
        "subCategory": p.article_type,   # API "subCategory" == articleType (see model)
        "colour": p.base_colour,
        "gender": p.gender,
        "price": float(p.price),
        "inStock": p.in_stock,
        "image_url": _image_url(p.id),
    }


def serialize_product_detail(p: Product) -> dict:
    """Card fields plus the catalogue detail the product modal can show."""
    return {
        **serialize_product(p),
        "season": p.season,
        "year": p.year,
        "usage": p.usage,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
_SORTS = {
    "id": asc(Product.id),
    "price_asc": asc(Product.price),
    "price_desc": desc(Product.price),
    "name": asc(Product.product_display_name),
}


@router.get("/products")
def list_products(
    category: Optional[str] = None,
    article_type: Optional[str] = None,
    colour: Optional[str] = None,
    gender: Optional[str] = None,
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    in_stock: Optional[bool] = None,
    q: Optional[str] = None,
    sort: Literal["id", "price_asc", "price_desc", "name"] = "id",
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Filtered, sorted, paginated product list.

    When `q` is given it uses Postgres full-text search (websearch_to_tsquery
    over search_vector) OR trigram fuzzy matching on the name, so typos still
    match. With no explicit sort, results come back by relevance; an explicit
    price/name sort still wins.
    """
    # Soft-deleted products never appear in the storefront (Phase 4). The rows
    # still exist — they must, for FAISS alignment — so every customer-facing
    # query filters them out explicitly.
    filters = [Product.is_active.is_(True)]
    if category:
        filters.append(Product.master_category == category)
    if article_type:
        filters.append(Product.article_type == article_type)
    if colour:
        filters.append(Product.base_colour == colour)
    if gender:
        filters.append(Product.gender == gender)
    if min_price is not None:
        filters.append(Product.price >= min_price)
    if max_price is not None:
        filters.append(Product.price <= max_price)
    if in_stock is not None:
        filters.append(Product.in_stock == in_stock)

    tsquery = None
    if q:
        tsquery = func.websearch_to_tsquery("english", q)
        filters.append(
            or_(
                Product.search_vector.op("@@")(tsquery),        # full-text
                Product.product_display_name.op("%")(q),         # trigram fuzzy
            )
        )

    total = db.scalar(select(func.count(Product.id)).where(*filters))

    # With a query and no explicit sort, order by relevance (full-text rank +
    # trigram similarity). id is always the final tiebreaker so pagination stays
    # deterministic even when the primary key has ties.
    if q and sort == "id":
        relevance = func.ts_rank(Product.search_vector, tsquery) + func.similarity(
            Product.product_display_name, q
        )
        order_by = [desc(relevance), asc(Product.id)]
    else:
        order_by = [_SORTS[sort], asc(Product.id)]

    stmt = select(Product).where(*filters).order_by(*order_by).limit(limit).offset(offset)
    items = db.scalars(stmt).all()
    return {
        "items": [serialize_product(p) for p in items],
        "total": total,
        "limit": limit,
        "offset": offset,
        "sort": sort,
    }


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)) -> dict:
    product = db.get(Product, product_id)
    # A soft-deleted product is gone as far as the storefront is concerned —
    # 404, not a visible-but-unbuyable page.
    if product is None or not product.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return serialize_product_detail(product)


@router.get("/categories")
def categories(db: Session = Depends(get_db)) -> dict:
    """Facet lists + price range powering the whole FilterSidebar in one call."""

    def distinct(column) -> list[str]:
        rows = db.execute(
            select(column)
            .where(column.is_not(None), Product.is_active.is_(True))
            .distinct()
            .order_by(column)
        ).all()
        return [value for (value,) in rows]

    # Price range spans active products only, so the slider cannot bracket a
    # range the catalog can no longer fill.
    lo, hi = db.execute(
        select(func.min(Product.price), func.max(Product.price)).where(
            Product.is_active.is_(True)
        )
    ).one()
    return {
        "categories": distinct(Product.master_category),
        "articleTypes": distinct(Product.article_type),
        "colours": distinct(Product.base_colour),
        "genders": distinct(Product.gender),
        "priceRange": {"min": float(lo), "max": float(hi)},
    }


@router.get("/autocomplete")
def autocomplete(
    q: str = Query(..., min_length=2),
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
) -> dict:
    """Type-ahead product-name suggestions: prefix matches + trigram fuzzy,
    ranked by similarity. Names are de-duplicated via GROUP BY."""
    similarity = func.max(func.similarity(Product.product_display_name, q)).label("sim")
    stmt = (
        select(Product.product_display_name, similarity)
        .where(
            or_(
                Product.product_display_name.op("%")(q),         # fuzzy
                Product.product_display_name.ilike(f"{q}%"),     # prefix
            ),
            Product.is_active.is_(True),
        )
        .group_by(Product.product_display_name)
        .order_by(similarity.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    return {"suggestions": [name for name, _ in rows]}
