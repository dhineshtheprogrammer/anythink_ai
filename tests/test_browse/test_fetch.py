"""Tests for browse/fetch.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.browse.fetch import BrowseFetcher, BrowseTool, _strip_html


class TestStripHtml:
    def test_removes_tags(self) -> None:
        assert _strip_html("<b>hello</b>") == "hello"

    def test_removes_script(self) -> None:
        assert "alert" not in _strip_html("<script>alert('x')</script>text")

    def test_removes_style(self) -> None:
        assert "color:red" not in _strip_html("<style>p{color:red}</style>text")

    def test_unescapes_entities(self) -> None:
        result = _strip_html("&amp;&lt;&gt;&quot;&nbsp;")
        assert "&" in result and "<" in result and ">" in result and '"' in result

    def test_collapses_whitespace(self) -> None:
        result = _strip_html("<p>a</p>   \n\n\n   <p>b</p>")
        assert "a" in result and "b" in result
        assert "   \n\n\n   " not in result

    def test_plain_text_unchanged(self) -> None:
        assert _strip_html("hello world") == "hello world"


class TestBrowseFetcherSnippets:
    async def test_returns_snippets_from_search(self) -> None:
        mock_result = MagicMock()
        mock_result.title = "Example"
        mock_result.snippet = "An example page."

        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(return_value=[mock_result])

        mock_registry = MagicMock()
        mock_registry.get_available = MagicMock(return_value=mock_backend)

        fetcher = BrowseFetcher(search_registry=mock_registry)
        pairs = await fetcher.fetch_snippets("example query")

        assert pairs == [("Example", "An example page.")]

    async def test_raises_search_error_when_no_registry(self) -> None:
        from anythink.exceptions import SearchError

        fetcher = BrowseFetcher(search_registry=None)
        with pytest.raises(SearchError, match="No search registry"):
            await fetcher.fetch_snippets("query")

    async def test_raises_search_error_when_no_backend(self) -> None:
        from anythink.exceptions import SearchError

        mock_registry = MagicMock()
        mock_registry.get_available = MagicMock(return_value=None)

        fetcher = BrowseFetcher(search_registry=mock_registry)
        with pytest.raises(SearchError, match="No search backend"):
            await fetcher.fetch_snippets("query")

    async def test_propagates_search_exception(self) -> None:
        from anythink.exceptions import SearchError

        mock_backend = AsyncMock()
        mock_backend.search = AsyncMock(side_effect=SearchError("network error"))

        mock_registry = MagicMock()
        mock_registry.get_available = MagicMock(return_value=mock_backend)

        fetcher = BrowseFetcher(search_registry=mock_registry)
        with pytest.raises(SearchError, match="network error"):
            await fetcher.fetch_snippets("query")


class TestBrowseToolAvailability:
    def test_available_when_httpx_importable(self) -> None:
        # httpx is a core dep, so this should always pass
        assert BrowseTool(BrowseFetcher()).is_available()

    def test_unavailable_when_httpx_missing(self) -> None:
        with patch.dict("sys.modules", {"httpx": None}):
            assert not BrowseTool(BrowseFetcher()).is_available()


class TestBrowseToolRunUrl:
    async def test_fetch_url_success(self) -> None:
        fetcher = BrowseFetcher()
        fetcher.fetch_page = AsyncMock(return_value="<html>hello world</html>")  # type: ignore[method-assign]

        tool = BrowseTool(fetcher)
        result = await tool.run(url="http://example.com")

        assert result.exit_code == 0
        assert result.succeeded
        assert "hello" in result.stdout

    async def test_fetch_url_error(self) -> None:
        from anythink.exceptions import BrowseError

        fetcher = BrowseFetcher()
        fetcher.fetch_page = AsyncMock(side_effect=BrowseError("fail", user_message="Network error"))  # type: ignore[method-assign]

        tool = BrowseTool(fetcher)
        result = await tool.run(url="http://bad.example")

        assert not result.succeeded
        assert "Network error" in result.stderr


class TestBrowseToolRunQuery:
    async def test_snippet_search_success(self) -> None:
        fetcher = BrowseFetcher()
        fetcher.fetch_snippets = AsyncMock(return_value=[("Title", "A snippet.")])  # type: ignore[method-assign]

        tool = BrowseTool(fetcher)
        result = await tool.run(query="test query")

        assert result.succeeded
        assert "Title" in result.stdout
        assert "A snippet." in result.stdout

    async def test_snippet_search_no_results(self) -> None:
        fetcher = BrowseFetcher()
        fetcher.fetch_snippets = AsyncMock(return_value=[])  # type: ignore[method-assign]

        tool = BrowseTool(fetcher)
        result = await tool.run(query="obscure query")

        assert not result.succeeded
        assert "No search results" in result.stderr

    async def test_no_url_no_query_returns_error(self) -> None:
        tool = BrowseTool(BrowseFetcher())
        result = await tool.run()

        assert not result.succeeded
        assert "url=" in result.stderr or "query=" in result.stderr


class TestBrowseFetcherHeadlessGuard:
    async def test_headless_raises_without_playwright(self) -> None:
        from anythink.exceptions import BrowseError

        fetcher = BrowseFetcher(mode="headless")
        with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
            with pytest.raises(BrowseError, match="Playwright"):
                await fetcher.fetch_page("http://example.com")
