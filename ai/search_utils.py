
import clip
import torch
import numpy as np
from PIL import Image
import faiss

def get_text_embedding(model, device, text_query):
    text = clip.tokenize([text_query]).to(device)
    with torch.no_grad():
        text_emb = model.encode_text(text).cpu().numpy()[0]
    text_emb = text_emb / np.linalg.norm(text_emb)
    return text_emb.astype("float32")

def get_image_embedding(model, preprocess, device, image_path):
    image = preprocess(Image.open(image_path).convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        img_emb = model.encode_image(image).cpu().numpy()[0]
    img_emb = img_emb / np.linalg.norm(img_emb)
    return img_emb.astype("float32")

def multimodal_search(model, preprocess, device, index, df,
                      text_query=None, image_path=None, alpha=0.7, top_k=5):
    if image_path and text_query:
        img_emb = get_image_embedding(model, preprocess, device, image_path)
        txt_emb = get_text_embedding(model, device, text_query)
        fused = alpha * img_emb + (1 - alpha) * txt_emb
        fused = fused / np.linalg.norm(fused)
    elif text_query:
        fused = get_text_embedding(model, device, text_query)
    elif image_path:
        fused = get_image_embedding(model, preprocess, device, image_path)
    else:
        raise ValueError("Provide at least a text query or image")

    fused = fused.reshape(1, -1).astype("float32")
    distances, indices = index.search(fused, top_k + 1)

    results = []
    for idx, score in zip(indices[0], distances[0]):
        row = df.iloc[idx]
        results.append({
            "id": int(row["id"]),
            "name": row["productDisplayName"],
            "category": row["masterCategory"],
            "subCategory": row["articleType"],
            "colour": row["baseColour"],
            "gender": row["gender"],
            "score": round(float(score), 4),
            "image_url": f"/images/{int(row['id'])}.jpg"
        })
    return results
