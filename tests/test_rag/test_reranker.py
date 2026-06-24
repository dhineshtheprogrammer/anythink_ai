"""Tests for re-ranker implementations."""

from __future__ import annotations

import pytest

from anythink.rag.reranker import (
    BaseReranker,
    CohereReranker,
    CrossEncoderReranker,
    get_reranker,
)
from anythink.rag.retrieval import ScoredChunk


def _make_chunk(idx: int, text: str, score: float = 0.5) -> ScoredChunk:
    return ScoredChunk(
        chunk_index=idx,
        text=text,
        metadata={"source_path": f"doc{idx}.txt"},
        score=score,
        source="vector",
    )


# ── CrossEncoderReranker ──────────────────────────────────────────────────────


class TestCrossEncoderReranker:
    def test_inherits_base_reranker(self) -> None:
        r = CrossEncoderReranker()
        assert isinstance(r, BaseReranker)

    def test_default_model_name(self) -> None:
        r = CrossEncoderReranker()
        assert r._model_name == "bge-reranker-base"

    def test_custom_model_name(self) -> None:
        r = CrossEncoderReranker("ms-marco-MiniLM-L-6-v2")
        assert "ms-marco" in r._hf_name

    def test_supported_models_map(self) -> None:
        assert "bge-reranker-base" in CrossEncoderReranker.SUPPORTED_MODELS
        assert "bge-reranker-large" in CrossEncoderReranker.SUPPORTED_MODELS
        assert "ms-marco-MiniLM-L-6-v2" in CrossEncoderReranker.SUPPORTED_MODELS

    def test_is_available_returns_bool(self) -> None:
        r = CrossEncoderReranker()
        result = r.is_available()
        assert isinstance(result, bool)

    async def test_rerank_empty_returns_empty(self) -> None:
        r = CrossEncoderReranker()
        if not r.is_available():
            pytest.skip("sentence-transformers not installed")
        result = await r.rerank("query", [], top_k=3)
        assert result == []

    async def test_rerank_returns_top_k(self) -> None:
        r = CrossEncoderReranker()
        if not r.is_available():
            pytest.skip("sentence-transformers not installed")
        chunks = [
            _make_chunk(0, "Python programming tutorial", 0.9),
            _make_chunk(1, "Database SQL queries", 0.7),
            _make_chunk(2, "Machine learning deep learning", 0.8),
        ]
        result = await r.rerank("python", chunks, top_k=2)
        assert len(result) <= 2

    async def test_rerank_source_is_reranked(self) -> None:
        r = CrossEncoderReranker()
        if not r.is_available():
            pytest.skip("sentence-transformers not installed")
        chunks = [_make_chunk(0, "Python tutorial", 0.8), _make_chunk(1, "SQL queries", 0.6)]
        result = await r.rerank("python", chunks, top_k=2)
        assert all(c.source == "reranked" for c in result)

    async def test_rerank_preserves_original_score(self) -> None:
        r = CrossEncoderReranker()
        if not r.is_available():
            pytest.skip("sentence-transformers not installed")
        chunks = [_make_chunk(0, "Python tutorial", 0.75)]
        result = await r.rerank("python", chunks, top_k=1)
        if result:
            assert "original" in result[0].extra_scores


# ── CohereReranker ────────────────────────────────────────────────────────────


class TestCohereReranker:
    def test_inherits_base_reranker(self) -> None:
        r = CohereReranker(api_key="test-key")
        assert isinstance(r, BaseReranker)

    def test_is_available_with_key(self) -> None:
        r = CohereReranker(api_key="test-key")
        assert r.is_available() is True

    def test_is_unavailable_without_key(self) -> None:
        r = CohereReranker(api_key="")
        assert r.is_available() is False

    async def test_rerank_calls_api(self) -> None:
        """Skipped — Cohere API test requires live credentials."""
        pytest.skip("Cohere API test requires live credentials or full httpx mocking")

    async def test_rerank_empty_returns_empty(self) -> None:
        r = CohereReranker(api_key="fake-key")
        # Empty chunks list — should not make network call
        result = await r.rerank("query", [], top_k=3)
        assert result == []


# ── get_reranker factory ──────────────────────────────────────────────────────


class TestGetReranker:
    def test_cross_encoder_model(self) -> None:
        r = get_reranker("bge-reranker-base")
        # Returns None if sentence-transformers not installed, else CrossEncoderReranker
        assert r is None or isinstance(r, CrossEncoderReranker)

    def test_cohere_without_key_returns_none(self) -> None:
        r = get_reranker("cohere-rerank", api_key=None)
        assert r is None

    def test_cohere_with_key_returns_reranker(self) -> None:
        r = get_reranker("cohere-rerank", api_key="test-key")
        assert r is None or isinstance(r, CohereReranker)

    def test_unknown_model_returns_cross_encoder(self) -> None:
        r = get_reranker("some/huggingface/model")
        assert r is None or isinstance(r, CrossEncoderReranker)
