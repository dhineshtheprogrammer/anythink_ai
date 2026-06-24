"""Tests for NewsAPISearch backend."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.exceptions import SearchError
from anythink.search.newsapi import NewsAPISearch, _domain_from_url


class TestDomainFromUrl:
    def test_strips_www(self) -> None:
        assert _domain_from_url("https://www.bbc.com/news") == "bbc.com"

    def test_no_www(self) -> None:
        assert _domain_from_url("https://techcrunch.com/ai") == "techcrunch.com"

    def test_empty_url_returns_none(self) -> None:
        assert _domain_from_url("") is None


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


class TestNewsAPISearch:
    def test_name(self) -> None:
        assert NewsAPISearch.name == "newsapi"

    def test_display_name(self) -> None:
        assert NewsAPISearch.display_name == "NewsAPI"

    def test_supports_news(self) -> None:
        assert NewsAPISearch.supports_news is True
        assert NewsAPISearch.supports_freshness is True

    def test_not_available_without_key(self) -> None:
        assert NewsAPISearch().is_available() is False

    def test_available_with_key(self) -> None:
        assert NewsAPISearch(api_key="k").is_available() is True

    async def test_raises_without_key(self) -> None:
        with pytest.raises(SearchError, match="NewsAPI"):
            await NewsAPISearch().search("test")

    async def test_search_returns_articles(self) -> None:
        data = {
            "articles": [
                {
                    "title": "AI Advances",
                    "url": "https://news.com/ai",
                    "description": "Big news",
                    "publishedAt": "2025-06-01T10:00:00Z",
                    "source": {"name": "TechCrunch"},
                }
            ]
        }
        client = _make_client(data)
        with patch("anythink.search.newsapi.httpx.AsyncClient", return_value=client):
            results = await NewsAPISearch(api_key="k").search("AI")
        assert len(results) == 1
        assert results[0].title == "AI Advances"
        assert results[0].published_date == "2025-06-01"
        assert results[0].source_domain == "TechCrunch"

    async def test_date_params_forwarded(self) -> None:
        client = _make_client({"articles": []})
        with patch("anythink.search.newsapi.httpx.AsyncClient", return_value=client):
            await NewsAPISearch(api_key="k").search(
                "test", date_from="2025-01-01", date_to="2025-06-01"
            )
        call_str = str(client.get.call_args)
        assert "2025-01-01" in call_str

    async def test_shorthand_freshness_not_forwarded(self) -> None:
        """Shorthand periods like '7d' are not ISO dates so they are skipped."""
        client = _make_client({"articles": []})
        with patch("anythink.search.newsapi.httpx.AsyncClient", return_value=client):
            await NewsAPISearch(api_key="k").search("test", date_from="7d")
        call_str = str(client.get.call_args)
        assert "7d" not in call_str

    async def test_http_error_raises_search_error(self) -> None:
        client = _make_client({}, status_code=401)
        with patch("anythink.search.newsapi.httpx.AsyncClient", return_value=client):
            with pytest.raises(SearchError, match="401"):
                await NewsAPISearch(api_key="k").search("test")

    async def test_network_error_raises_search_error(self) -> None:
        import httpx

        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.RequestError("network"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("anythink.search.newsapi.httpx.AsyncClient", return_value=client):
            with pytest.raises(SearchError, match="network"):
                await NewsAPISearch(api_key="k").search("test")

    async def test_empty_articles_returns_empty(self) -> None:
        client = _make_client({"articles": []})
        with patch("anythink.search.newsapi.httpx.AsyncClient", return_value=client):
            results = await NewsAPISearch(api_key="k").search("test")
        assert results == []

    async def test_max_results_respected(self) -> None:
        articles = [
            {"title": f"T{i}", "url": f"http://u{i}.com", "description": "d",
             "publishedAt": None, "source": {"name": "S"}}
            for i in range(10)
        ]
        client = _make_client({"articles": articles})
        with patch("anythink.search.newsapi.httpx.AsyncClient", return_value=client):
            results = await NewsAPISearch(api_key="k").search("test", max_results=3)
        assert len(results) == 3

    async def test_include_domains_forwarded(self) -> None:
        client = _make_client({"articles": []})
        with patch("anythink.search.newsapi.httpx.AsyncClient", return_value=client):
            await NewsAPISearch(api_key="k").search(
                "python", include_domains=["techcrunch.com"]
            )
        call_str = str(client.get.call_args)
        assert "techcrunch.com" in call_str

    async def test_exclude_domains_forwarded(self) -> None:
        client = _make_client({"articles": []})
        with patch("anythink.search.newsapi.httpx.AsyncClient", return_value=client):
            await NewsAPISearch(api_key="k").search(
                "python", exclude_domains=["reddit.com"]
            )
        call_str = str(client.get.call_args)
        assert "reddit.com" in call_str

    async def test_date_to_forwarded(self) -> None:
        client = _make_client({"articles": []})
        with patch("anythink.search.newsapi.httpx.AsyncClient", return_value=client):
            await NewsAPISearch(api_key="k").search(
                "test", date_from="2025-01-01", date_to="2025-06-30"
            )
        call_str = str(client.get.call_args)
        assert "2025-06-30" in call_str

    async def test_article_with_url_based_domain(self) -> None:
        """When source.name is absent, fall back to URL-based domain."""
        data = {
            "articles": [
                {
                    "title": "T",
                    "url": "https://news.ycombinator.com/item?id=1",
                    "description": "d",
                    "publishedAt": None,
                    "source": {"name": ""},
                }
            ]
        }
        client = _make_client(data)
        with patch("anythink.search.newsapi.httpx.AsyncClient", return_value=client):
            results = await NewsAPISearch(api_key="k").search("test")
        assert results[0].source_domain == "news.ycombinator.com"
