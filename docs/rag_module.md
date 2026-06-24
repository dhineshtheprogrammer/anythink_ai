# `src/anythink/rag` — Retrieval-Augmented Generation Module

## Purpose

The `rag` package implements Anythink's complete Retrieval-Augmented Generation pipeline. It lets users build named vector indexes from local files or project directories, then automatically injects the most relevant text chunks into the LLM's context window before each AI request.

The pipeline has four clearly separated layers:

```
Files on disk
  └── chunkers.py     — splits files into overlapping text chunks
        └── store.py  — embeds and stores vectors; answers similarity queries
              └── manager.py — orchestrates named indexes; owns metadata YAML
                    └── models.py — shared data structures (IndexInfo, RetrievalResult)
```

The package has five source files:

| File | Responsibility |
|---|---|
| `__init__.py` | Package marker |
| `models.py` | Data structures: `IndexInfo` and `RetrievalResult` |
| `chunkers.py` | File reading and text splitting (document-aware and code-aware) |
| `store.py` | In-memory cosine-similarity vector store with gzip JSON persistence |
| `manager.py` | `RAGManager`: lifecycle coordination, index build, activation, retrieval |

---

## File: `__init__.py`

```python
"""Retrieval-Augmented Generation: index management and vector stores."""
```

Empty beyond its module docstring. Makes `src/anythink/rag/` a Python package. No symbols are re-exported.

---

## File: `models.py`

**Full path:** `src/anythink/rag/models.py`

Defines the two data structures shared across the entire RAG system: `IndexInfo` (what an index is) and `RetrievalResult` (what retrieval returns). Both are plain `@dataclass` objects with YAML-friendly serialisation methods.

---

### `IndexInfo`

```python
@dataclass
class IndexInfo:
    name: str
    index_type: str          # "project" | "document"
    source_path: str
    persistence_mode: str    # "rebuild" | "persist"
    embedding_backend: str = "local"
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_indexed: datetime | None = None
    file_count: int = 0
    chunk_count: int = 0
```

Stores the metadata for one named RAG index. Lives in a YAML file at `$XDG_DATA_HOME/anythink/rag/<name>.yaml`.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | User-chosen identifier for the index (e.g. `"my-code"`) |
| `index_type` | `str` | `"project"` indexes code + config files; `"document"` indexes markdown, plain text, PDFs, CSV |
| `source_path` | `str` | Absolute path to the directory (or file) to index |
| `persistence_mode` | `str` | `"persist"` — save the vector store to disk after build; `"rebuild"` — rebuild from scratch on each `/rag rebuild` without persisting |
| `embedding_backend` | `str` | Name of the embedding backend used (written back after build; default `"local"`) |
| `created_at` | `datetime` | UTC datetime when `create_index()` was first called |
| `last_indexed` | `datetime \| None` | UTC datetime of the most recent successful `build_index()` call; `None` if never built |
| `file_count` | `int` | Number of files included in the last build |
| `chunk_count` | `int` | Number of chunks in the vector store after the last build |

#### `to_dict() -> dict[str, Any]`

Serialises the object to a plain dict suitable for YAML. `datetime` fields are stored as ISO-8601 strings. `None` is preserved as `null`.

#### `from_dict(data: dict[str, Any]) -> IndexInfo` (classmethod)

Deserialises from the YAML-loaded dict. All fields have safe defaults so partially-written YAML files don't crash:
- `index_type` defaults to `"document"`
- `persistence_mode` defaults to `"rebuild"`
- `embedding_backend` defaults to `"local"`
- `created_at` defaults to `datetime.utcnow()` if absent
- `last_indexed` is `None` if the key is absent or null

---

### `RetrievalResult`

```python
@dataclass
class RetrievalResult:
    source_path: str
    chunk_text: str
    relevance: float       # cosine similarity 0.0–1.0
    start_line: int | None = None
    end_line: int | None = None
    section: str | None = None
```

Represents one chunk returned from a `VectorStore.query()` call.

