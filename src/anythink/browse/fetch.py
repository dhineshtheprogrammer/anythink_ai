"""Agentic web browsing: two-tier snippet search + full-page fetch."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from anythink.exceptions import BrowseError, SearchError
from anythink.tools.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from anythink.search.registry import SearchRegistry

_MAX_PAGE_CHARS = 15_000

# Extended HTML named entity map for technical and news content
_HTML_ENTITIES: dict[str, str] = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
    "&mdash;": "—",
    "&ndash;": "–",
    "&ldquo;": "“",
    "&rdquo;": "”",
    "&lsquo;": "‘",
    "&rsquo;": "’",
    "&middot;": "·",
    "&copy;": "©",
    "&reg;": "®",
    "&trade;": "™",
    "&hellip;": "…",
    "&bull;": "•",
    "&times;": "×",
    "&divide;": "÷",
    "&euro;": "€",
    "&pound;": "£",
    "&yen;": "¥",
    "&deg;": "°",
    "&frac12;": "½",
    "&frac14;": "¼",
    "&frac34;": "¾",
}


def _extract_tables(html: str) -> str:
    """Convert HTML <table> blocks to Markdown pipe tables, innermost first."""

    def _process_table(m: re.Match[str]) -> str:
        table_html = m.group(0)
        rows: list[list[str]] = []
        header_row: list[str] = []

        # Extract header row
        th_match = re.search(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)
        if th_match and re.search(r"<th", th_match.group(1), re.IGNORECASE):
            cells = re.findall(r"<th[^>]*>(.*?)</th>", th_match.group(1), re.DOTALL | re.IGNORECASE)
            header_row = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]

        # Extract data rows
        for row_m in re.finditer(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row_m.group(1), re.DOTALL | re.IGNORECASE)
            if cells:
                rows.append([re.sub(r"<[^>]+>", "", c).strip() for c in cells])

        if not rows and not header_row:
            return " "

        # Cap wide tables
        max_cols = 10
        if header_row:
            header_row = header_row[:max_cols]
        rows = [r[:max_cols] for r in rows]

        lines: list[str] = []
        if header_row:
            lines.append("| " + " | ".join(header_row) + " |")
            lines.append("|" + "|".join("---" for _ in header_row) + "|")
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")

        return "\n" + "\n".join(lines) + "\n"

    # Process innermost tables first (no nested tables inside)
    pattern = r"<table[^>]*>(?:(?!<table).)*?</table>"
    prev = None
    result = html
    while prev != result:
        prev = result
        result = re.sub(pattern, _process_table, result, flags=re.DOTALL | re.IGNORECASE)
    return result


def _strip_html(html: str) -> str:
    """Strip HTML to plain text: table extraction → tag removal → entity unescaping."""
    # Extract tables before generic stripping so structure is preserved
    text = _extract_tables(html)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)

    # Unescape named entities
    for entity, char in _HTML_ENTITIES.items():
        text = text.replace(entity, char)
    # Unescape numeric entities (&#NNN; and &#xHH;)
    text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"&#([0-9]+);", lambda m: chr(int(m.group(1))), text)

    text = re.sub(r"\s{3,}", "\n\n", text)
    return text.strip()


async def _http_get(url: str, max_chars: int = _MAX_PAGE_CHARS) -> str:
    """Fetch *url* via httpx and return plain text (max *max_chars* chars)."""
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
    return text[:max_chars]


async def _headless_get(url: str, max_chars: int = _MAX_PAGE_CHARS) -> str:
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
    return str(text)[:max_chars]


class BrowseFetcher:
    """Two-tier fetcher: snippet search via search backends + full-page via httpx/Playwright."""

    def __init__(
        self,
        *,
        search_registry: SearchRegistry | None = None,
        mode: str = "http",
        preferred_search: str = "duckduckgo",
        max_page_chars: int = _MAX_PAGE_CHARS,
    ) -> None:
        self._search_registry = search_registry
        self._mode = mode
        self._preferred_search = preferred_search
        self._max_page_chars = max_page_chars

    async def fetch_snippets(self, query: str) -> list[tuple[str, str]]:
        """Return (title, snippet) pairs from the active search backend.

        Raises ``SearchError`` if no backend is available or the search fails,
        so callers can surface the problem to the user.
        """
        if self._search_registry is None:
            raise SearchError(
                "No search registry configured.",
                user_message=(
                    "Web search is not configured. Install a backend: pip install anythink[search]"
                ),
            )
        backend = self._search_registry.get_available(self._preferred_search)
        if backend is None:
            raise SearchError(
                "No search backend available.",
                user_message=(
                    "No search backend available. Install one with: pip install anythink[search]"
                ),
            )
        results = await backend.search(query)
        return [(r.title, r.snippet or "") for r in results if r.snippet]

    async def fetch_page(self, url: str) -> str:
        """Fetch *url* according to the configured mode."""
        if self._mode == "headless":
            return await _headless_get(url, max_chars=self._max_page_chars)
        return await _http_get(url, max_chars=self._max_page_chars)


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
            try:
                pairs = await self._fetcher.fetch_snippets(query)
            except SearchError as exc:
                return ToolResult(
                    tool_name=self.name,
                    stderr=exc.user_message,
                    exit_code=1,
                    duration_s=round(time.monotonic() - t0, 3),
                )
            if not pairs:
                return ToolResult(
                    tool_name=self.name,
                    stderr="No search results found.",
                    exit_code=1,
                    duration_s=round(time.monotonic() - t0, 3),
                )
            result_lines = [f"{title}\n{snippet}" for title, snippet in pairs]
            return ToolResult(
                tool_name=self.name,
                stdout="\n\n".join(result_lines),
                duration_s=round(time.monotonic() - t0, 3),
            )

        return ToolResult(
            tool_name=self.name,
            stderr="Provide url= or query=.",
            exit_code=1,
            duration_s=0.0,
        )
