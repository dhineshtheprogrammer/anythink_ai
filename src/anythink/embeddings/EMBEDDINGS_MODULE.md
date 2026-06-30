# Embeddings Module — `anythink.embeddings`

The `embeddings` package provides a **pluggable, uniform interface** for converting text into float vectors. It is consumed by the RAG system for similarity search and by MCP tool servers that need semantic retrieval. Six backends ship out of the box — from a zero-dependency mock for tests, to local CPU inference, to four provider APIs — all discovered at runtime via Python entry points.

---

## Directory Layout

```
src/anythink/embeddings/
├── __init__.py       # Package marker ("Pluggable embedding backends")
├── base.py           # Abstract base class — the contract every backend must satisfy
├── registry.py       # EmbeddingRegistry — entry-point discovery & backend selection
├── mock.py           # MockEmbeddingBackend — deterministic, zero-dep, for testing
├── local.py          # LocalEmbeddingBackend — sentence-transformers (offline)
├── openai_emb.py     # OpenAIEmbeddingBackend — text-embedding-3-small / large
├── cohere_emb.py     # CohereEmbeddingBackend — embed-english-v3.0 / multilingual
├── google_emb.py     # GoogleEmbeddingBackend — text-embedding-004
└── ollama.py         # OllamaEmbeddingBackend — local Ollama server
```

---

## Architecture Overview

```
AppContext
    │
    └── EmbeddingRegistry.from_entry_points()
              │
              ├── MockEmbeddingBackend      (always available — test/fallback)
              ├── LocalEmbeddingBackend     (available if sentence-transformers installed)
              ├── OllamaEmbeddingBackend    (available if local Ollama server responds)
              ├── OpenAIEmbeddingBackend    (available if openai key configured)
              ├── CohereEmbeddingBackend    (available if cohere key configured)
              └── GoogleEmbeddingBackend    (available if gemini key configured)
                          │
                          ▼
              get_available(config.embedding_backend)
                          │
                          ▼
              BaseEmbeddingBackend.embed(texts) → list[list[float]]
                          │
                          ▼
              RAGManager / MCPServer / SearchOrchestrator
```

All backends implement the same `BaseEmbeddingBackend` interface, so the consuming code never needs to know which backend is active.

---

## `base.py` — `BaseEmbeddingBackend`

The abstract base class every backend must subclass. Defines the full contract.

```python
class BaseEmbeddingBackend(ABC):
    name: str           # registry key (e.g. "local", "openai-emb")
    display_name: str   # human-readable label for UI/settings panel

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    def is_available(self) -> bool: ...

    @property
    def dimensions(self) -> int: ...
```

### Methods

| Method | Signature | Description |
|---|---|---|
| `embed` | `async (texts: list[str]) → list[list[float]]` | Convert a batch of strings to vectors. Returns one `list[float]` per input, in the same order. Must be awaited. |
| `is_available` | `() → bool` | Return `True` if the backend can be used right now (dependencies installed, server reachable, API key present). Never raises. |
| `dimensions` | `@property → int` | The fixed length of every returned vector. Needed by the RAG index to allocate storage. |

### Contract invariants

- `embed` must return exactly `len(texts)` vectors, in input order.
- All vectors from a given backend instance have the same length (`dimensions`).
- `is_available` must not raise; exceptions must be swallowed internally.
- SDK imports are always deferred inside method bodies — never at module level — so a missing optional dependency does not break the import chain.

---

## `registry.py` — `EmbeddingRegistry`

Discovers, stores, and selects embedding backend instances.

### Entry-point group

```
anythink.embedding_backends
```

Registered in `pyproject.toml`:

```toml
[project.entry-points."anythink.embedding_backends"]
mock       = "anythink.embeddings.mock:MockEmbeddingBackend"
local      = "anythink.embeddings.local:LocalEmbeddingBackend"
ollama     = "anythink.embeddings.ollama:OllamaEmbeddingBackend"
openai-emb = "anythink.embeddings.openai_emb:OpenAIEmbeddingBackend"
cohere-emb = "anythink.embeddings.cohere_emb:CohereEmbeddingBackend"
google-emb = "anythink.embeddings.google_emb:GoogleEmbeddingBackend"
```

Third-party packages can register additional backends under the same group without modifying Anythink's source.

### Internal storage

```python
_backends: dict[str, BaseEmbeddingBackend]  # keyed by backend.name
```

### Methods

| Method | Signature | Description |
|---|---|---|
| `register` | `(backend: BaseEmbeddingBackend) → None` | Add a backend instance to the registry under `backend.name`. |
| `get` | `(name: str) → BaseEmbeddingBackend \| None` | Exact-name lookup; returns `None` if not found. |
| `names` | `() → list[str]` | All registered backend names. |
| `get_available` | `(preferred: str \| None) → BaseEmbeddingBackend \| None` | Preferred-first selection (see below). |
| `list_all` | `() → list[dict[str, object]]` | Info dicts for every backend (used by `/settings` and the wizard panel). |
| `from_entry_points` | `@classmethod () → EmbeddingRegistry` | Factory: discovers and instantiates all backends from the entry-point group. |

