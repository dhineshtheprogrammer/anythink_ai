"""Google Custom Search Engine (CSE) backend."""

from __future__ import annotations

import httpx

from anythink.exceptions import SearchError
from anythink.search.base import BaseSearchBackend, SearchResult

_BASE_URL = "https://www.googleapis.com/customsearch/v1"

# dateRestrict values approximate for common freshness shorthand
_FRESHNESS_MAP = {"24h": "d1", "7d": "d7", "30d": "m1", "3m": "m3"}


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


class GoogleCSESearch(BaseSearchBackend):
    """Web search via Google Custom Search JSON API.

    Requires a Google API key and a Custom Search Engine ID.
    Key setup:
      anythink keys add google_cse    (format: "<api_key>:<cx_id>")
    """

    name = "google_cse"
    display_name = "Google"
    supports_freshness = True
    supports_safe_search = True

    def is_available(self) -> bool:
        return bool(self._api_key and ":" in (self._api_key or ""))

    def _parse_key(self) -> tuple[str, str]:
        """Split stored key into (api_key, cx_id)."""
        if not self._api_key or ":" not in self._api_key:
            raise SearchError(
                "Google CSE key malformed (expected 'api_key:cx_id').",
                user_message="Google CSE key must be 'api_key:cx_id'. Run: anythink keys add google_cse",
            )
        api_key, cx = self._api_key.split(":", 1)
        return api_key, cx

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
        api_key, cx = self._parse_key()

        params: dict[str, str | int] = {
            "q": query,
            "key": api_key,
            "cx": cx,
            "num": min(max_results, 10),  # CSE max is 10 per request
        }
        if date_from:
            params["dateRestrict"] = _FRESHNESS_MAP.get(date_from, "d7")
        if safe_search:
            params["safe"] = "active" if safe_search != "off" else "off"
        if include_domains:
            params["siteSearch"] = include_domains[0]
            params["siteSearchFilter"] = "i"
        if exclude_domains:
            params["siteSearch"] = exclude_domains[0]
            params["siteSearchFilter"] = "e"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(_BASE_URL, params=params)
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
        except httpx.HTTPStatusError as exc:
            raise SearchError(
                f"Google CSE HTTP error: {exc.response.status_code}",
                user_message=f"Google search failed (HTTP {exc.response.status_code}).",
            ) from exc
        except httpx.RequestError as exc:
            raise SearchError(
                f"Google CSE request error: {exc}",
                user_message="Google search failed: network error.",
            ) from exc

        results: list[SearchResult] = []
        items = data.get("items", [])
        if isinstance(items, list):
            for item in items[:max_results]:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("link", ""))
                pagemap = item.get("pagemap", {})
                pub_date: str | None = None
                if isinstance(pagemap, dict):
                    metatags = pagemap.get("metatags", [{}])
                    if isinstance(metatags, list) and metatags:
                        mt = metatags[0]
                        if isinstance(mt, dict):
                            pub_date = str(mt.get("article:published_time", ""))[:10] or None
                results.append(
                    SearchResult(
                        title=str(item.get("title", "")),
                        url=url,
                        snippet=str(item.get("snippet", "")),
                        published_date=pub_date,
                        source_domain=_domain_from_url(url),
                    )
                )
        return results
