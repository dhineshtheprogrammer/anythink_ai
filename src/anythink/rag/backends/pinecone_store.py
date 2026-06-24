"""Pinecone serverless vector store backend.

Requires ``pip install anythink[rag-pinecone]`` (pinecone-client>=3.0) and
a valid Pinecone API key stored via ``anythink keys add pinecone <key>``.

Pinecone is a cloud-only backend; ``persist()`` and ``load()`` are no-ops
because the index lives in the cloud.  The local ``_texts``/``_metas`` cache
is rebuilt from Pinecone on ``load()`` (using ``fetch``).

Dimension and index name are controlled by the ``_PINECONE_INDEX`` class
variable, or passed via ``from_config(index_name, api_key, dimension)``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from anythink.exceptions import RAGError
from anythink.rag.backends.base import BaseVectorStore


class PineconeVectorStore(BaseVectorStore):
    """Pinecone serverless backend (cloud storage, no local files)."""

    _PINECONE_INDEX = "anythink-rag"

    def __init__(
        self,
        api_key: str = "",
        index_name: str = _PINECONE_INDEX,
        dimension: int = 384,
        namespace: str = "default",
    ) -> None:
        self._api_key = api_key
        self._index_name = index_name
        self._dimension = dimension
        self._namespace = namespace
        self._index: object | None = None
        self._texts: list[str] = []
        self._metas: list[dict[str, Any]] = []
        self._ids: list[str] = []

    def is_available(self) -> bool:
        try:
            from pinecone import Pinecone  # noqa: F401

            return bool(self._api_key)
        except ImportError:
            return False

    def _require_pinecone(self) -> Any:
        try:
            from pinecone import Pinecone

            return Pinecone
        except ImportError as exc:
            raise RAGError(
                "pinecone-client not installed.",
                user_message="Pinecone backend requires: pip install anythink[rag-pinecone]",
            ) from exc

    def _get_index(self) -> object:
        if self._index is None:
            Pinecone = self._require_pinecone()
            pc = Pinecone(api_key=self._api_key)
            self._index = pc.Index(self._index_name)
        return self._index

    # ── write ──────────────────────────────────────────────────────────────

    def add(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        if not texts or not self._api_key:
            return

        import uuid

        idx = self._get_index()
        vectors_to_upsert = []
        for i, (text, meta, vec) in enumerate(zip(texts, metadatas, vectors, strict=False)):
            doc_id = str(uuid.uuid4())
            pinecone_meta = {
                k: (v if isinstance(v, (str, int, float, bool)) else str(v))
                for k, v in meta.items()
            }
            pinecone_meta["_text"] = text[:500]
            vectors_to_upsert.append((doc_id, vec, pinecone_meta))
            self._ids.append(doc_id)
            self._texts.append(text)
            self._metas.append(meta)

        # Upsert in batches of 100
        for i in range(0, len(vectors_to_upsert), 100):
            batch = vectors_to_upsert[i : i + 100]
            idx.upsert(vectors=batch, namespace=self._namespace)  # type: ignore[union-attr]

    def remove_by_source(self, source_path: str) -> int:
        to_remove = [
            (i, doc_id)
            for i, (doc_id, meta) in enumerate(zip(self._ids, self._metas, strict=False))
            if str(meta.get("source_path", "")) == source_path
        ]
        if not to_remove:
            return 0

        try:
            idx = self._get_index()
            ids = [doc_id for _, doc_id in to_remove]
            idx.delete(ids=ids, namespace=self._namespace)  # type: ignore[union-attr]
        except Exception:
            pass

        remove_set = {i for i, _ in to_remove}
        self._texts = [t for i, t in enumerate(self._texts) if i not in remove_set]
        self._metas = [m for i, m in enumerate(self._metas) if i not in remove_set]
        self._ids = [d for i, d in enumerate(self._ids) if i not in remove_set]
        return len(to_remove)

    # ── read ───────────────────────────────────────────────────────────────

    def count(self) -> int:
        return len(self._texts)

    def query_ranked(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
    ) -> list[tuple[int, float]]:
        if not self._api_key or self.count() == 0:
            return []

        k = min(top_k, self.count())
        try:
            idx = self._get_index()
            result = idx.query(  # type: ignore[union-attr]
                vector=query_vector,
                top_k=k,
                namespace=self._namespace,
                include_metadata=False,
            )
            matches = result.get("matches", [])
        except Exception:
            return []

        ranked: list[tuple[int, float]] = []
        for match in matches:
            doc_id = match.get("id", "")
            if doc_id in self._ids:
                seq_idx = self._ids.index(doc_id)
                score = float(match.get("score", 0.0))
                ranked.append((seq_idx, score))

        return sorted(ranked, key=lambda x: x[1], reverse=True)

    def get_chunk_at(self, idx: int) -> tuple[str, dict[str, Any]]:
        return self._texts[idx], self._metas[idx]

    def get_vector_at(self, idx: int) -> list[float]:
        return []

    def all_texts(self) -> list[str]:
        return list(self._texts)

    # ── persistence (cloud — no local files) ─────────────────────────────

    def persist(self, base_path: Path) -> None:
        pass  # Pinecone auto-persists in the cloud

    @classmethod
    def load(cls, base_path: Path) -> PineconeVectorStore:
        return cls()  # Cloud index is always available; populate via add()

    @classmethod
    def exists(cls, base_path: Path) -> bool:
        return False  # Cloud backend: always "available" if key is set

    @classmethod
    def delete_files(cls, base_path: Path) -> None:
        pass  # No local files

    @classmethod
    def rename_files(cls, old_base: Path, new_base: Path) -> None:
        pass  # No local files
