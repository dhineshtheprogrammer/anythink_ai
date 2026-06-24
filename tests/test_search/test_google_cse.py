"""Tests for GoogleCSESearch backend."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.exceptions import SearchError
from anythink.search.google_cse import GoogleCSESearch, _domain_from_url


class TestDomainFromUrl:
    def test_strips_www(self) -> None:
        assert _domain_from_url("https://www.google.com/search") == "google.com"

    def test_no_www(self) -> None:
        assert _domain_from_url("https://developers.google.com") == "developers.google.com"

    def test_empty(self) -> None:
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


class TestGoogleCSESearch:
    def test_name(self) -> None:
        assert GoogleCSESearch.name == "google_cse"

    def test_display_name(self) -> None:
        assert GoogleCSESearch.display_name == "Google"

    def test_supports_flags(self) -> None:
        assert GoogleCSESearch.supports_freshness is True
        assert GoogleCSESearch.supports_safe_search is True

    def test_not_available_without_key(self) -> None:
        assert GoogleCSESearch().is_available() is False

    def test_not_available_without_cx(self) -> None:
        assert GoogleCSESearch(api_key="apikey").is_available() is False

    def test_available_with_key_and_cx(self) -> None:
        assert GoogleCSESearch(api_key="key:cx123").is_available() is True

    async def test_raises_without_key(self) -> None:
        with pytest.raises(SearchError):
            await GoogleCSESearch().search("test")

    async def test_raises_with_malformed_key(self) -> None:
        with pytest.raises(SearchError, match="malformed"):
            await GoogleCSESearch(api_key="nokeycolon").search("test")

    async def test_search_returns_results(self) -> None:
        data = {
            "items": [
                {"title": "Python", "link": "https://python.org", "snippet": "A lang"},
            ]
        }
        client = _make_client(data)
        with patch("anythink.search.google_cse.httpx.AsyncClient", return_value=client):
            results = await GoogleCSESearch(api_key="key:cx123").search("python")
        assert len(results) == 1
        assert results[0].title == "Python"
        assert results[0].source_domain == "python.org"

    async def test_freshness_param_in_request(self) -> None:
        client = _make_client({"items": []})
        with patch("anythink.search.google_cse.httpx.AsyncClient", return_value=client):
            await GoogleCSESearch(api_key="k:cx").search("python", date_from="7d")
        call_str = str(client.get.call_args)
        assert "dateRestrict" in call_str

    async def test_http_error_raises_search_error(self) -> None:
        client = _make_client({}, status_code=429)
        with patch("anythink.search.google_cse.httpx.AsyncClient", return_value=client):
            with pytest.raises(SearchError, match="429"):
                await GoogleCSESearch(api_key="k:cx").search("test")

    async def test_network_error_raises_search_error(self) -> None:
        import httpx

        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.RequestError("net"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("anythink.search.google_cse.httpx.AsyncClient", return_value=client):
            with pytest.raises(SearchError, match="net"):
                await GoogleCSESearch(api_key="k:cx").search("test")

    async def test_empty_items_returns_empty(self) -> None:
        client = _make_client({"items": []})
        with patch("anythink.search.google_cse.httpx.AsyncClient", return_value=client):
            results = await GoogleCSESearch(api_key="k:cx").search("test")
        assert results == []

    async def test_missing_items_key_returns_empty(self) -> None:
        client = _make_client({})
        with patch("anythink.search.google_cse.httpx.AsyncClient", return_value=client):
            results = await GoogleCSESearch(api_key="k:cx").search("test")
        assert results == []

    async def test_include_domains_in_request(self) -> None:
        client = _make_client({"items": []})
        with patch("anythink.search.google_cse.httpx.AsyncClient", return_value=client):
            await GoogleCSESearch(api_key="k:cx").search(
                "python", include_domains=["docs.python.org"]
            )
        call_str = str(client.get.call_args)
        assert "siteSearch" in call_str

    async def test_exclude_domains_in_request(self) -> None:
        client = _make_client({"items": []})
        with patch("anythink.search.google_cse.httpx.AsyncClient", return_value=client):
            await GoogleCSESearch(api_key="k:cx").search(
                "python", exclude_domains=["w3schools.com"]
            )
        call_str = str(client.get.call_args)
        assert "siteSearch" in call_str

    async def test_safe_search_in_request(self) -> None:
        client = _make_client({"items": []})
        with patch("anythink.search.google_cse.httpx.AsyncClient", return_value=client):
            await GoogleCSESearch(api_key="k:cx").search("python", safe_search="strict")
        call_str = str(client.get.call_args)
        assert "safe" in call_str

    async def test_published_date_extracted_from_metatags(self) -> None:
        data = {
            "items": [
                {
                    "title": "Python",
                    "link": "https://python.org",
                    "snippet": "s",
                    "pagemap": {
                        "metatags": [{"article:published_time": "2025-06-01T10:00:00Z"}]
                    },
                }
            ]
        }
        client = _make_client(data)
        with patch("anythink.search.google_cse.httpx.AsyncClient", return_value=client):
            results = await GoogleCSESearch(api_key="k:cx").search("test")
        assert results[0].published_date == "2025-06-01"
