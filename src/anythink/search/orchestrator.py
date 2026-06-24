"""Search orchestrator: drives the multi-query autonomous search loop."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from anythink.search.base import BaseSearchBackend, SearchResult
from anythink.search.cache import SearchCache
from anythink.search.registry import SearchRegistry

_NEWS_BACKENDS = ("newsapi", "bing")


@dataclass
class OrchestratorResult:
    """Aggregated result from one or more sequential searches."""

    queries: list[str] = field(default_factory=list)
    results: list[SearchResult] = field(default_factory=list)
    from_cache: list[bool] = field(default_factory=list)
    backend_used: str = ""
    elapsed_s: float = 0.0
    error: str | None = None


class SearchOrchestrator:
    """Drive up to *max_searches* sequential searches for a single response turn.

    Handles backend selection for news vs general mode, result caching,
    domain post-filtering, deduplication, and live progress callbacks.
    """

    def __init__(
        self,
        registry: SearchRegistry,
        cache: SearchCache,
        *,
        preferred_backend: str = "duckduckgo",
        max_searches: int = 5,
    ) -> None:
        self._registry = registry
        self._cache = cache
        self._preferred = preferred_backend
        self._max_searches = max_searches

    async def run(
        self,
        queries: list[str],
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        safe_search: str = "moderate",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        news_mode: bool = False,
        progress_cb: Callable[[str], None] | None = None,
    ) -> OrchestratorResult:
        """Execute up to *max_searches* queries sequentially and return unified results."""
        result = OrchestratorResult()
        t0 = time.monotonic()

        backend = self._pick_backend(news_mode)
        if backend is None:
            mode_label = "news" if news_mode else "web"
            msg = f"No {mode_label} search backend available."
            result.error = msg
            if progress_cb:
                progress_cb(msg)
            return result

        result.backend_used = backend.display_name
        all_results: list[SearchResult] = []

        for i, query in enumerate(queries[: self._max_searches]):
            result.queries.append(query)
            cache_key = backend.name

            # Check cache
            cached = self._cache.get(query, cache_key)
            if cached is not None:
                result.from_cache.append(True)
                if progress_cb:
                    progress_cb(f"Cache hit for: {query!r}")
                all_results.extend(cached)
                continue

            result.from_cache.append(False)
            if progress_cb:
                label = "Re-searching" if i > 0 else "Searching"
                progress_cb(f"{label} {backend.display_name}: {query!r}…")

            try:
                new_results = await backend.search(
                    query,
                    max_results=10,
                    date_from=date_from,
                    date_to=date_to,
                    safe_search=safe_search,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                )
            except Exception as exc:
                if progress_cb:
                    progress_cb(f"Search error: {exc}")
                continue

            new_results = self._post_filter(new_results, include_domains, exclude_domains)
            self._cache.put(query, cache_key, new_results)
            all_results.extend(new_results)

            if progress_cb:
                progress_cb(
                    f"Found {len(new_results)} results ({backend.display_name})"
                )

        result.results = self._deduplicate(all_results)
        result.elapsed_s = time.monotonic() - t0
        return result

    def _pick_backend(self, news_mode: bool) -> BaseSearchBackend | None:
        """Select the appropriate backend based on mode."""
        if news_mode:
            for name in _NEWS_BACKENDS:
                b = self._registry.get(name)
                if b is not None and b.is_available():
                    return b
            # Fall back to any news-capable backend
            for name in self._registry.names():
                b = self._registry.get(name)
                if b is not None and b.is_available() and b.supports_news:
                    return b
            return None
        return self._registry.get_available(self._preferred)

    def _post_filter(
        self,
        results: list[SearchResult],
        include_domains: list[str] | None,
        exclude_domains: list[str] | None,
    ) -> list[SearchResult]:
        """Client-side domain filtering after results are returned."""
        if not include_domains and not exclude_domains:
            return results
        filtered: list[SearchResult] = []
        for r in results:
            domain = r.source_domain or ""
            if exclude_domains and any(d in domain for d in exclude_domains):
                continue
            if include_domains and not any(d in domain for d in include_domains):
                continue
            filtered.append(r)
        return filtered

    def _deduplicate(self, results: list[SearchResult]) -> list[SearchResult]:
        """Remove duplicate URLs, preserving order of first appearance."""
        seen: set[str] = set()
        out: list[SearchResult] = []
        for r in results:
            if r.url not in seen:
                seen.add(r.url)
                out.append(r)
        return out
