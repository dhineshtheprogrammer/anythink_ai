# `src/anythink/debug` — V3.2.0 Debug Infrastructure Module

## Purpose

The `debug` package is Anythink's unified observational layer, introduced in V3.2.0. It captures a complete lifecycle snapshot of every AI request — timing, token usage, RAG retrieval, tool calls, plugin hooks, and raw HTTP traffic — and exposes all of it through a `/debug` slash command namespace with 25+ subcommands.

**Key design principle:** `DebugManager` is always instantiated in `AppContext` but is **zero-cost when inactive**. Every instrumentation call in `_stream_response()` is gated by `is_active()`, so there is no overhead in normal operation.

The package has five source files, each with a distinct responsibility:

| File | Responsibility |
|---|---|
| `__init__.py` | Package marker |
| `models.py` | Frozen data structures for all captured state |
| `manager.py` | Central coordinator: enable/disable, record lifecycle, export |
| `http_logger.py` | Raw HTTP traffic capture via httpx event hooks |
| `formatters.py` | Pure display functions: convert records to formatted text |
| `commands.py` | `/debug` slash command router and all subcommand handlers |

---

## File: `__init__.py`

```python
"""V3.2.0 debug infrastructure — unified observational debug layer."""
```

Empty beyond its docstring. Makes `src/anythink/debug/` a Python package so `from anythink.debug.manager import DebugManager` resolves correctly. No symbols are re-exported.

---

## File: `models.py`

**Full path:** `src/anythink/debug/models.py`

Defines all data structures that represent captured debug state. All types are plain `@dataclass` objects (not frozen) so they can be mutated progressively during a request's lifetime. All cross-module imports are under `TYPE_CHECKING` to avoid circular imports at runtime.

---

### `TokenEntry`

```python
@dataclass
class TokenEntry:
    index: int
    text: str
    delta_ms: float
```

Represents a single token captured during Level 3 token-trace recording.

| Field | Type | Description |
|---|---|---|
| `index` | `int` | Zero-based position of this token in the stream |
| `text` | `str` | The raw token text as received from the provider |
| `delta_ms` | `float` | Milliseconds elapsed since the previous token (inter-token gap) |

Used by `formatters.format_token_trace()` to detect and flag anomalously long pauses (defined as `delta_ms > 3× average`). Collected in `RequestDebugRecord.token_trace` only when debug level is 3.

---

### `ToolCallEntry`

```python
@dataclass
class ToolCallEntry:
    name: str
    arguments: dict[str, Any]
    result_summary: str
    duration_s: float
    success: bool
    used_in_response: bool = False
```

Records a single tool call that occurred during a request.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Tool name (e.g. `"browse"`, `"exec"`, `"mcp"`) |
| `arguments` | `dict[str, Any]` | Arguments passed to the tool |
| `result_summary` | `str` | First ~120 chars of the tool's output, for display |
| `duration_s` | `float` | Wall-clock seconds the tool took to complete |
| `success` | `bool` | Whether `ToolResult.succeeded` was `True` |
| `used_in_response` | `bool` | Heuristic: `True` if the result text appears in the AI's response buffer |

Appended to `RequestDebugRecord.tool_calls` by `_log_tool_debug()` in `app.py` after each tool completes.

---

### `PluginEvent`

```python
@dataclass
class PluginEvent:
    plugin_name: str
    hook_name: str
    duration_ms: float
    modified: bool
```

A single plugin hook invocation captured during a request.

| Field | Type | Description |
|---|---|---|
| `plugin_name` | `str` | Name of the plugin that was invoked |
| `hook_name` | `str` | Name of the hook (e.g. `"pre_prompt"`, `"post_response"`) |
| `duration_ms` | `float` | How long the hook took in milliseconds |
| `modified` | `bool` | `True` if the hook returned a non-passthrough value (i.e. mutated the data) |

Accumulated in `RequestDebugRecord.plugin_events`. Displayed by `/debug plugins`.

---

### `HttpLogEntry`

```python
@dataclass
class HttpLogEntry:
    method: str
    url: str
    status_code: int
    request_headers: dict[str, str]
    request_body_snippet: str
    response_headers: dict[str, str]
    round_trip_ms: float
```

One HTTP request/response pair captured by the API logger.

| Field | Type | Description |
|---|---|---|
| `method` | `str` | HTTP verb (e.g. `"POST"`) |
| `url` | `str` | Full request URL |
| `status_code` | `int` | HTTP response status code |
| `request_headers` | `dict[str, str]` | Request headers (auth headers masked) |
| `request_body_snippet` | `str` | First 2 000 characters of the JSON request body |
| `response_headers` | `dict[str, str]` | Response headers |
| `round_trip_ms` | `float` | Total milliseconds from request sent to response received |

