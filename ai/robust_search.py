
from PIL import Image
import numpy as np
import io

def safe_search(model, preprocess, device, index, df,
                text_query=None, image_bytes=None, top_k=5):
    try:
        if text_query:
            text_query = text_query[:200].strip()
            if not text_query:
                return {"error": "Empty query", "results": []}

        if image_bytes:
            img = Image.open(image_bytes).convert("RGB")
            emb = preprocess(img).unsqueeze(0).to(device)
            with torch.no_grad():
                img_emb = model.encode_image(emb).cpu().numpy()[0]
            img_emb = img_emb / np.linalg.norm(img_emb)
            fused = img_emb.astype("float32")
        elif text_query:
            text = clip.tokenize([text_query]).to(device)
            with torch.no_grad():
                fused = model.encode_text(text).cpu().numpy()[0]
            fused = fused / np.linalg.norm(fused)
            fused = fused.astype("float32")
        else:
            return {"error": "No input provided", "results": []}

        fused = fused.reshape(1, -1)
        distances, indices = index.search(fused, top_k)

        results = []
        for idx, score in zip(indices[0], distances[0]):
            row = df.iloc[idx]
            results.append({
                "id": int(row["id"]),
                "name": row["productDisplayName"],
                "category": row["masterCategory"],
                "subCategory": row["articleType"],
                "colour": row["baseColour"],
                "score": round(float(score), 4)
            })
        return {"results": results}

    except Exception as e:
        return {"error": str(e), "results": []}
