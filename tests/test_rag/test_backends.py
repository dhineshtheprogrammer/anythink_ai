"""Tests for vector store backends (Phase 5).

Pure backend is always tested.  FAISS, Chroma, and Lance tests are skipped
when the optional dependency is not installed.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from anythink.rag.backends.base import BaseVectorStore
from anythink.rag.backends.pure import PureVectorStore
from anythink.rag.backends.registry import (
    BACKENDS,
    available_backends,
    get_backend,
    get_backend_class,
    is_backend_available,
    load_store,
    store_exists,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _vec(dim: int, seed: float) -> list[float]:
    """Unit-length vector of dimension *dim* seeded by *seed*."""
    raw = [math.sin(seed + i) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def _sample_data(
    n: int = 5, dim: int = 8
) -> tuple[list[str], list[dict[str, Any]], list[list[float]]]:
    texts = [f"sample chunk {i}: hello world" for i in range(n)]
    metas = [{"source_path": f"file{i % 2}.txt", "chunk_index": i} for i in range(n)]
    vecs = [_vec(dim, i * 0.5) for i in range(n)]
    return texts, metas, vecs


# ── Registry tests ────────────────────────────────────────────────────────────


class TestRegistry:
    def test_backends_list_contains_expected(self) -> None:
        for name in ("pure", "faiss", "chroma", "lance", "pinecone", "azure"):
            assert name in BACKENDS

    def test_get_backend_class_pure(self) -> None:
        cls = get_backend_class("pure")
        assert cls is PureVectorStore

    def test_get_backend_class_unknown_falls_back_to_pure(self) -> None:
        cls = get_backend_class("nonexistent_backend_xyz")
        assert cls is PureVectorStore

    def test_get_backend_pure_returns_instance(self) -> None:
        store = get_backend("pure")
        assert isinstance(store, PureVectorStore)

    def test_get_backend_unknown_falls_back_to_pure(self) -> None:
        store = get_backend("nonexistent_xyz")
        assert isinstance(store, PureVectorStore)

    def test_pure_always_available(self) -> None:
        assert is_backend_available("pure") is True

    def test_available_backends_includes_pure(self) -> None:
        avail = available_backends()
        assert "pure" in avail

    def test_available_backends_subset_of_all(self) -> None:
        avail = available_backends()
        assert all(b in BACKENDS for b in avail)


# ── BaseVectorStore contract ──────────────────────────────────────────────────


class _BackendContractMixin:
    """Common contract tests run against any BaseVectorStore implementation."""

    def make_store(self) -> BaseVectorStore:
        raise NotImplementedError

    def test_implements_base(self) -> None:
        store = self.make_store()
        assert isinstance(store, BaseVectorStore)

    def test_empty_count_is_zero(self) -> None:
        store = self.make_store()
        assert store.count() == 0

    def test_add_increases_count(self) -> None:
        store = self.make_store()
        texts, metas, vecs = _sample_data(3)
        store.add(texts, metas, vecs)
        assert store.count() == 3

    def test_query_ranked_returns_sorted_results(self) -> None:
        store = self.make_store()
        texts, metas, vecs = _sample_data(5)
        store.add(texts, metas, vecs)
        ranked = store.query_ranked(vecs[0], top_k=3)
        assert len(ranked) <= 3
        scores = [s for _, s in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_query_ranked_top_result_is_self(self) -> None:
        store = self.make_store()
        texts, metas, vecs = _sample_data(5)
        store.add(texts, metas, vecs)
        ranked = store.query_ranked(vecs[2], top_k=1)
        assert ranked[0][0] == 2

    def test_query_ranked_empty_store_returns_empty(self) -> None:
        store = self.make_store()
        assert store.query_ranked(_vec(8, 0.0), top_k=5) == []

    def test_get_chunk_at_returns_correct_data(self) -> None:
        store = self.make_store()
        texts, metas, vecs = _sample_data(3)
        store.add(texts, metas, vecs)
        text, meta = store.get_chunk_at(1)
        assert text == texts[1]
        assert meta.get("chunk_index") == 1

    def test_all_texts_returns_all(self) -> None:
        store = self.make_store()
        texts, metas, vecs = _sample_data(4)
        store.add(texts, metas, vecs)
        all_t = store.all_texts()
        assert len(all_t) == 4
        assert set(all_t) == set(texts)

    def test_remove_by_source_removes_matching(self) -> None:
        store = self.make_store()
        texts, metas, vecs = _sample_data(5)
        store.add(texts, metas, vecs)
        # file0.txt appears at idx 0, 2, 4
        removed = store.remove_by_source("file0.txt")
        assert removed == 3
        assert store.count() == 2
        remaining_sources = [
            m.get("source_path") for m in [store.get_chunk_at(i)[1] for i in range(store.count())]
        ]
        assert all(s == "file1.txt" for s in remaining_sources)

    def test_remove_by_source_no_match_returns_zero(self) -> None:
        store = self.make_store()
        texts, metas, vecs = _sample_data(3)
        store.add(texts, metas, vecs)
        removed = store.remove_by_source("nonexistent.txt")
        assert removed == 0
        assert store.count() == 3

    def test_query_method_returns_scored_chunks(self) -> None:
        store = self.make_store()
        texts, metas, vecs = _sample_data(3)
        store.add(texts, metas, vecs)
        results = store.query(vecs[0], top_k=2)
        assert len(results) <= 2
        for r in results:
            assert hasattr(r, "score")
            assert hasattr(r, "text")


# ── PureVectorStore ───────────────────────────────────────────────────────────


class TestPureVectorStore(_BackendContractMixin):
    def make_store(self) -> PureVectorStore:
        return PureVectorStore()

    def test_persist_and_load_roundtrip(self, tmp_path: Path) -> None:
        store = PureVectorStore()
        texts, metas, vecs = _sample_data(4)
        store.add(texts, metas, vecs)
        base = tmp_path / "myidx"
        store.persist(base)
        assert PureVectorStore.exists(base)

        loaded = PureVectorStore.load(base)
        assert loaded.count() == 4
        assert loaded.all_texts() == texts

    def test_load_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        store = PureVectorStore.load(tmp_path / "missing")
        assert store.count() == 0

    def test_delete_files(self, tmp_path: Path) -> None:
        store = PureVectorStore()
        store.add(["text"], [{"source_path": "a.txt"}], [_vec(8, 0.0)])
        base = tmp_path / "del_test"
        store.persist(base)
        assert PureVectorStore.exists(base)
        PureVectorStore.delete_files(base)
        assert not PureVectorStore.exists(base)

    def test_rename_files(self, tmp_path: Path) -> None:
        store = PureVectorStore()
        store.add(["text"], [{"source_path": "a.txt"}], [_vec(8, 0.0)])
        old_base = tmp_path / "old"
        new_base = tmp_path / "new"
        store.persist(old_base)
        PureVectorStore.rename_files(old_base, new_base)
        assert not PureVectorStore.exists(old_base)
        assert PureVectorStore.exists(new_base)

    def test_get_vector_at_returns_correct_dim(self) -> None:
        store = PureVectorStore()
        texts, metas, vecs = _sample_data(2, dim=8)
        store.add(texts, metas, vecs)
        vec = store.get_vector_at(0)
        assert len(vec) == 8

    def test_remove_by_source_then_query_works(self) -> None:
        store = PureVectorStore()
        texts, metas, vecs = _sample_data(4)
        store.add(texts, metas, vecs)
        store.remove_by_source("file0.txt")
        ranked = store.query_ranked(vecs[1], top_k=3)
        assert len(ranked) <= store.count()


# ── Registry persistence helpers ──────────────────────────────────────────────


class TestRegistryPersistenceHelpers:
    def test_store_exists_false_for_missing(self, tmp_path: Path) -> None:
        assert not store_exists("pure", tmp_path / "no_such")

    def test_store_exists_true_after_persist(self, tmp_path: Path) -> None:
        store = PureVectorStore()
        store.add(["hello"], [{"source_path": "a.txt"}], [_vec(8, 0.1)])
        base = tmp_path / "mystore"
        store.persist(base)
        assert store_exists("pure", base)

    def test_load_store_pure_roundtrip(self, tmp_path: Path) -> None:
        store = PureVectorStore()
        store.add(["chunk one", "chunk two"], [{"source_path": "x.py"}] * 2, [_vec(8, 0.0)] * 2)
        base = tmp_path / "load_test"
        store.persist(base)
        loaded = load_store("pure", base)
        assert loaded.count() == 2

    def test_load_store_falls_back_to_pure_for_unavailable(self, tmp_path: Path) -> None:
        # "nonexistent_xyz" falls back to pure
        store = PureVectorStore()
        store.add(["text"], [{"source_path": "f.txt"}], [_vec(8, 0.5)])
        base = tmp_path / "fallback"
        store.persist(base)
        loaded = load_store("nonexistent_xyz", base)
        assert isinstance(loaded, PureVectorStore)
        assert loaded.count() == 1

    def test_load_store_returns_empty_if_no_data(self, tmp_path: Path) -> None:
        loaded = load_store("pure", tmp_path / "empty")
        assert loaded.count() == 0


# ── FAISS backend (conditional) ───────────────────────────────────────────────

faiss_available = pytest.mark.skipif(
    not is_backend_available("faiss"),
    reason="faiss-cpu not installed",
)


@faiss_available
class TestFAISSVectorStore(_BackendContractMixin):
    def make_store(self) -> BaseVectorStore:
        from anythink.rag.backends.faiss_store import FAISSVectorStore

        return FAISSVectorStore()

    def test_persist_and_load_roundtrip(self, tmp_path: Path) -> None:
        from anythink.rag.backends.faiss_store import FAISSVectorStore

        store = FAISSVectorStore()
        texts, metas, vecs = _sample_data(4)
        store.add(texts, metas, vecs)
        base = tmp_path / "faiss_idx"
        store.persist(base)
        assert FAISSVectorStore.exists(base)

        loaded = FAISSVectorStore.load(base)
        assert loaded.count() == 4

    def test_get_vector_at_matches_original(self, tmp_path: Path) -> None:
        from anythink.rag.backends.faiss_store import FAISSVectorStore

        store = FAISSVectorStore()
        texts, metas, vecs = _sample_data(3, dim=16)
        store.add(texts, metas, vecs)
        got = store.get_vector_at(1)
        assert len(got) == 16

    def test_remove_by_source_and_query(self) -> None:
        from anythink.rag.backends.faiss_store import FAISSVectorStore

        store = FAISSVectorStore()
        texts, metas, vecs = _sample_data(6, dim=8)
        store.add(texts, metas, vecs)
        store.remove_by_source("file0.txt")
        assert store.count() == 3
        ranked = store.query_ranked(vecs[1], top_k=2)
        assert len(ranked) <= 2


# ── Chroma backend (conditional) ─────────────────────────────────────────────

chroma_available = pytest.mark.skipif(
    not is_backend_available("chroma"),
    reason="chromadb not installed",
)


@chroma_available
class TestChromaVectorStore(_BackendContractMixin):
    def make_store(self) -> BaseVectorStore:
        from anythink.rag.backends.chroma_store import ChromaVectorStore

        store = ChromaVectorStore()
        store._init_client(Path("/tmp/anythink_test_chroma"))  # type: ignore[attr-defined]
        return store

    def test_supports_metadata_filter(self) -> None:
        from anythink.rag.backends.chroma_store import ChromaVectorStore

        store = ChromaVectorStore()
        assert store.supports_metadata_filter() is True


# ── LanceDB backend (conditional) ────────────────────────────────────────────

lance_available = pytest.mark.skipif(
    not is_backend_available("lance"),
    reason="lancedb not installed",
)


@lance_available
class TestLanceVectorStore(_BackendContractMixin):
    def make_store(self) -> BaseVectorStore:
        from anythink.rag.backends.lance_store import LanceVectorStore

        store = LanceVectorStore()
        import tempfile

        store._init_db(Path(tempfile.mkdtemp()) / "lance_test")  # type: ignore[attr-defined]
        return store

    def test_supports_metadata_filter(self) -> None:
        from anythink.rag.backends.lance_store import LanceVectorStore

        store = LanceVectorStore()
        assert store.supports_metadata_filter() is True


class TestRegistryEdgeCases:
    def test_get_backend_class_import_error_falls_back(self) -> None:
        from unittest.mock import patch

        from anythink.rag.backends.registry import get_backend_class
        from anythink.rag.backends.pure import PureVectorStore

        with patch("importlib.import_module", side_effect=ImportError("no faiss")):
            cls = get_backend_class("faiss")
        assert cls is PureVectorStore

    def test_is_backend_available_falls_back_returns_false(self) -> None:
        from unittest.mock import patch

        from anythink.rag.backends.registry import is_backend_available
        from anythink.rag.backends.pure import PureVectorStore

        with patch("anythink.rag.backends.registry.get_backend_class", return_value=PureVectorStore):
            result = is_backend_available("faiss")
        assert result is False

    def test_is_backend_available_no_is_available_method_returns_true(self) -> None:
        from unittest.mock import MagicMock, patch

        from anythink.rag.backends.registry import is_backend_available

        class FakeCls:
            name = "FakeCls"
            __name__ = "FakeCls"

            def __init__(self):
                pass

        with patch("anythink.rag.backends.registry.get_backend_class", return_value=FakeCls):
            result = is_backend_available("fake")
        assert result is True