**Note:** `request_headers` always has auth values masked via `_mask_auth()` unless `DebugHttpLogger._show_keys` is `True` (never set in normal usage). Stored at `RequestDebugRecord.http_log`.

---

### `RequestDebugRecord`

**Location:** `models.py:61`

The central data structure. One instance is created per AI request/response cycle by `DebugManager.begin_request()` and is mutated progressively throughout `_stream_response()`. It is committed to the session deque by `DebugManager.finalize_request()` after the response completes.

#### Identity fields (set at creation, immutable)

| Field | Type | Description |
|---|---|---|
| `request_id` | `int` | Auto-incremented integer, unique within the session |
| `session_id` | `str` | ID of the current chat session |
| `timestamp` | `datetime` | UTC datetime when `begin_request()` was called |
| `model_id` | `str` | Raw model ID string (e.g. `"claude-opus-4-8"`) |
| `provider_name` | `str` | Provider display name (e.g. `"Anthropic"`) |
| `alias_name` | `str` | Model alias name as configured by the user |
| `prompt_payload` | `list[dict[str, Any]]` | Full serialised chat history as sent to the API |
| `gen_params` | `GenerationParams \| None` | Active generation parameters (temperature, max_tokens, etc.) |

#### Timing fields (monotonic seconds, set progressively during streaming)

All timing fields use `time.monotonic()` values. Convenience methods on the record compute durations from pairs of these timestamps.

| Field | Type | Set when |
|---|---|---|
| `t_start` | `float` | Immediately at start of `_stream_response()` |
| `t_prompt_assembled` | `float` | After building the full prompt payload |
| `t_rag_start` | `float \| None` | When RAG retrieval begins (only if RAG is active) |
| `t_rag_end` | `float \| None` | When RAG retrieval completes |
| `t_search_start` | `float \| None` | When web search begins (only if search is active) |
| `t_search_end` | `float \| None` | When web search completes |
| `t_api_sent` | `float` | Just before the `stream_chat()` call is awaited |
| `t_first_token` | `float \| None` | When the first token arrives from the provider |
| `t_stream_end` | `float` | When the token stream closes |
| `t_render_end` | `float` | After the final Textual render/redraw completes |

#### Outcome fields

| Field | Type | Description |
|---|---|---|
| `stop_reason` | `str \| None` | Provider stop reason (e.g. `"end_turn"`, `"max_tokens"`) |
| `usage` | `TokenUsage \| None` | Token usage reported by the provider |
| `completion_tokens` | `int` | Number of completion tokens (used for TPS calculation) |
| `tokens_per_second` | `float \| None` | Computed tokens/second (completion_tokens ÷ stream_duration) |
| `was_stopped_by_user` | `bool` | `True` if the user pressed Ctrl+C to interrupt generation |

#### RAG fields

| Field | Type | Description |
|---|---|---|
| `rag_query` | `str` | The query string used for RAG retrieval |
| `rag_results` | `list[RetrievalResult]` | All retrieved chunks with relevance scores |
| `rag_embedding_ms` | `float \| None` | Time taken to embed the query |
| `rag_candidates_evaluated` | `int` | Total number of vector candidates compared |

#### Detail layer fields

| Field | Type | Populated at level |
|---|---|---|
| `tool_calls` | `list[ToolCallEntry]` | Level 1+ (whenever tools run) |
| `plugin_events` | `list[PluginEvent]` | Level 1+ (whenever plugins fire) |
| `http_log` | `HttpLogEntry \| None` | Only when `/debug api` is active |
| `token_trace` | `list[TokenEntry]` | Level 3 only |
| `agent_thinking` | `str` | Only for Anthropic extended thinking responses |

#### V4 MMOS fields (populated when optimization engine is active)

| Field | Type | Description |
|---|---|---|
| `routing_decision` | `RoutingDecision \| None` | MMOS routing decision (strategy, model selection, confidence) |
| `history_selection_log` | `list[dict]` | Log of which history turns were included and why |
| `rate_limit_events` | `list[dict]` | Rate limit events encountered during an MMOS query |
| `plan_trace` | `ExecutionPlan \| None` | Full Plan Mode execution trace |

#### Convenience methods

All methods return derived durations in milliseconds. Return `None` or `0.0` if the relevant timestamps were never set (e.g. RAG was not active).

