"""Local semantic embeddings for the upstream GA retrieval implementation."""
from functools import lru_cache
import os

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_encoder = None

def load_encoder():
    global _encoder
    if _encoder is None:
        from fastembed import TextEmbedding
        _encoder = TextEmbedding(MODEL_NAME, cache_dir=os.environ.get("DS_EMBEDDING_CACHE"), threads=2)
    return _encoder

@lru_cache(maxsize=12000)
def get_embedding(text):
    return next(iter(load_encoder().embed([str(text)]))).tolist()