| Field | Type | Description |
|---|---|---|
| `source_path` | `str` | Absolute path to the file the chunk came from |
| `chunk_text` | `str` | The raw text of the chunk |
| `relevance` | `float` | Cosine similarity score between the query embedding and this chunk's embedding, rounded to 4 decimal places; range `[0.0, 1.0]` |
| `start_line` | `int \| None` | Estimated start line number within the source file (1-based, None if unavailable) |
| `end_line` | `int \| None` | Estimated end line number within the source file |
| `section` | `str \| None` | Optional section heading (not currently populated by the built-in chunker; reserved for future use) |

#### `excerpt(max_chars: int = 120) -> str`

Returns a short preview of the chunk for display. Takes the first line of `chunk_text` and truncates it to `max_chars` characters, appending `"…"` if truncated. Used by debug formatters (`/debug chunks`, `/debug raginject`).

**Injection threshold:** Chunks with `relevance >= 0.70` are injected into the LLM context. Chunks below this threshold are retrieved but not injected (visible in `/debug chunks` as "rejected"). The threshold is hardcoded at 0.70 in `_stream_response()` and in the debug formatters.

---

## File: `chunkers.py`

**Full path:** `src/anythink/rag/chunkers.py`

Implements three public functions for splitting files into LLM-friendly chunks. No external dependencies — pure Python with `re` and `pathlib`.

---

### Module-level constants

```python
_CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rs", ".cpp", ".c", ".h", ".cs", ".rb", ".swift", ".kt", ".php"
})

_DEFAULT_CHUNK = 512    # characters per chunk
_DEFAULT_OVERLAP = 64   # overlap between consecutive chunks
```

`_CODE_EXTENSIONS` — the set of file suffixes (lowercase) that trigger code-aware chunking in `chunk_file()`. All other extensions use `chunk_text()`.

`_DEFAULT_CHUNK = 512` and `_DEFAULT_OVERLAP = 64` — the defaults used throughout unless the caller overrides them. At typical text density, 512 characters ≈ 100–150 tokens.

---

### `chunk_text(text, *, chunk_size=512, overlap=64) -> list[str]`

**Location:** `chunkers.py:33`

Generic character-level chunker with boundary-seeking and overlap.

**Algorithm:**
1. If `text.strip()` is empty, return `[]`.
2. Start a `start` cursor at 0.
3. On each iteration, set `end = min(start + chunk_size, n)`.
4. If `end < n` (not the last segment), walk backward within the segment looking for a clean break point in priority order:
   - `\n\n` (paragraph break) — highest priority
   - `\.\s` (sentence end + whitespace)
   - `\s` (any whitespace)
   - If none found, the chunk is cut at exactly `chunk_size` characters.
5. Strip the segment and append it if non-empty.
6. Advance `start = max(start + 1, end - overlap)` — the `overlap` characters at the tail of the current chunk become the head of the next, giving the model cross-boundary context.

**Result:** A list of stripped strings, each ≤ `chunk_size` characters (plus any extra captured by the boundary-seeking walk-back). Empty chunks are discarded.

---

### `chunk_code(text, *, chunk_size=512, overlap=64) -> list[str]`

**Location:** `chunkers.py:76`

Code-aware chunker that splits first at top-level function and class definition boundaries.

**Algorithm:**
1. If `text.strip()` is empty, return `[]`.
2. Find all positions matching:
   ```
   ^(def |class |fn |func |function |public |private |async def )
   ```
   (multiline, so `^` matches after every `\n`). This covers Python, JavaScript/TypeScript (function), Go (func), Rust (fn), Java/C#/C++ (public/private), and Swift/Kotlin.
3. If no boundaries are found, fall back to `chunk_text()`.
4. Build "natural blocks" by slicing the text between consecutive boundary positions. The final block (from the last boundary to EOF) is included.
5. For each block:
   - If `len(block) <= chunk_size` → keep it as a single chunk.
   - If `len(block) > chunk_size` → pass it through `chunk_text()` with the same `chunk_size` and `overlap`.

**Effect:** Each top-level function or class definition starts at the beginning of a chunk rather than in the middle of one, improving the relevance of code retrieval significantly.

---