### `get_available(preferred)` — selection logic

```
if preferred is set
    and backend[preferred] exists
    and backend[preferred].is_available()
        → return backend[preferred]
else
    → return first backend in registration order where is_available() is True
    → return None if no backend is available
```

The `preferred` value comes from `AppConfig.embedding_backend` (default `"local"`).

### `list_all()` — return schema

```python
[
    {
        "name": "local",
        "display_name": "Local (sentence-transformers)",
        "dimensions": 384,
        "available": True,
    },
    ...
]
```

### `from_entry_points()` — loading behaviour

- Iterates every entry point in the `anythink.embedding_backends` group.
- Calls `ep.load()` to import the class, then instantiates it with no arguments.
- Any backend that raises during load or instantiation is silently skipped (`# nosec B110`), so one broken plugin never prevents other backends from loading.

### Integration with `AppContext`

`AppContext.create()` calls `EmbeddingRegistry.from_entry_points()` **twice**:

1. **`embedding_registry`** field — holds the full registry, used by `/rag` commands and the settings panel.
2. **`emb` local variable** — calls `get_available(config.embedding_backend)` and passes the resolved backend to `RAGServer` and `MCPManager`.

---

## `mock.py` — `MockEmbeddingBackend`

| Property | Value |
|---|---|
| `name` | `"mock"` |
| `display_name` | `"Mock (test)"` |
| `dimensions` | `64` |
| Requires API key | No |
| Requires extra install | No |
| `is_available()` | Always `True` |

### Algorithm — `_char_vec(text) → list[float]`

Produces a **deterministic 64-dimensional character-frequency vector**:

1. Lowercase the input string.
2. For each alphabetic character, compute `idx = (ord(ch) - ord('a')) % 64` and increment `vec[idx]` by 1.0.
3. L2-normalise the result: `vec[i] /= sqrt(sum(x² for x in vec))`.
4. Return the zero vector unchanged if the input contains no alphabetic characters (norm = 0).

This means texts with similar letter distributions produce similar vectors, which is sufficient for deterministic similarity tests without any ML dependency.

### `embed(texts)`

Calls `_char_vec(t)` for each text synchronously and wraps the results in a coroutine. No I/O occurs.

---

## `local.py` — `LocalEmbeddingBackend`

Runs embedding models **locally on CPU/GPU** using the `sentence-transformers` library. No API key or internet connection required at inference time.

| Property | Value |
|---|---|
| `name` | `"local"` |
| `display_name` | `"Local (sentence-transformers)"` |
| Install extra | `pip install anythink[rag]` |
| `is_available()` | `True` if `sentence_transformers` can be imported |

### Supported models

| Model name | Dimensions | Notes |
|---|---|---|
| `all-MiniLM-L6-v2` _(default)_ | 384 | Fast, good general-purpose English model |
| `all-MiniLM-L12-v2` | 384 | Slightly stronger than L6 |
| `bge-small-en-v1.5` | 384 | BGE small — efficient |
| `bge-base-en-v1.5` | 768 | BGE base |
| `bge-large-en-v1.5` | 1024 | BGE large — highest quality of the BGE set |
| `bge-m3` | 1024 | Multilingual BGE |
| `e5-base-v2` | 768 | E5 base |
| `e5-large-v2` | 1024 | E5 large |

Unrecognised model names fall back to dimension `384`.

### Lazy model loading — `_load()`

The `SentenceTransformer` model object is loaded once on first call to `embed()` and cached in `self._model`. Subsequent calls reuse the cached object, avoiding repeated disk I/O.

### `embed(texts)` — thread-safety

`SentenceTransformer.encode()` is a **blocking, CPU-bound** call. To avoid blocking the asyncio event loop:

```python
vecs = await asyncio.to_thread(model.encode, texts, convert_to_numpy=True)
```

`asyncio.to_thread` runs the call in the default thread-pool executor. The returned numpy arrays are converted to `list[list[float]]` before returning.

### `dimensions` property

Returns the dimension from `SUPPORTED_MODELS` for the configured model name, or `384` as fallback.

---

## `openai_emb.py` — `OpenAIEmbeddingBackend`

Calls the **OpenAI Embeddings REST API** directly over `httpx`. Does not require the `openai` Python SDK.

| Property | Value |
|---|---|
| `name` | `"openai-emb"` (default model) or `"openai-emb/<model>"` |
| `display_name` | `"OpenAI Embeddings"` |
| API endpoint | `https://api.openai.com/v1/embeddings` |
| Timeout | 30 seconds |
| `is_available()` | `True` if an API key is found |

