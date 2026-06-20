"""Tests for SerpAPISearch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.exceptions import SearchError
from anythink.search.base import SearchResult
from anythink.search.serpapi import SerpAPISearch


def _make_mock_client(json_data: dict, status_code: int = 200) -> MagicMock:
    """Return a mock httpx.AsyncClient that returns *json_data*."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=json_data)
    if status_code != 200:
        import httpx

        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock(status_code=status_code)
        )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestSerpAPISearch:
    def test_name(self) -> None:
        assert SerpAPISearch.name == "serpapi"

    def test_display_name(self) -> None:
        assert SerpAPISearch.display_name == "SerpAPI"

    def test_is_available_false_without_key(self) -> None:
        assert SerpAPISearch().is_available() is False

    def test_is_available_true_with_key(self) -> None:
        assert SerpAPISearch(api_key="abc").is_available() is True

    async def test_search_raises_when_no_key(self) -> None:
        with pytest.raises(SearchError, match="SerpAPI key"):
            await SerpAPISearch().search("python")

    async def test_search_returns_results(self) -> None:
        backend = SerpAPISearch(api_key="key-123")
        data = {
            "organic_results": [
                {"title": "Python", "link": "https://python.org", "snippet": "A language"},
            ]
        }
        mock_client = _make_mock_client(data)
        with patch("anythink.search.serpapi.httpx.AsyncClient", return_value=mock_client):
            results = await backend.search("python")

        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].title == "Python"
        assert results[0].url == "https://python.org"
        assert results[0].snippet == "A language"

    async def test_search_respects_max_results(self) -> None:
        backend = SerpAPISearch(api_key="key")
        data = {
            "organic_results": [
                {"title": f"R{i}", "link": f"https://{i}.com", "snippet": ""} for i in range(10)
            ]
        }
        mock_client = _make_mock_client(data)
        with patch("anythink.search.serpapi.httpx.AsyncClient", return_value=mock_client):
            results = await backend.search("q", max_results=3)

        assert len(results) == 3

    async def test_search_handles_empty_organic_results(self) -> None:
        backend = SerpAPISearch(api_key="key")
        mock_client = _make_mock_client({"organic_results": []})
        with patch("anythink.search.serpapi.httpx.AsyncClient", return_value=mock_client):
            results = await backend.search("obscure query")

        assert results == []

    async def test_search_handles_missing_organic_results_key(self) -> None:
        backend = SerpAPISearch(api_key="key")
        mock_client = _make_mock_client({})
        with patch("anythink.search.serpapi.httpx.AsyncClient", return_value=mock_client):
            results = await backend.search("q")

        assert results == []

    async def test_search_raises_on_http_error(self) -> None:
        backend = SerpAPISearch(api_key="bad-key")
        mock_client = _make_mock_client({}, status_code=403)
        with patch("anythink.search.serpapi.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(SearchError, match="SerpAPI HTTP error"):
                await backend.search("python")

    async def test_search_raises_on_network_error(self) -> None:
        import httpx

        backend = SerpAPISearch(api_key="key")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("timeout", request=MagicMock()))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("anythink.search.serpapi.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(SearchError, match="SerpAPI request error"):
                await backend.search("python")
