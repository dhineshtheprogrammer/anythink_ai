"""Tests for SerpAPISearch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.exceptions import SearchError
from anythink.search.base import SearchResult
from anythink.search.serpapi import (
    SerpAPISearch,
    _domain_from_url,
    _freshness_to_tbs,
)


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


class TestSerpAPIHelpers:
    def test_freshness_to_tbs_known_values(self) -> None:
        assert _freshness_to_tbs("24h") == "qdr:d"
        assert _freshness_to_tbs("7d") == "qdr:w"
        assert _freshness_to_tbs("30d") == "qdr:m"
        assert _freshness_to_tbs("3m") == "qdr:m"

    def test_freshness_to_tbs_unknown_defaults_to_week(self) -> None:
        assert _freshness_to_tbs("unknown") == "qdr:w"

    def test_domain_from_url_strips_www(self) -> None:
        assert _domain_from_url("https://www.python.org/docs") == "python.org"

    def test_domain_from_url_no_www(self) -> None:
        assert _domain_from_url("https://docs.python.org") == "docs.python.org"

    def test_domain_from_url_empty(self) -> None:
        assert _domain_from_url("") is None

    async def test_search_with_freshness_filter(self) -> None:
        data = {"organic_results": [{"title": "T", "link": "http://u.com", "snippet": "s"}]}
        client = _make_mock_client(data)
        with patch("anythink.search.serpapi.httpx.AsyncClient", return_value=client):
            results = await SerpAPISearch(api_key="k").search("python", date_from="7d")
        assert len(results) == 1
        call_str = str(client.get.call_args)
        assert "qdr:w" in call_str

    async def test_search_with_include_domains(self) -> None:
        data = {"organic_results": [{"title": "T", "link": "http://u.com", "snippet": "s"}]}
        client = _make_mock_client(data)
        with patch("anythink.search.serpapi.httpx.AsyncClient", return_value=client):
            await SerpAPISearch(api_key="k").search("python", include_domains=["docs.python.org"])
        call_str = str(client.get.call_args)
        assert "docs.python.org" in call_str

    async def test_search_with_safe_search(self) -> None:
        data = {"organic_results": []}
        client = _make_mock_client(data)
        with patch("anythink.search.serpapi.httpx.AsyncClient", return_value=client):
            await SerpAPISearch(api_key="k").search("python", safe_search="strict")
        call_str = str(client.get.call_args)
        assert "active" in call_str

    def test_domain_from_url_empty_host(self) -> None:
        # URL with empty host after scheme
        result = _domain_from_url("https:///path/to/resource")
        assert result is None

    def test_domain_from_url_exception_returns_none(self) -> None:
        # Passing a non-str triggers exception → None
        result = _domain_from_url(None)  # type: ignore[arg-type]
        assert result is None
