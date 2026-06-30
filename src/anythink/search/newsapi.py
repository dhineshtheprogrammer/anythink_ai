"""NewsAPI.org search backend (news articles only)."""

from __future__ import annotations

import httpx

from anythink.exceptions import SearchError
from anythink.search.base import BaseSearchBackend, SearchResult

_EVERYTHING_URL = "https://newsapi.org/v2/everything"
_HEADLINES_URL = "https://newsapi.org/v2/top-headlines"


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


class NewsAPISearch(BaseSearchBackend):
    """News article search via NewsAPI.org.

    Key setup: anythink keys add newsapi
    """

    name = "newsapi"
    display_name = "NewsAPI"
    supports_freshness = True
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
    ) -> list[SearchResult]:
        if not self._api_key:
            raise SearchError(
                "NewsAPI key not configured.",
                user_message="NewsAPI key not set. Add it with: anythink keys add newsapi",
            )
        params: dict[str, str | int] = {
            "q": query,
            "pageSize": min(max_results, 100),
            "apiKey": self._api_key,
            "language": "en",
        }
        if date_from and len(date_from) == 10:
            # Accept ISO dates (YYYY-MM-DD) directly; skip shorthand periods
            params["from"] = date_from
        if date_to and len(date_to) == 10:
            params["to"] = date_to
        if include_domains:
            params["domains"] = ",".join(include_domains)
        if exclude_domains:
            params["excludeDomains"] = ",".join(exclude_domains)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(_EVERYTHING_URL, params=params)
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
        except httpx.HTTPStatusError as exc:
            raise SearchError(
                f"NewsAPI HTTP error: {exc.response.status_code}",
                user_message=f"News search failed (HTTP {exc.response.status_code}).",
            ) from exc
        except httpx.RequestError as exc:
            raise SearchError(
                f"NewsAPI request error: {exc}", user_message="News search failed: network error."
            ) from exc

        results: list[SearchResult] = []
        articles = data.get("articles", [])
        if isinstance(articles, list):
            for art in articles[:max_results]:
                if not isinstance(art, dict):
                    continue
                url = str(art.get("url", ""))
                raw_date = art.get("publishedAt", "")
                pub_date = str(raw_date)[:10] if raw_date else None
                source = art.get("source", {})
                source_name = str(source.get("name", "")) if isinstance(source, dict) else ""
                results.append(
                    SearchResult(
                        title=str(art.get("title", "")),
                        url=url,
                        snippet=str(art.get("description", art.get("content", "")) or ""),
                        published_date=pub_date,
                        source_domain=source_name or _domain_from_url(url),
                    )
                )
        return results
