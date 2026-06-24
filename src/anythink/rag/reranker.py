"""Cross-encoder re-rankers for the RAG retrieval pipeline.

Re-ranking improves retrieval quality by applying a more accurate (but slower)
cross-encoder model to a small candidate pool retrieved by a fast first-pass
strategy.

Supported re-rankers:
  CrossEncoderReranker  — local, via sentence-transformers CrossEncoder
  CohereReranker        — cloud, via Cohere Rerank API (httpx)

Both implement ``BaseReranker`` with:
  ``is_available()``             — dependency / credentials check
  ``rerank(query, chunks, k)``  — async, returns top-k re-scored ScoredChunks
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anythink.rag.retrieval import ScoredChunk


# ── Abstract base ─────────────────────────────────────────────────────────────


class BaseReranker(ABC):
    """Common interface for all re-rankers."""

    @abstractmethod
    def is_available(self) -> bool:
        """True if the re-ranker's dependencies/credentials are satisfied."""
        ...

    @abstractmethod
    async def rerank(
        self,
        query: str,
        chunks: list[ScoredChunk],
        top_k: int,
    ) -> list[ScoredChunk]:
        """Re-score *chunks* against *query* and return the top *top_k*.

        The returned chunks have ``score`` replaced by the re-ranker's score
        and ``source`` set to ``"reranked"``.
        """
        ...


# ── CrossEncoderReranker ──────────────────────────────────────────────────────


class CrossEncoderReranker(BaseReranker):
    """Local cross-encoder re-ranker via sentence-transformers.

    Requires ``pip install anythink[rag]`` (sentence-transformers is already
    listed there).  The model is downloaded on first use and cached by
    HuggingFace Hub.
    """

    SUPPORTED_MODELS: dict[str, str] = {
        "bge-reranker-base": "BAAI/bge-reranker-base",
        "bge-reranker-large": "BAAI/bge-reranker-large",
        "ms-marco-MiniLM-L-6-v2": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "ms-marco-MiniLM-L-12-v2": "cross-encoder/ms-marco-MiniLM-L-12-v2",
    }

    def __init__(self, model_name: str = "bge-reranker-base") -> None:
        self._model_name = model_name
        self._hf_name = self.SUPPORTED_MODELS.get(model_name, model_name)
        self._model: object | None = None

    def is_available(self) -> bool:
        """True if sentence-transformers is importable."""
        try:
            from sentence_transformers import CrossEncoder  # noqa: F401

            return True
        except ImportError:
            return False

    def _load(self) -> None:
        """Lazy-load the cross-encoder model on first use."""
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._hf_name)

    async def rerank(
        self,
        query: str,
        chunks: list[ScoredChunk],
        top_k: int,
    ) -> list[ScoredChunk]:
        """Score each (query, chunk) pair with the cross-encoder; return top-k."""
        import asyncio

        from anythink.rag.retrieval import ScoredChunk as SC

        if not chunks:
            return []

        self._load()
        model = self._model
        pairs = [(query, c.text) for c in chunks]

        # Run CPU-bound inference in a thread to avoid blocking the event loop
        raw_scores: list[float] = await asyncio.to_thread(
            lambda: list(model.predict(pairs))  # type: ignore[union-attr]
        )

        scored = sorted(
            zip(raw_scores, chunks, strict=False),
            key=lambda t: t[0],
            reverse=True,
        )

        result: list[SC] = []
        for score, chunk in scored[:top_k]:
            result.append(
                SC(
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    metadata=chunk.metadata,
                    score=float(score),
                    source="reranked",
                    extra_scores={**chunk.extra_scores, "original": chunk.score},
                )
            )
        return result


# ── CohereReranker ────────────────────────────────────────────────────────────


class CohereReranker(BaseReranker):
    """Cloud re-ranker via the Cohere Rerank API.

    Requires a valid Cohere API key and internet access.  The key should be
    stored via ``anythink keys add cohere-rerank <key>`` and passed here.
    """

    _ENDPOINT = "https://api.cohere.ai/v1/rerank"
    _DEFAULT_MODEL = "rerank-english-v3.0"

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def is_available(self) -> bool:
        """True if an API key is present."""
        return bool(self._api_key)

    async def rerank(
        self,
        query: str,
        chunks: list[ScoredChunk],
        top_k: int,
    ) -> list[ScoredChunk]:
        """Call the Cohere Rerank endpoint and return re-scored top-*k* chunks."""
        import httpx

        from anythink.rag.retrieval import ScoredChunk as SC

        if not chunks:
            return []

        documents = [c.text for c in chunks]
        payload = {
            "model": self._model,
            "query": query,
            "documents": documents,
            "top_n": min(top_k, len(documents)),
            "return_documents": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        result: list[SC] = []
        for hit in data.get("results", []):
            orig_idx = int(hit["index"])
            score = float(hit["relevance_score"])
            chunk = chunks[orig_idx]
            result.append(
                SC(
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    metadata=chunk.metadata,
                    score=score,
                    source="reranked",
                    extra_scores={**chunk.extra_scores, "original": chunk.score},
                )
            )
        return result

    @property
    def _endpoint(self) -> str:
        return self._ENDPOINT


# ── Factory ───────────────────────────────────────────────────────────────────


def get_reranker(
    model_name: str,
    api_key: str | None = None,
) -> BaseReranker | None:
    """Return the appropriate re-ranker for *model_name*, or None if unavailable.

    Cross-encoder models map to ``CrossEncoderReranker``.
    ``"cohere-rerank"`` maps to ``CohereReranker`` (requires *api_key*).
    Returns None if the required dependency / credentials are absent.
    """
    if model_name == "cohere-rerank":
        if not api_key:
            return None
        r: BaseReranker = CohereReranker(api_key=api_key)
    else:
        r = CrossEncoderReranker(model_name=model_name)

    return r if r.is_available() else None
