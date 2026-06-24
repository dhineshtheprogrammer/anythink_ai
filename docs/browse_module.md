# `src/anythink/browse` — Agentic Web Browsing Module

## Purpose

The `browse` package implements Anythink's two-tier web browsing capability. It lets the AI fetch live web content either as search-result snippets (quick, low-cost) or as a full scraped page (deep content). The entire package is contained in two files:

| File | Role |
|---|---|
| `__init__.py` | Package marker; re-exports the public API description |
| `fetch.py` | All logic: helpers, `BrowseFetcher`, `BrowseTool` |

---

## File: `__init__.py`

```python
"""Agentic web browsing: two-tier snippet + full-page fetch."""
```

Empty beyond its module docstring. Its only job is to make `src/anythink/browse/` a proper Python package so `from anythink.browse.fetch import ...` works. No symbols are re-exported here.

---

## File: `fetch.py`

**Full path:** `src/anythink/browse/fetch.py`

### Module-level constant

```python
_MAX_PAGE_CHARS = 8_000
```

Hard cap on how many characters are returned from any full-page fetch (both `_http_get` and `_headless_get`). Keeps content injected into the LLM context window bounded. Value is 8 000 characters (~2 000 tokens at typical ratios).

---

### Private helper: `_strip_html(html: str) -> str`

**Location:** `fetch.py:18`

Converts raw HTML to plain text in a minimal, dependency-free way. Applied whenever the HTTP response `Content-Type` header contains `"html"`.

**Steps (in order):**
1. Strip `<script>…</script>` blocks (including content) to remove JavaScript noise.
2. Strip `<style>…</style>` blocks to remove CSS noise.
3. Remove all remaining HTML tags (`<[^>]+>`), replacing each with a space.
4. Unescape the five most common HTML entities: `&nbsp;`, `&amp;`, `&lt;`, `&gt;`, `&quot;`.
5. Collapse any run of 3+ whitespace characters into a double newline (`\n\n`).
6. Strip leading/trailing whitespace.

This is intentionally minimal (no dependency on `beautifulsoup4`, `lxml`, etc.) and is enough to produce readable text for LLM context. It is NOT a full-fidelity renderer.

---

### Private helper: `_http_get(url: str) -> str`

**Location:** `fetch.py:32`  
**Async:** yes

Fetches a URL using `httpx` and returns plain text, capped at `_MAX_PAGE_CHARS`.

**Behavior:**
- Raises `BrowseError` immediately if `httpx` is not installed, with a user-friendly install hint.
- Sends a `User-Agent` header identifying the client as `Anythink/2.0`.
- Uses an `httpx.AsyncClient` with `follow_redirects=True` and a 15-second timeout.
- Calls `resp.raise_for_status()` — any 4xx/5xx response is converted to a `BrowseError`.
- Any other exception (network error, timeout, DNS failure) is also wrapped in `BrowseError`.
- If `Content-Type` contains `"html"`, the response body is passed through `_strip_html()` before truncation; otherwise the raw text is returned as-is (useful for plain-text files, JSON APIs, etc.).
- Returns at most `_MAX_PAGE_CHARS` characters.

**Raises:** `BrowseError` (from `anythink.exceptions`)

---

### Private helper: `_headless_get(url: str) -> str`

**Location:** `fetch.py:56`  
**Async:** yes

Fetches a URL using a headless Chromium browser via Playwright. Handles JavaScript-rendered pages that `_http_get` cannot read.

**Behavior:**
- Raises `BrowseError` immediately if `playwright` is not installed, with a user-friendly hint pointing to `pip install anythink[browser]`.
- Launches a headless Chromium instance (not Firefox or WebKit).
- Navigates to the URL with a 15-second timeout (in milliseconds: `timeout=15_000`).
- Extracts visible body text via `page.inner_text("body")` — this gives rendered text without HTML tags, similar to what a screen reader sees.
- Always closes the browser in a `finally` block to prevent resource leaks.
- Returns at most `_MAX_PAGE_CHARS` characters.

**Note:** This path requires `pip install anythink[browser]` which pulls in `playwright` and the Chromium binary. It is significantly heavier than `_http_get` and is only used when `config.browse_mode == "headless"`.

**Raises:** `BrowseError`

---

### Class: `BrowseFetcher`

