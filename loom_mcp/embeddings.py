"""loom-code embedding engine using sentence-transformers."""

import logging
import struct
from typing import TYPE_CHECKING

import numpy as np

from loom_mcp.config import EMBEDDING_DIM, EMBEDDING_MODEL, MODEL_CACHE_DIR

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_model: "SentenceTransformer | None" = None


def _get_model() -> "SentenceTransformer":
    """Lazy-load the sentence-transformers model."""
    global _model  # noqa: PLW0603
    if _model is None:
        from sentence_transformers import SentenceTransformer

        MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _model = SentenceTransformer(
            EMBEDDING_MODEL,
            cache_folder=str(MODEL_CACHE_DIR),
        )
        logger.info(
            "Embedding model loaded",
            extra={"model": EMBEDDING_MODEL, "cache": str(MODEL_CACHE_DIR)},
        )
    return _model


def _vector_to_bytes(vector: np.ndarray) -> bytes:
    """Convert a float32 numpy vector to bytes."""
    return struct.pack(f"{EMBEDDING_DIM}f", *vector.tolist())


def _bytes_to_vector(data: bytes) -> np.ndarray:
    """Convert bytes back to a float32 numpy vector."""
    return np.array(
        struct.unpack(f"{EMBEDDING_DIM}f", data),
        dtype=np.float32,
    )


def warmup() -> None:
    """Pre-load the embedding model at server startup to avoid first-call latency."""
    _get_model()
    logger.info("Embedding model warmed up", extra={"model": EMBEDDING_MODEL})


def embed(text: str) -> bytes:
    """Embed a single text string, returning bytes suitable for SQLite BLOB."""
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return _vector_to_bytes(vector)


def embed_batch(texts: list[str]) -> list[bytes]:
    """Embed multiple texts, returning list of bytes."""
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True)
    return [_vector_to_bytes(v) for v in vectors]


def cosine_similarity(a: bytes, b: bytes) -> float:
    """Compute cosine similarity between two embedding BLOBs.

    Embeddings are already L2-normalized, so dot product = cosine similarity.
    """
    vec_a = _bytes_to_vector(a)
    vec_b = _bytes_to_vector(b)
    return float(np.dot(vec_a, vec_b))


def search(
    query_emb: bytes,
    candidates: list[tuple[str, bytes]],
) -> list[tuple[str, float]]:
    """Rank candidates by cosine similarity to query.

    Args:
        query_emb: The query embedding as bytes.
        candidates: List of (id, embedding_bytes) tuples.

    Returns:
        List of (id, score) tuples sorted by descending similarity.
    """
    if not candidates:
        return []

    query_vec = _bytes_to_vector(query_emb)
    candidate_ids = [c[0] for c in candidates]
    candidate_matrix = np.array(
        [_bytes_to_vector(c[1]) for c in candidates],
        dtype=np.float32,
    )

    # Dot product with normalized vectors = cosine similarity
    scores = candidate_matrix @ query_vec

    ranked = sorted(
        zip(candidate_ids, scores.tolist(), strict=True),
        key=lambda x: x[1],
        reverse=True,
    )
    return [(rid, score) for rid, score in ranked]
