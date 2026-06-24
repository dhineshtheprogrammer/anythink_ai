"""Retrieval strategies for RAG: vector, BM25, hybrid (RRF), and MMR.

All strategy functions operate on already-built indexes and return
``ScoredChunk`` lists.  The top-level ``retrieve()`` function orchestrates
embedding, strategy dispatch, optional query expansion, optional re-ranking,
and converts the final set to ``RetrievalResult`` objects.

Strategy overview:
  vector  — cosine similarity between query and chunk embeddings
  bm25    — BM25 term-frequency ranking (keyword matching)
  hybrid  — Reciprocal Rank Fusion of vector + BM25 ranked lists
  mmr     — Maximum Marginal Relevance: balance relevance and diversity
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from anythink.rag.models import RetrievalResult

if TYPE_CHECKING:
    from anythink.embeddings.base import BaseEmbeddingBackend
    from anythink.rag.bm25 import BM25Index
    from anythink.rag.reranker import BaseReranker
    from anythink.rag.store import VectorStore


# ── ScoredChunk ───────────────────────────────────────────────────────────────


@dataclass
class ScoredChunk:
    """Intermediate representation used by retrieval strategies.

    Converted to ``RetrievalResult`` after all retrieval/reranking stages.
    """

    chunk_index: int
    text: str
    metadata: dict[str, Any]
    score: float
    source: str = "vector"  # "vector" | "bm25" | "hybrid" | "mmr" | "reranked"
    extra_scores: dict[str, float] = field(default_factory=dict)


# ── Score helpers ─────────────────────────────────────────────────────────────


def _normalize(pairs: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Normalise scores to [0, 1] by dividing by the maximum."""
    if not pairs:
        return []
    max_s = max(s for _, s in pairs)
    if max_s <= 0:
        return pairs
    return [(idx, s / max_s) for idx, s in pairs]


