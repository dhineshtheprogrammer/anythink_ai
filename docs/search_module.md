# `src/anythink/search/` — Web Search Backends

This module provides Anythink's pluggable web search layer. It is used by the
`BrowseTool` in `browse/fetch.py` to retrieve search snippets before optionally
fetching full pages. All backends share a single abstract interface and are
discovered at runtime via Python entry points, so third-party backends can be
added without touching core code.

---

## Folder Structure

```
src/anythink/search/
├── __init__.py       # Package marker; single-line docstring
├── base.py           # Abstract base class + SearchResult dataclass
├── registry.py       # SearchRegistry — discovery, storage, selection
├── duckduckgo.py     # DuckDuckGo backend (free, no key)
└── serpapi.py        # SerpAPI backend (Google results, requires key)
```

---

## File-by-File Reference

---

### `__init__.py`

**Purpose:** Makes `anythink.search` a Python package.

**Contents:** A single module-level docstring:

```python
"""Agentic web search backends for Anythink."""
```

Nothing is re-exported here. Callers import directly from submodules
(`from anythink.search.registry import SearchRegistry`, etc.).

---

### `base.py`

**Purpose:** Defines the shared data model (`SearchResult`) and the contract
(`BaseSearchBackend`) that every backend must fulfil.

#### `SearchResult` (dataclass)

Represents one item returned by a search query.

| Field     | Type  | Description                              |
|-----------|-------|------------------------------------------|
| `title`   | `str` | Page or article title                    |
| `url`     | `str` | Full URL of the result                   |
| `snippet` | `str` | Short excerpt / description of the page  |

`SearchResult` is a plain `@dataclass` with no defaults — all three fields are
required.

#### `BaseSearchBackend` (ABC)

All search backends inherit from this class.

**Constructor**

```python
def __init__(self, api_key: str | None = None) -> None
```

Stores `api_key` as `self._api_key`. Backends that do not require a key (e.g.
DuckDuckGo) simply ignore this value.

**Class-level attributes** (must be set on each concrete subclass)

| Attribute      | Type  | Description                                    |
|----------------|-------|------------------------------------------------|
| `name`         | `str` | Machine-readable identifier (used as dict key) |
| `display_name` | `str` | Human-readable label shown in the UI           |

**Abstract methods**

```python
async def search(self, query: str, max_results: int = 5) -> list[SearchResult]
```
Runs the query and returns up to `max_results` results. Must be async.

```python
def is_available(self) -> bool
```
Returns `True` when the backend's dependencies are installed and it is
properly configured (key present if required). Called by `SearchRegistry` to
filter viable backends at runtime.

**Design note:** `is_available()` is intentionally synchronous so it can be
called cheaply inside list comprehensions and registry selection logic without
`await`.

---

### `registry.py`

**Purpose:** Owns the collection of registered backends and selects the best
available one on demand.

#### `SearchRegistry`

```python
class SearchRegistry:
    def __init__(self) -> None
```

Internally holds `_backends: dict[str, BaseSearchBackend]` keyed by
`backend.name`.

**Methods**

| Method | Signature | Description |
|--------|-----------|-------------|
| `register` | `(backend: BaseSearchBackend) -> None` | Adds a backend to the registry under its `.name`. |
| `get` | `(name: str) -> BaseSearchBackend \| None` | Fetches a backend by name, or `None` if not found. |
| `names` | `() -> list[str]` | Returns all registered backend names. |
| `get_available` | `(preferred: str \| None = None) -> BaseSearchBackend \| None` | Returns the preferred backend if it exists **and** `is_available()`, otherwise the first available backend, or `None` if none are available. |
| `from_entry_points` | `(api_keys: dict[str, str \| None] \| None = None) -> SearchRegistry` | Class method. Discovers and registers backends via the `anythink.search_backends` entry-point group. |

**`get_available` selection logic**

```
if preferred is given AND backend[preferred] exists AND backend[preferred].is_available()
    → return backend[preferred]
else
    → return first backend where is_available() is True
    → return None if none are available
```

**`from_entry_points` — plugin discovery**

```python
@classmethod
def from_entry_points(cls, api_keys: dict[str, str | None] | None = None) -> SearchRegistry
```

- Reads all entry points registered under the group `"anythink.search_backends"`.
- For each entry point, loads the backend class, instantiates it with
  `api_key=api_keys.get(ep.name)`, and registers it.
