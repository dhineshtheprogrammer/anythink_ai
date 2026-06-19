"""Tests for DuckDuckGoSearch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from anythink.exceptions import SearchError
from anythink.search.base import SearchResult
from anythink.search.duckduckgo import DuckDuckGoSearch


def _make_ddgs_module(raw_results: list[dict]) -> MagicMock:
    """Return a mock duckduckgo_search module whose DDGS yields *raw_results*."""
    mock_ddgs = MagicMock()
    mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
    mock_ddgs.__exit__ = MagicMock(return_value=False)
    mock_ddgs.text = MagicMock(return_value=raw_results)

    mock_module = MagicMock()
    mock_module.DDGS = MagicMock(return_value=mock_ddgs)
    return mock_module


class TestDuckDuckGoSearch:
    def test_name(self) -> None:
        assert DuckDuckGoSearch.name == "duckduckgo"

    def test_display_name(self) -> None:
        assert DuckDuckGoSearch.display_name == "DuckDuckGo"

    def test_is_available_true_when_sdk_importable(self) -> None:
        ddg = DuckDuckGoSearch()
        with patch.dict("sys.modules", {"duckduckgo_search": MagicMock()}):
            assert ddg.is_available() is True

    def test_is_available_false_when_sdk_missing(self) -> None:
        ddg = DuckDuckGoSearch()
        with patch.dict("sys.modules", {"duckduckgo_search": None}):
            assert ddg.is_available() is False

    async def test_search_raises_when_not_available(self) -> None:
        ddg = DuckDuckGoSearch()
        with patch.object(ddg, "is_available", return_value=False):
            with pytest.raises(SearchError, match="anythink"):
                await ddg.search("python")

    async def test_search_returns_results(self) -> None:
        raw = [{"title": "PEP 8", "href": "https://peps.python.org/pep-0008/", "body": "Style guide."}]
        ddg = DuckDuckGoSearch()
        mock_module = _make_ddgs_module(raw)

        with patch.dict("sys.modules", {"duckduckgo_search": mock_module}), \
                patch.object(ddg, "is_available", return_value=True):
            results = await ddg.search("pep 8", max_results=1)

        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].title == "PEP 8"
        assert results[0].url == "https://peps.python.org/pep-0008/"
        assert results[0].snippet == "Style guide."

    async def test_search_raises_search_error_on_exception(self) -> None:
        ddg = DuckDuckGoSearch()
        with patch.object(ddg, "is_available", return_value=True), \
                patch.object(ddg, "_sync_search", side_effect=RuntimeError("network error")):
            with pytest.raises(SearchError, match="DuckDuckGo search failed"):
                await ddg.search("query")

    async def test_search_re_raises_search_error_directly(self) -> None:
        ddg = DuckDuckGoSearch()
        original = SearchError("already a search error", user_message="already a search error")
        with patch.object(ddg, "is_available", return_value=True), \
                patch.object(ddg, "_sync_search", side_effect=original):
            with pytest.raises(SearchError, match="already a search error"):
                await ddg.search("query")

    def test_sync_search_maps_fields(self) -> None:
        ddg = DuckDuckGoSearch()
        raw = [{"title": "Go", "href": "https://go.dev", "body": "A language."}]
        mock_module = _make_ddgs_module(raw)

        with patch.dict("sys.modules", {"duckduckgo_search": mock_module}):
            results = ddg._sync_search("go lang", 1)

        assert results[0].title == "Go"
        assert results[0].url == "https://go.dev"
        assert results[0].snippet == "A language."

    def test_sync_search_returns_multiple_results(self) -> None:
        ddg = DuckDuckGoSearch()
        raw = [
            {"title": "A", "href": "https://a.com", "body": "First"},
            {"title": "B", "href": "https://b.com", "body": "Second"},
        ]
        mock_module = _make_ddgs_module(raw)

        with patch.dict("sys.modules", {"duckduckgo_search": mock_module}):
            results = ddg._sync_search("query", 2)

        assert len(results) == 2
        assert results[1].title == "B"

    def test_sync_search_handles_missing_fields(self) -> None:
        ddg = DuckDuckGoSearch()
        raw = [{}]  # all fields missing
        mock_module = _make_ddgs_module(raw)

        with patch.dict("sys.modules", {"duckduckgo_search": mock_module}):
            results = ddg._sync_search("query", 1)

        assert results[0].title == ""
        assert results[0].url == ""
        assert results[0].snippet == ""