### `chunk_file(path, *, chunk_size=512, overlap=64) -> list[tuple[str, dict[str, object]]]`

**Location:** `chunkers.py:116`

The main entry point called by `RAGManager.build_index()`. Reads a single file, chooses the right chunker, and attaches metadata to each chunk.

**Returns:** A list of `(chunk_text, metadata)` 2-tuples where `metadata` is:
```python
{
    "source_path": str(path),   # absolute path string
    "start_line": int,          # 1-based line number where this chunk starts
    "end_line": int,            # 1-based line number where this chunk ends
}
```

**Behavior:**
1. Reads the file with `encoding="utf-8", errors="replace"` — undecodable bytes become the Unicode replacement character `�` rather than raising.
2. Returns `[]` on `OSError` or `UnicodeDecodeError` (missing file, permission error, truly binary file).
3. Chooses `chunk_code()` if `path.suffix.lower()` is in `_CODE_EXTENSIONS`, else `chunk_text()`.
4. Tracks a running `line_no` counter by counting `"\n"` characters in each chunk to estimate start/end lines. This is an approximation — it counts newlines in the chunk text, not in the original file, so overlap regions cause slight drift.

---

## File: `store.py`

**Full path:** `src/anythink/rag/store.py`

A self-contained, pure-Python in-memory vector store with cosine similarity retrieval and gzip JSON persistence. No external vector database is required.

---

### `_cosine(a, b) -> float`

**Location:** `store.py:14`

Computes cosine similarity between two equal-length float vectors.

```
cosine(a, b) = dot(a, b) / (|a| × |b|)
```

Returns `0.0` if either vector has zero magnitude (prevents division by zero). Uses `zip(..., strict=False)` so mismatched-length vectors don't raise — shorter vector wins.

---

### `_Chunk` (internal dataclass)

```python
@dataclass
class _Chunk:
    text: str
    metadata: dict[str, Any]
    vector: list[float]
```

The private storage unit inside `VectorStore`. Not exposed to callers.

`to_dict()` / `from_dict()` handle JSON serialisation. `vector` is stored as a plain `list[float]` — JSON-native, no binary encoding needed.

---

### `VectorStore`

**Location:** `store.py:42`

```
Suitable for small-to-medium indexes (< 50 k chunks at typical embedding sizes).
```

In-memory store backed by a single `list[_Chunk]`. All query operations are O(n) linear scans with cosine similarity. Fast enough for typical local codebases (thousands of chunks); not suitable for millions of chunks.

#### Constructor

```python
VectorStore()
```

Creates an empty store. `_chunks: list[_Chunk] = []`.

#### Write methods

**`add(texts, metadatas, vectors) -> None`**

Bulk-inserts chunks. All three lists must be the same length (enforced implicitly by `zip`). Each `(text, metadata, vector)` triple is wrapped in a `_Chunk` and appended to `_chunks`. This is the only write path — there is no per-chunk `add` or upsert.

**`clear() -> None`**

Removes all chunks from memory. Called before a rebuild to ensure stale vectors don't linger.

#### Read methods

**`query(query_vector, *, top_k=5) -> list[RetrievalResult]`**

The core retrieval operation.

1. Returns `[]` immediately if `_chunks` is empty.
2. Computes `_cosine(query_vector, chunk.vector)` for every chunk — O(n).
3. Sorts all `(score, chunk)` pairs descending.
4. Takes the top `top_k` entries and converts each to a `RetrievalResult`:
   - `source_path` from `chunk.metadata.get("source_path", "unknown")`
   - `chunk_text` from `chunk.text`
   - `relevance = round(score, 4)`
   - `start_line` / `end_line` from metadata (cast to `int`; `None` if absent)
5. Returns the list in descending relevance order.

**`count() -> int`**

Returns `len(self._chunks)`. Used to report `chunk_count` in `IndexInfo` and to short-circuit `retrieve()` in `RAGManager` when the store is empty.

#### Persistence methods

**`persist(path: Path) -> None`**

Serialises all `_Chunk` objects to `path` as **gzip-compressed JSON**. Uses `gzip.open(path, "wt")` so the output is valid UTF-8 text inside gzip. Creates parent directories automatically. Defers `import gzip` inside the method (no module-level import of optional stdlib modules).

