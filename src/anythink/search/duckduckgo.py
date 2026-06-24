"""DuckDuckGo search backend (free, no API key required)."""

from __future__ import annotations

import asyncio

from anythink.exceptions import SearchError
from anythink.search.base import BaseSearchBackend, SearchResult

_INSTALL_HINT = "pip install anythink[search]"
_TIMEOUT_S = 10.0
_MAX_RETRIES = 2
_RETRY_DELAY_S = 1.5


class DuckDuckGoSearch(BaseSearchBackend):
    """Web search via DuckDuckGo.

    Requires: pip install anythink[search]  (installs duckduckgo-search)
    """

    name = "duckduckgo"
    display_name = "DuckDuckGo"

    def is_available(self) -> bool:
        try:
            import duckduckgo_search  # noqa: F401

            return True
        except ImportError:
            return False

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self.is_available():
            raise SearchError(
                f"duckduckgo-search not installed. Install with: {_INSTALL_HINT}",
                user_message=f"DuckDuckGo search requires: {_INSTALL_HINT}",
            )
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self._sync_search, query, max_results),
                    timeout=_TIMEOUT_S,
                )
            except SearchError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY_S * (attempt + 1))
        assert last_exc is not None
        is_timeout = isinstance(last_exc, TimeoutError)
        raise SearchError(
            f"DuckDuckGo search {'timed out' if is_timeout else f'failed after {_MAX_RETRIES + 1} attempts'}: {last_exc}",
            user_message=(
                "Web search timed out. DuckDuckGo may be rate-limiting requests."
                if is_timeout
                else f"Web search failed after retries: {last_exc}"
            ),
        ) from last_exc

    def _sync_search(self, query: str, max_results: int) -> list[SearchResult]:
        from duckduckgo_search import DDGS

        results: list[SearchResult] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(
                    SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                    )
                )
        return results
