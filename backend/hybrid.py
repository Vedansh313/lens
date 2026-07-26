"""Hybrid search: CLIP+FAISS semantic ranking fused with catalog filters.

The existing /api/v1/search returns semantically ranked products but knows
nothing about price or stock. This endpoint reuses the SAME re-ranker (image +
text fusion + metadata boosts) and then enriches/filters the results against
Postgres, so a caller gets visual/semantic relevance AND real commerce filters
in one call.

Built as a factory: server.py injects the already-loaded AI closures
(rerank_search, embed_image, embed_text), so this module never imports server
and the ai/ pipeline is not modified.
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np
from fastapi import APIRouter, File, Form, UploadFile
from sqlalchemy import select

from catalog import serialize_product
from db import SessionLocal
from models import Product


def build_hybrid_router(
    *,
    rerank_search: Callable,
    embed_image: Callable[[bytes], np.ndarray],
    embed_text: Callable[[str], np.ndarray],
) -> APIRouter:
    router = APIRouter(tags=["search"])

    @router.post("/api/v1/hybrid-search")
    async def hybrid_search(
        query: Optional[str] = Form(None),
        image: Optional[UploadFile] = File(None),
        alpha: float = Form(0.7),
        top_k: int = Form(10),
        category: Optional[str] = Form(None),
        colour: Optional[str] = Form(None),
        gender: Optional[str] = Form(None),
        min_price: Optional[float] = Form(None),
        max_price: Optional[float] = Form(None),
        in_stock: Optional[bool] = Form(None),
    ) -> dict:
        query = (query or "").strip()
        has_image = image is not None
        if not query and not has_image:
            return {"products": [], "total": 0, "error": "Provide a text query or an image."}

        try:
            # Stage 1 — fuse image + text into one query embedding (identical to
            # server.py's search). Text-only lets the re-ranker encode the text.
            query_emb = None
            if has_image:
                img_emb = embed_image(await image.read())
                if query:
                    txt_emb = embed_text(query)
                    fused = alpha * img_emb + (1 - alpha) * txt_emb
                    query_emb = (fused / np.linalg.norm(fused)).astype("float32")
                else:
                    query_emb = img_emb

            # Over-fetch when filtering so the post-filter doesn't starve top_k.
            has_filters = any(
                v is not None
                for v in (category, colour, gender, min_price, max_price, in_stock)
            )
            retrieve_n = min(1000, max(200, top_k * 20)) if has_filters else max(50, top_k)
            ranked = rerank_search(
                query, top_k=retrieve_n, retrieve_n=retrieve_n, query_emb=query_emb
            )
        except Exception as exc:  # keep the frontend contract intact on failure
            return {"products": [], "total": 0, "error": str(exc)}

        ranked_ids = [r["id"] for r in ranked]
        if not ranked_ids:
            return {"products": [], "total": 0}
        score_by_id = {r["id"]: r["score"] for r in ranked}

        # Stage 2 — enrich with real catalog data and apply commerce filters.
        filters = [Product.id.in_(ranked_ids)]
        if category:
            filters.append(Product.master_category == category)
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

        with SessionLocal() as db:
            rows = {p.id: p for p in db.scalars(select(Product).where(*filters)).all()}

        # Re-assemble in the AI ranking order (the DB query loses it), trim to top_k.
        products = []
        for pid in ranked_ids:
            product = rows.get(pid)
            if product is None:
                continue  # filtered out, or (rarely) absent from the catalog
            item = serialize_product(product)
            item["score"] = score_by_id[pid]
            item["match"] = round(score_by_id[pid] * 100)
            products.append(item)
            if len(products) >= top_k:
                break

        return {"products": products, "total": len(products)}

    return router
