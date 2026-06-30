"""Tests for SearchOrchestrator."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from anythink.search.base import SearchResult
from anythink.search.cache import SearchCache
from anythink.search.orchestrator import OrchestratorResult, SearchOrchestrator
from anythink.search.registry import SearchRegistry


def _make_result(url: str, title: str = "T") -> SearchResult:
    return SearchResult(title=title, url=url, snippet="snippet")


def _make_backend(name: str, results: list[SearchResult], available: bool = True) -> MagicMock:
    backend = MagicMock()
    backend.name = name
    backend.display_name = name.title()
    backend.is_available.return_value = available
    backend.supports_news = name in ("newsapi", "bing")
    backend.search = AsyncMock(return_value=results)
    return backend


def _make_registry(*backends: MagicMock) -> SearchRegistry:
    registry = MagicMock(spec=SearchRegistry)
    backend_map = {b.name: b for b in backends}

    def _get(name: str) -> MagicMock | None:
        return backend_map.get(name)

    def _get_available(preferred: str | None = None) -> MagicMock | None:
        if preferred and preferred in backend_map:
            b = backend_map[preferred]
            if b.is_available():
                return b
        return next((b for b in backends if b.is_available()), None)

    def _names() -> list[str]:
        return list(backend_map)

    registry.get = MagicMock(side_effect=_get)
    registry.get_available = MagicMock(side_effect=_get_available)
    registry.names = MagicMock(side_effect=_names)
    return registry


class TestOrchestratorResult:
    def test_default_empty(self) -> None:
        r = OrchestratorResult()
        assert r.results == []
        assert r.queries == []
        assert r.error is None


class TestSearchOrchestrator:
    async def test_run_single_query(self) -> None:
        results = [_make_result("http://a.com"), _make_result("http://b.com")]
        backend = _make_backend("duckduckgo", results)
        registry = _make_registry(backend)
        cache = SearchCache()
        orch = SearchOrchestrator(registry, cache, preferred_backend="duckduckgo")

        result = await orch.run(["python asyncio"])
        assert len(result.results) == 2
        assert result.backend_used == "Duckduckgo"
        assert result.queries == ["python asyncio"]
        assert result.from_cache == [False]

    async def test_run_deduplicates_urls(self) -> None:
        dup = _make_result("http://same.com")
        backend = _make_backend("ddg", [dup, dup, _make_result("http://other.com")])
        registry = _make_registry(backend)
        orch = SearchOrchestrator(registry, SearchCache())

        result = await orch.run(["test"])
        urls = [r.url for r in result.results]
        assert len(urls) == len(set(urls))

    async def test_run_multi_query(self) -> None:
        results = [_make_result("http://a.com")]
        backend = _make_backend("ddg", results)
        registry = _make_registry(backend)
        orch = SearchOrchestrator(registry, SearchCache(), max_searches=5)

        result = await orch.run(["q1", "q2", "q3"])
        assert len(result.queries) == 3
        assert backend.search.call_count == 3

    async def test_run_respects_max_searches(self) -> None:
        backend = _make_backend("ddg", [_make_result("http://a.com")])
        registry = _make_registry(backend)
        orch = SearchOrchestrator(registry, SearchCache(), max_searches=2)

        result = await orch.run(["q1", "q2", "q3", "q4"])
        assert len(result.queries) == 2
        assert backend.search.call_count == 2

    async def test_run_returns_cache_hit(self) -> None:
        cached = [_make_result("http://cached.com")]
        backend = _make_backend("ddg", [_make_result("http://new.com")])
        registry = _make_registry(backend)
        cache = SearchCache()
        cache.put("python async", "ddg", cached)

        orch = SearchOrchestrator(registry, cache, preferred_backend="ddg")
        result = await orch.run(["python async"])
        assert result.from_cache == [True]
        assert result.results[0].url == "http://cached.com"
        backend.search.assert_not_called()

    async def test_run_no_backend_returns_error(self) -> None:
        registry = MagicMock(spec=SearchRegistry)
        registry.get_available = MagicMock(return_value=None)
        orch = SearchOrchestrator(registry, SearchCache())

        result = await orch.run(["test"])
        assert result.error is not None
        assert result.results == []

    async def test_news_mode_picks_newsapi(self) -> None:
        news_results = [_make_result("http://news.com")]
        newsapi = _make_backend("newsapi", news_results)
        ddg = _make_backend("duckduckgo", [_make_result("http://ddg.com")])
        registry = _make_registry(newsapi, ddg)
        orch = SearchOrchestrator(registry, SearchCache())

        result = await orch.run(["AI news"], news_mode=True)
        assert result.backend_used == "Newsapi"
        assert result.results[0].url == "http://news.com"

    async def test_news_mode_no_news_backend_returns_error(self) -> None:
        ddg = _make_backend("duckduckgo", [_make_result("http://ddg.com")])
        ddg.supports_news = False
        registry = _make_registry(ddg)

        # Override registry.get to return None for news backends
        def _get(name: str) -> MagicMock | None:
            return None if name in ("newsapi", "bing") else (ddg if name == "duckduckgo" else None)

        registry.get = MagicMock(side_effect=_get)
        registry.names = MagicMock(return_value=["duckduckgo"])

        orch = SearchOrchestrator(registry, SearchCache())
        result = await orch.run(["news"], news_mode=True)
        assert result.error is not None

    async def test_progress_cb_called(self) -> None:
        backend = _make_backend("ddg", [_make_result("http://a.com")])
        registry = _make_registry(backend)
        messages: list[str] = []
        orch = SearchOrchestrator(registry, SearchCache(), preferred_backend="ddg")

        await orch.run(["test"], progress_cb=messages.append)
        assert len(messages) > 0

    async def test_backend_error_skips_query(self) -> None:
        from anythink.exceptions import SearchError

        backend = _make_backend("ddg", [])
        backend.search = AsyncMock(side_effect=SearchError("network fail"))
        registry = _make_registry(backend)
        orch = SearchOrchestrator(registry, SearchCache(), preferred_backend="ddg")

        result = await orch.run(["q1", "q2"])
        # Errors are swallowed, result is empty but no exception raised
        assert result.results == []
        assert result.error is None

    async def test_post_filter_exclude_domains(self) -> None:
        results = [
            _make_result("http://good.com"),
            _make_result("http://bad.com"),
        ]
        results[0].source_domain = "good.com"
        results[1].source_domain = "bad.com"
        backend = _make_backend("ddg", results)
        registry = _make_registry(backend)
        orch = SearchOrchestrator(registry, SearchCache(), preferred_backend="ddg")

        result = await orch.run(["test"], exclude_domains=["bad.com"])
        assert all("bad.com" not in r.url for r in result.results)

    async def test_elapsed_time_recorded(self) -> None:
        backend = _make_backend("ddg", [_make_result("http://a.com")])
        registry = _make_registry(backend)
        orch = SearchOrchestrator(registry, SearchCache())

        result = await orch.run(["test"])
        assert result.elapsed_s >= 0.0

    async def test_no_backend_progress_cb_called(self) -> None:
        registry = MagicMock(spec=SearchRegistry)
        registry.get_available = MagicMock(return_value=None)
        messages: list[str] = []
        orch = SearchOrchestrator(registry, SearchCache())

        result = await orch.run(["test"], progress_cb=messages.append)
        assert result.error is not None
        assert len(messages) > 0

    async def test_cache_hit_progress_cb_called(self) -> None:
        cached = [_make_result("http://cached.com")]
        backend = _make_backend("ddg", [])
        registry = _make_registry(backend)
        cache = SearchCache()
        cache.put("python", "ddg", cached)

        messages: list[str] = []
        orch = SearchOrchestrator(registry, cache, preferred_backend="ddg")
        await orch.run(["python"], progress_cb=messages.append)
        assert any("Cache hit" in m for m in messages)

    async def test_error_progress_cb_called(self) -> None:
        from anythink.exceptions import SearchError

        backend = _make_backend("ddg", [])
        backend.search = AsyncMock(side_effect=SearchError("oops"))
        registry = _make_registry(backend)
        messages: list[str] = []
        orch = SearchOrchestrator(registry, SearchCache(), preferred_backend="ddg")

        await orch.run(["test"], progress_cb=messages.append)
        assert any("error" in m.lower() for m in messages)

    async def test_post_filter_include_domains(self) -> None:
        results = [
            _make_result("http://good.com"),
            _make_result("http://bad.com"),
        ]
        results[0].source_domain = "good.com"
        results[1].source_domain = "bad.com"
        backend = _make_backend("ddg", results)
        registry = _make_registry(backend)
        orch = SearchOrchestrator(registry, SearchCache(), preferred_backend="ddg")

        result = await orch.run(["test"], include_domains=["good.com"])
        assert len(result.results) == 1
        assert result.results[0].source_domain == "good.com"

    async def test_news_mode_fallback_to_generic_news_capable_backend(self) -> None:
        """Line 133: fallback when no _NEWS_BACKENDS available but another backend supports news."""
        news_results = [_make_result("http://custom-news.com")]
        custom = _make_backend("custom_news", news_results)
        custom.supports_news = True

        registry = MagicMock(spec=SearchRegistry)

        def _get(name: str) -> MagicMock | None:
            if name in ("newsapi", "bing"):
                return None  # primary news backends unavailable
            return custom if name == "custom_news" else None

        registry.get = MagicMock(side_effect=_get)
        registry.names = MagicMock(return_value=["custom_news"])
        orch = SearchOrchestrator(registry, SearchCache())
        result = await orch.run(["breaking news"], news_mode=True)
        assert result.results[0].url == "http://custom-news.com"

    async def test_news_mode_fallback_to_bing(self) -> None:
        bing_results = [_make_result("http://bing-news.com")]
        bing = _make_backend("bing", bing_results)
        bing.supports_news = True
        ddg = _make_backend("duckduckgo", [])

        registry = _make_registry(bing, ddg)

        def _get(name: str) -> MagicMock | None:
            return (
                None
                if name == "newsapi"
                else (bing if name == "bing" else ddg if name == "duckduckgo" else None)
            )

        registry.get = MagicMock(side_effect=_get)
        orch = SearchOrchestrator(registry, SearchCache())
        result = await orch.run(["breaking news"], news_mode=True)
        assert result.backend_used == "Bing"
