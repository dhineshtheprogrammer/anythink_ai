"""Tests for search/base.py."""

from __future__ import annotations

from anythink.search.base import SearchResult


class TestSearchResult:
    def test_stores_title(self) -> None:
        r = SearchResult(title="Python", url="https://python.org", snippet="A language")
        assert r.title == "Python"

    def test_stores_url(self) -> None:
        r = SearchResult(title="Python", url="https://python.org", snippet="A language")
        assert r.url == "https://python.org"

    def test_stores_snippet(self) -> None:
        r = SearchResult(title="Python", url="https://python.org", snippet="A language")
        assert r.snippet == "A language"

    def test_empty_snippet_allowed(self) -> None:
        r = SearchResult(title="Go", url="https://go.dev", snippet="")
        assert r.snippet == ""
