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

    # --- Per-index config (added in RAG V2) ---
    chunk_strategy: str = "fixed"  # fixed|sentence|paragraph|semantic|code|heading
    chunk_size: int = 512
    chunk_overlap: int = 100
    retrieval_strategy: str = "vector"  # vector|bm25|hybrid|mmr
    reranking_enabled: bool = False
    reranking_model: str = "bge-reranker-base"
    quality_threshold: float = 0.65
    top_k: int = 3
    vector_backend: str = "pure"  # pure|faiss|chroma|lance|pinecone|azure
    ingestion_history: list[dict[str, Any]] = field(default_factory=list)
    file_mtime_cache: dict[str, float] = field(default_factory=dict)

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
            "chunk_strategy": self.chunk_strategy,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "retrieval_strategy": self.retrieval_strategy,
            "reranking_enabled": self.reranking_enabled,
            "reranking_model": self.reranking_model,
            "quality_threshold": self.quality_threshold,
            "top_k": self.top_k,
            "vector_backend": self.vector_backend,
            "ingestion_history": self.ingestion_history,
            "file_mtime_cache": self.file_mtime_cache,
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
            chunk_strategy=str(data.get("chunk_strategy", "fixed")),
            chunk_size=int(data.get("chunk_size", 512)),
            chunk_overlap=int(data.get("chunk_overlap", 100)),
            retrieval_strategy=str(data.get("retrieval_strategy", "vector")),
            reranking_enabled=bool(data.get("reranking_enabled", False)),
            reranking_model=str(data.get("reranking_model", "bge-reranker-base")),
            quality_threshold=float(data.get("quality_threshold", 0.65)),
            top_k=int(data.get("top_k", 3)),
            vector_backend=str(data.get("vector_backend", "pure")),
            ingestion_history=list(data.get("ingestion_history", [])),
            file_mtime_cache=dict(data.get("file_mtime_cache", {})),
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

    # --- Extended metadata (added in RAG V2) ---
    heading_path: str = ""  # "## Setup > ### Installation"
    function_name: str = ""  # for code chunks
    page_number: int | None = None  # for PDF chunks
    ingested_at: datetime | None = None
    file_modified_at: datetime | None = None
    chunk_index: int = 0

    def excerpt(self, max_chars: int = 120) -> str:
        """Return a short excerpt of the chunk text."""
        first_line = self.chunk_text.split("\n", 1)[0]
        if len(first_line) > max_chars:
            return first_line[:max_chars] + "…"
        return first_line

    def source_label(self) -> str:
        """Human-readable source reference for citation display."""
        label = self.source_path
        if self.heading_path:
            label += f"  §{self.heading_path}"
        elif self.function_name:
            label += f"  {self.function_name}()"
        elif self.start_line and self.end_line:
            label += f"  L{self.start_line}–{self.end_line}"
        elif self.page_number is not None:
            label += f"  p.{self.page_number}"
        return label
