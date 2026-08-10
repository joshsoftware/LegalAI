"""Address similarity via embeddings.

Embeddings come from BAAI/bge-small-en-v1.5 (sentence-transformers),
running locally on CPU — no API key or network call per request. The
model is loaded once per process (module-level singleton) since load time
is the expensive part; encoding individual addresses is fast.
"""

import math
import re
from functools import lru_cache

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384

# bge models are trained to prepend this instruction for retrieval queries.
_QUERY_PREFIX = "represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def _normalize_address(address: str) -> str:
    text = address.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_address_embedding(address: str) -> list[float]:
    normalized = _normalize_address(address)
    if not normalized:
        return [0.0] * EMBEDDING_DIMENSIONS

    model = _get_model()
    vector = model.encode(_QUERY_PREFIX + normalized, normalize_embeddings=True)
    return vector.tolist()


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def address_similarity(address_a: str, address_b: str) -> float:
    if not address_a or not address_b:
        return 0.0
    vec_a = get_address_embedding(address_a)
    vec_b = get_address_embedding(address_b)
    similarity = cosine_similarity(vec_a, vec_b)
    return max(0.0, similarity)
