"""SerpAPI search backend (requires SerpAPI key)."""

from __future__ import annotations

import httpx

from anythink.exceptions import SearchError
from anythink.search.base import BaseSearchBackend, SearchResult

_BASE_URL = "https://serpapi.com/search.json"

_FRESHNESS_MAP = {"24h": "qdr:d", "7d": "qdr:w", "30d": "qdr:m", "3m": "qdr:m"}


def _freshness_to_tbs(date_from: str) -> str:
    return _FRESHNESS_MAP.get(date_from, "qdr:w")


def _domain_from_url(url: str) -> str | None:
    try:
        if not url:
            return None
        after_scheme = url.split("://", 1)[1] if "://" in url else url
        host = after_scheme.split("/")[0]
        if not host:
            return None
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return None


class SerpAPISearch(BaseSearchBackend):
    """Web search via SerpAPI.

    Requires a SerpAPI key: https://serpapi.com/
    """

    name = "serpapi"
    display_name = "SerpAPI"
    supports_freshness = True
    supports_safe_search = True

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def search(
        self,
        query: str,
        max_results: int = 5,
        date_from: str | None = None,
        date_to: str | None = None,
        safe_search: str | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[SearchResult]:
        if not self._api_key:
            raise SearchError(
                "SerpAPI key not configured.",
                user_message="SerpAPI key not set. Add it with: anythink keys add serpapi",
            )
        params: dict[str, str | int] = {
            "q": query,
            "api_key": self._api_key,
            "num": max_results,
            "engine": "google",
        }
        if date_from:
            params["tbs"] = _freshness_to_tbs(date_from)
        if safe_search and safe_search != "off":
            params["safe"] = "active"
        if include_domains:
            params["as_sitesearch"] = include_domains[0]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(_BASE_URL, params=params)
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
                    url = str(r.get("link", ""))
                    results.append(
                        SearchResult(
                            title=str(r.get("title", "")),
                            url=url,
                            snippet=str(r.get("snippet", "")),
                            source_domain=_domain_from_url(url),
                        )
                    )
        return results
