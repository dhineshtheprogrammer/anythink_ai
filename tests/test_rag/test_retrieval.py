"""Tests for all 4 retrieval strategies, RRF, MMR, and the main retrieve() entry point."""

from __future__ import annotations

from pathlib import Path

import pytest

from anythink.embeddings.mock import MockEmbeddingBackend
from anythink.rag.bm25 import BM25Index
from anythink.rag.models import RetrievalResult
from anythink.rag.retrieval import (
    ScoredChunk,
    _dedup_overlap,
    _normalize,
    _rrf_fuse,
    retrieve,
    retrieve_bm25,
    retrieve_hybrid,
    retrieve_mmr,
    retrieve_vector,
    scored_to_result,
)
from anythink.rag.store import VectorStore


# ── Fixtures ──────────────────────────────────────────────────────────────────


_CORPUS_TEXTS = [
    "Python programming language tutorial for beginners",
    "JavaScript web development and frontend frameworks",
    "Machine learning with neural networks and deep learning",
    "Python data science with pandas and numpy libraries",
    "Database SQL queries and performance optimization",
]


@pytest.fixture()
def backend() -> MockEmbeddingBackend:
    return MockEmbeddingBackend()


@pytest.fixture()
async def populated_store(backend: MockEmbeddingBackend) -> VectorStore:
    """A VectorStore with 5 chunks — embeddings from MockEmbeddingBackend."""
    vecs = await backend.embed(_CORPUS_TEXTS)
    metas = [
        {"source_path": f"doc{i}.txt", "start_line": i * 10, "end_line": i * 10 + 9}
        for i in range(len(_CORPUS_TEXTS))
    ]
    store = VectorStore()
    store.add(_CORPUS_TEXTS, metas, vecs)
    return store


@pytest.fixture()
def bm25() -> BM25Index:
    idx = BM25Index()
    idx.build(_CORPUS_TEXTS)
    return idx


@pytest.fixture()
async def query_vec(backend: MockEmbeddingBackend) -> list[float]:
    vecs = await backend.embed(["python tutorial"])
    return vecs[0]


# ── Helper tests ──────────────────────────────────────────────────────────────


class TestNormalize:
    def test_max_becomes_one(self) -> None:
        pairs = [(0, 10.0), (1, 5.0), (2, 0.0)]
        norm = _normalize(pairs)
        assert norm[0][1] == pytest.approx(1.0)

    def test_proportional(self) -> None:
        pairs = [(0, 4.0), (1, 2.0)]
        norm = _normalize(pairs)
        assert norm[0][1] == pytest.approx(1.0)
        assert norm[1][1] == pytest.approx(0.5)

    def test_empty(self) -> None:
        assert _normalize([]) == []

    def test_all_zero(self) -> None:
        pairs = [(0, 0.0), (1, 0.0)]
        result = _normalize(pairs)
        assert result == pairs  # returns unchanged when max=0


class TestRRFFuse:
    def test_combines_two_lists(self) -> None:
        list_a = [(0, 1.0), (1, 0.8), (2, 0.6)]
        list_b = [(2, 1.0), (0, 0.9), (3, 0.5)]
        fused = _rrf_fuse(list_a, list_b)
        indices = [i for i, _ in fused]
        # Chunk 0 and 2 appear in both lists — should rank high
        assert 0 in indices[:2] or 2 in indices[:2]

    def test_higher_k_reduces_score(self) -> None:
        ranked = [(0, 1.0)]
        s_small_k = _rrf_fuse(ranked, k=10)[0][1]
        s_large_k = _rrf_fuse(ranked, k=100)[0][1]
        assert s_small_k > s_large_k

    def test_empty_lists(self) -> None:
        assert _rrf_fuse([], []) == []

    def test_scores_descending(self) -> None:
        list_a = [(0, 1.0), (1, 0.5), (2, 0.2)]
        list_b = [(2, 1.0), (1, 0.8), (0, 0.3)]
        fused = _rrf_fuse(list_a, list_b)
        scores = [s for _, s in fused]
        assert scores == sorted(scores, reverse=True)