| Method | Returns | Formula |
|---|---|---|
| `ttft_ms()` | `float \| None` | `(t_first_token - t_api_sent) × 1000` |
| `stream_duration_ms()` | `float` | `(t_stream_end - t_first_token) × 1000` |
| `total_wall_ms()` | `float` | `(t_render_end - t_start) × 1000` |
| `rag_duration_ms()` | `float \| None` | `(t_rag_end - t_rag_start) × 1000` |
| `search_duration_ms()` | `float \| None` | `(t_search_end - t_search_start) × 1000` |
| `prompt_assembly_ms()` | `float` | `(t_prompt_assembled - t_start) × 1000` |
| `api_overhead_ms()` | `float` | `(t_first_token - t_prompt_assembled) × 1000` |

---

## File: `manager.py`

**Full path:** `src/anythink/debug/manager.py`

Contains `DebugManager`, the single central coordinator for all debug state. One instance lives at `AppContext.debug_manager` for the entire application lifetime.

---

### `DebugManager`

```python
class DebugManager:
    MAX_RECORDS = 100
```

`MAX_RECORDS = 100` — the in-memory deque holds at most 100 `RequestDebugRecord` objects. Older records are automatically evicted when the limit is reached (FIFO).

#### Internal state

| Attribute | Type | Initial value | Description |
|---|---|---|---|
| `_records` | `deque[RequestDebugRecord]` | `deque(maxlen=100)` | Sliding window of completed records |
| `_active` | `bool` | `False` | Whether debug instrumentation is on |
| `_level` | `int` | `2` | Verbosity level (1–3) |
| `_api_logging` | `bool` | `False` | Whether HTTP-level capture is active |
| `_panel_open` | `bool` | `False` | Whether the TUI debug side panel is visible |
| `_request_counter` | `int` | `0` | Auto-incrementing request ID |
| `_pending_record` | `RequestDebugRecord \| None` | `None` | The in-flight record being built |
| `_export_active` | `bool` | `False` | Whether live-append export is running |
| `_export_path` | `Path \| None` | `None` | Path for live-append export |
| `_http_client` | `Any` | `None` | Lazy-constructed instrumented `httpx.AsyncClient` |

#### State accessors (read-only)

| Method | Returns | Description |
|---|---|---|
| `is_active()` | `bool` | Whether debug mode is currently enabled |
| `level()` | `int` | Current verbosity level (1–3) |
| `api_logging_active()` | `bool` | Whether HTTP-level capture is on |
| `panel_open()` | `bool` | Whether the debug side panel is open |

#### State mutators

**`enable(level: int = 2) -> None`**  
Activates debug mode and sets the level, clamped to the range `[1, 3]`.

**`disable() -> None`**  
Deactivates debug mode. Does not clear existing records.

**`toggle() -> bool`**  
Flips debug mode. If disabling, calls `disable()`. If enabling, calls `enable(self._level)` so the previously set level is preserved. Returns the new active state.

**`set_level(n: int) -> None`**  
Changes the verbosity level, clamped to `[1, 3]`. Can be called whether or not debug mode is active.

**`toggle_api_logging() -> bool`**  
Flips HTTP-level capture. When toggled off, also clears `_http_client` to release the httpx client. Returns the new state.

**`toggle_panel() -> bool`**  
Flips the `_panel_open` flag. The TUI reads this to show/hide the `DebugPanel` widget. Returns the new state.

#### Request lifecycle

**`begin_request(session_id, model_id, provider_name, alias_name, prompt_payload, gen_params, t_start) -> RequestDebugRecord`**

Called at the very start of `_stream_response()` (only when `is_active()` is `True`). Creates a new `RequestDebugRecord` with an auto-incremented `request_id`, stores it as `_pending_record`, and returns it so the caller can mutate it progressively.

**`finalize_request(record: RequestDebugRecord) -> None`**

Called at the end of `_stream_response()` after the response is complete. Clears `_pending_record`, appends the record to the `_records` deque, and — if live-append export is active — calls `_append_export(record)`.

#### Record access

| Method | Returns | Description |
|---|---|---|
| `latest()` | `RequestDebugRecord \| None` | The most recently finalized record, or `None` if empty |
| `get(request_id: int)` | `RequestDebugRecord \| None` | Linear scan of the deque by `request_id` |
| `all_records()` | `list[RequestDebugRecord]` | A snapshot list of all records in the deque (oldest first) |

#### Export methods

**`export_json(path: Path) -> Path`**  
Serialises all current records to a structured JSON file using `_record_to_dict()`. Creates parent directories if needed. Returns the path written.

