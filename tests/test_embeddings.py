"""Tests for the embeddings module."""

import struct

import numpy as np
import pytest

from loom_mcp.config import EMBEDDING_DIM
from loom_mcp.embeddings import (
    _bytes_to_vector,
    _vector_to_bytes,
    cosine_similarity,
    embed,
    embed_batch,
    search,
)


class TestVectorSerialization:
    def test_roundtrip(self) -> None:
        vec = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        blob = _vector_to_bytes(vec)
        recovered = _bytes_to_vector(blob)
        np.testing.assert_array_almost_equal(vec, recovered)

    def test_blob_size(self) -> None:
        vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        blob = _vector_to_bytes(vec)
        assert len(blob) == EMBEDDING_DIM * 4  # float32 = 4 bytes


class TestEmbed:
    def test_embed_returns_bytes(self) -> None:
        result = embed("hello world")
        assert isinstance(result, bytes)
        assert len(result) == EMBEDDING_DIM * 4

    def test_embed_batch_returns_list(self) -> None:
        results = embed_batch(["hello", "world"])
        assert len(results) == 2
        for r in results:
            assert isinstance(r, bytes)
            assert len(r) == EMBEDDING_DIM * 4

    def test_embed_batch_empty(self) -> None:
        assert embed_batch([]) == []

    def test_similar_texts_high_similarity(self) -> None:
        a = embed("python programming language")
        b = embed("python coding language")
        sim = cosine_similarity(a, b)
        assert sim > 0.7

    def test_different_texts_lower_similarity(self) -> None:
        a = embed("python programming")
        b = embed("chocolate cake recipe")
        sim = cosine_similarity(a, b)
        assert sim < 0.5


class TestSearch:
    def test_search_ranks_by_similarity(self) -> None:
        query = embed("python error handling")
        candidates = [
            ("a", embed("python exception try catch")),
            ("b", embed("chocolate cake recipe")),
            ("c", embed("python error traceback")),
        ]
        results = search(query, candidates)
        ids = [r[0] for r in results]
        # Python-related should rank above cake
        assert ids[-1] == "b"

    def test_search_empty_candidates(self) -> None:
        query = embed("test")
        assert search(query, []) == []

    def test_search_returns_scores(self) -> None:
        query = embed("test")
        candidates = [("a", embed("test")), ("b", embed("other"))]
        results = search(query, candidates)
        for _id, score in results:
            assert 0.0 <= score <= 1.1  # Small tolerance for floating point
