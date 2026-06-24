"""Tests for the 6-stage RAG ingestion pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from anythink.embeddings.mock import MockEmbeddingBackend
from anythink.rag.ingestion import IngestionProgress, IngestionResult, run_ingestion
from anythink.rag.manager import RAGManager
from anythink.rag.models import IndexInfo


@pytest.fixture()
def mgr(tmp_path: Path) -> RAGManager:
    return RAGManager(
        rag_dir=tmp_path / "rag",
        cache_dir=tmp_path / "cache",
    )


@pytest.fixture()
def backend() -> MockEmbeddingBackend:
    return MockEmbeddingBackend()


@pytest.fixture()
def source_dir(tmp_path: Path) -> Path:
    src = tmp_path / "source"
    src.mkdir()
    (src / "readme.md").write_text("# Guide\nIntro.\n## Setup\nInstall here.", encoding="utf-8")
    (src / "main.py").write_text(
        "def greet():\n    print('hello')\n\ndef bye():\n    print('bye')\n",
        encoding="utf-8",
    )
    (src / "data.txt").write_text("Some plain text content.", encoding="utf-8")
    return src


@pytest.fixture()
def index_info(source_dir: Path) -> IndexInfo:
    return IndexInfo(
        name="test-idx",
        index_type="document",
        source_path=str(source_dir),
        persistence_mode="rebuild",
    )


class TestRunIngestionBasic:
    async def test_returns_ingestion_result(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, index_info: IndexInfo
    ) -> None:
        mgr.create_index(index_info)
        result = await run_ingestion("test-idx", mgr, backend)
        assert isinstance(result, IngestionResult)
        assert result.name == "test-idx"
        assert result.chunks_created > 0
        assert result.files_processed > 0

    async def test_chunks_are_stored_and_retrievable(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, tmp_path: Path
    ) -> None:
        # Use persist mode so store is written to disk and loadable via use_index
        src = tmp_path / "persist_src"
        src.mkdir()
        (src / "a.md").write_text("# Guide\nContent here.", encoding="utf-8")
        info = IndexInfo(
            name="persist-test",
            index_type="document",
            source_path=str(src),
            persistence_mode="persist",
        )
        mgr.create_index(info)
        await run_ingestion("persist-test", mgr, backend)
        mgr.use_index("persist-test")
        assert mgr._active_store is not None
        assert mgr._active_store.count() > 0

    async def test_index_info_updated_after_ingestion(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, index_info: IndexInfo
    ) -> None:
        mgr.create_index(index_info)
        await run_ingestion("test-idx", mgr, backend)
        updated = mgr.get_info("test-idx")
        assert updated is not None
        assert updated.last_indexed is not None
        assert updated.chunk_count > 0
        assert updated.file_count > 0

    async def test_ingestion_history_recorded(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, index_info: IndexInfo
    ) -> None:
        mgr.create_index(index_info)
        await run_ingestion("test-idx", mgr, backend)
        info = mgr.get_info("test-idx")
        assert info is not None
        assert len(info.ingestion_history) == 1
        entry = info.ingestion_history[0]
        assert "timestamp" in entry
        assert "chunks_created" in entry
        assert entry["mode"] == "incremental"

    async def test_embedding_backend_recorded(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, index_info: IndexInfo
    ) -> None:
        mgr.create_index(index_info)
        await run_ingestion("test-idx", mgr, backend)
        info = mgr.get_info("test-idx")
        assert info is not None
        assert info.embedding_backend == "mock"

    async def test_progress_callback_called(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, index_info: IndexInfo
    ) -> None:
        mgr.create_index(index_info)
        stages_seen: list[int] = []

        def _cb(prog: IngestionProgress) -> None:
            stages_seen.append(prog.stage)

        await run_ingestion("test-idx", mgr, backend, progress_callback=_cb)
        # Should see progress from multiple stages
        assert len(stages_seen) >= 3
        assert 1 in stages_seen  # discovery
        assert 5 in stages_seen  # embedding (at least one batch)

    async def test_progress_callback_is_optional(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, index_info: IndexInfo
    ) -> None:
        mgr.create_index(index_info)
        # No callback — should not raise
        result = await run_ingestion("test-idx", mgr, backend, progress_callback=None)
        assert result.chunks_created > 0

    async def test_full_mode_processes_all_files(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, index_info: IndexInfo
    ) -> None:
        mgr.create_index(index_info)
        result = await run_ingestion("test-idx", mgr, backend, mode="full")
        assert result.mode == "full"
        assert result.files_processed > 0

    async def test_unknown_index_raises(
        self, mgr: RAGManager, backend: MockEmbeddingBackend
    ) -> None:
        from anythink.exceptions import RAGError

        with pytest.raises(RAGError):
            await run_ingestion("nonexistent", mgr, backend)


class TestRunIngestionWithPersistedStore:
    async def test_persist_mode_writes_store_file(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("Content A.", encoding="utf-8")
        info = IndexInfo(
            name="persist-idx",
            index_type="document",
            source_path=str(src),
            persistence_mode="persist",
        )
        mgr.create_index(info)
        await run_ingestion("persist-idx", mgr, backend)
        from anythink.rag.backends.registry import store_exists
        assert store_exists("pure", mgr._store_base_path("persist-idx"))

    async def test_rebuild_mode_does_not_write_store_file(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, tmp_path: Path
    ) -> None:
        src = tmp_path / "src2"
        src.mkdir()
        (src / "b.txt").write_text("Content B.", encoding="utf-8")
        info = IndexInfo(
            name="rebuild-idx",
            index_type="document",
            source_path=str(src),
            persistence_mode="rebuild",
        )
        mgr.create_index(info)
        await run_ingestion("rebuild-idx", mgr, backend)
        from anythink.rag.backends.registry import store_exists
        assert not store_exists("pure", mgr._store_base_path("rebuild-idx"))


class TestRunIngestionManagerPipeline:
    async def test_run_ingestion_pipeline_method(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, index_info: IndexInfo
    ) -> None:
        mgr.create_index(index_info)
        result = await mgr.run_ingestion_pipeline("test-idx", backend)
        assert result is not None
        assert hasattr(result, "chunks_created")