- Any backend that fails to load (missing optional dependency, import error,
  etc.) is silently skipped — the `except Exception: pass` block is marked
  `# nosec B110` because swallowing errors here is intentional (unavailable
  backends are expected during normal operation when optional extras are not
  installed).

**Entry-point group constant**

```python
_ENTRY_POINT_GROUP = "anythink.search_backends"
```

Backends declare themselves in `pyproject.toml` under:

```toml
[project.entry-points."anythink.search_backends"]
duckduckgo = "anythink.search.duckduckgo:DuckDuckGoSearch"
serpapi    = "anythink.search.serpapi:SerpAPISearch"
```

**Usage in AppContext**

`SearchRegistry` is constructed once at startup (in `app/context.py`) and stored
as `ctx.search_registry`. The `BrowseTool` calls
`ctx.search_registry.get_available(preferred)` to obtain the backend before
each search.

---

### `duckduckgo.py`

**Purpose:** Implements web search using the `duckduckgo-search` Python library.
No API key is required; this is the default free backend.

#### Module-level constants

| Constant         | Value  | Description                                              |
|------------------|--------|----------------------------------------------------------|
| `_INSTALL_HINT`  | `"pip install anythink[search]"` | Shown in error messages when the package is missing |
| `_TIMEOUT_S`     | `10.0` | Per-attempt asyncio timeout in seconds                   |
| `_MAX_RETRIES`   | `2`    | Number of retry attempts after a transient failure       |
| `_RETRY_DELAY_S` | `1.5`  | Base delay in seconds between retries (multiplied by attempt number) |

#### `DuckDuckGoSearch(BaseSearchBackend)`

```
name         = "duckduckgo"
display_name = "DuckDuckGo"
```

**`is_available() -> bool`**

Attempts `import duckduckgo_search`. Returns `True` on success, `False` on
`ImportError`. The import is deferred (inside the method body) so the module
can be imported even when the optional package is absent.

**`async search(query, max_results=5) -> list[SearchResult]`**

1. Calls `is_available()`; raises `SearchError` immediately if the package is
   missing.
2. Enters a retry loop (`_MAX_RETRIES + 1` total attempts):
   - Wraps the synchronous `_sync_search()` in `asyncio.to_thread()` to avoid
     blocking the event loop, then applies `asyncio.wait_for(..., timeout=_TIMEOUT_S)`.
   - On `TimeoutError`: raises `SearchError` immediately (no retry — DuckDuckGo
     is likely rate-limiting).
   - On `SearchError` (raised by `_sync_search`): re-raises without retrying.
   - On any other `Exception`: stores it as `last_exc` and retries after
     `_RETRY_DELAY_S * (attempt + 1)` seconds.
3. If all attempts are exhausted, raises `SearchError` wrapping `last_exc`.

**`_sync_search(query, max_results) -> list[SearchResult]`** (private, synchronous)

- Instantiates `DDGS()` as a context manager.
- Calls `ddgs.text(query, max_results=max_results)`.
- Maps each raw dict to a `SearchResult`, pulling `"title"`, `"href"`, and
  `"body"` keys (defaulting to `""` when absent).

**Optional dependency**

```
pip install anythink[search]   # installs duckduckgo-search
```

The `duckduckgo_search` import inside `_sync_search` is always inside a
function body, so missing the package only raises at call time.

---

### `serpapi.py`

**Purpose:** Implements web search using SerpAPI, which proxies Google Search
results. Requires a paid SerpAPI key.

#### Module-level constant

| Constant    | Value                                  | Description                  |
|-------------|----------------------------------------|------------------------------|
| `_BASE_URL` | `"https://serpapi.com/search.json"` | SerpAPI endpoint             |

#### `SerpAPISearch(BaseSearchBackend)`

```
name         = "serpapi"
display_name = "SerpAPI"
```

**`is_available() -> bool`**

Returns `bool(self._api_key)` — available if and only if an API key was passed
at construction time. No import check is needed because `httpx` is a core
(non-optional) Anythink dependency.

**`async search(query, max_results=5) -> list[SearchResult]`**

1. Raises `SearchError` if `self._api_key` is falsy (not configured).
2. Imports `httpx` inside the method body; raises `SearchError` if it is absent
   (defensive, since `httpx` is a core dep).
