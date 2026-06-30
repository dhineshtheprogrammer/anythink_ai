"""Bing Web Search API v7 backend (general + news mode)."""

from __future__ import annotations

import httpx

from anythink.exceptions import SearchError
from anythink.search.base import BaseSearchBackend, SearchResult

_WEB_URL = "https://api.bing.microsoft.com/v7.0/search"
_NEWS_URL = "https://api.bing.microsoft.com/v7.0/news/search"

_FRESHNESS_MAP = {"24h": "Day", "7d": "Week", "30d": "Month", "3m": "Month"}
_SAFE_MAP = {"strict": "Strict", "moderate": "Moderate", "off": "Off"}


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


class BingSearch(BaseSearchBackend):
    """Web search via Microsoft Bing Search API v7.

    Key setup: anythink keys add bing
    """

    name = "bing"
    display_name = "Bing"
    supports_freshness = True
    supports_safe_search = True
    supports_news = True

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
        *,
        news_mode: bool = False,
    ) -> list[SearchResult]:
        if not self._api_key:
            raise SearchError(
                "Bing API key not configured.",
                user_message="Bing key not set. Add it with: anythink keys add bing",
            )
        q = query
        if include_domains:
            q += " site:" + " OR site:".join(include_domains)
        if exclude_domains:
            q += " " + " ".join(f"-site:{d}" for d in exclude_domains)

        params: dict[str, str | int] = {"q": q, "count": max_results}
        if date_from:
            params["freshness"] = _FRESHNESS_MAP.get(date_from, "Week")
        if safe_search:
            params["safeSearch"] = _SAFE_MAP.get(safe_search, "Moderate")

        url = _NEWS_URL if news_mode else _WEB_URL
        headers = {"Ocp-Apim-Subscription-Key": self._api_key}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
        except httpx.HTTPStatusError as exc:
            raise SearchError(
                f"Bing HTTP error: {exc.response.status_code}",
                user_message=f"Bing search failed (HTTP {exc.response.status_code}).",
            ) from exc
        except httpx.RequestError as exc:
            raise SearchError(
                f"Bing request error: {exc}", user_message="Bing search failed: network error."
            ) from exc

        results: list[SearchResult] = []
        if news_mode:
            items = data.get("value", [])
        else:
            web_pages = data.get("webPages", {})
            items = web_pages.get("value", []) if isinstance(web_pages, dict) else []

        if isinstance(items, list):
            for item in items[:max_results]:
                if not isinstance(item, dict):
                    continue
                result_url = str(item.get("url", ""))
                pub_date: str | None = None
                if news_mode:
                    raw_date = item.get("datePublished", "")
                    pub_date = str(raw_date)[:10] if raw_date else None
                results.append(
                    SearchResult(
                        title=str(item.get("name", "")),
                        url=result_url,
                        snippet=str(item.get("snippet", item.get("description", ""))),
                        published_date=pub_date,
                        source_domain=_domain_from_url(result_url),
                    )
                )
        return results