**`export_txt(path: Path) -> Path`**  
Writes a human-readable plain-text summary of all records (one block per request: ID, timestamp, model, total wall time, TTFT, TPS, stop reason). Returns the path written.

**`_append_export(record: RequestDebugRecord) -> None`**  
Internal. Appends a single record as a JSON line to `_export_path`. Silently ignores `OSError` so a full disk does not crash the session.

**`_record_to_dict(rec: RequestDebugRecord) -> dict[str, Any]`**  
Internal. Converts one record to a JSON-serialisable dict. Includes: identity fields, a nested `timing` dict (all durations computed via convenience methods), stop reason, completion tokens, TPS, full `usage` breakdown, RAG summary, and a compact tool-call list. Does **not** include `token_trace`, `plugin_events`, or `http_log` in the export — those are available only in the live TUI.

#### HTTP client management

**`http_client() -> Any`**  
Returns an instrumented `httpx.AsyncClient` when API logging is active (`_api_logging == True`). The client is constructed lazily on first call using `DebugHttpLogger.make_hooks()`. Returns `None` when API logging is off. Providers check this and use the instrumented client if non-`None`, so no provider code needs to know about `DebugHttpLogger` directly.

---

## File: `http_logger.py`

**Full path:** `src/anythink/debug/http_logger.py`

Captures raw HTTP API traffic by installing event hooks on an `httpx.AsyncClient`. Used exclusively through `DebugManager.http_client()`.

---

### `_mask_auth(headers: dict[str, str]) -> dict[str, str]`

**Location:** `http_logger.py:13`

Replaces the value of any `Authorization` header (case-insensitive match) with the literal string `"Bearer sk-...***"`. All other headers are passed through unchanged. Applied to every outgoing request so API keys are never written to the log file.

---

### `DebugHttpLogger`

```python
class DebugHttpLogger:
    MAX_BYTES = 50 * 1024 * 1024  # 50 MB
```

Captures raw HTTP request/response pairs and writes them to a rolling log file.

`MAX_BYTES = 50 MB` — the `RotatingFileHandler` is configured with `maxBytes=50MB, backupCount=2`, so the total disk usage is capped at ~150 MB (current log + 2 rotated backups).

#### Constructor

```python
DebugHttpLogger(log_path: Path | None = None)
```

| Parameter | Default | Description |
|---|---|---|
| `log_path` | `None` | Path to write the rolling log. If `None`, nothing is written to disk (hooks still fire but the `_get_logger()` call returns `None`). In practice, the TUI passes `$XDG_STATE_HOME/anythink/logs/api_debug.log`. |

#### `_get_logger() -> logging.Logger | None`

Lazy-initialises a `logging.Logger` instance with a `RotatingFileHandler` on first call. Logger name includes `id(self)` to avoid namespace collisions if multiple instances exist. Sets `propagate = False` to prevent log lines leaking into the root logger. Returns `None` if `_log_path` is `None` or if the file could not be opened.

#### `make_hooks() -> dict[str, list[Callable]]`

Returns an `httpx` `event_hooks` dict with two async callables:

**`_on_request(request)`**
- Records `time.monotonic()` keyed by `id(request)` in `_request_start_times`.
- Reads `request.headers` and applies `_mask_auth()` unless `_show_keys` is `True`.
- Reads up to 2 000 characters of the request body (`request.content.decode(...)`).
- Writes a formatted `── REQUEST <METHOD> <URL> ──` block to the log.
- All exceptions are silently swallowed (`# nosec B110`) so a logging failure never interrupts a real request.

**`_on_response(response)`**
- Pops the corresponding start time from `_request_start_times` and computes `round_trip_ms`.
- Calls `await response.aread()` to ensure the body is available (streaming responses are read here for logging purposes only — the content is still available to the caller).
- Reads up to 2 000 characters of the response body.
- Writes a `── RESPONSE <STATUS> (<ms>) ──` block to the log.
- All exceptions silently swallowed.

**Log format** (both blocks):
```
── REQUEST POST https://api.anthropic.com/v1/messages ──
Headers: {'content-type': 'application/json', 'authorization': 'Bearer sk-...***', ...}
Body: {"model": "claude-opus-4-8", "messages": [...], ...}

── RESPONSE 200 (342ms) ──
Headers: {'content-type': 'text/event-stream', ...}
Body: data: {"type": "content_block_start", ...}
```

The log file path is `$XDG_STATE_HOME/anythink/logs/api_debug.log` (set by `AppPaths`).

---

## File: `formatters.py`

**Full path:** `src/anythink/debug/formatters.py`

