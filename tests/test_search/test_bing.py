"""Tests for BingSearch backend."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.exceptions import SearchError
from anythink.search.bing import BingSearch, _domain_from_url


class TestDomainFromUrl:
    def test_strips_www(self) -> None:
        assert _domain_from_url("https://www.python.org/docs") == "python.org"

    def test_no_www(self) -> None:
        assert _domain_from_url("https://docs.python.org/3/") == "docs.python.org"

    def test_empty_url(self) -> None:
        assert _domain_from_url("") is None

    def test_host_becomes_empty(self) -> None:
        # URL where host would be empty string
        assert _domain_from_url("https:///path") is None


def _make_client(json_data: dict, status_code: int = 200) -> MagicMock:
    import httpx

    mock_resp = MagicMock()
    mock_resp.json = MagicMock(return_value=json_data)
    if status_code != 200:
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "err", request=MagicMock(), response=MagicMock(status_code=status_code)
        )
    else:
        mock_resp.raise_for_status = MagicMock()
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


class TestBingSearch:
    def test_name(self) -> None:
        assert BingSearch.name == "bing"

    def test_display_name(self) -> None:
        assert BingSearch.display_name == "Bing"

    def test_supports_flags(self) -> None:
        assert BingSearch.supports_freshness is True
        assert BingSearch.supports_safe_search is True
        assert BingSearch.supports_news is True

    def test_not_available_without_key(self) -> None:
        assert BingSearch().is_available() is False

    def test_available_with_key(self) -> None:
        assert BingSearch(api_key="k").is_available() is True

    async def test_raises_without_key(self) -> None:
        with pytest.raises(SearchError, match="Bing"):
            await BingSearch().search("test")

    async def test_web_search_returns_results(self) -> None:
        data = {"webPages": {"value": [
            {"name": "Python", "url": "https://python.org", "snippet": "A language"},
        ]}}
        client = _make_client(data)
        with patch("anythink.search.bing.httpx.AsyncClient", return_value=client):
            results = await BingSearch(api_key="key").search("python")
        assert len(results) == 1
        assert results[0].title == "Python"
        assert results[0].url == "https://python.org"
        assert results[0].source_domain == "python.org"

    async def test_news_search_returns_results(self) -> None:
        data = {"value": [
            {"name": "AI News", "url": "https://news.com/ai", "description": "AI stuff",
             "datePublished": "2025-06-01T12:00:00Z"},
        ]}
        client = _make_client(data)
        with patch("anythink.search.bing.httpx.AsyncClient", return_value=client):
            results = await BingSearch(api_key="key").search("AI news", news_mode=True)
        assert len(results) == 1
        assert results[0].published_date == "2025-06-01"

    async def test_freshness_param_applied(self) -> None:
        data = {"webPages": {"value": []}}
        client = _make_client(data)
        with patch("anythink.search.bing.httpx.AsyncClient", return_value=client):
            await BingSearch(api_key="k").search("test", date_from="7d")
        call_kwargs = client.get.call_args
        assert "freshness" in str(call_kwargs)

    async def test_http_error_raises_search_error(self) -> None:
        client = _make_client({}, status_code=403)
        with patch("anythink.search.bing.httpx.AsyncClient", return_value=client):
            with pytest.raises(SearchError, match="403"):
                await BingSearch(api_key="k").search("test")

    async def test_network_error_raises_search_error(self) -> None:
        import httpx

        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.RequestError("network"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("anythink.search.bing.httpx.AsyncClient", return_value=client):
            with pytest.raises(SearchError, match="network"):
                await BingSearch(api_key="k").search("test")

    async def test_domain_filters_appended_to_query(self) -> None:
        data = {"webPages": {"value": []}}
        client = _make_client(data)
        with patch("anythink.search.bing.httpx.AsyncClient", return_value=client):
            await BingSearch(api_key="k").search(
                "python", include_domains=["docs.python.org"]
            )
        call_str = str(client.get.call_args)
        assert "docs.python.org" in call_str

    async def test_empty_response_returns_empty_list(self) -> None:
        client = _make_client({"webPages": {"value": []}})
        with patch("anythink.search.bing.httpx.AsyncClient", return_value=client):
            results = await BingSearch(api_key="k").search("test")
        assert results == []

    async def test_safe_search_strict(self) -> None:
        client = _make_client({"webPages": {"value": []}})
        with patch("anythink.search.bing.httpx.AsyncClient", return_value=client):
            await BingSearch(api_key="k").search("test", safe_search="strict")
        call_str = str(client.get.call_args)
        assert "Strict" in call_str

    async def test_safe_search_off(self) -> None:
        client = _make_client({"webPages": {"value": []}})
        with patch("anythink.search.bing.httpx.AsyncClient", return_value=client):
            await BingSearch(api_key="k").search("test", safe_search="off")
        call_str = str(client.get.call_args)
        assert "Off" in call_str

    async def test_exclude_domains_query(self) -> None:
        client = _make_client({"webPages": {"value": []}})
        with patch("anythink.search.bing.httpx.AsyncClient", return_value=client):
            await BingSearch(api_key="k").search("test", exclude_domains=["bad.com"])
        call_str = str(client.get.call_args)
        assert "-site:bad.com" in call_str
