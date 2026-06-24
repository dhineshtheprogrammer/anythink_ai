"""ChromaDB vector store backend.

Requires ``pip install anythink[rag-chroma]`` (chromadb>=0.5).

Storage layout:
  {base_path}_chroma/  — ChromaDB persistent directory (DuckDB+Parquet)

ChromaDB collections support built-in metadata filtering (``where`` clauses),
so ``supports_metadata_filter()`` returns True for this backend.

Sequential integer indices are maintained via an internal ``_id_list`` that
maps position → ChromaDB document ID.  This allows ``get_chunk_at(idx)`` and
``get_vector_at(idx)`` to work like the pure backend.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anythink.exceptions import RAGError
from anythink.rag.backends.base import BaseVectorStore

_SUFFIX = "_chroma"


class ChromaVectorStore(BaseVectorStore):
    """ChromaDB-backed vector store with built-in metadata filtering."""

    def __init__(self) -> None:
        self._client: object | None = None
        self._collection: object | None = None
        self._id_list: list[str] = []  # sequential idx → chroma doc ID
        self._texts: list[str] = []
        self._metas: list[dict[str, Any]] = []

    def is_available(self) -> bool:
        try:
            import chromadb  # noqa: F401

            return True
        except ImportError:
            return False

    def _require_chroma(self) -> Any:
        try:
            import chromadb

            return chromadb
        except ImportError as exc:
            raise RAGError(
                "chromadb not installed.",
                user_message="ChromaDB backend requires: pip install anythink[rag-chroma]",
            ) from exc

    def _init_client(self, persist_dir: Path) -> None:
        chromadb = self._require_chroma()
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(  # type: ignore[union-attr]
            name="anythink_rag",
            metadata={"hnsw:space": "cosine"},
        )

    # ── write ──────────────────────────────────────────────────────────────

    def add(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        if self._collection is None or not texts:
            return

        import uuid

        ids: list[str] = [str(uuid.uuid4()) for _ in texts]
        # ChromaDB requires metadata values to be str/int/float/bool
        safe_metas = [
            {k: (v if isinstance(v, (str, int, float, bool)) else json.dumps(v)) for k, v in m.items()}
            for m in metadatas
        ]
        self._collection.add(  # type: ignore[union-attr]
            ids=ids,
            documents=texts,
            embeddings=vectors,
            metadatas=safe_metas,
        )
        self._id_list.extend(ids)
        self._texts.extend(texts)
        self._metas.extend(metadatas)

    def remove_by_source(self, source_path: str) -> int:
        if self._collection is None:
            return 0
        try:
            results = self._collection.get(  # type: ignore[union-attr]
                where={"source_path": source_path}
            )
            ids = results.get("ids", [])
            if ids:
                self._collection.delete(ids=ids)  # type: ignore[union-attr]
            removed = len(ids)
        except Exception:
            removed = 0

        # Sync local index lists
        keep = [
            i for i, m in enumerate(self._metas)
            if str(m.get("source_path", "")) != source_path
        ]
        self._texts = [self._texts[i] for i in keep]
        self._metas = [self._metas[i] for i in keep]
        self._id_list = [self._id_list[i] for i in keep if i < len(self._id_list)]
        return removed

    # ── read ───────────────────────────────────────────────────────────────

    def count(self) -> int:
        if self._collection is None:
            return 0
        return self._collection.count()  # type: ignore[union-attr]

    def query_ranked(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
    ) -> list[tuple[int, float]]:
        if self._collection is None or self.count() == 0:
            return []

        k = min(top_k, self.count())
        results = self._collection.query(  # type: ignore[union-attr]
            query_embeddings=[query_vector],
            n_results=k,
            include=["distances", "documents"],
        )
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        ranked: list[tuple[int, float]] = []
        for doc_id, dist in zip(ids, distances, strict=False):
            if doc_id in self._id_list:
                seq_idx = self._id_list.index(doc_id)
                # Chroma cosine distance → similarity
                score = float(max(0.0, 1.0 - dist))
                ranked.append((seq_idx, score))

        return sorted(ranked, key=lambda x: x[1], reverse=True)

    def get_chunk_at(self, idx: int) -> tuple[str, dict[str, Any]]:
        return self._texts[idx], self._metas[idx]

    def get_vector_at(self, idx: int) -> list[float]:
        if self._collection is None or idx >= len(self._id_list):
            return []
        try:
            doc_id = self._id_list[idx]
            result = self._collection.get(  # type: ignore[union-attr]
                ids=[doc_id], include=["embeddings"]
            )
            embeddings = result.get("embeddings", [])
            if embeddings:
                return list(map(float, embeddings[0]))
        except Exception:
            pass
        return []

    def all_texts(self) -> list[str]:
        return list(self._texts)

    def supports_metadata_filter(self) -> bool:
        return True

    # ── persistence ────────────────────────────────────────────────────────

    def persist(self, base_path: Path) -> None:
        # ChromaDB PersistentClient auto-persists; nothing extra needed.
        pass

    @classmethod
    def load(cls, base_path: Path) -> ChromaVectorStore:
        store = cls()
        persist_dir = Path(str(base_path) + _SUFFIX)
        if not persist_dir.exists():
            return store

        store._init_client(persist_dir)

        # Rebuild local index lists from ChromaDB
        try:
            results = store._collection.get(include=["documents", "metadatas", "embeddings"])  # type: ignore[union-attr]
            ids = results.get("ids", [])
            docs = results.get("documents", [])
            metas = results.get("metadatas", []) or [{}] * len(ids)
            store._id_list = list(ids)
            store._texts = list(docs)
            store._metas = [dict(m) for m in metas]
        except Exception:
            pass

        return store

    @classmethod
    def exists(cls, base_path: Path) -> bool:
        return Path(str(base_path) + _SUFFIX).exists()

    @classmethod
    def delete_files(cls, base_path: Path) -> None:
        import shutil

        p = Path(str(base_path) + _SUFFIX)
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    @classmethod
    def rename_files(cls, old_base: Path, new_base: Path) -> None:
        old = Path(str(old_base) + _SUFFIX)
        new = Path(str(new_base) + _SUFFIX)
        if old.exists():
            old.rename(new)