The file format is a JSON array where each element is:
```json
{
  "text": "...",
  "metadata": {"source_path": "...", "start_line": 1, "end_line": 12},
  "vector": [0.12, -0.34, ...]
}
```

File extension by convention is `.store.gz` (set by `RAGManager._store_path()`).

**`VectorStore.load(path: Path) -> VectorStore`** (classmethod)

Deserialises a previously persisted store. Returns an empty `VectorStore()` if `path` does not exist (safe no-op). Reads the gzip file, deserialises each dict via `_Chunk.from_dict()`, and sets `store._chunks` directly. Defers `import gzip`.

---

## File: `manager.py`

**Full path:** `src/anythink/rag/manager.py`

Contains `RAGManager`, the top-level coordinator for all RAG operations. One instance lives at `AppContext.rag_manager` for the entire application lifetime. It is constructed from two XDG-based directories and coordinates all four layers: metadata YAML files, chunk production, vector storage, and retrieval.

---

### Module-level extension sets

```python
_PROJECT_EXTS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".cpp", ".c", ".h", ".cs", ".rb", ".swift", ".kt",
    ".json", ".yaml", ".yml", ".toml", ".md"
})

_DOC_EXTS = frozenset({".md", ".txt", ".rst", ".pdf", ".csv"})

_ALL_EXTS = _PROJECT_EXTS | _DOC_EXTS
```

These sets determine which files under the `source_path` are included during `build_index()`:

- `index_type == "project"` → uses `_PROJECT_EXTS`: source code + config + markdown.
- `index_type == "document"` → uses `_ALL_EXTS` (union of both sets): adds `.txt`, `.rst`, `.pdf`, `.csv` on top of everything in `_PROJECT_EXTS`.

Note: `.md` appears in both sets, so it is indexed under either type.

---

### `RAGManager`

```python
class RAGManager:
    def __init__(self, rag_dir: Path, cache_dir: Path) -> None:
```

| Parameter | XDG location | Contains |
|---|---|---|
| `rag_dir` | `$XDG_DATA_HOME/anythink/rag/` | `{name}.yaml` index metadata files |
| `cache_dir` | `$XDG_CACHE_HOME/anythink/rag/` | `{name}.store.gz` persisted vector stores |

#### Internal state

| Attribute | Type | Description |
|---|---|---|
| `_rag_dir` | `Path` | Metadata directory |
| `_cache_dir` | `Path` | Vector store cache directory |
| `_active_info` | `IndexInfo \| None` | Metadata of the currently active index, or `None` |
| `_active_store` | `VectorStore \| None` | The in-memory store currently serving queries, or `None` |

#### Properties

**`is_active -> bool`**
`True` when `_active_info is not None`. Checked in `_stream_response()` to decide whether to run retrieval. Also checked by `StatsPanel.update_stats()` and the HUD to show the active index name.

**`active_name -> str | None`**
The name of the currently active index, or `None`.

---

### Index management methods

#### `list_indexes() -> list[IndexInfo]`

Reads all `*.yaml` files from `_rag_dir` (sorted alphabetically), deserialises each via `IndexInfo.from_dict()`, and returns the list. Corrupt or unreadable YAML files are silently skipped (`# nosec B110`). Returns `[]` if the directory does not exist.

#### `get_info(name: str) -> IndexInfo | None`

Reads a single index's metadata YAML. Returns `None` if the file does not exist or fails to parse. Used internally by `build_index()`, `use_index()`, and the `/rag` command handler.

#### `create_index(info: IndexInfo) -> None`

Writes `info.to_dict()` to `_meta_path(info.name)` as YAML. Creates `_rag_dir` if needed. Called both when creating a new index from the command and when `build_index()` updates statistics after a rebuild (same method, just called twice).

#### `delete_index(name: str) -> None`

1. Verifies the metadata file exists; raises `RAGError` if not.
2. Deletes the metadata YAML (`missing_ok=True`).
3. Deletes the vector store file (`missing_ok=True`).
4. If the deleted index is the currently active one, clears `_active_info` and `_active_store`.

