"""Tests for SearchCache."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from anythink.search.base import SearchResult
from anythink.search.cache import SearchCache, _cosine, _tfidf_vector, _tokenize


def _make_results(n: int = 1) -> list[SearchResult]:
    return [SearchResult(title=f"T{i}", url=f"http://u{i}.com", snippet=f"s{i}") for i in range(n)]


class TestHelpers:
    def test_tokenize_lowercases(self) -> None:
        assert _tokenize("Hello World") == ["hello", "world"]

    def test_tokenize_strips_punctuation(self) -> None:
        assert _tokenize("foo, bar!") == ["foo", "bar"]

    def test_tokenize_numbers(self) -> None:
        assert "3" in _tokenize("python 3")

    def test_tfidf_vector_non_empty(self) -> None:
        idf = {"python": 1.0, "async": 1.0}
        vec = _tfidf_vector(["python", "async", "python"], idf)
        assert "python" in vec
        assert vec["python"] > vec["async"]

    def test_cosine_identical(self) -> None:
        v = {"a": 1.0, "b": 2.0}
        assert _cosine(v, v) == pytest.approx(1.0)

    def test_cosine_disjoint(self) -> None:
        assert _cosine({"a": 1.0}, {"b": 1.0}) == pytest.approx(0.0)

    def test_cosine_zero_vectors(self) -> None:
        assert _cosine({}, {"a": 1.0}) == 0.0


class TestSearchCache:
    def test_get_miss_on_empty(self) -> None:
        cache = SearchCache()
        assert cache.get("python", "ddg") is None

    def test_put_and_exact_get(self) -> None:
        cache = SearchCache()
        results = _make_results(2)
        cache.put("python async", "ddg", results)
        got = cache.get("python async", "ddg")
        assert got is not None
        assert len(got) == 2

    def test_exact_match_case_insensitive(self) -> None:
        cache = SearchCache()
        cache.put("Python Async", "ddg", _make_results())
        assert cache.get("python async", "ddg") is not None

    def test_different_backend_is_miss(self) -> None:
        cache = SearchCache()
        cache.put("python", "ddg", _make_results())
        assert cache.get("python", "bing") is None

    def test_semantic_hit_near_duplicate(self) -> None:
        cache = SearchCache()
        cache.put("python asyncio", "ddg", _make_results(3))
        # Very similar query should hit semantic cache
        result = cache.get("asyncio python", "ddg")
        assert result is not None

    def test_semantic_miss_unrelated(self) -> None:
        cache = SearchCache()
        cache.put("python asyncio", "ddg", _make_results())
        assert cache.get("quantum computing blockchain", "ddg") is None

    def test_evict_expired(self) -> None:
        cache = SearchCache(ttl_minutes=1)
        cache.put("python", "ddg", _make_results())
        # Manually expire the entry
        cache._entries[0].created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        removed = cache.evict_expired()
        assert removed == 1
        assert cache.get("python", "ddg") is None

    def test_not_expired_within_ttl(self) -> None:
        cache = SearchCache(ttl_minutes=30)
        cache.put("python", "ddg", _make_results())
        removed = cache.evict_expired()
        assert removed == 0

    def test_clear(self) -> None:
        cache = SearchCache()
        cache.put("python", "ddg", _make_results())
        cache.put("rust", "ddg", _make_results())
        cache.clear()
        assert cache.get("python", "ddg") is None
        assert cache.status()["entries"] == 0

    def test_status_empty(self) -> None:
        cache = SearchCache()
        s = cache.status()
        assert s["entries"] == 0
        assert s["oldest_age_s"] is None

    def test_status_with_entry(self) -> None:
        cache = SearchCache()
        cache.put("python", "ddg", _make_results())
        s = cache.status()
        assert s["entries"] == 1
        assert isinstance(s["oldest_age_s"], float)

    def test_max_entries_evicts_oldest(self) -> None:
        cache = SearchCache(max_entries=2)
        cache.put("a", "ddg", _make_results())
        cache.put("b", "ddg", _make_results())
        cache.put("c", "ddg", _make_results())
        assert cache.status()["entries"] == 2
        assert cache.get("a", "ddg") is None  # oldest was evicted

    def test_put_returns_copy_not_reference(self) -> None:
        cache = SearchCache()
        results = _make_results(1)
        cache.put("q", "ddg", results)
        results.append(SearchResult(title="X", url="x", snippet="x"))
        got = cache.get("q", "ddg")
        assert got is not None
        assert len(got) == 1


class TestCosineSimilarityZeroMagnitude:
    def test_cosine_zero_magnitude_with_common_key(self) -> None:
        # Both have common key but value=0 → mag_a=0 → line 42 branch
        assert _cosine({"x": 0.0}, {"x": 1.0}) == pytest.approx(0.0)
