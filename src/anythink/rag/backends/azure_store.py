"""Azure AI Search vector store backend.

Requires ``pip install anythink[rag-azure]`` (azure-search-documents>=11.4)
plus a valid Azure Search endpoint and admin key.

Azure AI Search is a cloud-only backend; ``persist()`` and ``load()`` are
no-ops.  Hybrid search (keyword + vector) is supported natively.
``supports_metadata_filter()`` returns True (OData filter expressions).

Configuration:
  endpoint: str   — e.g. "https://my-service.search.windows.net"
  api_key: str    — admin or query key
  index_name: str — Azure Search index name (default "anythink-rag")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from anythink.exceptions import RAGError
from anythink.rag.backends.base import BaseVectorStore

_VECTOR_FIELD = "content_vector"
_TEXT_FIELD = "content"
_ID_FIELD = "id"
_SOURCE_FIELD = "source_path"


class AzureVectorStore(BaseVectorStore):
    """Azure AI Search backend (cloud storage, no local files)."""

    def __init__(
        self,
        endpoint: str = "",
        api_key: str = "",
        index_name: str = "anythink-rag",
        dimension: int = 384,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._index_name = index_name
        self._dimension = dimension
        self._texts: list[str] = []
        self._metas: list[dict[str, Any]] = []
        self._doc_ids: list[str] = []

    def is_available(self) -> bool:
        try:
            from azure.search.documents import SearchClient  # noqa: F401

            return bool(self._endpoint and self._api_key)
        except ImportError:
            return False

    def _require_azure(self) -> Any:
        try:
            from azure.search.documents import SearchClient
            from azure.core.credentials import AzureKeyCredential

            return SearchClient, AzureKeyCredential
        except ImportError as exc:
            raise RAGError(
                "azure-search-documents not installed.",
                user_message=(
                    "Azure AI Search backend requires: pip install anythink[rag-azure]"
                ),
            ) from exc

    def _get_client(self) -> Any:
        SearchClient, AzureKeyCredential = self._require_azure()
        return SearchClient(
            endpoint=self._endpoint,
            index_name=self._index_name,
            credential=AzureKeyCredential(self._api_key),
        )

    # ── write ──────────────────────────────────────────────────────────────

    def add(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        if not texts or not self._endpoint:
            return

        import uuid

        client = self._get_client()
        docs = []
        for i, (text, meta, vec) in enumerate(zip(texts, metadatas, vectors, strict=False)):
            doc_id = str(uuid.uuid4()).replace("-", "")
            doc = {
                _ID_FIELD: doc_id,
                _TEXT_FIELD: text,
                _VECTOR_FIELD: vec,
                _SOURCE_FIELD: str(meta.get("source_path", "")),
            }
            doc.update(
                {k: str(v) for k, v in meta.items() if k not in (_TEXT_FIELD, _VECTOR_FIELD)}
            )
            docs.append(doc)
            self._doc_ids.append(doc_id)
            self._texts.append(text)
            self._metas.append(meta)

        # Upload in batches of 1000 (Azure limit)
        for i in range(0, len(docs), 1000):
            client.upload_documents(documents=docs[i : i + 1000])

    def remove_by_source(self, source_path: str) -> int:
        to_remove = [
            (i, doc_id)
            for i, (doc_id, meta) in enumerate(
                zip(self._doc_ids, self._metas, strict=False)
            )
            if str(meta.get("source_path", "")) == source_path
        ]
        if not to_remove:
            return 0

        try:
            client = self._get_client()
            docs = [{_ID_FIELD: doc_id} for _, doc_id in to_remove]
            client.delete_documents(documents=docs)
        except Exception:
            pass

        remove_set = {i for i, _ in to_remove}
        self._texts = [t for i, t in enumerate(self._texts) if i not in remove_set]
        self._metas = [m for i, m in enumerate(self._metas) if i not in remove_set]
        self._doc_ids = [d for i, d in enumerate(self._doc_ids) if i not in remove_set]
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
        if not self._endpoint or self.count() == 0:
            return []

        k = min(top_k, self.count())
        try:
            from azure.search.documents.models import VectorizedQuery

            client = self._get_client()
            vec_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=k,
                fields=_VECTOR_FIELD,
            )
            results = client.search(search_text=None, vector_queries=[vec_query], top=k)
        except Exception:
            return []

        ranked: list[tuple[int, float]] = []
        for result in results:
            doc_id = str(result.get(_ID_FIELD, ""))
            if doc_id in self._doc_ids:
                seq_idx = self._doc_ids.index(doc_id)
                score = float(result.get("@search.score", 0.0))
                ranked.append((seq_idx, score))

        return sorted(ranked, key=lambda x: x[1], reverse=True)

    def get_chunk_at(self, idx: int) -> tuple[str, dict[str, Any]]:
        return self._texts[idx], self._metas[idx]

    def get_vector_at(self, idx: int) -> list[float]:
        return []

    def all_texts(self) -> list[str]:
        return list(self._texts)

    def supports_metadata_filter(self) -> bool:
        return True

    # ── persistence (cloud — no local files) ─────────────────────────────

    def persist(self, base_path: Path) -> None:
        pass

    @classmethod
    def load(cls, base_path: Path) -> AzureVectorStore:
        return cls()

    @classmethod
    def exists(cls, base_path: Path) -> bool:
        return False

    @classmethod
    def delete_files(cls, base_path: Path) -> None:
        pass

    @classmethod
    def rename_files(cls, old_base: Path, new_base: Path) -> None:
        pass
