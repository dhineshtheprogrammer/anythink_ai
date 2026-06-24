"""Tests for the pure-Python BM25 index."""

from __future__ import annotations

from pathlib import Path

import pytest

from anythink.rag.bm25 import BM25Index, _tokenize


class TestTokenize:
    def test_lowercase(self) -> None:
        assert _tokenize("Hello World") == ["hello", "world"]

    def test_strips_punctuation(self) -> None:
        tokens = _tokenize("Hello, world! Python's great.")
        assert "hello" in tokens
        assert "world" in tokens
        assert "python" in tokens

    def test_empty_string(self) -> None:
        assert _tokenize("") == []

    def test_numbers_kept(self) -> None:
        tokens = _tokenize("v3 config item 42")
        assert "v3" in tokens
        assert "42" in tokens


class TestBM25Build:
    def test_is_built_after_build(self) -> None:
        idx = BM25Index()
        assert not idx.is_built
        idx.build(["alpha beta gamma"])
        assert idx.is_built

    def test_corpus_size(self) -> None:
        idx = BM25Index()
        idx.build(["doc one", "doc two", "doc three"])
        assert idx.corpus_size == 3

    def test_empty_corpus(self) -> None:
        idx = BM25Index()
        idx.build([])
        assert idx.corpus_size == 0
        assert idx.score("query", top_k=5) == []

    def test_rebuild_replaces_previous(self) -> None:
        idx = BM25Index()
        idx.build(["doc one"])
        idx.build(["doc one", "doc two"])
        assert idx.corpus_size == 2


class TestBM25Score:
    @pytest.fixture()
    def idx(self) -> BM25Index:
        corpus = [
            "python programming language tutorial",
            "javascript web development frontend",
            "machine learning neural networks deep learning",
            "python data science pandas numpy",
            "database sql queries optimization",
        ]
        bm25 = BM25Index()
        bm25.build(corpus)
        return bm25

    def test_returns_list_of_tuples(self, idx: BM25Index) -> None:
        result = idx.score("python", top_k=3)
        assert isinstance(result, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in result)

    def test_python_query_ranks_python_docs_first(self, idx: BM25Index) -> None:
        result = idx.score("python", top_k=5)
        indices = [i for i, _ in result]
        # Doc 0 (python tutorial) and doc 3 (python data science) should rank high
        assert 0 in indices or 3 in indices
        if indices:
            assert indices[0] in (0, 3)

    def test_scores_sorted_descending(self, idx: BM25Index) -> None:
        result = idx.score("python programming", top_k=5)
        scores = [s for _, s in result]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_limits_results(self, idx: BM25Index) -> None:
        result = idx.score("learning", top_k=2)
        assert len(result) <= 2

    def test_no_match_returns_empty(self, idx: BM25Index) -> None:
        result = idx.score("zzz_nonexistent_term_xyz", top_k=5)
        assert result == []

    def test_multi_word_query(self, idx: BM25Index) -> None:
        result = idx.score("deep learning neural", top_k=3)
        indices = [i for i, _ in result]
        # Doc 2 (machine learning neural networks) should rank first
        assert indices[0] == 2

    def test_not_built_returns_empty(self) -> None:
        idx = BM25Index()
        assert idx.score("anything", top_k=5) == []

    def test_scores_are_positive(self, idx: BM25Index) -> None:
        result = idx.score("python", top_k=5)
        assert all(s > 0 for _, s in result)

    def test_idf_rare_terms_score_higher(self) -> None:
        corpus = ["common word appears everywhere"] * 10 + ["unique special term here"]
        idx = BM25Index()
        idx.build(corpus)
        # Query for the rare term should score the last doc highest
        result = idx.score("unique special term", top_k=1)
        assert result and result[0][0] == 10  # last doc


class TestBM25Persistence:
    def test_persist_and_load_roundtrip(self, tmp_path: Path) -> None:
        corpus = ["alpha beta gamma", "delta epsilon zeta", "theta iota kappa"]
        original = BM25Index()
        original.build(corpus)
        path = tmp_path / "test.bm25.gz"
        original.persist(path)

        loaded = BM25Index.load(path)
        assert loaded.is_built
        assert loaded.corpus_size == 3

    def test_loaded_scores_match_original(self, tmp_path: Path) -> None:
        corpus = ["machine learning model", "deep neural network", "data science pipeline"]
        original = BM25Index()
        original.build(corpus)
        path = tmp_path / "idx.bm25.gz"
        original.persist(path)

        loaded = BM25Index.load(path)
        orig_scores = original.score("machine learning", top_k=3)
        load_scores = loaded.score("machine learning", top_k=3)
        assert [i for i, _ in orig_scores] == [i for i, _ in load_scores]

    def test_load_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        idx = BM25Index.load(tmp_path / "missing.bm25.gz")
        assert not idx.is_built

    def test_persist_creates_parent_dirs(self, tmp_path: Path) -> None:
        idx = BM25Index()
        idx.build(["some text"])
        deep = tmp_path / "a" / "b" / "c" / "idx.bm25.gz"
        idx.persist(deep)
        assert deep.exists()

    def test_k1_b_preserved_across_roundtrip(self, tmp_path: Path) -> None:
        idx = BM25Index(k1=2.0, b=0.5)
        idx.build(["text"])
        path = tmp_path / "idx.bm25.gz"
        idx.persist(path)
        loaded = BM25Index.load(path)
        assert loaded.k1 == 2.0
        assert loaded.b == 0.5
