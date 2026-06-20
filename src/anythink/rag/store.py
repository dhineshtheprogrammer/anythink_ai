"""Pure-Python vector store with JSON persistence and cosine-similarity retrieval."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anythink.rag.models import RetrievalResult


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass
class _Chunk:
    text: str
    metadata: dict[str, Any]
    vector: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "metadata": self.metadata, "vector": self.vector}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _Chunk:
        return cls(
            text=str(data["text"]),
            metadata=dict(data.get("metadata", {})),
            vector=list(map(float, data["vector"])),
        )


class VectorStore:
    """In-memory vector store backed by JSON for optional persistence.

    Suitable for small-to-medium indexes (< 50 k chunks at typical embedding
    sizes).  For large indexes swap in a Chroma-backed store via the
    ``anythink.vector_stores`` entry-point group (Phase 7+).
    """

    def __init__(self) -> None:
        self._chunks: list[_Chunk] = []

    # ── write ──────────────────────────────────────────────────────────────

    def add(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        """Bulk-add *texts* with their pre-computed *vectors*."""
        for text, meta, vec in zip(texts, metadatas, vectors, strict=False):
            self._chunks.append(_Chunk(text, meta, vec))

    def clear(self) -> None:
        self._chunks.clear()

    # ── read ───────────────────────────────────────────────────────────────

    def query(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Return the top-*k* most similar chunks."""
        if not self._chunks:
            return []

        scored = [(_cosine(query_vector, c.vector), c) for c in self._chunks]
        scored.sort(key=lambda t: t[0], reverse=True)

        results: list[RetrievalResult] = []
        for score, chunk in scored[:top_k]:
            meta = chunk.metadata
            results.append(
                RetrievalResult(
                    source_path=str(meta.get("source_path", "unknown")),
                    chunk_text=chunk.text,
                    relevance=round(score, 4),
                    start_line=(int(meta["start_line"]) if "start_line" in meta else None),
                    end_line=int(meta["end_line"]) if "end_line" in meta else None,
                )
            )
        return results

    def count(self) -> int:
        return len(self._chunks)

    # ── persistence ────────────────────────────────────────────────────────

    def persist(self, path: Path) -> None:
        """Serialise all chunks to *path* as gzip-compressed JSON."""
        import gzip

        path.parent.mkdir(parents=True, exist_ok=True)
        data = [c.to_dict() for c in self._chunks]
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(data, fh)

    @classmethod
    def load(cls, path: Path) -> VectorStore:
        """Deserialise a previously persisted store from *path*."""
        import gzip

        store = cls()
        if not path.exists():
            return store
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            data: list[dict[str, Any]] = json.load(fh)
        store._chunks = [_Chunk.from_dict(d) for d in data]
        return store