---

### Build method

#### `async build_index(name, backend, *, chunk_size=512, overlap=64) -> IndexInfo`

The main indexing pipeline. Called by the TUI `_rebuild_rag_index()` background worker.

**Full algorithm:**

1. Load `IndexInfo` for `name` via `get_info()`; raise `RAGError` if not found.
2. Resolve `source_path` to a `Path`; raise `RAGError` if it does not exist.
3. Create a fresh empty `VectorStore()`.
4. Choose extension set: `_PROJECT_EXTS` if `index_type == "project"`, else `_ALL_EXTS`.
5. Walk the source directory with `source.rglob("*")`, collecting all files whose lowercase suffix is in the chosen extension set.
6. For each file, call `chunk_file(fpath, chunk_size=chunk_size, overlap=overlap)` and accumulate all `(text, metadata)` pairs into `all_texts` / `all_metas`.
7. If `all_texts` is non-empty, embed in **batches of 64**:
   ```python
   for i in range(0, len(all_texts), 64):
       vecs = await backend.embed(all_texts[i:i+64])
       all_vectors.extend(vecs)
   ```
   Then call `store.add(all_texts, all_metas, all_vectors)`.
8. Update `IndexInfo`:
   - `last_indexed = datetime.utcnow()`
   - `file_count = len(files)`
   - `chunk_count = store.count()`
   - `embedding_backend = backend.name`
9. If `persistence_mode == "persist"`, write the store to `_store_path(name)` via `store.persist()`.
10. Write updated metadata back to disk via `create_index(info)`.
11. Return the updated `IndexInfo`.

**The batch size of 64** avoids sending thousands of texts in a single embedding call, which can exceed provider payload limits or cause memory spikes.

**Note:** The build result is **not** automatically made active. The caller must call `use_index(name)` separately to load the newly built store. The TUI worker does not do this automatically — the user either had the index active before the rebuild (in which case `use_index()` was already called) or needs to call `/rag use <name>` again.

---

### Activation methods

#### `use_index(name: str) -> bool`

Loads index `name` as the active store.

1. Calls `get_info(name)` — returns `False` if not found.
2. Checks whether `_store_path(name)` exists:
   - **Yes** → calls `VectorStore.load(store_path)`, loads the persisted store.
   - **No** → creates an empty `VectorStore()` (retrieval will return nothing until the user runs `/rag rebuild <name>`).
3. Sets `_active_info = info` and `_active_store = store`.
4. Returns `True`.

This is called both from `commands/handlers.py` (on `/rag use <name>`) and from `app/context.py` at startup when `config.active_rag_index` is set from a previous session.

#### `deactivate() -> None`

Clears `_active_info` and `_active_store` to `None`. Does not delete any files. Called by `/rag off`.

---

### Retrieval method

#### `async retrieve(query, backend, *, top_k=5, debug_callback=None) -> list[RetrievalResult]`

The hot path called on every AI request when `is_active` is `True`.

1. Returns `[]` immediately if `_active_store is None` or `_active_store.count() == 0`.
2. Records `t_emb_start = time.monotonic()`.
3. Calls `await backend.embed([query])` to get a 1-item list of embedding vectors.
4. Computes `emb_ms = (time.monotonic() - t_emb_start) * 1000`.
5. Reads `candidates = self._active_store.count()`.
6. If `debug_callback` is provided and callable, calls `debug_callback(emb_ms, candidates)` inside `contextlib.suppress(Exception)` so a debug instrumentation error cannot crash retrieval.
7. Calls `self._active_store.query(vecs[0], top_k=top_k)` and returns the result list.

**`debug_callback` signature:** `(emb_ms: float, candidates: int) -> None`

In `_stream_response()`, the callback captures `emb_ms` and `candidates` into the active `RequestDebugRecord`:
```python
def _rag_debug_cb(emb_ms, candidates):
    _debug_record.rag_embedding_ms = emb_ms
    _debug_record.rag_candidates_evaluated = candidates
```