Contains all display formatting logic for the debug inspection system. **All functions are pure**: they accept data objects and return formatted strings. There is no TUI coupling, no side effects, and no state. This makes every formatter independently testable.

All output is rendered inside a Unicode box drawn by the `_box()` helper.

---

### Private helpers

#### `_box(title: str, lines: list[str], width: int = 68) -> str`

Wraps content in a box with rounded Unicode corners (`╭`, `╮`, `╰`, `╯`) and pipe-character sides. The title appears in the top border. Each line in `lines` is left-padded with `│  ` and right-padded to `width`. Default box width is 68 characters.

#### `_ms(v: float | None) -> str`

Formats a millisecond value as `"1234ms"`, or returns `"—"` for `None`.

---

### `format_prompt_payload(record: RequestDebugRecord) -> str`

**Used by:** `/debug prompt [n]`

Renders the full prompt payload (all chat messages as sent to the API). Shows model ID, provider, request number, active generation parameters, then each message turn formatted as:
```
── TURN 1 · SYSTEM ──────────────────────────────
  You are a helpful assistant...
```
Text is word-wrapped to 60 characters. Multi-part content (list-type messages) is joined with spaces before wrapping.

---

### `format_timing_breakdown(record: RequestDebugRecord) -> str`

**Used by:** `/debug timing [n]`

Renders a table of per-stage latencies with a running cumulative column:

```
Stage                                Duration   Cumulative
──────────────────────────────────────────────────────────────
Prompt assembly                           8ms          8ms
RAG retrieval                            42ms         50ms
API call (queue + network)              180ms        230ms
Time to first token (TTFT)              180ms        230ms
Token stream duration                   820ms       1050ms
Response rendering                        9ms       1059ms
──────────────────────────────────────────────────────────────
Total wall time                        1059ms
```

Stages that did not occur (e.g. RAG when it was not active) are omitted entirely. Cumulative column always starts at 0.

---

### `format_stop_reason(record: RequestDebugRecord) -> str`

**Used by:** `/debug stopreason`

Maps the raw provider stop reason string to a human-readable description using `_STOP_DESCRIPTIONS`:

| Stop reason | Description |
|---|---|
| `end_turn` | Model naturally completed its response |
| `max_tokens` / `length` | Response was cut off at the token limit |
| `stop_sequence` | A configured stop string halted generation |
| `tool_use` | Model paused to call a tool |
| `cancelled` | Generation was stopped by the user |
| `error` | Generation ended due to a provider-side error |
| `timeout` | Generation halted due to a connection timeout |
| `stop` | Model naturally completed its response |

For `max_tokens` / `length`, adds a warning that the response was silently truncated and suggests increasing `max_tokens`.

---

### `format_token_trace(record: RequestDebugRecord) -> str`

**Used by:** `/debug tokens`

Renders the per-token stream trace (Level 3 only). Shows up to 80 tokens:
```
  #0    '\n'               +12ms
  #1    'Hello'            +28ms ← long pause
  #2    ' there'           +9ms
  …
▸ 312 tokens  avg 15ms/token  total stream 4680ms
```

Tokens with `delta_ms > 3× average` are flagged with `← long pause`. Tokens beyond 80 show a truncation notice.

Returns a plain text prompt `"Enable Level 3 before sending a message: /debug level 3"` if `token_trace` is empty.

---

### `format_context_window(state: Any, record: RequestDebugRecord | None) -> str`

**Used by:** `/debug context`

Renders a context window composition breakdown. Token counts are estimated using a `len(text) // 4` heuristic (one token ≈ 4 characters). Shows each turn with its estimated token count and percentage of the context window, plus a progress bar:

```
Component                                Tokens       %
──────────────────────────────────────────────────────────
Turn · system                               245   1.49%
Turn · user                                 312   1.90%
Turn · assistant                           1024   6.24%
──────────────────────────────────────────────────────────
Total used                               10,234  62.44%
Remaining                                 6,138  37.56%

████████████████████░░░░░░░░░░  62.44%
```

Uses `state.context_window` for the denominator; if `0` or missing, percentages show `"—"`.

---

### `format_latency_chart(records: list[RequestDebugRecord], width: int = 60) -> str`

**Used by:** `/debug latency`

Renders an ASCII dot plot of total wall time across all recorded requests. The Y-axis is scaled to the maximum wall time in the session. Each request is plotted as `●` at its proportional height. Below the chart, shows avg/min/max with the request ID of the fastest and slowest.

---

### `format_perf_summary(records: list[RequestDebugRecord]) -> str`

**Used by:** `/debug perf`