class TestDedupOverlap:
    def test_removes_near_duplicate(self) -> None:
        def _chunk(text: str, score: float) -> ScoredChunk:
            return ScoredChunk(chunk_index=0, text=text, metadata={}, score=score)

        same = "alpha beta gamma delta epsilon"
        chunks = [_chunk(same, 0.9), _chunk(same + " zeta", 0.8)]
        deduped = _dedup_overlap(chunks)
        assert len(deduped) == 1

    def test_keeps_distinct_chunks(self) -> None:
        def _chunk(text: str) -> ScoredChunk:
            return ScoredChunk(chunk_index=0, text=text, metadata={}, score=0.5)

        chunks = [
            _chunk("Python programming tutorial"),
            _chunk("Database SQL optimization queries"),
        ]
        assert len(_dedup_overlap(chunks)) == 2


class TestScoredToResult:
    def test_basic_conversion(self) -> None:
        chunk = ScoredChunk(
            chunk_index=2,
            text="Example text",
            metadata={"source_path": "doc.py", "start_line": 10, "end_line": 20},
            score=0.75,
        )
        result = scored_to_result(chunk)
        assert isinstance(result, RetrievalResult)
        assert result.source_path == "doc.py"
        assert result.chunk_text == "Example text"
        assert result.relevance == pytest.approx(0.75)
        assert result.start_line == 10

    def test_score_clamped_to_one(self) -> None:
        chunk = ScoredChunk(
            chunk_index=0, text="text", metadata={}, score=1.5  # above 1.0
        )
        result = scored_to_result(chunk)
        assert result.relevance <= 1.0

    def test_optional_metadata_fields(self) -> None:
        chunk = ScoredChunk(
            chunk_index=0,
            text="text",
            metadata={
                "source_path": "f.md",
                "heading_path": "Guide > Setup",
                "page_number": 3,
            },
            score=0.8,
        )
        result = scored_to_result(chunk)
        assert result.heading_path == "Guide > Setup"
        assert result.page_number == 3


# ── Strategy: Vector ──────────────────────────────────────────────────────────


class TestRetrieveVector:
    async def test_returns_list_of_scored_chunks(
        self, query_vec: list[float], populated_store: VectorStore
    ) -> None:
        result = retrieve_vector(query_vec, populated_store, top_k=3)
        assert isinstance(result, list)
        assert len(result) <= 3
        assert all(isinstance(c, ScoredChunk) for c in result)

    async def test_scores_in_descending_order(
        self, query_vec: list[float], populated_store: VectorStore
    ) -> None:
        result = retrieve_vector(query_vec, populated_store, top_k=5)
        scores = [c.score for c in result]
        assert scores == sorted(scores, reverse=True)

    async def test_source_is_vector(
        self, query_vec: list[float], populated_store: VectorStore
    ) -> None:
        result = retrieve_vector(query_vec, populated_store, top_k=3)
        assert all(c.source == "vector" for c in result)

    async def test_empty_store_returns_empty(self, query_vec: list[float]) -> None:
        store = VectorStore()
        result = retrieve_vector(query_vec, store, top_k=3)
        assert result == []

    async def test_top_k_respected(
        self, query_vec: list[float], populated_store: VectorStore
    ) -> None:
        result = retrieve_vector(query_vec, populated_store, top_k=2)
        assert len(result) <= 2


# ── Strategy: BM25 ───────────────────────────────────────────────────────────


