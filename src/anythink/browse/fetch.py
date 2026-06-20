"""Agentic web browsing: two-tier snippet search + full-page fetch."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from anythink.exceptions import BrowseError
from anythink.tools.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from anythink.search.registry import SearchRegistry

_MAX_PAGE_CHARS = 8_000


def _strip_html(html: str) -> str:
    """Minimal HTML→text: strip tags, collapse whitespace, unescape entities."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s{3,}", "\n\n", text)
    return text.strip()


async def _http_get(url: str) -> str:
    """Fetch *url* via httpx and return plain text (max ``_MAX_PAGE_CHARS`` chars)."""
    try:
        import httpx
    except ImportError as exc:
        raise BrowseError(
            "httpx not installed",
            user_message="httpx is required for browsing. Run: pip install httpx",
        ) from exc

    headers = {"User-Agent": "Anythink/2.0 (+https://github.com/anythink-ai/anythink)"}
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
    except Exception as exc:  # httpx.HTTPError + network errors
        raise BrowseError(str(exc), user_message=f"Failed to fetch {url}: {exc}") from exc

    ct = resp.headers.get("content-type", "")
    raw = resp.text
    text = _strip_html(raw) if "html" in ct else raw
    return text[:_MAX_PAGE_CHARS]


async def _headless_get(url: str) -> str:
    """Fetch *url* via Playwright (requires ``anythink[browser]`` extra)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise BrowseError(
            "Playwright not installed",
            user_message="Headless browsing requires: pip install anythink[browser]",
        ) from exc

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(url, timeout=15_000)
            text = await page.inner_text("body")
        finally:
            await browser.close()
    return str(text)[:_MAX_PAGE_CHARS]


class BrowseFetcher:
    """Two-tier fetcher: snippet search via search backends + full-page via httpx/Playwright."""

    def __init__(
        self,
        *,
        search_registry: SearchRegistry | None = None,
        mode: str = "http",
        preferred_search: str = "duckduckgo",
    ) -> None:
        self._search_registry = search_registry
        self._mode = mode
        self._preferred_search = preferred_search

    async def fetch_snippets(self, query: str) -> list[tuple[str, str]]:
        """Return (title, snippet) pairs from the active search backend."""
        if self._search_registry is None:
            return []
        backend = self._search_registry.get_available(self._preferred_search)
        if backend is None:
            return []
        try:
            results = await backend.search(query)
        except Exception:
            return []
        return [(r.title, r.snippet or "") for r in results if r.snippet]

    async def fetch_page(self, url: str) -> str:
        """Fetch *url* according to the configured mode."""
        if self._mode == "headless":
            return await _headless_get(url)
        return await _http_get(url)


class BrowseTool(BaseTool):
    """Agentic browsing: snippet search + full-page HTTP/headless fetch."""

    name = "browse"
    description = "Fetch web content via snippet search or full-page HTTP/headless fetch."

    def __init__(self, fetcher: BrowseFetcher) -> None:
        self._fetcher = fetcher

    def is_available(self) -> bool:
        try:
            import httpx  # noqa: F401

            return True
        except ImportError:
            return False

    async def run(  # type: ignore[override]
        self,
        *,
        url: str = "",
        query: str = "",
    ) -> ToolResult:
        """Fetch *url* (full page) or search *query* (snippets)."""
        t0 = time.monotonic()

        if url:
            try:
                text = await self._fetcher.fetch_page(url)
            except BrowseError as exc:
                return ToolResult(
                    tool_name=self.name,
                    stderr=exc.user_message,
                    exit_code=1,
                    duration_s=round(time.monotonic() - t0, 3),
                )
            return ToolResult(
                tool_name=self.name,
                stdout=text,
                duration_s=round(time.monotonic() - t0, 3),
            )

        if query:
            pairs = await self._fetcher.fetch_snippets(query)
            if not pairs:
                return ToolResult(
                    tool_name=self.name,
                    stderr="No search results found.",
                    exit_code=1,
                    duration_s=round(time.monotonic() - t0, 3),
                )
            lines = [f"{title}\n{snippet}" for title, snippet in pairs]
            return ToolResult(
                tool_name=self.name,
                stdout="\n\n".join(lines),
                duration_s=round(time.monotonic() - t0, 3),
            )

        return ToolResult(
            tool_name=self.name,
            stderr="Provide url= or query=.",
            exit_code=1,
            duration_s=0.0,
        )
