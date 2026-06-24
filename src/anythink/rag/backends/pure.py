"""Pure-Python vector store backend — no external dependencies required.

Adapted from the original ``anythink.rag.store.VectorStore`` to implement
``BaseVectorStore``.  The store is held entirely in memory as a list of
``_Chunk`` objects and optionally persisted as gzip-compressed JSON.

Suitable for indexes up to ~50 k chunks at typical embedding sizes.
"""

from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anythink.rag.backends.base import BaseVectorStore


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


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


_SUFFIX = ".store.gz"


class PureVectorStore(BaseVectorStore):
    """In-memory, pure-Python vector store with gzip-JSON persistence."""

    def __init__(self) -> None:
        self._chunks: list[_Chunk] = []

    # ── write ──────────────────────────────────────────────────────────────

    def add(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        for text, meta, vec in zip(texts, metadatas, vectors, strict=False):
            self._chunks.append(_Chunk(text, meta, vec))

    def remove_by_source(self, source_path: str) -> int:
        before = len(self._chunks)
        self._chunks = [
            c for c in self._chunks if str(c.metadata.get("source_path", "")) != source_path
        ]
        return before - len(self._chunks)

    def clear(self) -> None:
        self._chunks.clear()

    # ── read ───────────────────────────────────────────────────────────────

    def count(self) -> int:
        return len(self._chunks)

    def query_ranked(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
    ) -> list[tuple[int, float]]:
        if not self._chunks:
            return []
        scored = [(_cosine(query_vector, c.vector), i) for i, c in enumerate(self._chunks)]
        scored.sort(key=lambda t: t[0], reverse=True)
        return [(idx, score) for score, idx in scored[:top_k]]

    def get_chunk_at(self, idx: int) -> tuple[str, dict[str, Any]]:
        c = self._chunks[idx]
        return c.text, c.metadata

    def get_vector_at(self, idx: int) -> list[float]:
        return self._chunks[idx].vector

    def all_texts(self) -> list[str]:
        return [c.text for c in self._chunks]

    # ── persistence ────────────────────────────────────────────────────────

    def persist(self, base_path: Path) -> None:
        path = Path(str(base_path) + _SUFFIX)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [c.to_dict() for c in self._chunks]
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(data, fh)

    @classmethod
    def load(cls, base_path: Path) -> PureVectorStore:
        store = cls()
        path = Path(str(base_path) + _SUFFIX)
        if not path.exists():
            return store
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            data: list[dict[str, Any]] = json.load(fh)
        store._chunks = [_Chunk.from_dict(d) for d in data]
        return store

    @classmethod
    def exists(cls, base_path: Path) -> bool:
        return Path(str(base_path) + _SUFFIX).exists()

    @classmethod
    def delete_files(cls, base_path: Path) -> None:
        Path(str(base_path) + _SUFFIX).unlink(missing_ok=True)

    @classmethod
    def rename_files(cls, old_base: Path, new_base: Path) -> None:
        old = Path(str(old_base) + _SUFFIX)
        new = Path(str(new_base) + _SUFFIX)
        if old.exists():
            old.rename(new)