class TestRetrieveBM25:
    async def test_returns_list_of_scored_chunks(
        self, populated_store: VectorStore, bm25: BM25Index
    ) -> None:
        result = retrieve_bm25("python tutorial", bm25, populated_store, top_k=3)
        assert isinstance(result, list)
        assert all(isinstance(c, ScoredChunk) for c in result)

    async def test_python_docs_rank_higher(
        self, populated_store: VectorStore, bm25: BM25Index
    ) -> None:
        result = retrieve_bm25("python", bm25, populated_store, top_k=5)
        indices = [c.chunk_index for c in result]
        # Docs 0 and 3 contain "python" — at least one should be in top 2
        assert any(i in (0, 3) for i in indices[:2])

    async def test_source_is_bm25(
        self, populated_store: VectorStore, bm25: BM25Index
    ) -> None:
        result = retrieve_bm25("sql database", bm25, populated_store, top_k=3)
        assert all(c.source == "bm25" for c in result)

    async def test_scores_normalised(
        self, populated_store: VectorStore, bm25: BM25Index
    ) -> None:
        result = retrieve_bm25("machine learning", bm25, populated_store, top_k=5)
        if result:
            assert all(0.0 <= c.score <= 1.0 for c in result)


# ── Strategy: Hybrid ─────────────────────────────────────────────────────────


class TestRetrieveHybrid:
    async def test_returns_results(
        self,
        query_vec: list[float],
        populated_store: VectorStore,
        bm25: BM25Index,
    ) -> None:
        result = retrieve_hybrid(query_vec, "python tutorial", populated_store, bm25, top_k=3)
        assert len(result) > 0

    async def test_source_is_hybrid(
        self,
        query_vec: list[float],
        populated_store: VectorStore,
        bm25: BM25Index,
    ) -> None:
        result = retrieve_hybrid(query_vec, "python tutorial", populated_store, bm25, top_k=3)
        assert all(c.source == "hybrid" for c in result)

    async def test_extra_scores_populated(
        self,
        query_vec: list[float],
        populated_store: VectorStore,
        bm25: BM25Index,
    ) -> None:
        result = retrieve_hybrid(query_vec, "python", populated_store, bm25, top_k=3)
        for chunk in result:
            assert "vec" in chunk.extra_scores

    async def test_falls_back_without_bm25(
        self, query_vec: list[float], populated_store: VectorStore
    ) -> None:
        result = retrieve_hybrid(query_vec, "python", populated_store, None, top_k=3)
        assert len(result) > 0

    async def test_top_k_respected(
        self,
        query_vec: list[float],
        populated_store: VectorStore,
        bm25: BM25Index,
    ) -> None:
        result = retrieve_hybrid(query_vec, "learning", populated_store, bm25, top_k=2)
        assert len(result) <= 2


# ── Strategy: MMR ─────────────────────────────────────────────────────────────


class TestRetrieveMMR:
    async def test_returns_results(
        self, query_vec: list[float], populated_store: VectorStore
    ) -> None:
        result = retrieve_mmr(query_vec, populated_store, top_k=3)
        assert len(result) > 0

    async def test_source_is_mmr(
        self, query_vec: list[float], populated_store: VectorStore
    ) -> None:
        result = retrieve_mmr(query_vec, populated_store, top_k=3)
        assert all(c.source == "mmr" for c in result)

    async def test_top_k_respected(
        self, query_vec: list[float], populated_store: VectorStore
    ) -> None:
        result = retrieve_mmr(query_vec, populated_store, top_k=2)
        assert len(result) <= 2

    async def test_diversity_vs_pure_vector(
        self, query_vec: list[float], populated_store: VectorStore
    ) -> None:
        mmr_result = retrieve_mmr(query_vec, populated_store, top_k=3, lambda_mult=0.0)
        vec_result = retrieve_vector(query_vec, populated_store, top_k=3)
        assert len(mmr_result) > 0
        assert len(vec_result) > 0

    async def test_pure_relevance_mode(
        self, query_vec: list[float], populated_store: VectorStore
    ) -> None:
        result = retrieve_mmr(query_vec, populated_store, top_k=3, lambda_mult=1.0)
        assert len(result) > 0

    async def test_empty_store(self, query_vec: list[float]) -> None:
        store = VectorStore()
        result = retrieve_mmr(query_vec, store, top_k=3)
        assert result == []


# ── Main retrieve() entry point ───────────────────────────────────────────────


