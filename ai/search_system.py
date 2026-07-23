
"""
Hybrid visual search system: semantic retrieval (CLIP+FAISS) + metadata re-ranking.
Usage:
    from search_system import build_search
    search = build_search(model, preprocess, device, index, df)
    results = search("blue sports shoes for men", top_k=10)
"""
import clip
import torch
import numpy as np


def build_search(model, preprocess, device, index, df):
    # ---- build vocabulary from the dataset itself ----
    known_categories = [str(c) for c in df["articleType"].dropna().unique()]
    known_colours = [str(c) for c in df["baseColour"].dropna().unique()]

    category_synonyms = {
        "sneakers": "Casual Shoes",
        "running shoes": "Sports Shoes",
        "trainers": "Sports Shoes",
        "dress": "Dresses",
        "sunglass": "Sunglasses",
        "purse": "Handbags",
        "wallet": "Wallets",
        "kurta": "Kurtas",
        "sandal": "Sandals",
        "flip flop": "Flip Flops",
    }

    def get_text_embedding(text_query):
        text = clip.tokenize([text_query]).to(device)
        with torch.no_grad():
            emb = model.encode_text(text).cpu().numpy()[0]
        emb = emb / np.linalg.norm(emb)
        return emb.astype("float32")

    def parse_query(query):
        q = query.lower()
        parsed = {"category": None, "colour": None, "gender": None}

        if "women" in q or "woman" in q or "ladies" in q:
            parsed["gender"] = "Women"
        elif "men" in q or "man" in q:
            parsed["gender"] = "Men"
        elif "boys" in q:
            parsed["gender"] = "Boys"
        elif "girls" in q:
            parsed["gender"] = "Girls"

        for c in known_colours:
            if isinstance(c, str) and c.lower() in q:
                parsed["colour"] = c
                break

        for cat in known_categories:
            if isinstance(cat, str) and cat.lower() in q:
                parsed["category"] = cat
                break
        if parsed["category"] is None:
            for syn, cat in category_synonyms.items():
                if syn in q:
                    parsed["category"] = cat
                    break

        return parsed

    def search(query, top_k=10, retrieve_n=50,
               cat_boost=0.15, colour_boost=0.10, gender_boost=0.05,
               query_emb=None):
        parsed = parse_query(query or "")

        # Stage 1 — broad semantic retrieval.
        # query_emb lets callers pass a precomputed (e.g. multimodal image+text
        # fused) embedding; falls back to encoding the text query.
        if query_emb is None:
            q_emb = get_text_embedding(query).reshape(1, -1)
        else:
            q_emb = np.asarray(query_emb, dtype="float32").reshape(1, -1)
        distances, indices = index.search(q_emb, retrieve_n)

        # Stage 2 — metadata-boosted re-ranking
        candidates = []
        for idx, sim in zip(indices[0], distances[0]):
            row = df.iloc[idx]
            score = float(sim)
            if parsed["category"] and str(row["articleType"]) == parsed["category"]:
                score += cat_boost
            if parsed["colour"] and str(row["baseColour"]) == parsed["colour"]:
                score += colour_boost
            if parsed["gender"] and str(row["gender"]) == parsed["gender"]:
                score += gender_boost
            candidates.append({
                "id": int(row["id"]),
                "name": row["productDisplayName"],
                "category": row["masterCategory"],
                "subCategory": row["articleType"],
                "colour": row["baseColour"],
                "gender": row["gender"],
                "score": round(score, 4),
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_k]

    return search