**Location:** `fetch.py:77`

The core fetching orchestrator. Holds configuration and delegates to the right backend. Does **not** subclass `BaseTool` — it is a plain helper class designed to be injected into `BrowseTool`.

#### Constructor

```python
BrowseFetcher(
    *,
    search_registry: SearchRegistry | None = None,
    mode: str = "http",
    preferred_search: str = "duckduckgo",
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `search_registry` | `SearchRegistry \| None` | `None` | Registry of available search backends. If `None`, `fetch_snippets()` raises `SearchError`. Sourced from `AppContext.search_registry`. |
| `mode` | `str` | `"http"` | Page-fetch mode. `"http"` → `_http_get()`, `"headless"` → `_headless_get()`. Sourced from `AppConfig.browse_mode`. |
| `preferred_search` | `str` | `"duckduckgo"` | Name of the preferred search backend. Passed to `SearchRegistry.get_available()`. Sourced from `AppConfig.search_provider`. |

All parameters are keyword-only.

#### Method: `fetch_snippets(query: str) -> list[tuple[str, str]]`

**Async:** yes

Runs a web search and returns `(title, snippet)` pairs.

**Flow:**
1. If `search_registry` is `None` → raises `SearchError("No search registry configured.")`.
2. Calls `search_registry.get_available(preferred_search)` → if `None` → raises `SearchError("No search backend available.")`.
3. Calls `backend.search(query)` and filters results to those that have a non-empty `snippet`.
4. Returns `[(r.title, r.snippet) for r in results if r.snippet]`.

The result is a flat list of 2-tuples. The caller (`BrowseTool.run()`) joins them into a newline-separated string for the LLM.

**Raises:** `SearchError` (from `anythink.exceptions`)

#### Method: `fetch_page(url: str) -> str`

**Async:** yes

Fetches a full web page according to `self._mode`.

- `mode == "headless"` → delegates to `_headless_get(url)`
- anything else (including default `"http"`) → delegates to `_http_get(url)`

**Raises:** `BrowseError`

---

### Class: `BrowseTool`

**Location:** `fetch.py:122`  
**Inherits:** `BaseTool` (from `anythink.tools.base`)

The public agentic tool surface. Registered in the tool framework under `name = "browse"`. Wraps a `BrowseFetcher` and exposes a single `run()` method that the TUI background worker calls.

#### Class attributes

| Attribute | Value |
|---|---|
| `name` | `"browse"` |
| `description` | `"Fetch web content via snippet search or full-page HTTP/headless fetch."` |

#### Constructor

```python
BrowseTool(fetcher: BrowseFetcher)
```

Accepts a pre-constructed `BrowseFetcher`. Dependency injection pattern — the TUI creates the fetcher with the right config before constructing the tool.

#### Method: `is_available() -> bool`

Returns `True` if `httpx` is importable, `False` otherwise. Used by the tool framework to surface availability without raising exceptions. Playwright availability is not checked here — headless mode failure is deferred to runtime.

#### Method: `run(*, url: str = "", query: str = "") -> ToolResult`

**Async:** yes

The single entry point for all browsing operations. Accepts **either** `url` or `query`, not both (first non-empty wins; `url` takes precedence).

**Dispatch logic:**

```
url provided  →  BrowseFetcher.fetch_page(url)  →  full page text in ToolResult.stdout
query provided →  BrowseFetcher.fetch_snippets(query)  →  formatted snippet list in ToolResult.stdout
neither       →  ToolResult with stderr="Provide url= or query=.", exit_code=1
```

**On success (`url` path):**
- `ToolResult.stdout` = full page text (up to 8 000 chars)
- `ToolResult.exit_code` = 0 (default)

**On success (`query` path):**
- `ToolResult.stdout` = newline-separated `"{title}\n{snippet}"` blocks joined by `"\n\n"`
- Empty results → `ToolResult.stderr = "No search results found."`, `exit_code=1`

**On error (either path):**
- `ToolResult.stderr` = `exc.user_message` from the caught exception
- `ToolResult.exit_code = 1`

`duration_s` is always set on the returned `ToolResult` using `time.monotonic()`.

---

## How the browse module fits into the larger system

### Trigger: the `/browse` slash command

In `commands/handlers.py`, the `/browse` command parses its argument and builds a `CommandResult` with `action="browse_request"` and `extra={"url": ..., "query": ...}`. It does **not** call `BrowseTool` directly — it only signals the TUI.

### TUI dispatch: `_dispatch_command` in `app.py`

When `result.action == "browse_request"`, the TUI checks `config.browse_autonomy`:
- `"auto"` → fires `_run_browse_tool()` as a background worker immediately.
- `"ask"` → sets `_pending_browse_data` and shows a confirmation prompt; the user types `y` to proceed.

### Background worker: `_run_browse_tool(url, query)` in `app.py:2049`

This is where `BrowseFetcher` and `BrowseTool` are instantiated (import is deferred to this function). The worker:

1. Adds a `SystemBubble("Browsing: …")` to the conversation view.
2. Constructs `BrowseFetcher` from live `AppContext` config.
3. Constructs `BrowseTool(fetcher)` and calls `await tool.run(url=url, query=query)`.
4. On failure: shows an error bubble.
5. On success:
   - Shows a preview bubble (first 500 chars of result).
   - Calls `_log_tool_event()` and `_log_tool_debug()` (debug mode instrumentation).
   - Fires a desktop notification via `ctx.notifier`.
   - Appends the full result as a `ChatMessage(role="user", content=...)` to `state.history`.
   - Opens an `AIBubble` and streams the AI's response based on the browsed content.

### Configuration fields that drive browse behavior

These live in `AppConfig` (`config/schema.py`):

| Field | Values | Effect |
|---|---|---|
| `browse_mode` | `"http"` (default), `"headless"` | Controls which fetch backend `BrowseFetcher` uses |
| `browse_autonomy` | `"auto"`, `"ask"` | Controls whether the TUI confirms before fetching |
| `search_provider` | `"duckduckgo"` (default), `"serpapi"`, etc. | Which backend `SearchRegistry.get_available()` prefers |

---

## Dependency map

```
BrowseTool
  └── BrowseFetcher
        ├── SearchRegistry  (injected; from AppContext.search_registry)
        │     └── BaseSearchBackend (e.g. DuckDuckGoBackend, SerpApiBackend)
        ├── _http_get()
        │     └── httpx  (core dep; always available)
        └── _headless_get()
              └── playwright  (optional; anythink[browser])
