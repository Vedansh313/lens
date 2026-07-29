"""
Local FastAPI server for the Lens visual product search system.

Loads the fine-tuned CLIP weights, the FAISS index, and the product metadata,
then serves the higher-scoring two-stage re-ranker from `search_system.py`
(semantic retrieval + metadata boosting) — not the basic single-stage search.

Endpoint contract matches what src/components/Dashboard.jsx POSTs:

    POST /api/v1/search   (multipart/form-data)
        image   : file        (optional)
        query   : str         (optional)
        alpha   : float = 0.7  (image weight when both image + query are given)
        top_k   : int   = 10

    -> { "products": [ { id, name, category, subCategory, colour,
                         gender, score, image_url } ], "total": N }

Run:  uvicorn server:app --host 127.0.0.1 --port 8000
"""
import io
import os
import sys
from pathlib import Path
from typing import Optional

import clip
import faiss
import numpy as np
import pandas as pd
import torch
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image

# The isolated CLIP+FAISS search module now lives in the sibling `ai/` package.
# Put the project root on sys.path so `import ai...` resolves when uvicorn is
# launched from backend/.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from ai.search_system import build_search

# Backend-local (server runs from backend/): product metadata now comes from
# Postgres instead of product_metadata.json.
from sqlalchemy import select
from db import SessionLocal
from models import Product
from admin import router as admin_router
from auth import router as auth_router
from catalog import router as catalog_router
from cart import router as cart_router
from checkout import router as checkout_router
from engagement import router as engagement_router
from orders import router as orders_router
from payments import router as payments_router
from hybrid import build_hybrid_router

# ---------------------------------------------------------------------------
# Config (override via environment variables)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
# Model artifacts live in the isolated ai/ module (ai/models/).
AI_DIR = BASE_DIR.parent / "ai"

INDEX_PATH = Path(os.getenv("INDEX_PATH", AI_DIR / "models" / "product_index.faiss"))
WEIGHTS_PATH = Path(os.getenv("CLIP_WEIGHTS", AI_DIR / "models" / "clip_finetuned.pt"))
IMAGES_DIR = Path(os.getenv("IMAGES_DIR", BASE_DIR / "images"))
# Base URL used to build image_url values returned to the frontend.
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "http://localhost:8000")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# ---------------------------------------------------------------------------
# Product metadata (from Postgres — replaces pd.read_json(product_metadata.json))
# ---------------------------------------------------------------------------
# search_system consumes the dataset's original camelCase column names; the DB
# stores snake_case, so we rename on the way out.
_DB_TO_DF_COLUMNS = {
    Product.id: "id",
    Product.product_display_name: "productDisplayName",
    Product.master_category: "masterCategory",
    Product.sub_category: "subCategory",
    Product.article_type: "articleType",
    Product.base_colour: "baseColour",
    Product.gender: "gender",
    Product.season: "season",
    Product.year: "year",
    Product.usage: "usage",
}


def _load_metadata_df() -> pd.DataFrame:
    """Load product metadata from Postgres, ordered so row i == FAISS vector i.

    ai.search_system resolves FAISS hits positionally (`df.iloc[idx]`), so the
    DataFrame's row order IS the contract. Ordering by faiss_index reproduces
    the exact order product_metadata.json was in, and the assertion below refuses
    to serve if that order is not a clean 0..n-1 sequence — the same paranoia the
    seed script applies, enforced again at load time.

    DO NOT add an is_active filter here (Phase 4). Soft-deleted products must
    still occupy their row: dropping one shifts every later position and breaks
    the alignment this frame exists to guarantee — the assertion below would
    then refuse to boot, which is the good outcome. Inactive products are kept
    out of RESULTS instead, at the DB join in hybrid.py and in catalog.py.
    """
    columns = list(_DB_TO_DF_COLUMNS.values())
    stmt = select(Product.faiss_index, *_DB_TO_DF_COLUMNS).order_by(Product.faiss_index)
    with SessionLocal() as session:
        rows = session.execute(stmt).all()

    df = pd.DataFrame(rows, columns=["faiss_index", *columns])

    # After ORDER BY faiss_index, the default 0..n-1 RangeIndex must equal the
    # faiss_index values — otherwise df.iloc[idx] would not resolve FAISS vector
    # idx and every result would be quietly wrong.
    if df["faiss_index"].tolist() != list(range(len(df))):
        raise RuntimeError(
            "products.faiss_index is not a contiguous 0..n-1 sequence; "
            "FAISS<->DB alignment cannot be trusted. Re-run backend/seed.py."
        )
    return df.drop(columns="faiss_index")