### API key resolution — `_get_api_key()`

1. Try `keyring.get_password("anythink", "openai")` — uses the system keychain (set via `anythink keys add openai`).
2. Fall back to `os.environ.get("OPENAI_API_KEY")`.
3. Return `None` if neither source has a key.

### Supported models

| Model name | Dimensions |
|---|---|
| `text-embedding-3-small` _(default)_ | 1536 |
| `text-embedding-3-large` | 3072 |

### `embed(texts)` — request / response

**Request body:**
```json
{ "model": "text-embedding-3-small", "input": ["text1", "text2"] }
```

**Response handling:**
- Parses `resp.json()["data"]` — a list of `{"index": N, "embedding": [...]}` objects.
- Sorts by `index` before extracting vectors to guarantee input order is preserved, regardless of API response ordering.
- Raises `httpx.HTTPStatusError` on non-2xx responses (via `resp.raise_for_status()`).

### `name` property

Dynamic: returns `"openai-emb"` when using the default model, or `"openai-emb/<model_name>"` for non-default models, allowing multiple instances with different models to coexist in the registry.

---

## `cohere_emb.py` — `CohereEmbeddingBackend`

Calls the **Cohere Embed REST API** directly over `httpx`. Does not require the `cohere` Python SDK.

| Property | Value |
|---|---|
| `name` | `"cohere-emb"` (default model) or `"cohere-emb/<model>"` |
| `display_name` | `"Cohere Embeddings"` |
| API endpoint | `https://api.cohere.com/v1/embed` |
| Timeout | 30 seconds |
| `is_available()` | `True` if an API key is found |

### API key resolution — `_get_api_key()`

1. Try `keyring.get_password("anythink", "cohere")`.
2. Fall back to `os.environ.get("COHERE_API_KEY")`.

### Supported models

| Model name | Dimensions | Notes |
|---|---|---|
| `embed-english-v3.0` _(default)_ | 1024 | English-only, high quality |
| `embed-multilingual-v3.0` | 1024 | Supports 100+ languages |
| `embed-english-light-v3.0` | 384 | Faster, lower-dim English model |

### `embed(texts)` — request / response

**Request body:**
```json
{
  "model": "embed-english-v3.0",
  "texts": ["text1", "text2"],
  "input_type": "search_document"
}
```

- `input_type: "search_document"` is hardcoded, optimising vectors for retrieval (not query embedding). This is appropriate because the RAG indexer embeds document chunks.
- Response vectors are returned directly from `resp.json()["embeddings"]` — Cohere preserves input order.

---

## `google_emb.py` — `GoogleEmbeddingBackend`

Calls the **Google Generative AI Embedding REST API** directly over `httpx`. Does not require the `google-generativeai` SDK.

| Property | Value |
|---|---|
| `name` | `"google-emb"` (default model) or `"google-emb/<model>"` |
| `display_name` | `"Google Embeddings"` |
| API base | `https://generativelanguage.googleapis.com/v1beta/models` |
| Timeout | 30 seconds per text |
| `is_available()` | `True` if an API key is found |

### API key resolution — `_get_api_key()`

1. Try `keyring.get_password("anythink", "gemini")`.
2. Fall back to `os.environ.get("GOOGLE_API_KEY")`.

### Supported models

| Model name | Dimensions |
|---|---|
| `text-embedding-004` _(default)_ | 768 |
| `embedding-001` | 768 |

### `embed(texts)` — sequential requests

Unlike other backends, the Google backend issues **one HTTP request per text** inside a sequential loop. This is because the Google Generative AI `embedContent` endpoint accepts a single content object, not a batch.

**Per-text request:**
```
POST https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={api_key}

{
  "model": "models/text-embedding-004",
  "content": { "parts": [{ "text": "..." }] }
}
```

Response: `resp.json()["embedding"]["values"]` — a flat list of floats.

All requests share a single `httpx.AsyncClient` session (one TCP connection pool for the batch), minimising connection overhead.

---

## `ollama.py` — `OllamaEmbeddingBackend`

Calls a **locally running Ollama server** for embeddings. No API key required; no cloud dependency.

| Property | Value |
|---|---|
| `name` | `"ollama"` (default model) or `"ollama/<model>"` |
| `display_name` | `"Ollama"` |
| Default base URL | `http://localhost:11434` |
| Timeout (`is_available`) | 2 seconds (synchronous probe) |
| Timeout (`embed`) | 30 seconds per text |
| `is_available()` | `True` if the Ollama server responds with HTTP 200 on `/api/tags` |

### Supported models