```

---

## Error handling summary

| Situation | Exception raised | `ToolResult.exit_code` |
|---|---|---|
| `httpx` not installed | `BrowseError` → caught → `exit_code=1` | 1 |
| HTTP 4xx/5xx or network error | `BrowseError` → caught → `exit_code=1` | 1 |
| `playwright` not installed | `BrowseError` → caught → `exit_code=1` | 1 |
| No search registry configured | `SearchError` → caught → `exit_code=1` | 1 |
| No search backend available | `SearchError` → caught → `exit_code=1` | 1 |
| Search returns zero snippets | No exception — `exit_code=1`, `stderr` set | 1 |
| `run()` called with no args | No exception — `exit_code=1`, `stderr` set | 1 |
| All other paths | — | 0 |

All exceptions that escape `BrowseTool.run()` are of types `BrowseError` or `SearchError`, both subclasses of `AnythinkError`.

---

## Key design decisions

- **Two-tier design** — Snippet search (`fetch_snippets`) is faster and cheaper; full-page (`fetch_page`) is deeper but heavier. The `/browse` command routes to one or the other based on whether the argument looks like a URL.
- **Deferred imports** — `httpx` and `playwright` are imported inside the functions that use them, never at module level. This means missing optional packages only raise errors at the moment they are actually needed, not at import time.
- **`BrowseFetcher` is separate from `BrowseTool`** — The fetcher holds configuration and can be used or tested independently. The tool wraps it in the `BaseTool` contract for the agentic framework.
- **Hard character cap** — `_MAX_PAGE_CHARS = 8_000` prevents a large page from flooding the LLM's context window. This is applied at the lowest layer (`_http_get`, `_headless_get`), so it is impossible for the tool to return more than this regardless of the fetch mode.
- **`TYPE_CHECKING` guard on `SearchRegistry`** — The import of `SearchRegistry` is under `if TYPE_CHECKING:` to avoid a circular import at runtime. At runtime the object is passed in by value (dependency injection); the type annotation is only needed for static analysis.
