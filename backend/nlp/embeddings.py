import torch
from sentence_transformers import SentenceTransformer

from backend.config import EMBEDDING_MODEL

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer(EMBEDDING_MODEL, device=DEVICE)

def generate_embedding(text: str) -> list:
    return model.encode(text, normalize_embeddings=True).tolist()

def generate_embeddings_batch(texts: list) -> list:
    return model.encode(texts, normalize_embeddings=True).tolist()