def _rrf_fuse(
    *ranked_lists: list[tuple[int, float]],
    k: int = 60,
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion across multiple ranked lists.

    rrf_score(d) = Σ_list  1 / (k + rank_in_list(d))

    ``k=60`` is the standard constant; it dampens the advantage of top-rank
    positions without fully eliminating it.
    """
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, (idx, _) in enumerate(ranked, 1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ── Strategy 1: Pure vector similarity ───────────────────────────────────────


def retrieve_vector(
    query_vec: list[float],
    store: VectorStore,
    top_k: int,
) -> list[ScoredChunk]:
    """Return top-*k* chunks by cosine similarity to *query_vec*."""
    ranked = store.query_ranked(query_vec, top_k=top_k)
    result = []
    for idx, score in ranked:
        text, meta = store.get_chunk_at(idx)
        result.append(
            ScoredChunk(
                chunk_index=idx,
                text=text,
                metadata=meta,
                score=round(score, 4),
                source="vector",
            )
        )
    return result


# ── Strategy 2: BM25 keyword search ──────────────────────────────────────────


def retrieve_bm25(
    query: str,
    bm25: BM25Index,
    store: VectorStore,
    top_k: int,
) -> list[ScoredChunk]:
    """Return top-*k* chunks by BM25 score; normalised to [0, 1]."""
    raw = bm25.score(query, top_k)
    normalised = _normalize(raw)
    result = []
    for idx, score in normalised:
        text, meta = store.get_chunk_at(idx)
        result.append(
            ScoredChunk(
                chunk_index=idx,
                text=text,
                metadata=meta,
                score=round(score, 4),
                source="bm25",
            )
        )
    return result


# ── Strategy 3: Hybrid — Reciprocal Rank Fusion ───────────────────────────────


def retrieve_hybrid(
    query_vec: list[float],
    query: str,
    store: VectorStore,
    bm25: BM25Index | None,
    top_k: int,
    *,
    rrf_k: int = 60,
    candidate_factor: int = 4,
) -> list[ScoredChunk]:
    """Fuse vector and BM25 ranked lists with Reciprocal Rank Fusion.

    If *bm25* is None or empty, falls back to pure vector retrieval.

    ``candidate_factor`` controls how many candidates each sub-ranker fetches
    before fusion (``top_k * candidate_factor``).  Higher values give RRF more
    to work with at the cost of a larger BM25 scan.
    """
    fetch = max(top_k, top_k * candidate_factor)

    # Vector candidates
    vec_ranked = store.query_ranked(query_vec, top_k=fetch)

    # BM25 candidates (skip if unavailable)
    bm25_ranked = bm25.score(query, fetch) if bm25 is not None and bm25.is_built else []

    if not bm25_ranked:
        # No BM25 — fall back to vector
        return retrieve_vector(query_vec, store, top_k)

    fused = _rrf_fuse(vec_ranked, bm25_ranked, k=rrf_k)[:top_k]

    # Normalise fused RRF scores to [0, 1]
    fused = _normalize(fused)
    result = []
    for idx, score in fused:
        text, meta = store.get_chunk_at(idx)
        result.append(
            ScoredChunk(
                chunk_index=idx,
                text=text,
                metadata=meta,
                score=round(score, 4),
                source="hybrid",
                extra_scores={
                    "vec": next((s for i, s in vec_ranked if i == idx), 0.0),
                    "bm25": next((s for i, s in (_normalize(bm25_ranked)) if i == idx), 0.0),
                },
            )
        )
    return result


# ── Strategy 4: Maximum Marginal Relevance ────────────────────────────────────


def retrieve_mmr(
    query_vec: list[float],
    store: VectorStore,
    top_k: int,
    *,
    lambda_mult: float = 0.5,
    fetch_k: int | None = None,
) -> list[ScoredChunk]:
    """Select chunks that balance relevance to the query and diversity.

    MMR score at each step:
      mmr(d) = λ * sim(d, query) - (1-λ) * max_{d' ∈ selected} sim(d, d')

    ``lambda_mult`` = 1.0 → pure relevance (identical to vector strategy).
    ``lambda_mult`` = 0.0 → maximum diversity, ignoring query relevance.
    0.5 (default) gives equal weight to both objectives.
    """
    if fetch_k is None:
        fetch_k = min(store.count(), max(top_k * 4, 20))

    # Fetch initial candidate pool by cosine similarity
    candidates = store.query_ranked(query_vec, top_k=fetch_k)
    if not candidates:
        return []

    selected: list[tuple[int, float]] = []
    selected_vecs: list[list[float]] = []
    remaining = list(candidates)

    while remaining and len(selected) < top_k:
        best_idx: int | None = None
        best_score = -math.inf

        for chunk_idx, rel_score in remaining:
            # Relevance term
            relevance = rel_score

            # Redundancy term: max cosine sim to already-selected chunks
            if selected_vecs:
                vec = store.get_vector_at(chunk_idx)
                max_sim = max(_cosine(vec, sv) for sv in selected_vecs)
            else:
                max_sim = 0.0

            mmr_score = lambda_mult * relevance - (1.0 - lambda_mult) * max_sim

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = chunk_idx

        if best_idx is None:
            break

        selected.append((best_idx, best_score))
        selected_vecs.append(store.get_vector_at(best_idx))
        remaining = [(i, s) for i, s in remaining if i != best_idx]

    # Normalise MMR scores
    selected_norm = _normalize(selected)
    result = []
    for idx, score in selected_norm:
        text, meta = store.get_chunk_at(idx)
        result.append(
            ScoredChunk(
                chunk_index=idx,
                text=text,
                metadata=meta,
                score=round(score, 4),
                source="mmr",
            )
        )
    return result


# ── Conversion helpers ────────────────────────────────────────────────────────


def scored_to_result(chunk: ScoredChunk) -> RetrievalResult:
    """Convert a ``ScoredChunk`` to a ``RetrievalResult``."""
    meta = chunk.metadata
    return RetrievalResult(
        source_path=str(meta.get("source_path", "unknown")),
        chunk_text=chunk.text,
        relevance=round(min(1.0, max(0.0, chunk.score)), 4),
        start_line=int(meta["start_line"]) if "start_line" in meta else None,
        end_line=int(meta["end_line"]) if "end_line" in meta else None,
        heading_path=str(meta.get("heading_path", "")),
        function_name=str(meta.get("function_name", "")),
        page_number=int(meta["page_number"]) if "page_number" in meta else None,
        chunk_index=int(meta.get("chunk_index", chunk.chunk_index)),
    )


def _dedup_overlap(chunks: list[ScoredChunk]) -> list[ScoredChunk]:
    """Remove near-duplicate chunks that share more than 80% of their text.

    Keeps the higher-scored chunk when duplicates are found.
    """
    seen: list[ScoredChunk] = []
    for chunk in chunks:
        tokens_new = set(chunk.text.lower().split())
        is_dup = False
        for prev in seen:
            tokens_prev = set(prev.text.lower().split())
            union = len(tokens_new | tokens_prev)
            if union == 0:
                continue
            jaccard = len(tokens_new & tokens_prev) / union
            if jaccard >= 0.80:
                is_dup = True
                break
        if not is_dup:
            seen.append(chunk)
    return seen


# ── Main entry point ──────────────────────────────────────────────────────────


async def retrieve(
    query: str,
    backend: BaseEmbeddingBackend,
    store: VectorStore,
    bm25: BM25Index | None = None,
    *,
    strategy: str = "vector",
    top_k: int = 3,
    reranker: BaseReranker | None = None,
    rerank_candidates: int = 20,
    expand_short_queries: bool = True,
    llm_expand_fn: Callable[[str], Any] | None = None,
    stage_callback: Callable[[str], None] | None = None,
    debug_callback: Callable[[float, int], None] | None = None,
) -> list[RetrievalResult]:
    """Full retrieval pipeline: expand → embed → strategy → rerank → convert.

    Args:
        query:               User query string.
        backend:             Embedding backend for query vectorisation.
        store:               VectorStore to search.
        bm25:                BM25Index for keyword strategies (optional).
        strategy:            One of "vector", "bm25", "hybrid", "mmr".
        top_k:               Final number of results to return.
        reranker:            Cross-encoder re-ranker (optional).
        rerank_candidates:   Candidate pool size before re-ranking.
        expand_short_queries: Expand queries shorter than 5 words.
        llm_expand_fn:       Async callable (query) → expanded_query.
        stage_callback:      Called with stage label for thinking-widget updates.
        debug_callback:      Called with (emb_ms, candidates) for debug tracing.

    Returns:
        List of up to *top_k* ``RetrievalResult`` objects, best-first.
    """
    import time as _t

    if store.count() == 0:
        return []

    # ── Stage 1: Query expansion ──────────────────────────────────────────────
    effective_query = query
    if expand_short_queries and llm_expand_fn and len(query.split()) < 5:
        try:
            expanded = await llm_expand_fn(query)
            if expanded and expanded.strip():
                effective_query = expanded.strip()
        except Exception:
            pass  # Use original query on any failure

    # ── Stage 2: Embed query ──────────────────────────────────────────────────
    if stage_callback:
        stage_callback("Retrieving context…")

    t_emb = _t.monotonic()
    vecs = await backend.embed([effective_query])
    emb_ms = (_t.monotonic() - t_emb) * 1000
    query_vec = vecs[0]

    if debug_callback:
        import contextlib

        with contextlib.suppress(Exception):
            debug_callback(emb_ms, store.count())

    # ── Stage 3: Candidate retrieval ──────────────────────────────────────────
    # When re-ranking, fetch a larger candidate pool first
    fetch_k = rerank_candidates if reranker is not None else top_k

    match strategy:
        case "bm25":
            if bm25 is not None and bm25.is_built:
                candidates = retrieve_bm25(effective_query, bm25, store, fetch_k)
            else:
                candidates = retrieve_vector(query_vec, store, fetch_k)
        case "hybrid":
            candidates = retrieve_hybrid(query_vec, effective_query, store, bm25, fetch_k)
        case "mmr":
            candidates = retrieve_mmr(query_vec, store, fetch_k)
        case _:
            # "vector" and any unknown strategy
            candidates = retrieve_vector(query_vec, store, fetch_k)

    # De-duplicate overlap-adjacent chunks
    candidates = _dedup_overlap(candidates)

    # ── Stage 4: Re-ranking ───────────────────────────────────────────────────
    if reranker is not None and candidates:
        if stage_callback:
            stage_callback("Re-ranking results…")
        try:
            candidates = await reranker.rerank(effective_query, candidates, top_k)
        except Exception:
            # Re-ranking failure is non-fatal — fall back to strategy results
            candidates = candidates[:top_k]
    else:
        candidates = candidates[:top_k]

    return [scored_to_result(c) for c in candidates]