When debug mode is active, `top_k` is raised to 10 (instead of the default 5) so the debug chunk inspector has more data to display. Only the top 5 are injected into context regardless.

---

### Private helpers

#### `_meta_path(name: str) -> Path`

Returns `_rag_dir / "{safe_name}.yaml"` where `safe_name` replaces spaces and `/` with `_`.

#### `_store_path(name: str) -> Path`

Returns `_cache_dir / "{safe_name}.store.gz"` with the same sanitisation.

---

## Embedding backends

`RAGManager` does not embed text itself — it delegates to a `BaseEmbeddingBackend` passed by the caller. The interface:

```python
class BaseEmbeddingBackend(ABC):
    name: str
    display_name: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    def is_available(self) -> bool: ...

    @property
    def dimensions(self) -> int: ...
```

Two built-in backends (in `src/anythink/embeddings/`):

| Backend | Name | Dimensions | Dependency |
|---|---|---|---|
| `MockEmbeddingBackend` | `"mock"` | 64 | None (zero-dep, deterministic) |
| `LocalEmbeddingBackend` | `"local"` | 384 | `sentence-transformers` (`anythink[rag]`) |

The active backend is resolved at call time via `EmbeddingRegistry.get_available(config.embedding_backend)`. If no backend is available, `_rebuild_rag_index()` in the TUI shows an error and aborts.

---

## Full RAG lifecycle

### 1. Index creation

```
/rag new my-code project /home/user/project persist
      ↓
handlers._rag_handler() parses subcommand "new"
      ↓
RAGManager.create_index(IndexInfo(
    name="my-code",
    index_type="project",
    source_path="/home/user/project",
    persistence_mode="persist",
))
      ↓
Writes $XDG_DATA_HOME/anythink/rag/my-code.yaml
(no vectors yet; chunk_count=0, last_indexed=None)
```

### 2. Index build

```
/rag rebuild my-code
      ↓
CommandResult(action="rag_rebuild:my-code")
      ↓
TUI _dispatch_command() fires:
  self.run_worker(_rebuild_rag_index("my-code"))
      ↓
_rebuild_rag_index():
  emb = EmbeddingRegistry.get_available("local")
  info = await RAGManager.build_index("my-code", emb)
      ↓
build_index():
  for each file in source_path.rglob("*") matching _PROJECT_EXTS:
    chunk_file(fpath) → [(text, {source_path, start_line, end_line}), ...]
  for i in range(0, len(all_texts), 64):
    vecs = await emb.embed(all_texts[i:i+64])
  VectorStore.add(all_texts, all_metas, all_vectors)
  store.persist($XDG_CACHE_HOME/anythink/rag/my-code.store.gz)
  create_index(updated_info)   # writes chunk_count, file_count, last_indexed
```

### 3. Index activation

```
/rag use my-code
      ↓
RAGManager.use_index("my-code")
  → VectorStore.load($XDG_CACHE_HOME/anythink/rag/my-code.store.gz)
  → _active_info = info
  → _active_store = store
      ↓
config.active_rag_index = "my-code"  (persisted so next session auto-loads)
CommandResult(action="rag_hud_update")  → HUD shows [RAG: my-code]
```

### 4. Per-request retrieval (hot path)

```
User sends message: "How does the auth middleware work?"
      ↓
_stream_response():
  query = "How does the auth middleware work?"
  if rag_mgr.is_active:
    rag_results = await rag_mgr.retrieve(query, emb, top_k=5)
      → emb.embed([query]) → query_vector
      → VectorStore.query(query_vector, top_k=5)
          → cosine(query_vector, chunk.vector) for all chunks
          → sort descending → top 5
      → returns list[RetrievalResult]

    inject_results = [r for r in rag_results if r.relevance >= 0.70]
    if inject_results:
      context_parts = "\n\n".join(
        f"[Source: {r.source_path}]\n{r.chunk_text}" for r in inject_results
      )
      state.history[-1] = ChatMessage(
        role="user",
        content=[
          TextPart("[RAG Context]\n" + context_parts),
          TextPart(query),
        ],
      )
      ↓
  # LLM now sees injected context before the user's question
  stream_chat(state.history, ...)
```

