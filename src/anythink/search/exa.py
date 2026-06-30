"""Exa (formerly Metaphor) semantic search backend."""

from __future__ import annotations

from anythink.exceptions import SearchError
from anythink.search.base import BaseSearchBackend, SearchResult

_INSTALL_HINT = "pip install anythink[exa]"


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


class ExaSearch(BaseSearchBackend):
    """Semantic web search via Exa.

    Requires: pip install anythink[exa]  (installs exa-py)
    Key setup: anythink keys add exa
    """

    name = "exa"
    display_name = "Exa"
    supports_freshness = True

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import exa_py  # noqa: F401

            return True
        except ImportError:
            return False

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
                "Exa API key not configured.",
                user_message="Exa key not set. Add it with: anythink keys add exa",
            )
        try:
            from exa_py import Exa
        except ImportError as exc:
            raise SearchError(
                f"exa-py not installed. Install with: {_INSTALL_HINT}",
                user_message=f"Exa search requires: {_INSTALL_HINT}",
            ) from exc

        import asyncio

        kwargs: dict[str, object] = {
            "num_results": max_results,
            "use_autoprompt": True,
            "text": True,
        }
        if date_from and len(date_from) == 10:
            kwargs["start_published_date"] = date_from
        if date_to and len(date_to) == 10:
            kwargs["end_published_date"] = date_to
        if include_domains:
            kwargs["include_domains"] = include_domains
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains

        def _sync_search() -> list[SearchResult]:
            client = Exa(api_key=self._api_key)
            response = client.search_and_contents(query, **kwargs)
            out: list[SearchResult] = []
            for r in response.results:
                pub = getattr(r, "published_date", None)
                out.append(
                    SearchResult(
                        title=getattr(r, "title", "") or "",
                        url=getattr(r, "url", "") or "",
                        snippet=_first_chars(getattr(r, "text", "") or "", 500),
                        published_date=str(pub)[:10] if pub else None,
                        source_domain=_domain_from_url(getattr(r, "url", "") or ""),
                    )
                )
            return out

        try:
            return await asyncio.wait_for(asyncio.to_thread(_sync_search), timeout=15.0)
        except TimeoutError as exc:
            raise SearchError(
                "Exa search timed out.", user_message="Exa search timed out."
            ) from exc
        except Exception as exc:
            raise SearchError(
                f"Exa search failed: {exc}", user_message=f"Exa search failed: {exc}"
            ) from exc


def _first_chars(text: str, n: int) -> str:
    return text[:n] + ("…" if len(text) > n else "")
