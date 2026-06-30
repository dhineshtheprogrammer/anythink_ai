"""Tests for ExaSearch backend."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.exceptions import SearchError
from anythink.search.exa import ExaSearch, _domain_from_url, _first_chars


class TestDomainFromUrl:
    def test_empty_url_returns_none(self) -> None:
        assert _domain_from_url("") is None

    def test_strips_www(self) -> None:
        assert _domain_from_url("https://www.exa.ai/") == "exa.ai"

    def test_no_www(self) -> None:
        assert _domain_from_url("https://exa.ai") == "exa.ai"


class TestFirstChars:
    def test_short_string_unchanged(self) -> None:
        assert _first_chars("hello", 10) == "hello"

    def test_long_string_truncated(self) -> None:
        result = _first_chars("a" * 600, 500)
        assert result.endswith("…")
        assert len(result) == 501


class TestExaSearch:
    def test_name(self) -> None:
        assert ExaSearch.name == "exa"

    def test_display_name(self) -> None:
        assert ExaSearch.display_name == "Exa"

    def test_supports_freshness(self) -> None:
        assert ExaSearch.supports_freshness is True

    def test_not_available_without_key(self) -> None:
        assert ExaSearch().is_available() is False

    def test_not_available_when_sdk_missing(self) -> None:
        with patch.dict(sys.modules, {"exa_py": None}):
            assert ExaSearch(api_key="key").is_available() is False

    def test_available_with_key_and_sdk(self) -> None:
        mock_exa = MagicMock()
        with patch.dict(sys.modules, {"exa_py": mock_exa}):
            assert ExaSearch(api_key="key").is_available() is True

    async def test_raises_without_key(self) -> None:
        with pytest.raises(SearchError, match="Exa"):
            await ExaSearch().search("test")

    async def test_raises_when_sdk_missing(self) -> None:
        with patch.dict(sys.modules, {"exa_py": None}):
            with pytest.raises(SearchError, match="exa-py"):
                await ExaSearch(api_key="key").search("test")

    async def test_search_returns_results(self) -> None:
        mock_result = MagicMock()
        mock_result.title = "Exa Result"
        mock_result.url = "https://example.com"
        mock_result.text = "Some content here"
        mock_result.published_date = None

        mock_response = MagicMock()
        mock_response.results = [mock_result]

        mock_client = MagicMock()
        mock_client.search_and_contents = MagicMock(return_value=mock_response)

        mock_exa_module = MagicMock()
        mock_exa_module.Exa = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"exa_py": mock_exa_module}):
            results = await ExaSearch(api_key="key").search("test")

        assert len(results) == 1
        assert results[0].title == "Exa Result"
        assert results[0].url == "https://example.com"
        assert "Some content" in results[0].snippet

    async def test_search_with_date_from(self) -> None:
        mock_result = MagicMock()
        mock_result.title = "T"
        mock_result.url = "http://u.com"
        mock_result.text = "text"
        mock_result.published_date = "2025-01-01"

        mock_response = MagicMock()
        mock_response.results = [mock_result]

        mock_client = MagicMock()
        mock_client.search_and_contents = MagicMock(return_value=mock_response)

        mock_exa_module = MagicMock()
        mock_exa_module.Exa = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"exa_py": mock_exa_module}):
            results = await ExaSearch(api_key="key").search(
                "test", date_from="2025-01-01"
            )

        assert results[0].published_date == "2025-01-01"
        call_kwargs = mock_client.search_and_contents.call_args[1]
        assert call_kwargs.get("start_published_date") == "2025-01-01"

    async def test_timeout_raises_search_error(self) -> None:
        import asyncio

        mock_exa_module = MagicMock()

        def _slow_init(*a: object, **kw: object) -> MagicMock:
            raise TimeoutError("timed out")

        mock_exa_module.Exa = MagicMock(side_effect=_slow_init)

        with patch.dict(sys.modules, {"exa_py": mock_exa_module}):
            # Force timeout by patching asyncio.wait_for
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                with pytest.raises(SearchError, match="timed out"):
                    await ExaSearch(api_key="key").search("test")

    async def test_general_error_raises_search_error(self) -> None:
        mock_exa_module = MagicMock()
        mock_client = MagicMock()
        mock_client.search_and_contents = MagicMock(side_effect=RuntimeError("API error"))
        mock_exa_module.Exa = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"exa_py": mock_exa_module}):
            with pytest.raises(SearchError, match="API error"):
                await ExaSearch(api_key="key").search("test")

    async def test_search_with_date_to_and_domains(self) -> None:
        mock_result = MagicMock()
        mock_result.title = "T"
        mock_result.url = "https://exa.ai/result"
        mock_result.text = "text"
        mock_result.published_date = "2025-06-01"

        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_client = MagicMock()
        mock_client.search_and_contents = MagicMock(return_value=mock_response)
        mock_exa_module = MagicMock()
        mock_exa_module.Exa = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"exa_py": mock_exa_module}):
            results = await ExaSearch(api_key="key").search(
                "test",
                date_from="2025-01-01",
                date_to="2025-12-31",
                include_domains=["exa.ai"],
                exclude_domains=["spam.com"],
            )

        call_kwargs = mock_client.search_and_contents.call_args[1]
        assert call_kwargs.get("end_published_date") == "2025-12-31"
        assert call_kwargs.get("include_domains") == ["exa.ai"]
        assert call_kwargs.get("exclude_domains") == ["spam.com"]
        assert results[0].source_domain == "exa.ai"