Renders a comprehensive session-level performance report with four sections:
- **Response Time** — avg/min/max TTFT; avg/slowest total time
- **Generation Speed** — avg/fastest/slowest tokens per second
- **Token Usage** — total prompt tokens, completion tokens, combined total across all records
- **Tool Usage** — total tool calls and success rate (shown only if tools were used)

---

### `format_rag_chunks(record: RequestDebugRecord) -> str`

**Used by:** `/debug chunks`

Shows the RAG chunk inspector. Partitions `rag_results` into injected (relevance ≥ 0.70) and rejected (< 0.70) sets and renders both with source path, score, and a 60-character excerpt. The threshold `0.70` is hardcoded in the display but can be changed via `/rag threshold`.

---

### `format_embeddings(record: RequestDebugRecord) -> str`

**Used by:** `/debug embeddings`

Shows a summary of the embedding search process: the query embedded, embedding time, total candidates evaluated, chunks above threshold, and how many were actually injected (capped at 5).

---

### `format_rag_inject(record: RequestDebugRecord) -> str`

**Used by:** `/debug raginject`

Renders a preview of exactly what was prepended to the prompt from RAG — the same preamble block the model received, with `[CHUNK N · source_path · lines X-Y]` headers and up to 200 characters of chunk text per chunk (first 5 chunks only).

---

### `format_tool_trace(record: RequestDebugRecord) -> str`

**Used by:** `/debug tools`

Renders the complete tool call trace: for each call, shows name, input arguments (JSON, first 60 chars), status (✓ Success / ✕ Failed), output summary, and whether the result was referenced in the response. At the bottom, shows total calls, total tool time, and tool time as a percentage of total wall time.

---

### `format_agent_log(record: RequestDebugRecord) -> str`

**Used by:** `/debug agent`

Renders the agent decision log / extended thinking text. Word-wraps `agent_thinking` to 62 characters. If empty, returns a plain-text explanation that extended thinking is only available for select Anthropic models when enabled in generation parameters.

---

### `format_tool_diff(a: RequestDebugRecord, b: RequestDebugRecord) -> str`

**Used by:** `/debug tooldiff [n1 n2]`

Generates a `difflib.unified_diff` between the tool output summaries of two records. Each line in the diff represents one tool call as `"name: result_summary[:80]"`. Shows up to 60 diff lines. Returns a plain equality message if the outputs are identical.

---

### `format_prompt_diff(a: RequestDebugRecord, b: RequestDebugRecord) -> str`

**Used by:** `/debug diff [n1 n2]`

Generates a `difflib.unified_diff` between the prompt payloads of two records. Each message is flattened to a single line `"[role] content[:120]"` before diffing. Shows up to 60 diff lines. Returns a plain equality message if the prompts are identical.

---

### `format_plugin_trace(record: RequestDebugRecord) -> str`

**Used by:** `/debug plugins`

Renders the plugin hook invocation trace, grouped by plugin name. For each hook shows: hook name, duration in ms, and whether the hook modified the data or was a passthrough.

---

### `format_compare_table(results: list[Any]) -> str`

**Used by:** `/debug compare <alias...>` (via compare runner)

Renders a side-by-side technical comparison table across multiple model aliases. Columns: TTFT, total wall time, tokens/second, stop reason. One column per alias, rows fixed. Used when `debug_compare=True` is set in the compare result.

---

### `format_validation_table(issues: list[Any]) -> str`

**Used by:** config validation output (not a `/debug` subcommand — shared formatter)

Renders the `/config validate` results table with severity icons (`✓`, `⚠`, `❌`), category, field name, message, and optional suggestion. Totals by severity at the bottom.

---

## File: `commands.py`

**Full path:** `src/anythink/debug/commands.py`

Implements all `/debug` slash command routing and subcommand handlers. Registered via `register_debug_commands()` into the `CommandRegistry`. All handlers return `CommandResult` objects; none perform TUI operations directly.

---

### `_DEBUG_HELP_TABLE`

A `dict[str, str]` mapping each subcommand signature to its one-line description. Used to generate the `/debug help` output. Full list:

