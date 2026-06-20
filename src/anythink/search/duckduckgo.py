"""DuckDuckGo search backend (free, no API key required)."""

from __future__ import annotations

import asyncio

from anythink.exceptions import SearchError
from anythink.search.base import BaseSearchBackend, SearchResult

_INSTALL_HINT = "pip install anythink[search]"


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
        try:
            return await asyncio.to_thread(self._sync_search, query, max_results)
        except SearchError:
            raise
        except Exception as exc:
            raise SearchError(
                f"DuckDuckGo search failed: {exc}",
                user_message=f"Web search failed: {exc}",
            ) from exc

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