# ---------------------------------------------------------------------------
# Load models + data once at import time
# ---------------------------------------------------------------------------
print(f"[lens] loading on device: {DEVICE}")

model, preprocess = clip.load("ViT-B/32", device=DEVICE)
if WEIGHTS_PATH.exists():
    state = torch.load(WEIGHTS_PATH, map_location=DEVICE)
    model.load_state_dict(state)
    print(f"[lens] loaded fine-tuned weights: {WEIGHTS_PATH.name}")
else:
    print(f"[lens] WARNING: {WEIGHTS_PATH.name} not found — using base CLIP weights")
model = model.float()  # weights were fine-tuned in float32
model.eval()

index = faiss.read_index(str(INDEX_PATH))
df = _load_metadata_df()
print(f"[lens] loaded {index.ntotal} vectors / {len(df)} metadata rows (from DB)")

# The certified higher-scoring re-ranker (parse_query + metadata boosts).
rerank_search = build_search(model, preprocess, DEVICE, index, df)


def _embed_text(text: str) -> np.ndarray:
    tokens = clip.tokenize([text]).to(DEVICE)
    with torch.no_grad():
        emb = model.encode_text(tokens).cpu().numpy()[0]
    return (emb / np.linalg.norm(emb)).astype("float32")


def _embed_image(image_bytes: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = preprocess(img).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        emb = model.encode_image(tensor).cpu().numpy()[0]
    return (emb / np.linalg.norm(emb)).astype("float32")


def _with_image_url(results: list) -> list:
    for r in results:
        r["image_url"] = f"{IMAGE_BASE_URL}/images/{r['id']}.jpg"
    return results


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Lens Visual Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

IMAGES_DIR.mkdir(exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")

# Auth endpoints (/auth/register, /login, /refresh, /logout, /me). Separate
# module; the search pipeline above is untouched.
app.include_router(auth_router)
# Catalog endpoints (/products, /products/{id}, /categories). Read-only.
app.include_router(catalog_router)
# Cart endpoints (/cart ...). Per-user, auth-protected.
app.include_router(cart_router)
# Wishlist + recently-viewed endpoints. Per-user, auth-protected.
app.include_router(engagement_router)
# Checkout: addresses, price quote, order creation. Auth-protected.
app.include_router(checkout_router)
# Simulated payment gateway (/orders/{id}/pay). Auth-protected.
app.include_router(payments_router)
# Order retrieval + invoice (/orders, /orders/{id}, /orders/{id}/invoice).
app.include_router(orders_router)
# Admin order management (/admin/...). Every route requires is_admin.
app.include_router(admin_router)
# Hybrid search (/api/v1/hybrid-search): reuses the re-ranker + embed helpers
# above (injected, not re-imported) and fuses in catalog filters + real pricing.
app.include_router(
    build_hybrid_router(
        rerank_search=rerank_search,
        embed_image=_embed_image,
        embed_text=_embed_text,
    )
)


@app.get("/")
def root():
    return {"status": "running", "products": index.ntotal, "device": DEVICE}


@app.post("/api/v1/search")
async def search(
    query: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    alpha: float = Form(0.7),
    top_k: int = Form(10),
):
    query = (query or "").strip()
    has_image = image is not None

    if not query and not has_image:
        return {"products": [], "total": 0, "error": "Provide a text query or an image."}

    try:
        # Build the Stage-1 query embedding. Text-only goes straight through the
        # re-ranker's own text encoder; image / multimodal fuses here and hands
        # the fused vector to the same two-stage re-ranker.
        query_emb = None
        if has_image:
            img_bytes = await image.read()
            img_emb = _embed_image(img_bytes)
            if query:
                txt_emb = _embed_text(query)
                fused = alpha * img_emb + (1 - alpha) * txt_emb
                query_emb = (fused / np.linalg.norm(fused)).astype("float32")
            else:
                query_emb = img_emb

        results = rerank_search(
            query,
            top_k=top_k,
            retrieve_n=max(50, top_k),
            query_emb=query_emb,
        )
    except Exception as exc:  # keep the frontend contract intact on failure
        return {"products": [], "total": 0, "error": str(exc)}

    results = _with_image_url(results)
    return {"products": results, "total": len(results)}
