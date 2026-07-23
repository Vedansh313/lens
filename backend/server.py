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

# ---------------------------------------------------------------------------
# Config (override via environment variables)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
# Model artifacts live in the isolated ai/ module (ai/models/).
AI_DIR = BASE_DIR.parent / "ai"

INDEX_PATH = Path(os.getenv("INDEX_PATH", AI_DIR / "models" / "product_index.faiss"))
METADATA_PATH = Path(os.getenv("METADATA_PATH", AI_DIR / "models" / "product_metadata.json"))
WEIGHTS_PATH = Path(os.getenv("CLIP_WEIGHTS", AI_DIR / "models" / "clip_finetuned.pt"))
IMAGES_DIR = Path(os.getenv("IMAGES_DIR", BASE_DIR / "images"))
# Base URL used to build image_url values returned to the frontend.
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "http://localhost:8000")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

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
df = pd.read_json(METADATA_PATH)
print(f"[lens] loaded {index.ntotal} vectors / {len(df)} metadata rows")

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
