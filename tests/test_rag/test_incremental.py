"""Tests for incremental ingestion: mtime-based change detection."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from anythink.embeddings.mock import MockEmbeddingBackend
from anythink.rag.ingestion import run_ingestion
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


class TestMtimeCache:
    async def test_first_run_populates_mtime_cache(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("Content A.", encoding="utf-8")
        info = IndexInfo(
            name="idx", index_type="document", source_path=str(src), persistence_mode="rebuild"
        )
        mgr.create_index(info)
        await run_ingestion("idx", mgr, backend)

        updated = mgr.get_info("idx")
        assert updated is not None
        assert len(updated.file_mtime_cache) > 0
        assert any("a.txt" in key for key in updated.file_mtime_cache)

    async def test_unchanged_files_skipped_in_incremental(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("Content A.", encoding="utf-8")
        info = IndexInfo(
            name="idx", index_type="document", source_path=str(src), persistence_mode="rebuild"
        )
        mgr.create_index(info)
        # First run
        await run_ingestion("idx", mgr, backend)

        # Second run — same files, no changes
        progress_calls: list[int] = []

        def _cb(prog: object) -> None:
            progress_calls.append(getattr(prog, "files_unchanged", 0))

        await run_ingestion("idx", mgr, backend, mode="incremental", progress_callback=_cb)
        # At discovery stage, unchanged count should be 1
        assert any(u >= 1 for u in progress_calls)

    async def test_modified_file_reprocessed(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        fpath = src / "a.txt"
        fpath.write_text("Original content.", encoding="utf-8")
        info = IndexInfo(
            name="idx", index_type="document", source_path=str(src), persistence_mode="rebuild"
        )
        mgr.create_index(info)
        await run_ingestion("idx", mgr, backend)

        # Modify file with a newer mtime
        time.sleep(0.05)  # ensure mtime is different
        fpath.write_text("Updated content.", encoding="utf-8")

        changed_counts: list[int] = []

        def _cb(prog: object) -> None:
            changed_counts.append(getattr(prog, "files_changed", 0))

        await run_ingestion("idx", mgr, backend, mode="incremental", progress_callback=_cb)
        assert any(c >= 1 for c in changed_counts)

    async def test_new_file_detected(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("File A.", encoding="utf-8")
        info = IndexInfo(
            name="idx", index_type="document", source_path=str(src), persistence_mode="rebuild"
        )
        mgr.create_index(info)
        await run_ingestion("idx", mgr, backend)

        # Add new file
        (src / "b.txt").write_text("File B — new file.", encoding="utf-8")

        new_counts: list[int] = []

        def _cb(prog: object) -> None:
            new_counts.append(getattr(prog, "files_new", 0))

        await run_ingestion("idx", mgr, backend, mode="incremental", progress_callback=_cb)
        assert any(n >= 1 for n in new_counts)

    async def test_full_mode_reprocesses_unchanged_files(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("Content A.", encoding="utf-8")
        info = IndexInfo(
            name="idx", index_type="document", source_path=str(src), persistence_mode="rebuild"
        )
        mgr.create_index(info)
        await run_ingestion("idx", mgr, backend)

        # Full mode — should process file even though it hasn't changed
        parsed_counts: list[int] = []

        def _cb(prog: object) -> None:
            parsed_counts.append(getattr(prog, "files_parsed", 0))

        result = await run_ingestion("idx", mgr, backend, mode="full", progress_callback=_cb)
        assert result.files_processed >= 1

    async def test_second_ingestion_appends_history(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("Content A.", encoding="utf-8")
        info = IndexInfo(
            name="idx", index_type="document", source_path=str(src), persistence_mode="rebuild"
        )
        mgr.create_index(info)
        await run_ingestion("idx", mgr, backend)
        await run_ingestion("idx", mgr, backend, mode="full")

        final_info = mgr.get_info("idx")
        assert final_info is not None
        assert len(final_info.ingestion_history) == 2
        assert final_info.ingestion_history[0]["mode"] == "incremental"
        assert final_info.ingestion_history[1]["mode"] == "full"


class TestExtraPath:
    async def test_extra_path_files_ingested(
        self, mgr: RAGManager, backend: MockEmbeddingBackend, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("Main content.", encoding="utf-8")

        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / "b.txt").write_text("Extra content.", encoding="utf-8")

        info = IndexInfo(
            name="idx", index_type="document", source_path=str(src), persistence_mode="rebuild"
        )
        mgr.create_index(info)
        result = await run_ingestion("idx", mgr, backend, extra_path=extra)
        # Both files should be processed
        assert result.files_processed >= 2
