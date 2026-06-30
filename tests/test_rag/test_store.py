"""Tests for VectorStore (pure-Python cosine-similarity store)."""

from __future__ import annotations

from pathlib import Path

import pytest

from anythink.rag.store import VectorStore, _cosine


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 0.0, 0.0]
        assert _cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine(a, b) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self) -> None:
        assert _cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestVectorStore:
    def _make_store(self) -> VectorStore:
        store = VectorStore()
        store.add(
            texts=["apple fruit", "banana fruit", "car vehicle"],
            metadatas=[
                {"source_path": "a.txt", "start_line": 1},
                {"source_path": "b.txt", "start_line": 1},
                {"source_path": "c.txt", "start_line": 1},
            ],
            vectors=[
                [1.0, 0.0, 0.0],
                [0.9, 0.1, 0.0],
                [0.0, 0.0, 1.0],
            ],
        )
        return store

    def test_count(self) -> None:
        store = self._make_store()
        assert store.count() == 3

    def test_query_returns_top_k(self) -> None:
        store = self._make_store()
        results = store.query([1.0, 0.0, 0.0], top_k=2)
        assert len(results) == 2

    def test_most_similar_first(self) -> None:
        store = self._make_store()
        results = store.query([1.0, 0.0, 0.0], top_k=3)
        # apple (exact match) should rank above banana, which above car
        assert results[0].source_path == "a.txt"
        assert results[-1].source_path == "c.txt"

    def test_relevance_in_range(self) -> None:
        store = self._make_store()
        results = store.query([1.0, 0.0, 0.0], top_k=3)
        for r in results:
            assert -1.0 <= r.relevance <= 1.0

    def test_empty_store_returns_empty(self) -> None:
        store = VectorStore()
        results = store.query([1.0, 0.0, 0.0])
        assert results == []

    def test_clear(self) -> None:
        store = self._make_store()
        store.clear()
        assert store.count() == 0

    def test_persist_and_load(self, tmp_path: Path) -> None:
        store = self._make_store()
        path = tmp_path / "store.gz"
        store.persist(path)
        loaded = VectorStore.load(path)
        assert loaded.count() == 3

    def test_load_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        loaded = VectorStore.load(tmp_path / "missing.gz")
        assert loaded.count() == 0

    def test_query_after_persist_load(self, tmp_path: Path) -> None:
        store = self._make_store()
        path = tmp_path / "store.gz"
        store.persist(path)
        loaded = VectorStore.load(path)
        results = loaded.query([1.0, 0.0, 0.0], top_k=1)
        assert results[0].source_path == "a.txt"

    def test_all_texts_returns_all_chunk_texts(self) -> None:
        store = self._make_store()
        texts = store.all_texts()
        assert len(texts) == 3
        assert "apple fruit" in texts
        assert "car vehicle" in texts

    def test_result_has_source_path(self) -> None:
        store = self._make_store()
        results = store.query([1.0, 0.0, 0.0], top_k=1)
        assert results[0].source_path in ("a.txt", "b.txt", "c.txt")

    def test_result_has_chunk_text(self) -> None:
        store = self._make_store()
        results = store.query([1.0, 0.0, 0.0], top_k=1)
        assert results[0].chunk_text != ""
