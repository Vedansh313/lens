"""Catalog API: product listing/detail + facet lists. Read-only, no auth.

Mounted in server.py via include_router. The product serialization here is the
single shape returned across the storefront (catalog, and later cart/wishlist),
so all product payloads stay consistent. AI search pipeline is untouched.
"""
from __future__ import annotations

import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, func, select
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

    `q` here is a plain case-insensitive substring match on the product name;
    real full-text + fuzzy search replaces it in step 3.
    """
    filters = []
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
    if q:
        filters.append(Product.product_display_name.ilike(f"%{q}%"))

    total = db.scalar(select(func.count(Product.id)).where(*filters))
    # id is always the final tiebreaker so pagination is deterministic even when
    # the primary sort key (e.g. price) has ties.
    stmt = (
        select(Product)
        .where(*filters)
        .order_by(_SORTS[sort], asc(Product.id))
        .limit(limit)
        .offset(offset)
    )
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
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return serialize_product_detail(product)


@router.get("/categories")
def categories(db: Session = Depends(get_db)) -> dict:
    """Facet lists + price range powering the whole FilterSidebar in one call."""

    def distinct(column) -> list[str]:
        rows = db.execute(
            select(column).where(column.is_not(None)).distinct().order_by(column)
        ).all()
        return [value for (value,) in rows]

    lo, hi = db.execute(select(func.min(Product.price), func.max(Product.price))).one()
    return {
        "categories": distinct(Product.master_category),
        "articleTypes": distinct(Product.article_type),
        "colours": distinct(Product.base_colour),
        "genders": distinct(Product.gender),
        "priceRange": {"min": float(lo), "max": float(hi)},
    }