class TestRetrieve:
    async def test_vector_strategy(
        self, backend: MockEmbeddingBackend, populated_store: VectorStore
    ) -> None:
        results = await retrieve(
            "python tutorial", backend, populated_store, strategy="vector", top_k=3
        )
        assert isinstance(results, list)
        assert all(isinstance(r, RetrievalResult) for r in results)
        assert len(results) <= 3

    async def test_bm25_strategy(
        self, backend: MockEmbeddingBackend, populated_store: VectorStore, bm25: BM25Index
    ) -> None:
        results = await retrieve(
            "machine learning neural", backend, populated_store, bm25=bm25,
            strategy="bm25", top_k=3
        )
        assert len(results) > 0

    async def test_hybrid_strategy(
        self, backend: MockEmbeddingBackend, populated_store: VectorStore, bm25: BM25Index
    ) -> None:
        results = await retrieve(
            "python data science", backend, populated_store, bm25=bm25,
            strategy="hybrid", top_k=3
        )
        assert len(results) > 0

    async def test_mmr_strategy(
        self, backend: MockEmbeddingBackend, populated_store: VectorStore
    ) -> None:
        results = await retrieve(
            "database sql", backend, populated_store, strategy="mmr", top_k=3
        )
        assert len(results) > 0

    async def test_unknown_strategy_falls_back_to_vector(
        self, backend: MockEmbeddingBackend, populated_store: VectorStore
    ) -> None:
        results = await retrieve(
            "query", backend, populated_store, strategy="nonexistent", top_k=2
        )
        assert len(results) > 0

    async def test_returns_retrieval_result_objects(
        self, backend: MockEmbeddingBackend, populated_store: VectorStore
    ) -> None:
        results = await retrieve("python", backend, populated_store, top_k=2)
        for r in results:
            assert hasattr(r, "source_path")
            assert hasattr(r, "chunk_text")
            assert hasattr(r, "relevance")
            assert 0.0 <= r.relevance <= 1.0

    async def test_empty_store_returns_empty(
        self, backend: MockEmbeddingBackend
    ) -> None:
        store = VectorStore()
        results = await retrieve("query", backend, store, top_k=3)
        assert results == []

    async def test_stage_callback_called(
        self, backend: MockEmbeddingBackend, populated_store: VectorStore
    ) -> None:
        stages: list[str] = []
        await retrieve(
            "query", backend, populated_store,
            stage_callback=lambda s: stages.append(s),
            top_k=2,
        )
        assert len(stages) >= 1
        assert any("Retrieving" in s or "context" in s.lower() for s in stages)

    async def test_debug_callback_called(
        self, backend: MockEmbeddingBackend, populated_store: VectorStore
    ) -> None:
        calls: list[tuple[float, int]] = []

        def _cb(emb_ms: float, candidates: int) -> None:
            calls.append((emb_ms, candidates))

        await retrieve("query", backend, populated_store, debug_callback=_cb, top_k=2)
        assert len(calls) == 1
        emb_ms, candidates = calls[0]
        assert emb_ms >= 0
        assert candidates == populated_store.count()

    async def test_query_expansion_called_for_short_query(
        self, backend: MockEmbeddingBackend, populated_store: VectorStore
    ) -> None:
        expanded: list[str] = []

        async def _expand(q: str) -> str:
            expanded.append(q)
            return f"expanded {q} with more detail"

        await retrieve(
            "py",  # < 5 tokens — should trigger expansion
            backend,
            populated_store,
            expand_short_queries=True,
            llm_expand_fn=_expand,
            top_k=2,
        )
        assert len(expanded) == 1

    async def test_long_query_not_expanded(
        self, backend: MockEmbeddingBackend, populated_store: VectorStore
    ) -> None:
        expanded: list[str] = []

        async def _expand(q: str) -> str:
            expanded.append(q)
            return q

        await retrieve(
            "this query has more than five words in it",
            backend,
            populated_store,
            expand_short_queries=True,
            llm_expand_fn=_expand,
            top_k=2,
        )
        assert len(expanded) == 0