---

## Storage layout

| Artifact | Path |
|---|---|
| Index metadata (all indexes) | `$XDG_DATA_HOME/anythink/rag/<name>.yaml` |
| Persisted vector store | `$XDG_CACHE_HOME/anythink/rag/<name>.store.gz` |
| Active index config entry | `$XDG_CONFIG_HOME/anythink/config.yaml` → `active_rag_index` field |

The metadata in `rag/` is the authoritative record. The store in `cache/` is derived and can be deleted; it is recreated by `/rag rebuild`. Deleting `config.yaml`'s `active_rag_index` field deactivates RAG without losing any data.

---

## TUI command integration

All `/rag` subcommands are handled in `commands/handlers.py:_rag_handler()`. The handler reads `ctx.rag_manager` directly.

| Subcommand | Handler action | What happens |
|---|---|---|
| `/rag status` | Inline response | Lists all indexes and shows which is active |
| `/rag new <name> <type> <path> <mode>` | Inline or `rag_new_request` | Creates `IndexInfo` YAML; no vectors yet |
| `/rag use <name>` | `rag_hud_update` | Calls `use_index()`; updates `config.active_rag_index` |
| `/rag off` | `rag_hud_update` | Calls `deactivate()`; clears `config.active_rag_index` |
| `/rag rebuild <name>` | `rag_rebuild:<name>` | TUI fires `_rebuild_rag_index()` background worker |
| `/rag delete <name>` | Inline response | Calls `delete_index()`; deactivates if it was active |

---

## Key design decisions

- **No external vector DB required** — `VectorStore` is pure Python with no dependencies. The only optional import is `gzip` (stdlib). This means RAG works out of the box without Docker, Chroma, Pinecone, or any database daemon.
- **Gzip JSON persistence** — Vector stores are stored as gzip-compressed JSON arrays. Human-readable without decompression tools, no binary format to version, easily inspected with `zcat`. Trades some disk efficiency for simplicity and portability.
- **Chunker dispatch in `chunk_file()`** — The decision between `chunk_text()` and `chunk_code()` is made at the file level based on extension. Code files get function/class-boundary chunking; all others get paragraph/sentence-boundary chunking. This keeps the chunkers pure (no file I/O) and `chunk_file()` as the single integration point.
- **Overlap for cross-boundary context** — `_DEFAULT_OVERLAP = 64` characters of overlap between consecutive chunks ensures that a sentence or code statement split across a chunk boundary appears in at least one chunk in its entirety, avoiding context loss at boundaries.
- **Batched embedding (batch size 64)** — Embedding is done in batches of 64 texts per `backend.embed()` call. This prevents single massive payloads and allows incremental progress on large codebases.
- **Rebuild does not auto-activate** — `build_index()` writes the vector store to disk but does not swap in `_active_store`. This keeps the build operation idempotent and safe — a rebuild in the background does not silently replace the active store mid-session.
- **`persistence_mode = "rebuild"` skips disk writes** — For ephemeral use cases, the user can create an index with `persistence_mode="rebuild"`. In this mode, `build_index()` does all the embedding work but does not call `store.persist()`. The next call to `use_index()` will find no `.store.gz` file and load an empty store, meaning the user must rebuild after each restart.
- **Relevance threshold = 0.70 is hardcoded** — The injection threshold is not configurable through `AppConfig` in the current version. It appears in both `_stream_response()` and the debug formatters. Future versions may expose it as `/rag threshold <value>` (the formatter already mentions this hint).
- **`TYPE_CHECKING` guard on `BaseEmbeddingBackend`** — `RAGManager` imports `BaseEmbeddingBackend` only under `TYPE_CHECKING`. At runtime, the embedding backend is passed by value through `build_index()` and `retrieve()` so no circular import occurs.
- **RAG errors are non-fatal during streaming** — In `_stream_response()`, the entire RAG retrieval block is wrapped in a bare `except Exception` with `# nosec B110`. A broken embedding backend or corrupted vector store silently falls back to no-RAG rather than aborting the response. This is intentional — the user's message still gets answered.