| Subcommand | Description |
|---|---|
| `on / off / toggle` | Activate or deactivate debug mode |
| `level <1\|2\|3>` | Set verbosity level |
| `panel` | Toggle live debug side panel |
| `prompt [n]` | Inspect raw payload of request n (or latest) |
| `timing [n]` | Per-stage latency breakdown |
| `stopreason` | Stop reason for the last response |
| `tokens` | Token-by-token stream trace (Level 3 only) |
| `tps` | Tokens per second for the last response |
| `context` | Context window composition breakdown |
| `diff [n1 n2]` | Prompt diff between two requests |
| `chunks` | RAG chunk inspector (injected + rejected) |
| `embeddings` | Embedding search process details |
| `raginject` | What RAG injected into context |
| `tools` | Tool call trace |
| `agent` | Agent decision log / extended thinking |
| `tooldiff [n1 n2]` | Diff tool outputs between two runs |
| `api` | Toggle raw HTTP request/response logging |
| `replay [n]` | Replay request n (or latest) to same provider |
| `replay [n] --provider <alias>` | Replay to a different provider |
| `latency` | ASCII latency history chart |
| `compare <alias...>` | Technical multi-provider comparison |
| `plugins` | Plugin invocation trace |
| `export` | Export debug log to JSON file |
| `export --format txt` | Export debug log to plain text |
| `perf` | Session performance summary |
| `routing` | Show MMOS routing decision for the last query |
| `plan` | Show full Plan Mode execution trace |
| `ratelimit` | Show rate limit event log |

---

### `_debug_handler(ctx, args, state, registry) -> CommandResult`

**Location:** `commands.py:49`

The single top-level async handler registered for the `/debug` command. Parses `args` into `sub` (the subcommand) and `rest` (remaining tokens), then dispatches to the appropriate `_handle_*` function.

**Guard:** All inspection subcommands (those in `_inspection_cmds`) check `dm.is_active()` before proceeding. If debug mode is off, returns an error: `"Debug mode is not active. Run /debug on first."` This prevents confusing output when the user tries an inspection command on a cold manager with no records.

**Mode-control subcommands** (`on`, `off`, `toggle`, `level`, `panel`, `api`) do **not** require debug mode to be active — they are how debug mode is turned on.

---

### Private helper: `_get_record(dm, rest) -> tuple[RequestDebugRecord | None, str | None]`

Resolves which record a command should inspect:
- If `rest` is non-empty and `rest[0]` is an integer string → look up `dm.get(n)`; return an error string if not found.
- If `rest` is empty or `rest[0]` is not an integer → use `dm.latest()`.
- Returns `(record, None)` on success, `(None, error_message)` on failure.

Used by all inspection handlers that accept an optional `[n]` argument.

---

### Subcommand handlers summary

Each handler is a private function named `_handle_<subcommand>`. They follow a consistent pattern:

1. Call `_get_record()` or `dm.latest()` to retrieve the target record.
2. Return `CommandResult(error=True, message=...)` on any lookup failure.
3. Import the relevant formatter function (deferred import inside the function).
4. Return `CommandResult(message=<formatted_string>, action="debug_display")`.

The `action="debug_display"` signal tells the TUI's `_dispatch_command()` to render the message in a debug overlay widget rather than as a normal chat bubble.

#### Special handlers

**`_handle_tps`** — Does not call a formatter. Directly builds a plain-text message from `rec.tokens_per_second` and `rec.completion_tokens`. Returns a plain `CommandResult` (no `action`) if usage data is unavailable.

**`_handle_diff` / `_handle_tooldiff`** — Takes two optional record IDs. If both are provided, looks up by ID. If neither or only one is provided, uses the two most recently finalized records. Returns an error if fewer than 2 records exist.

**`_handle_compare`** — Does **not** perform a comparison directly. Returns `CommandResult(action="compare_request", extra={"aliases": rest, "debug_compare": True})`. The TUI intercepts this and fires the compare worker, which passes `debug_compare=True` to produce a technical comparison table via `format_compare_table()`.

**`_handle_replay`** — Parses optional `--provider <alias>` flag and optional record ID from `rest`. Returns `CommandResult(action="replay_stream", extra={"record_id": ..., "provider_alias": ...})`. The TUI's `_replay_debug_stream()` worker handles actual re-execution.

**`_handle_export`** — Reads `ctx.paths.debug_exports_dir`, generates a timestamped filename (`debug_YYYYMMDD_HHMMSS.json` or `.txt`), and calls either `dm.export_json()` or `dm.export_txt()`. Export directory is `$XDG_DATA_HOME/anythink/debug_exports/`.

**`_handle_routing` / `_handle_plan` / `_handle_ratelimit`** (V4 MMOS handlers) — Read fields from the latest record that are populated only when the MMOS optimization engine is active. Return guidance messages when the relevant data is absent.

---

### `register_debug_commands(registry: CommandRegistry) -> None`

**Location:** `commands.py:634`

The sole public function in this file. Called during app startup to register one `SlashCommand`:

```python
SlashCommand(
    "debug",
    "Debug mode and inspection tools",
    _debug_handler,
    "/debug [on|off|toggle|level 1-3|panel|prompt|timing|...]",
)
```

