"""RAGManager: build, persist, and query named RAG indexes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from anythink.exceptions import RAGError
from anythink.rag.bm25 import BM25Index
from anythink.rag.chunkers import chunk_file
from anythink.rag.models import IndexInfo, RetrievalResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from anythink.embeddings.base import BaseEmbeddingBackend
    from anythink.rag.backends.base import BaseVectorStore

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
    """Manages named RAG indexes: metadata in YAML, vector stores via backend registry.

    ``rag_dir``   — stores ``{name}.yaml`` index metadata files
    ``cache_dir`` — stores backend-specific vector store files
    """

    def __init__(self, rag_dir: Path, cache_dir: Path) -> None:
        self._rag_dir = rag_dir
        self._cache_dir = cache_dir
        self._active_info: IndexInfo | None = None
        self._active_store: BaseVectorStore | None = None
        self._active_bm25: BM25Index | None = None
        self._last_results: list[RetrievalResult] = []

    # ── lifecycle ──────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active_info is not None

    @property
    def active_name(self) -> str | None:
        return self._active_info.name if self._active_info else None

    @property
    def active_embedding_model(self) -> str:
        """Short embedding backend name of the active index, or '' when inactive."""
        if self._active_info is None:
            return ""
        return self._active_info.embedding_backend

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
        info = self.get_info(name)
        meta.unlink(missing_ok=True)

        # Delete backend-specific files
        if info:
            self._delete_backend_files(name, info.vector_backend)
        else:
            # Fallback: try legacy pure store path
            self._legacy_store_path(name).unlink(missing_ok=True)

        self._bm25_path(name).unlink(missing_ok=True)

        if self._active_info and self._active_info.name == name:
            self._active_info = None
            self._active_store = None
            self._active_bm25 = None

    def rename_index(self, old_name: str, new_name: str) -> None:
        """Rename an index — updates metadata name, renames files on disk."""
        old_meta = self._meta_path(old_name)
        new_meta = self._meta_path(new_name)
        if not old_meta.exists():
            raise RAGError(
                f"Index '{old_name}' not found.",
                user_message=f"No RAG index named '{old_name}'.",
            )
        if new_meta.exists():
            raise RAGError(
                f"Index '{new_name}' already exists.",
                user_message=f"An index named '{new_name}' already exists.",
            )
        info = self.get_info(old_name)
        if info is None:
            raise RAGError(f"Could not read metadata for '{old_name}'.")

        from dataclasses import replace as _replace

        new_info = _replace(info, name=new_name)
        self.create_index(new_info)

        # Rename backend-specific files
        self._rename_backend_files(old_name, new_name, info.vector_backend)

        # Rename BM25 file
        old_bm25 = self._bm25_path(old_name)
        if old_bm25.exists():
            old_bm25.rename(self._bm25_path(new_name))

        old_meta.unlink(missing_ok=True)
        if self._active_info and self._active_info.name == old_name:
            self._active_info = new_info

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

        from anythink.rag.backends.registry import get_backend

        store = get_backend(info.vector_backend)
        exts = _PROJECT_EXTS if info.index_type == "project" else _ALL_EXTS
        files = [p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in exts]

        all_texts: list[str] = []
        all_metas: list[dict[str, object]] = []

        for fpath in files:
            for text, meta in chunk_file(fpath, chunk_size=chunk_size, overlap=overlap):
                all_texts.append(text)
                all_metas.append(meta)

        if all_texts:
            batch_size = 64
            all_vectors: list[list[float]] = []
            for i in range(0, len(all_texts), batch_size):
                batch = all_texts[i : i + batch_size]
                vecs = await backend.embed(batch)
                all_vectors.extend(vecs)
            store.add(all_texts, list(all_metas), all_vectors)

        from datetime import datetime

        info.last_indexed = datetime.utcnow()
        info.file_count = len(files)
        info.chunk_count = store.count()
        info.embedding_backend = backend.name

        if info.persistence_mode == "persist":
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            store.persist(self._store_base_path(name))

        self.create_index(info)
        return info

    # ── activation ─────────────────────────────────────────────────────────

    def use_index(self, name: str) -> bool:
        """Load index *name* as the active store.  Returns False if not found."""
        info = self.get_info(name)
        if info is None:
            return False

        from anythink.rag.backends.registry import load_store, store_exists

        base = self._store_base_path(name)
        if store_exists(info.vector_backend, base):
            self._active_store = load_store(info.vector_backend, base)
        else:
            from anythink.rag.backends.registry import get_backend

            self._active_store = get_backend(info.vector_backend)

        bm25_path = self._bm25_path(name)
        if bm25_path.exists():
            self._active_bm25 = BM25Index.load(bm25_path)
        else:
            self._active_bm25 = None

        self._active_info = info
        return True

    def deactivate(self) -> None:
        self._active_info = None
        self._active_store = None
        self._active_bm25 = None

    # ── retrieval ──────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        backend: BaseEmbeddingBackend,
        *,
        top_k: int = 5,
        debug_callback: Callable[[float, int], None] | None = None,
        stage_callback: Callable[[str], None] | None = None,
        llm_expand_fn: Callable[[str], object] | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve chunks using the active index's configured strategy."""
        from anythink.rag.retrieval import retrieve as _retrieve

        if self._active_store is None or self._active_store.count() == 0:
            return []

        info = self._active_info
        strategy = info.retrieval_strategy if info else "vector"
        reranking = info.reranking_enabled if info else False
        reranking_model = info.reranking_model if info else "bge-reranker-base"

        reranker = None
        if reranking:
            from anythink.rag.reranker import get_reranker

            reranker = get_reranker(reranking_model)

        results = await _retrieve(
            query=query,
            backend=backend,
            store=self._active_store,  # type: ignore[arg-type]
            bm25=self._active_bm25,
            strategy=strategy,
            top_k=top_k,
            reranker=reranker,
            rerank_candidates=max(20, top_k * 5),
            llm_expand_fn=llm_expand_fn,
            stage_callback=stage_callback,
            debug_callback=debug_callback,
        )

        self._last_results = results
        return results

    # ── pipeline ───────────────────────────────────────────────────────────

    async def run_ingestion_pipeline(
        self,
        name: str,
        backend: BaseEmbeddingBackend,
        *,
        mode: str = "incremental",
        extra_path: Path | None = None,
        progress_callback: object = None,
    ) -> object:
        """Run the full 6-stage ingestion pipeline and return an IngestionResult."""
        from anythink.rag.ingestion import IngestionResult, run_ingestion

        result: IngestionResult = await run_ingestion(
            name,
            self,
            backend,
            mode=mode,  # type: ignore[arg-type]
            extra_path=extra_path,
            progress_callback=progress_callback,  # type: ignore[arg-type]
        )
        return result

    # ── helpers ────────────────────────────────────────────────────────────

    def _meta_path(self, name: str) -> Path:
        safe = name.replace(" ", "_").replace("/", "_")
        return self._rag_dir / f"{safe}.yaml"

    def _store_base_path(self, name: str) -> Path:
        """Base path (no extension) for vector store files."""
        safe = name.replace(" ", "_").replace("/", "_")
        return self._cache_dir / safe

    def _legacy_store_path(self, name: str) -> Path:
        """Full path to old-style pure store (.store.gz) — for cleanup only."""
        safe = name.replace(" ", "_").replace("/", "_")
        return self._cache_dir / f"{safe}.store.gz"

    def _bm25_path(self, name: str) -> Path:
        safe = name.replace(" ", "_").replace("/", "_")
        return self._cache_dir / f"{safe}.bm25.gz"

    def _delete_backend_files(self, name: str, vector_backend: str) -> None:
        from anythink.rag.backends.registry import get_backend_class

        cls = get_backend_class(vector_backend)
        cls.delete_files(self._store_base_path(name))
        # Also clean up legacy pure store in case of migration
        self._legacy_store_path(name).unlink(missing_ok=True)

    def _rename_backend_files(self, old_name: str, new_name: str, vector_backend: str) -> None:
        from anythink.rag.backends.registry import get_backend_class

        cls = get_backend_class(vector_backend)
        cls.rename_files(self._store_base_path(old_name), self._store_base_path(new_name))
        # Also rename legacy pure store if present
        old_legacy = self._legacy_store_path(old_name)
        if old_legacy.exists():
            old_legacy.rename(self._legacy_store_path(new_name))
