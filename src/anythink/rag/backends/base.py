"""Abstract base class for all RAG vector store backends."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anythink.rag.retrieval import ScoredChunk


class BaseVectorStore(ABC):
    """Interface every vector-store backend must implement.

    Each backend is responsible for:
    - Storing chunk texts, metadata, and embedding vectors.
    - Supporting ranked similarity queries (``query_ranked``).
    - Providing random-access to individual chunks (``get_chunk_at``,
      ``get_vector_at``) so the retrieval strategies can apply MMR and
      hybrid ranking on top of the raw scores.
    - Persisting data to disk and loading it back (``persist`` / ``load``).
    - Removing chunks belonging to a changed/deleted source file
      (``remove_by_source``), which is required for incremental ingestion.

    Path convention:
    ``persist(base_path)`` and ``load(base_path)`` receive a path WITH NO
    EXTENSION (e.g. ``~/.cache/anythink/rag/myindex``).  Each backend
    appends its own suffix(es) internally:
    - Pure  → ``{base_path}.store.gz``
    - FAISS → ``{base_path}.faiss``  +  ``{base_path}.meta.gz``
    - Chroma → ``{base_path}_chroma/``
    - Lance  → ``{base_path}.lance``
    """

    # ── write ──────────────────────────────────────────────────────────────

    @abstractmethod
    def add(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        """Bulk-add *texts* with their pre-computed embedding *vectors*."""
        ...

    @abstractmethod
    def remove_by_source(self, source_path: str) -> int:
        """Remove all chunks whose metadata ``source_path`` matches.

        Returns the number of chunks removed.
        """
        ...

    # ── read ───────────────────────────────────────────────────────────────

    @abstractmethod
    def count(self) -> int:
        """Return the total number of stored chunks."""
        ...

    @abstractmethod
    def query_ranked(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
    ) -> list[tuple[int, float]]:
        """Return ``(chunk_index, score)`` pairs for the top-*k* matches.

        Scores should be in [0, 1] (cosine similarity or normalised equivalent).
        Results must be sorted descending by score.
        """
        ...

    @abstractmethod
    def get_chunk_at(self, idx: int) -> tuple[str, dict[str, Any]]:
        """Return ``(text, metadata)`` for the chunk at sequential *idx*."""
        ...

    @abstractmethod
    def get_vector_at(self, idx: int) -> list[float]:
        """Return the raw embedding vector for the chunk at sequential *idx*."""
        ...

    @abstractmethod
    def all_texts(self) -> list[str]:
        """Return all chunk texts in store order (used for BM25 corpus)."""
        ...

    def query(self, query_vector: list[float], top_k: int = 5) -> list[ScoredChunk]:
        """Return top-*k* chunks as ``ScoredChunk`` objects.

        Default implementation wraps ``query_ranked`` + ``get_chunk_at``.
        Backends may override for efficiency.
        """
        from anythink.rag.retrieval import ScoredChunk

        result: list[ScoredChunk] = []
        for idx, score in self.query_ranked(query_vector, top_k=top_k):
            text, meta = self.get_chunk_at(idx)
            result.append(
                ScoredChunk(chunk_index=idx, text=text, metadata=meta, score=score)
            )
        return result

    def supports_metadata_filter(self) -> bool:
        """True if this backend can filter by metadata fields natively."""
        return False

    # ── persistence ────────────────────────────────────────────────────────

    @abstractmethod
    def persist(self, base_path: Path) -> None:
        """Persist all data to disk.  ``base_path`` has no extension."""
        ...

    @classmethod
    @abstractmethod
    def load(cls, base_path: Path) -> "BaseVectorStore":
        """Load from disk.  ``base_path`` has no extension."""
        ...

    @classmethod
    def exists(cls, base_path: Path) -> bool:
        """Return True if persisted data exists at *base_path*."""
        return False

    @classmethod
    def delete_files(cls, base_path: Path) -> None:
        """Remove all persisted files for this backend at *base_path*."""

    @classmethod
    def rename_files(cls, old_base: Path, new_base: Path) -> None:
        """Rename all persisted files from *old_base* to *new_base*."""

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        """Cosine similarity between two equal-length float vectors."""
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)

    @staticmethod
    def _normalize(v: list[float]) -> list[float]:
        """Return a unit-length copy of *v*."""
        norm = math.sqrt(sum(x * x for x in v))
        if norm == 0.0:
            return v
        return [x / norm for x in v]