3. Opens an `httpx.AsyncClient` with a 10-second timeout.
4. Makes a `GET` to `_BASE_URL` with query parameters:

   | Param     | Value            |
   |-----------|------------------|
   | `q`       | `query`          |
   | `api_key` | `self._api_key`  |
   | `num`     | `max_results`    |
   | `engine`  | `"google"`       |

5. Calls `resp.raise_for_status()` — HTTP 4xx/5xx becomes `SearchError` via
   `httpx.HTTPStatusError`.
6. Parses `data["organic_results"]` — a list of dicts. Maps each dict to
   `SearchResult` using keys `"title"`, `"link"`, `"snippet"` (all coerced to
   `str`). Slices to `[:max_results]`.
7. Error mapping:
   - `httpx.HTTPStatusError` → `SearchError` with status code.
   - `httpx.RequestError` → `SearchError` with "network error".

**Setting up the SerpAPI key**

```bash
anythink keys add serpapi
```

The key is stored via `KeyManager` and passed to `SerpAPISearch` at startup
through `from_entry_points(api_keys={"serpapi": key_value})`.

---

## How the Backends Are Wired Together

```
pyproject.toml
  [project.entry-points."anythink.search_backends"]
      duckduckgo = "anythink.search.duckduckgo:DuckDuckGoSearch"
      serpapi    = "anythink.search.serpapi:SerpAPISearch"
          │
          ▼
SearchRegistry.from_entry_points(api_keys={...})
  ├── loads DuckDuckGoSearch(api_key=None)   → registered as "duckduckgo"
  └── loads SerpAPISearch(api_key="sk-...")  → registered as "serpapi"
          │
          ▼
ctx.search_registry   (stored in AppContext)
          │
          ▼
BrowseTool (browse/fetch.py)
  └── ctx.search_registry.get_available(preferred=config.search_backend)
        └── calls backend.search(query, max_results)
              └── returns list[SearchResult]  →  snippets injected into chat
```

---

## Adding a New Search Backend

1. Create `src/anythink/search/<name>.py` subclassing `BaseSearchBackend`.
2. Set `name` and `display_name` class attributes.
3. Implement `is_available()` and `async search()`.
4. Import the third-party SDK **lazily** (inside method bodies only).
5. Register in `pyproject.toml`:

   ```toml
   [project.entry-points."anythink.search_backends"]
   mybackend = "anythink.search.mybackend:MyBackendSearch"
   ```

6. Add the SDK package to the appropriate optional extra in `pyproject.toml`
   (e.g. `[search]` or a new group).

---

## Error Handling

All search errors raise `anythink.exceptions.SearchError`, which is a subclass
of `AnythinkError`. `SearchError` carries both an internal `message` (logged)
and a `user_message` (shown in the terminal).

| Condition                         | Exception raised                     |
|-----------------------------------|--------------------------------------|
| Missing optional package          | `SearchError` with install hint      |
| DuckDuckGo timeout                | `SearchError` (no retry)             |
| DuckDuckGo transient failure      | `SearchError` after `_MAX_RETRIES`   |
| SerpAPI key not set               | `SearchError` with key-setup hint    |
| SerpAPI HTTP 4xx/5xx              | `SearchError` with status code       |
| SerpAPI network error             | `SearchError` with "network error"   |

---

## Key Design Decisions

- **Deferred imports** — Optional SDK imports (`duckduckgo_search`, `httpx`) are
  always inside method bodies so that importing `anythink.search` never fails
  due to a missing optional package.
- **`is_available()` is synchronous** — Allows cheap filtering in registry
  selection without needing `await`.
- **Thread offloading for DuckDuckGo** — The `duckduckgo-search` library is
  synchronous. `asyncio.to_thread` keeps the event loop unblocked.
- **No retries for SerpAPI** — SerpAPI is a paid, metered API; retrying on
  failure could burn quota unexpectedly. Network errors are surfaced immediately.
- **Retry with back-off for DuckDuckGo** — DuckDuckGo rate-limits aggressively;
  a short exponential back-off recovers from transient blocks without user
  intervention.
- **Silent skip in `from_entry_points`** — Backends that fail to load are
  skipped silently. This is deliberate: optional extras may not be installed and
  that is not an error.
