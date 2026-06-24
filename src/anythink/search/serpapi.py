"""SerpAPI search backend (requires SerpAPI key)."""

from __future__ import annotations

from anythink.exceptions import SearchError
from anythink.search.base import BaseSearchBackend, SearchResult

_BASE_URL = "https://serpapi.com/search.json"


class SerpAPISearch(BaseSearchBackend):
    """Web search via SerpAPI.

    Requires a SerpAPI key: https://serpapi.com/
    """

    name = "serpapi"
    display_name = "SerpAPI"

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self._api_key:
            raise SearchError(
                "SerpAPI key not configured.",
                user_message="SerpAPI key not set. Add it with: anythink keys add serpapi",
            )
        try:
            import httpx
        except ImportError as exc:
            raise SearchError(
                "httpx not installed.",
                user_message="httpx is required for SerpAPI search. Run: pip install httpx",
            ) from exc
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    _BASE_URL,
                    params={
                        "q": query,
                        "api_key": self._api_key,
                        "num": max_results,
                        "engine": "google",
                    },
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
        except httpx.HTTPStatusError as exc:
            raise SearchError(
                f"SerpAPI HTTP error: {exc.response.status_code}",
                user_message=f"Web search failed (HTTP {exc.response.status_code}).",
            ) from exc
        except httpx.RequestError as exc:
            raise SearchError(
                f"SerpAPI request error: {exc}",
                user_message="Web search failed: network error.",
            ) from exc

        results: list[SearchResult] = []
        organic = data.get("organic_results", [])
        if isinstance(organic, list):
            for r in organic[:max_results]:
                if isinstance(r, dict):
                    results.append(
                        SearchResult(
                            title=str(r.get("title", "")),
                            url=str(r.get("link", "")),
                            snippet=str(r.get("snippet", "")),
                        )
                    )
        return results