| Model name | Dimensions | Notes |
|---|---|---|
| `nomic-embed-text` _(default)_ | 768 | General-purpose, widely used |
| `mxbai-embed-large` | 1024 | High-quality English embeddings |
| `all-minilm` | 384 | Lightweight |
| `snowflake-arctic-embed` | 1024 | Strong retrieval model |

Unrecognised model names fall back to dimension `768`.

### `is_available()` — server probe

Issues a **synchronous** `GET /api/tags` with a 2-second timeout via `httpx.Client`. Returns `True` only on HTTP 200. Any exception (connection refused, timeout) returns `False`. This is intentionally synchronous because `is_available()` is called from non-async contexts (e.g. the settings panel).

### `embed(texts)` — sequential requests

Like the Google backend, Ollama's `/api/embeddings` endpoint accepts a single prompt per call, so the backend loops:

```
POST http://localhost:11434/api/embeddings
{ "model": "nomic-embed-text", "prompt": "..." }
```

Response: `resp.json()["embedding"]`.

### `base_url` normalisation

The constructor strips trailing slashes from `base_url` (`base_url.rstrip("/")`), ensuring paths like `/api/embeddings` are always constructed correctly.

---

## Backend Comparison Table

| Backend | `name` | Dims | Requires API key | Requires install | Batching | Sequential requests |
|---|---|---|---|---|---|---|
| `MockEmbeddingBackend` | `mock` | 64 | No | No | Yes (in-process) | No |
| `LocalEmbeddingBackend` | `local` | 384–1024 | No | `anythink[rag]` | Yes (thread pool) | No |
| `OllamaEmbeddingBackend` | `ollama[/model]` | 384–1024 | No | Ollama server | No | Yes (1 req/text) |
| `OpenAIEmbeddingBackend` | `openai-emb[/model]` | 1536–3072 | Yes (openai) | No | Yes (single API call) | No |
| `CohereEmbeddingBackend` | `cohere-emb[/model]` | 384–1024 | Yes (cohere) | No | Yes (single API call) | No |
| `GoogleEmbeddingBackend` | `google-emb[/model]` | 768 | Yes (gemini) | No | No | Yes (1 req/text) |

---

## `AppConfig` Integration

`AppConfig.embedding_backend` (in `config/schema.py`) holds the preferred backend name:

```python
embedding_backend: str = "local"  # default
```

This string is passed directly to `EmbeddingRegistry.get_available(preferred)` during `AppContext` creation. If the preferred backend is unavailable (e.g. `sentence-transformers` not installed), the registry automatically falls back to the first available backend in registration order — typically `mock`.

---

## Dependencies

| Dependency | Scope | Role |
|---|---|---|
| `abc` | stdlib | `ABC`, `abstractmethod` for `BaseEmbeddingBackend` |
| `math` | stdlib | `math.sqrt` for L2 normalisation in `MockEmbeddingBackend` |
| `asyncio` | stdlib | `asyncio.to_thread` in `LocalEmbeddingBackend` |
| `os` | stdlib | `os.environ` fallback for API keys |
| `importlib.metadata` | stdlib | `entry_points()` for backend discovery in `EmbeddingRegistry` |
| `sentence_transformers` | optional (`anythink[rag]`) | `LocalEmbeddingBackend` — lazy import |
| `httpx` | core dep | All API-based backends (`openai_emb`, `cohere_emb`, `google_emb`, `ollama`) |
| `keyring` | core dep | API key lookup in `openai_emb`, `cohere_emb`, `google_emb` — failure is swallowed |

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Backend class fails to load / instantiate | Silently skipped in `from_entry_points` |
| No backend available | `get_available()` returns `None`; caller must handle |
| `sentence-transformers` not installed | `is_available()` returns `False`; `embed()` raises `ImportError` |
| API key missing at embed time | Raises `EnvironmentError` with `anythink keys add <provider>` guidance |
| HTTP non-2xx response | Raises `httpx.HTTPStatusError` (via `resp.raise_for_status()`) |
| Ollama server unreachable | `is_available()` returns `False`; `embed()` raises `httpx.ConnectError` |
| `keyring` unavailable | Exception swallowed in `_get_api_key()`; falls back to env var |

---

## Adding a New Backend

1. Create `src/anythink/embeddings/<name>.py` subclassing `BaseEmbeddingBackend`.
2. Set `name`, `display_name` as class attributes.
3. Implement `embed()`, `is_available()`, and `dimensions`.
4. Defer all SDK imports inside method bodies (never at module level).
5. Register in `pyproject.toml`:
   ```toml
   [project.entry-points."anythink.embedding_backends"]
   my-backend = "anythink.embeddings.<name>:MyBackend"
   ```
6. Re-run `pip install -e .` so the entry point is picked up.

The new backend will be automatically discovered by `EmbeddingRegistry.from_entry_points()` and appear in `list_all()` without any changes to `AppContext` or the RAG system.
