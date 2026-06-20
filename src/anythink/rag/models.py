"""Data models for RAG index metadata and retrieval results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class IndexInfo:
    """Metadata for a named RAG index."""

    name: str
    index_type: str  # "project" | "document"
    source_path: str
    persistence_mode: str  # "rebuild" | "persist"
    embedding_backend: str = "local"
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_indexed: datetime | None = None
    file_count: int = 0
    chunk_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "index_type": self.index_type,
            "source_path": self.source_path,
            "persistence_mode": self.persistence_mode,
            "embedding_backend": self.embedding_backend,
            "created_at": self.created_at.isoformat(),
            "last_indexed": self.last_indexed.isoformat() if self.last_indexed else None,
            "file_count": self.file_count,
            "chunk_count": self.chunk_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IndexInfo:
        last = data.get("last_indexed")
        return cls(
            name=str(data["name"]),
            index_type=str(data.get("index_type", "document")),
            source_path=str(data.get("source_path", "")),
            persistence_mode=str(data.get("persistence_mode", "rebuild")),
            embedding_backend=str(data.get("embedding_backend", "local")),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.utcnow()
            ),
            last_indexed=datetime.fromisoformat(last) if last else None,
            file_count=int(data.get("file_count", 0)),
            chunk_count=int(data.get("chunk_count", 0)),
        )


@dataclass
class RetrievalResult:
    """A single chunk retrieved from a RAG index."""

    source_path: str
    chunk_text: str
    relevance: float  # cosine similarity 0.0–1.0
    start_line: int | None = None
    end_line: int | None = None
    section: str | None = None

    def excerpt(self, max_chars: int = 120) -> str:
        """Return a short excerpt of the chunk text."""
        first_line = self.chunk_text.split("\n", 1)[0]
        if len(first_line) > max_chars:
            return first_line[:max_chars] + "…"
        return first_line