All subcommands are dispatched inside `_debug_handler`; there is only one registered slash command entry for the entire `/debug` namespace.

---

## Verbosity levels

| Level | What is captured |
|---|---|
| 1 | Timing, stop reason, usage, tool calls, plugin events |
| 2 (default) | All of Level 1 + RAG results + embedding metadata + HTTP log entry (if API logging on) |
| 3 | All of Level 2 + per-token stream trace in `token_trace` |

The level controls which instrumentation code in `_stream_response()` actually fires. Level 3 has measurable overhead because it appends one `TokenEntry` per token.

---

## TUI integration: action signals

All `CommandResult` objects returned from `commands.py` that carry an `action` field are handled by `_dispatch_command()` in `app.py`. The debug-specific action values:

| `action` value | TUI behavior |
|---|---|
| `"debug_display"` | Renders `result.message` in a debug overlay widget |
| `"debug_hud_update"` | Refreshes the HUD to show/hide the `[DEBUG L2]` indicator |
| `"debug_panel_toggle"` | Calls `toggle_panel()` on `DebugManager` and shows/hides `DebugPanel` |
| `"replay_stream"` | Fires `_replay_debug_stream(record_id, provider_alias)` background worker |
| `"compare_request"` | Fires the compare worker with `debug_compare=True` |

---

## Lifecycle: how a record is built

```
_stream_response() begins
  └── [if is_active()]
        ├── dm.begin_request(...)        → allocates RequestDebugRecord, stores as _pending_record
        │     record.t_start = t0
        │
        ├── prompt assembled
        │     record.t_prompt_assembled = time.monotonic()
        │
        ├── [if RAG active]
        │     record.t_rag_start = ...
        │     record.rag_query = ...
        │     record.rag_results = ...
        │     record.t_rag_end = ...
        │
        ├── [if search active]
        │     record.t_search_start = ...
        │     record.t_search_end = ...
        │
        ├── API call begins
        │     record.t_api_sent = time.monotonic()
        │
        ├── first token arrives
        │     record.t_first_token = time.monotonic()
        │
        ├── [if level == 3] each token:
        │     record.token_trace.append(TokenEntry(...))
        │
        ├── stream ends
        │     record.t_stream_end = time.monotonic()
        │     record.stop_reason = ...
        │     record.usage = ...
        │     record.tokens_per_second = ...
        │     record.was_stopped_by_user = ...
        │     record.agent_thinking = ...
        │
        ├── render completes
        │     record.t_render_end = time.monotonic()
        │
        └── dm.finalize_request(record)  → appended to _records deque
```

---

## Storage locations

| Artifact | Path |
|---|---|
| In-memory records (live session) | `DebugManager._records` (deque, max 100) |
| JSON export | `$XDG_DATA_HOME/anythink/debug_exports/debug_YYYYMMDD_HHMMSS.json` |
| Plain-text export | `$XDG_DATA_HOME/anythink/debug_exports/debug_YYYYMMDD_HHMMSS.txt` |
| HTTP traffic log | `$XDG_STATE_HOME/anythink/logs/api_debug.log` (rolling, max 50 MB + 2 backups) |

---

## Key design decisions

- **Always instantiated, never imported conditionally** — `DebugManager` lives in `AppContext` from startup. There is no conditional creation. The cost when inactive is a single `is_active()` boolean check at each instrumentation site.
- **Deferred imports in all handlers** — Every `commands.py` handler imports its formatter inside the function body. This avoids loading the formatters module at startup and means a syntax error in a formatter cannot prevent the app from launching.
- **Pure formatters, no TUI coupling** — All of `formatters.py` is dependency-free with respect to Textual. Formatters can be unit-tested by constructing a `RequestDebugRecord` and calling the function directly.
- **`TYPE_CHECKING` guards throughout** — `models.py`, `manager.py`, and `commands.py` all import heavy types (`RequestDebugRecord`, `GenerationParams`, `ChatState`) under `if TYPE_CHECKING:` only. At runtime, objects are passed by value through the call stack so no circular imports occur.
- **Auth masking at the logging layer** — `_mask_auth()` is applied in `_on_request` before anything is written to disk or stored. There is no code path that can log a real API key.
- **Record eviction** — Using `collections.deque(maxlen=100)` means eviction is automatic and O(1). There is no cleanup loop needed.
- **Export format** — JSON export uses `default=str` as the fallback serializer so `datetime`, `Path`, and other non-JSON-native types are serialized as strings without raising exceptions.
