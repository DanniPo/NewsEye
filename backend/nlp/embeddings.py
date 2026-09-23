import torch
from sentence_transformers import SentenceTransformer

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer("all-MiniLM-L6-v2", device=DEVICE)

def generate_embedding(text: str) -> list:
    return model.encode(text, normalize_embeddings=True).tolist()

def generate_embeddings_batch(texts: list) -> list:
    return model.encode(texts, normalize_embeddings=True).tolist()