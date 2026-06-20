"""RAGManager: build, persist, and query named RAG indexes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from anythink.exceptions import RAGError
from anythink.rag.chunkers import chunk_file
from anythink.rag.models import IndexInfo, RetrievalResult
from anythink.rag.store import VectorStore

if TYPE_CHECKING:
    from anythink.embeddings.base import BaseEmbeddingBackend

# Extensions to index for "project" (code) type indexes
_PROJECT_EXTS = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".go",
        ".rs",
        ".cpp",
        ".c",
        ".h",
        ".cs",
        ".rb",
        ".swift",
        ".kt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".md",
    }
)
# Extensions for "document" (doc) type indexes
_DOC_EXTS = frozenset({".md", ".txt", ".rst", ".pdf", ".csv"})

_ALL_EXTS = _PROJECT_EXTS | _DOC_EXTS


class RAGManager:
    """Manages named RAG indexes: metadata in YAML, stores as gzip JSON.

    ``rag_dir``   — stores ``{name}.yaml`` index metadata files
    ``cache_dir`` — stores ``{name}.store.gz`` persisted vector stores
    """

    def __init__(self, rag_dir: Path, cache_dir: Path) -> None:
        self._rag_dir = rag_dir
        self._cache_dir = cache_dir
        self._active_info: IndexInfo | None = None
        self._active_store: VectorStore | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active_info is not None

    @property
    def active_name(self) -> str | None:
        return self._active_info.name if self._active_info else None

    # ── index management ───────────────────────────────────────────────────

    def list_indexes(self) -> list[IndexInfo]:
        """Return all index metadata objects sorted by name."""
        if not self._rag_dir.exists():
            return []
        infos: list[IndexInfo] = []
        for path in sorted(self._rag_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                infos.append(IndexInfo.from_dict(raw))
            except Exception:  # nosec B110 - skip corrupt metadata
                pass
        return infos

    def get_info(self, name: str) -> IndexInfo | None:
        path = self._meta_path(name)
        if not path.exists():
            return None
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            return IndexInfo.from_dict(raw)
        except Exception:
            return None

    def create_index(self, info: IndexInfo) -> None:
        """Persist index metadata.  Does not build yet."""
        self._rag_dir.mkdir(parents=True, exist_ok=True)
        path = self._meta_path(info.name)
        path.write_text(
            yaml.dump(info.to_dict(), default_flow_style=False, sort_keys=True),
            encoding="utf-8",
        )

    def delete_index(self, name: str) -> None:
        """Remove metadata and any persisted store."""
        meta = self._meta_path(name)
        if not meta.exists():
            raise RAGError(
                f"Index '{name}' not found.",
                user_message=f"No RAG index named '{name}'.",
            )
        meta.unlink(missing_ok=True)
        self._store_path(name).unlink(missing_ok=True)
        if self._active_info and self._active_info.name == name:
            self._active_info = None
            self._active_store = None

    # ── build / rebuild ────────────────────────────────────────────────────

    async def build_index(
        self,
        name: str,
        backend: BaseEmbeddingBackend,
        *,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> IndexInfo:
        """Chunk all files under the index's source path and embed them.

        Returns the updated ``IndexInfo``.
        """
        info = self.get_info(name)
        if info is None:
            raise RAGError(f"Index '{name}' not found.", user_message=f"Unknown index '{name}'.")

        source = Path(info.source_path)
        if not source.exists():
            raise RAGError(
                f"Source path '{source}' does not exist.",
                user_message=f"Source path for index '{name}' no longer exists.",
            )

        store = VectorStore()
        exts = _PROJECT_EXTS if info.index_type == "project" else _ALL_EXTS
        files = [p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in exts]

        all_texts: list[str] = []
        all_metas: list[dict[str, object]] = []

        for fpath in files:
            for text, meta in chunk_file(fpath, chunk_size=chunk_size, overlap=overlap):
                all_texts.append(text)
                all_metas.append(meta)

        if all_texts:
            # Embed in batches of 64
            batch_size = 64
            all_vectors: list[list[float]] = []
            for i in range(0, len(all_texts), batch_size):
                batch = all_texts[i : i + batch_size]
                vecs = await backend.embed(batch)
                all_vectors.extend(vecs)
            store.add(all_texts, all_metas, all_vectors)

        # Update metadata
        from datetime import datetime

        info.last_indexed = datetime.utcnow()
        info.file_count = len(files)
        info.chunk_count = store.count()
        info.embedding_backend = backend.name

        # Persist store if configured
        if info.persistence_mode == "persist":
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            store.persist(self._store_path(name))

        self.create_index(info)
        return info

    # ── activation ─────────────────────────────────────────────────────────

    def use_index(self, name: str) -> bool:
        """Load index *name* as the active store.  Returns False if not found."""
        info = self.get_info(name)
        if info is None:
            return False

        store_path = self._store_path(name)
        if store_path.exists():
            self._active_store = VectorStore.load(store_path)
        else:
            # Index not yet built — use empty store; retrieval will return nothing
            # until the user runs /rag rebuild <name>
            self._active_store = VectorStore()

        self._active_info = info
        return True

    def deactivate(self) -> None:
        self._active_info = None
        self._active_store = None

    # ── retrieval ──────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        backend: BaseEmbeddingBackend,
        *,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Retrieve the most relevant chunks for *query* from the active store."""
        if self._active_store is None or self._active_store.count() == 0:
            return []

        vecs = await backend.embed([query])
        return self._active_store.query(vecs[0], top_k=top_k)

    # ── helpers ────────────────────────────────────────────────────────────

    def _meta_path(self, name: str) -> Path:
        safe = name.replace(" ", "_").replace("/", "_")
        return self._rag_dir / f"{safe}.yaml"

    def _store_path(self, name: str) -> Path:
        safe = name.replace(" ", "_").replace("/", "_")
        return self._cache_dir / f"{safe}.store.gz"
