"""Tests for RAGManager: create, build, use, retrieve, delete."""

from __future__ import annotations

from pathlib import Path

import pytest

from anythink.embeddings.mock import MockEmbeddingBackend
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
    (src / "readme.md").write_text("Anythink is a CLI AI chatbot.", encoding="utf-8")
    (src / "main.py").write_text("def main():\n    print('hello')\n", encoding="utf-8")
    return src


class TestCreateAndList:
    def test_list_empty_initially(self, mgr: RAGManager) -> None:
        assert mgr.list_indexes() == []

    def test_create_persists_metadata(self, mgr: RAGManager, source_dir: Path) -> None:
        info = IndexInfo(
            name="test-idx",
            index_type="project",
            source_path=str(source_dir),
            persistence_mode="rebuild",
        )
        mgr.create_index(info)
        assert mgr.get_info("test-idx") is not None

    def test_list_returns_created_indexes(self, mgr: RAGManager, source_dir: Path) -> None:
        for name in ("alpha", "beta"):
            mgr.create_index(
                IndexInfo(
                    name=name,
                    index_type="document",
                    source_path=str(source_dir),
                    persistence_mode="rebuild",
                )
            )
        names = [i.name for i in mgr.list_indexes()]
        assert "alpha" in names
        assert "beta" in names


class TestBuildIndex:
    async def test_build_populates_chunks(
        self, mgr: RAGManager, source_dir: Path, backend: MockEmbeddingBackend
    ) -> None:
        info = IndexInfo(
            name="build-test",
            index_type="project",
            source_path=str(source_dir),
            persistence_mode="rebuild",
        )
        mgr.create_index(info)
        updated = await mgr.build_index("build-test", backend)
        assert updated.chunk_count > 0
        assert updated.file_count > 0

    async def test_build_updates_last_indexed(
        self, mgr: RAGManager, source_dir: Path, backend: MockEmbeddingBackend
    ) -> None:
        mgr.create_index(
            IndexInfo(
                name="ts-test",
                index_type="document",
                source_path=str(source_dir),
                persistence_mode="rebuild",
            )
        )
        info = await mgr.build_index("ts-test", backend)
        assert info.last_indexed is not None

    async def test_build_with_persist_creates_store_file(
        self, mgr: RAGManager, source_dir: Path, backend: MockEmbeddingBackend
    ) -> None:
        mgr.create_index(
            IndexInfo(
                name="persist-test",
                index_type="project",
                source_path=str(source_dir),
                persistence_mode="persist",
            )
        )
        await mgr.build_index("persist-test", backend)
        from anythink.rag.backends.registry import store_exists
        assert store_exists("pure", mgr._store_base_path("persist-test"))

    async def test_build_nonexistent_raises(
        self, mgr: RAGManager, backend: MockEmbeddingBackend
    ) -> None:
        from anythink.exceptions import RAGError

        with pytest.raises(RAGError):
            await mgr.build_index("no-such-index", backend)


class TestUseAndRetrieve:
    async def test_retrieve_returns_results(
        self, mgr: RAGManager, source_dir: Path, backend: MockEmbeddingBackend
    ) -> None:
        mgr.create_index(
            IndexInfo(
                name="ret-test",
                index_type="document",
                source_path=str(source_dir),
                persistence_mode="persist",
            )
        )
        await mgr.build_index("ret-test", backend)
        mgr.use_index("ret-test")
        results = await mgr.retrieve("chatbot", backend, top_k=3)
        assert len(results) > 0

    async def test_retrieve_empty_when_not_active(
        self, mgr: RAGManager, backend: MockEmbeddingBackend
    ) -> None:
        results = await mgr.retrieve("anything", backend)
        assert results == []

    def test_use_index_nonexistent_returns_false(self, mgr: RAGManager) -> None:
        assert mgr.use_index("ghost-index") is False

    def test_is_active_after_use(
        self, mgr: RAGManager, source_dir: Path, backend: MockEmbeddingBackend
    ) -> None:
        mgr.create_index(
            IndexInfo(
                name="active-test",
                index_type="document",
                source_path=str(source_dir),
                persistence_mode="rebuild",
            )
        )
        mgr.use_index("active-test")
        assert mgr.is_active

    def test_deactivate(self, mgr: RAGManager, source_dir: Path) -> None:
        mgr.create_index(
            IndexInfo(
                name="deact",
                index_type="document",
                source_path=str(source_dir),
                persistence_mode="rebuild",
            )
        )
        mgr.use_index("deact")
        mgr.deactivate()
        assert not mgr.is_active


class TestDelete:
    def test_delete_removes_metadata(self, mgr: RAGManager, source_dir: Path) -> None:
        mgr.create_index(
            IndexInfo(
                name="del-test",
                index_type="document",
                source_path=str(source_dir),
                persistence_mode="rebuild",
            )
        )
        mgr.delete_index("del-test")
        assert mgr.get_info("del-test") is None

    def test_delete_nonexistent_raises(self, mgr: RAGManager) -> None:
        from anythink.exceptions import RAGError

        with pytest.raises(RAGError):
            mgr.delete_index("does-not-exist")

    def test_delete_active_deactivates(self, mgr: RAGManager, source_dir: Path) -> None:
        mgr.create_index(
            IndexInfo(
                name="del-active",
                index_type="document",
                source_path=str(source_dir),
                persistence_mode="rebuild",
            )
        )
        mgr.use_index("del-active")
        mgr.delete_index("del-active")
        assert not mgr.is_active


class TestIndexInfoModel:
    def test_round_trip(self) -> None:
        info = IndexInfo(
            name="test",
            index_type="project",
            source_path="/home/user/project",
            persistence_mode="persist",
            embedding_backend="local",
            file_count=5,
            chunk_count=42,
        )
        restored = IndexInfo.from_dict(info.to_dict())
        assert restored.name == "test"
        assert restored.index_type == "project"
        assert restored.chunk_count == 42
        assert restored.file_count == 5
