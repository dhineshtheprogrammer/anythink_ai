# `src/anythink/mcp/` — Model Context Protocol Layer

This module implements Anythink's full MCP (Model Context Protocol) integration.
It covers four orthogonal concerns:

1. **Inbound tool use** — built-in servers that expose Anythink capabilities
   (filesystem, RAG, web search, sessions) as MCP tools callable by any
   MCP-aware agent or slash command.
2. **Outbound connections** — `MCPClient` connects to external MCP servers
   (via stdio or SSE), discovers their tools, and proxies calls to them.
3. **Serving** — `AnythinkMCPServer` flips the role: Anythink itself becomes
   an MCP server so external agents can call its built-in tools over SSE.
4. **Windows OS integration** — ten Windows-only built-in servers give the AI
   audited, permission-controlled access to the Windows operating system: file
   management, Explorer, app launching, window control, process management,
   system info, settings, clipboard, screenshots, and desktop notifications.

The `mcp` SDK is an optional dependency (`pip install anythink[mcp]`). All SDK
imports are deferred inside methods so the rest of Anythink works without it.
Built-in servers require no SDK at all — they are pure Python.
Windows servers require `pip install anythink[windows]` and only activate when
`config.windows_enabled = True` on a Windows host.

---

## Folder Structure

```
src/anythink/mcp/
├── __init__.py                    Package marker
├── models.py                      Shared data models (MCPTool, MCPCallResult, etc.)
├── manager.py                     MCPManager — central registry and dispatcher
├── client.py                      MCPClient — outbound connection to one external server
├── server.py                      AnythinkMCPServer — run Anythink as an MCP server
│
├── builtin/                       All built-in server implementations
│   ├── __init__.py                Sub-package marker
│   ├── base.py                    BuiltinMCPServer ABC
│   ├── filesystem.py              FilesystemServer — list_dir, read_file
│   ├── rag.py                     RAGServer — rag_search
│   ├── search.py                  SearchServer — web_search
│   ├── sessions.py                SessionsServer — list_sessions, get_session
│   │
│   ├── windows_filesystem.py      WindowsFilesystemServer — 13 tools, full file CRUD
│   ├── windows_explorer.py        WindowsExplorerServer — 4 tools, File Explorer control
│   ├── windows_apps.py            WindowsAppsServer — 2 tools, app discovery & launch
│   ├── windows_window.py          WindowsWindowServer — 7 tools, window control
│   ├── windows_process.py         WindowsProcessServer — 4 tools, process management
│   ├── windows_system.py          WindowsSystemServer — 8 tools, system info
│   ├── windows_settings.py        WindowsSettingsServer — 11 tools, OS settings
│   ├── windows_clipboard.py       WindowsClipboardServer — 3 tools, clipboard R/W
│   ├── windows_screenshot.py      WindowsScreenshotServer — 3 tools, screen capture
│   └── windows_notification.py    WindowsNotificationServer — 4 tools, toast alerts
│
└── windows/                       Windows cross-cutting infrastructure
    ├── __init__.py                Re-exports: WindowsAuditLog, WindowsPathGuard, WindowsSafetyChecker
    ├── safety.py                  WindowsSafetyChecker — four-tier classification
    ├── paths.py                   WindowsPathGuard — allowed/blocked path enforcement
    └── audit.py                   WindowsAuditLog — persistent JSONL audit log
```

**Total Windows tools: 59** across 10 servers. All 59 tool names are unique
within the `_tool_index`.

---

## File-by-File Reference

---

### `__init__.py`

**Purpose:** Makes `anythink.mcp` a Python package.

**Contents:**
```python
"""Model Context Protocol: client, server, and built-in servers."""
```

Nothing is re-exported. Callers import directly from submodules.

---

### `models.py`

**Purpose:** All shared data classes that flow between the manager, clients,
built-in servers, slash commands, and the TUI. Defines the wire types for tool
definitions, call results, server metadata, and connection config.

---

#### `MCPTool` (dataclass)

Represents a single tool advertised by any MCP server (built-in or external).

| Field          | Type              | Description |
|----------------|-------------------|-------------|
| `name`         | `str`             | Unique tool name used as the dispatch key (e.g. `"list_dir"`) |
| `description`  | `str`             | Human-readable description shown in `/mcp tools` |
| `input_schema` | `dict[str, Any]`  | JSON Schema fragment describing accepted arguments |
| `server_name`  | `str`             | Name of the server that owns this tool (must equal `server.name`) |

---

#### `MCPCallResult` (dataclass)

The outcome of invoking any MCP tool.

| Field        | Type    | Default | Description |
|--------------|---------|---------|-------------|
| `tool_name`  | `str`   | —       | Name of the tool that was called |
| `server_name`| `str`   | —       | Server that handled the call |
| `content`    | `str`   | —       | Text output of the tool (or error message) |
| `is_error`   | `bool`  | `False` | `True` when the tool returned an error or raised |
| `duration_s` | `float` | `0.0`   | Wall-clock call duration in seconds (monotonic) |

`content` is always a plain string regardless of tool type. Multi-item results
are newline-joined by the caller.

---

#### `MCPServerInfo` (dataclass)

A snapshot of one registered server's metadata, returned by
`MCPManager.list_servers()`. Consumed by the TUI stats panel and `/mcp status`.

| Field        | Type   | Default | Description |
|--------------|--------|---------|-------------|
| `name`       | `str`  | —       | Server name |
| `kind`       | `str`  | —       | `"builtin"` or `"external"` |
| `transport`  | `str`  | —       | `"builtin"`, `"stdio"`, or `"sse"` |
| `connected`  | `bool` | `True`  | Whether the server is currently connected |
| `tool_count` | `int`  | `0`     | Number of tools this server exposes |
| `command`    | `str`  | `""`    | Subprocess command (stdio servers only) |
| `url`        | `str`  | `""`    | SSE endpoint URL (SSE servers only) |
| `description`| `str`  | `""`    | Human-readable description (built-in servers only) |

---

#### `MCPConnectConfig` (dataclass)

Parameters passed to `MCPManager.connect()` to establish an outbound connection
to an external MCP server.

| Field       | Type        | Default | Description |
|-------------|-------------|---------|-------------|
| `name`      | `str`       | —       | Logical name for this connection (used as the dict key) |
| `transport` | `str`       | —       | `"stdio"` or `"sse"` |
| `command`   | `str`       | `""`    | Shell command to launch (stdio only; split on whitespace) |
| `url`       | `str`       | `""`    | Full SSE endpoint URL (sse only) |
| `args`      | `list[str]` | `[]`    | Extra arguments appended after the command's own args (stdio only) |

---

### `manager.py`

**Purpose:** The central orchestrator for all MCP activity. `MCPManager` holds
references to every registered built-in server and every connected external
client, maintains a flat `_tool_index` for O(1) routing, and is the single
entry point for tool discovery and dispatch.

Stored in `AppContext` as `ctx.mcp_manager`. Constructed once at startup in
`app/context.py` with all built-in servers pre-registered.

---

#### `MCPManager`

**Constructor**

```python
def __init__(self, builtin_servers: list[BuiltinMCPServer] | None = None) -> None
```

Initialises three internal dicts and calls `register_builtin()` for each item
in `builtin_servers`:

| Attribute        | Type                              | Purpose |
|------------------|-----------------------------------|---------|
| `_builtins`      | `dict[str, BuiltinMCPServer]`     | Built-in servers keyed by `server.name` |
| `_externals`     | `dict[str, MCPClient]`            | External clients keyed by connection name |
| `_tool_index`    | `dict[str, str]`                  | `tool_name → server_name` for O(1) dispatch |

**Important:** `MCPClient` is only imported inside `connect()` (not at module
level), keeping the mcp SDK optional for the import-time code path.

---

##### Registration

**`register_builtin(server: BuiltinMCPServer) -> None`**

Stores `server` under `_builtins[server.name]` and adds every tool it
advertises to `_tool_index`. Called at startup for built-in servers and can be
called at runtime to add more.

---

##### External Connections

**`async connect(config: MCPConnectConfig) -> None`**

Connects to an external MCP server:

1. If a server with `config.name` is already connected, calls `disconnect()`
   first (reconnect semantics).
2. Creates an `MCPClient` with the transport params from `config`.
3. Awaits `client.connect()` — opens the transport and calls `session.list_tools()`.
4. Stores the client in `_externals` and indexes its tools in `_tool_index`.

**`async disconnect(name: str) -> None`**

Disconnects an external server:

1. Raises `MCPError` if `name` is not in `_externals`.
2. Pops the client and awaits `client.disconnect()`.
3. Removes all tools belonging to `name` from `_tool_index` via a dict comprehension.

---

##### Queries

**`list_servers() -> list[MCPServerInfo]`**

Returns a combined list of `MCPServerInfo` objects — built-in servers first,
then external clients — with live `tool_count` and `connected` values.

**`list_tools() -> list[MCPTool]`**

Returns every tool from every registered server: iterates `_builtins.values()`
and calls `server.list_tools()`, then extends with `client.cached_tools` for
each external client.

**`get_tool(name: str) -> MCPTool | None`**

Linear scan of `list_tools()`. Returns the first matching tool or `None`.

---

##### Dispatch

**`async call_tool(tool_name: str, arguments: dict[str, Any]) -> MCPCallResult`**

The primary dispatch method. Routing logic:

```
1. Look up tool_name in _tool_index → server_name
   └── Not found → return MCPCallResult(is_error=True, "Unknown tool...")

2. If server_name in _builtins → await _builtins[server_name].call_tool(...)
3. If server_name in _externals → await _externals[server_name].call_tool(...)
4. Fallback → MCPCallResult(is_error=True, "Server no longer connected")
```

Step 4 handles the race where a server was indexed but then disconnected before
the call arrived.

---

**Startup wiring in `app/context.py`:**

```python
mcp_manager = MCPManager(
    builtin_servers=[
        FilesystemServer(),
        SessionsServer(session_manager),
        RAGServer(rag_manager, emb),
        SearchServer(search_reg, preferred=config.search_provider),
        *_build_windows_servers(config, resolved),   # empty list when disabled/non-Windows
    ]
)
```

`_build_windows_servers(config, paths)` is a module-level factory in
`app/context.py` that returns an empty list when `sys.platform != "win32"` or
`config.windows_enabled == False`, and returns 10 fully wired Windows server
instances otherwise. All Windows imports are deferred inside this function so
non-Windows environments never import Windows-only code.

---

### `client.py`

**Purpose:** `MCPClient` manages the full lifecycle of a connection to a single
external MCP server — opening the transport, initialising the protocol session,
caching the tool list, proxying calls, and tearing down cleanly.

Requires `pip install anythink[mcp]` for actual use. The `mcp` SDK is imported
lazily inside `connect()` so that importing this module never fails.

---

#### `MCPClient`

**Constructor**

```python
def __init__(
    self,
    name: str,
    transport: str,          # "stdio" | "sse"
    *,
    command: str = "",       # stdio: command string to split and launch
    url: str = "",           # sse: full endpoint URL
    args: list[str] | None = None,  # extra CLI args appended after command
) -> None
```

Sets `self.name`, `self.transport`, stores connection params, and initialises:
- `self._tools: list[MCPTool] = []` — populated after `connect()`
- `self._session: Any = None` — the active `mcp.ClientSession`
- `self._exit_stack: contextlib.AsyncExitStack | None` — manages transport lifetime

**Properties**

| Property        | Type              | Description |
|-----------------|-------------------|-------------|
| `tool_count`    | `int`             | `len(self._tools)` |
| `cached_tools`  | `list[MCPTool]`   | Copy of the tool list fetched during `connect()` |
| `is_connected`  | `bool`            | `True` when `self._session is not None` |

---

**`async connect() -> None`**

Opens the transport, initialises the MCP session, and fetches the tool list.

**Transport: `"stdio"`**

1. Lazy-imports `mcp.ClientSession` and `mcp.StdioServerParameters`,
   `mcp.client.stdio.stdio_client`.
2. Splits `self._command` on whitespace; raises `MCPError` if empty.
3. Builds `StdioServerParameters(command=parts[0], args=parts[1:] + self._args)`.
4. Enters `stdio_client(params)` into the `AsyncExitStack`, getting
   `(read, write)` streams.

**Transport: `"sse"`**

1. Lazy-imports `mcp.client.sse.sse_client`.
2. Raises `MCPError` if `self._url` is empty.
3. Enters `sse_client(self._url)` into the `AsyncExitStack`, getting
   `(read, write)` streams.

**After transport opens (both):**

```python
session = await stack.enter_async_context(ClientSession(read, write))
await session.initialize()
self._session = session
self._exit_stack = stack

response = await session.list_tools()
self._tools = [MCPTool(name=t.name, ..., server_name=self.name) for t in response.tools]
```

The `AsyncExitStack` is the key resource-management construct: entering all
contexts into it means a single `stack.aclose()` in `disconnect()` cleans up
the session, the transport, and the subprocess (stdio) or HTTP connection (SSE)
in the correct order.

---

**`async disconnect() -> None`**

Closes the exit stack (which cleans up all entered contexts in reverse order),
then resets `_exit_stack`, `_session`, and `_tools` to their initial state.
Safe to call even if already disconnected.

---

**`async call_tool(name: str, arguments: dict[str, Any]) -> MCPCallResult`**

1. Returns an error `MCPCallResult` immediately if `_session is None`.
2. Calls `await self._session.call_tool(name, arguments)` with a monotonic timer.
3. On any exception: returns `MCPCallResult(is_error=True, content=str(exc), ...)`.
4. On success: extracts text from `result.content` items that have a `.text`
   attribute, joins with `"\n"`, and returns `MCPCallResult(is_error=result.isError, ...)`.
   `duration_s` is rounded to 3 decimal places.

---

### `server.py`

**Purpose:** Flips Anythink's role — instead of consuming MCP tools,
`AnythinkMCPServer` exposes Anythink's own built-in tools as an MCP server
that external agents can connect to over SSE.

Requires `pip install anythink[mcp]` (uses `mcp.server.fastmcp.FastMCP`).
The SDK is imported lazily inside `start()`.

---

#### `AnythinkMCPServer`

**Constructor**

```python
def __init__(self, mcp_manager: MCPManager) -> None
```

Stores `self._manager = mcp_manager`. Initialises `_running = False` and
`_address = ""`.

**Properties**

| Property    | Type   | Description |
|-------------|--------|-------------|
| `is_running`| `bool` | Whether the server has been started |
| `address`   | `str`  | The SSE URL clients connect to (e.g. `"http://localhost:8765/sse"`) |

---

**`async start(host: str = "localhost", port: int = 8765) -> str`**

1. Lazy-imports `mcp.server.fastmcp.FastMCP`; raises `MCPError` if absent.
2. Creates `app = FastMCP("Anythink")`.
3. Registers two tools on the FastMCP app:

   **`call_anythink_tool(tool_name: str, arguments: str) -> str`**
   - Parses `arguments` as JSON (returns an error string on `JSONDecodeError`).
   - Delegates to `manager.call_tool(tool_name, args)`.
   - Returns `result.content`.

   **`list_anythink_tools() -> str`**
   - Calls `manager.list_tools()`.
   - Returns newline-joined `"<name> (<server>): <description>"` lines.

4. Sets `self._running = True` and `self._address = f"http://{host}:{port}/sse"`.
5. Returns the address string.

**Note on background execution:** The current implementation uses a placeholder
`asyncio.get_event_loop().run_in_executor(None, lambda: None)` for non-blocking
startup. The actual FastMCP server startup is not yet wired to a live asyncio
task — this is a known scaffold.

---

**`async stop() -> None`**

Resets `_running = False` and `_address = ""`. Does not send a shutdown signal
to the FastMCP app in the current implementation.

---

**TUI wiring:** The `/mcp server start` slash command creates an
`AnythinkMCPServer(mgr)`, awaits `srv.start()`, and returns
`action="mcp_server_started"` with `extra={"address": address}`. The TUI's
`_dispatch_command` logs the address.

---

### `builtin/base.py`

**Purpose:** Defines `BuiltinMCPServer`, the abstract base class all built-in
servers inherit from.

---

#### `BuiltinMCPServer` (ABC)

```python
class BuiltinMCPServer(ABC):
    name: str = ""
    description: str = ""
```

Built-in servers require **no mcp SDK and no network transport** — they run
in-process as pure Python objects.

**Class attributes** (must be set on each subclass)

| Attribute     | Type  | Description |
|---------------|-------|-------------|
| `name`        | `str` | Machine-readable server name; used as the registry key in `MCPManager` |
| `description` | `str` | Human-readable description shown in `/mcp status` |

**Abstract methods**

```python
def list_tools(self) -> list[MCPTool]
```
Returns the complete list of tools this server exposes. Called at registration
time by `MCPManager.register_builtin()` to populate `_tool_index`.

```python
async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult
```
Dispatches a tool call by name with the given arguments. Must always return an
`MCPCallResult` — never raise (errors are returned as `is_error=True` results).

**Implementation pattern followed by all subclasses:**
```python
async def call_tool(self, name, arguments):
    t0 = time.monotonic()
    try:
        content = await self._dispatch(name, arguments)
        return MCPCallResult(tool_name=name, server_name=self.name,
                             content=content, duration_s=round(time.monotonic()-t0, 3))
    except Exception as exc:
        return MCPCallResult(tool_name=name, server_name=self.name,
                             content=str(exc), is_error=True,
                             duration_s=round(time.monotonic()-t0, 3))
```

---

### `builtin/filesystem.py`

**Purpose:** Exposes two filesystem operations as MCP tools. Requires no
dependencies beyond the Python standard library.

Also used directly by the TUI file browser panel outside the MCP dispatch path —
it instantiates `FilesystemServer()` directly and calls `call_tool("list_dir", ...)`.

---

#### `FilesystemServer(BuiltinMCPServer)`

```
name        = "filesystem"
description = "Read and list local files."
```

**Module-level constant:** `_MAX_READ_CHARS = 8_000`

**Tools exposed**

| Tool name   | Description | Arguments |
|-------------|-------------|-----------|
| `list_dir`  | List files and directories at the given path | `path: str` (default `"."`) |
| `read_file` | Read a text file and return its content | `path: str`, `max_chars: int` (default `8000`) |

`_list_dir` sorts entries: directories first, then files (case-insensitive
within each group), formatted as `[D] <name>` or `[F] <name>`.
`_read_file` reads with `encoding="utf-8", errors="replace"` and appends a
truncation notice when content exceeds `max_chars`.

---

### `builtin/rag.py`

**Purpose:** Bridges the active RAG index into the MCP tool space, allowing any
MCP-aware agent to perform semantic search over Anythink's vector store.

#### `RAGServer(BuiltinMCPServer)`

```
name        = "rag"
description = "Search the active RAG index for relevant content."
```

**Constructor:** `__init__(rag_manager: RAGManager, embedding_backend: BaseEmbeddingBackend | None = None)`

**Tools exposed**

| Tool name    | Description | Arguments |
|--------------|-------------|-----------|
| `rag_search` | Search the active RAG index and return the most relevant chunks | `query: str`, `top_k: int` (default `5`) |

Call flow: checks `rag.is_active` → checks `emb is not None` → awaits
`rag.retrieve(query, emb, top_k)` → formats chunks as
`"[source]\nchunk_text\n(relevance: 0.xxx)"` joined with `"\n\n---\n\n"`.

---

### `builtin/search.py`

**Purpose:** Bridges the `SearchRegistry` (DuckDuckGo / SerpAPI / any backend)
into the MCP tool space.

#### `SearchServer(BuiltinMCPServer)`

```
name        = "search"
description = "Search the web using the configured search backend."
```

**Constructor:** `__init__(search_registry: SearchRegistry, preferred: str = "duckduckgo")`

**Tools exposed**

| Tool name    | Description | Arguments |
|--------------|-------------|-----------|
| `web_search` | Search the web and return titles, URLs, and snippets | `query: str`, `max_results: int` (default `5`) |

Call flow: `registry.get_available(preferred)` → `await backend.search(query)` →
formats up to `max_results` entries as `"<title>\n<url>\n  <snippet[:200]>"`.

---

### `builtin/sessions.py`

**Purpose:** Exposes saved Anythink conversation sessions as MCP tools.

#### `SessionsServer(BuiltinMCPServer)`

```
name        = "sessions"
description = "List and retrieve saved Anythink conversation sessions."
```

**Constructor:** `__init__(session_manager: SessionManager)`

**Module-level constant:** `_MAX_MESSAGES = 20`

**Tools exposed**

| Tool name       | Description | Arguments |
|-----------------|-------------|-----------|
| `list_sessions` | List all saved sessions with IDs, names, and message counts | *(none)* |
| `get_session`   | Retrieve recent messages from a session | `id_or_name: str`, `last_n: int` (default `20`) |

`list_sessions` formats a right-aligned table of 8-char truncated IDs, message
counts, and names. `get_session` truncates each message to 300 characters with
a trailing `…`.

---

## Windows MCP Infrastructure (`mcp/windows/`)

The three classes in `mcp/windows/` are shared cross-cutting components
injected into every Windows builtin server. They are only instantiated when
`_build_windows_servers()` runs (i.e. Windows + `windows_enabled = True`).

---

### `windows/safety.py` — `WindowsSafetyChecker`

**Purpose:** Classifies every Windows tool call into one of four safety tiers
before execution. The tier determines whether the operation proceeds
automatically, follows the user's autonomy mode setting, requires an explicit
confirmation, or requires double confirmation.

**Four tiers:**

| Tier | Name | Behaviour | Examples |
|------|------|-----------|---------|
| 1 | Auto-allowed | Proceeds immediately, no confirmation | All read-only tools: `list_dir`, `get_cpu_info`, `read_clipboard` |
| 2 | Autonomy mode | `"auto"` → no prompt; `"ask"` → confirmation | `write_file` (new), `launch_app`, `send_notification`, `take_screenshot` |
| 3 | Always confirm | Confirmation required regardless of autonomy mode | `delete_file`, `kill_process`, `set_volume`, `close_window` |
| 4 | Double confirm | Two separate confirmations; user types `"confirm"` | `delete_folder` with `recursive=True`, bulk deletions |

**Dynamic tier overrides** (evaluated at call time):

| Tool | Condition | Effective tier |
|------|-----------|---------------|
| `write_file` | File does not exist | 2 |
| `write_file` | File exists or `overwrite=True` | 3 |
| `copy_file` | Destination does not exist | 2 |
| `copy_file` | Destination exists or `overwrite=True` | 3 |
| `delete_folder` | `recursive=False` | 3 |
| `delete_folder` | `recursive=True` | 4 |

**Key methods:**

| Method | Signature | Returns |
|--------|-----------|---------|
| `get_tier` | `(server_name, tool_name, **kwargs) -> int` | Tier 1–4 after applying dynamic overrides |
| `is_auto_allowed` | `(tier) -> bool` | `True` when `tier == 1` |
| `requires_double_confirm` | `(tier) -> bool` | `True` when `tier >= 4` |
| `build_confirmation_prompt` | `(tier, operation, server, target, consequence) -> str` | Rich-formatted confirmation box |
| `all_tiers` | `() -> dict[str, dict[str, int]]` | Full static tier table (all 59 tools) |

---

### `windows/paths.py` — `WindowsPathGuard`

**Purpose:** Single gatekeeper for all filesystem operations. Every path passed
to a Windows filesystem or Explorer tool is validated before execution. A
rejected path returns an `MCPCallResult(is_error=True)` immediately — no
confirmation prompt is shown.

**Validation order (checked in sequence):**

1. **Non-removable system blocked** — hardcoded frozenset (`C:\Windows\`,
   `C:\Windows\System32\`, `C:\Windows\SysWOW64\`, `C:\Program Files\`,
   `C:\Program Files (x86)\`, `C:\ProgramData\Microsoft\`). Cannot be
   removed at runtime.
2. **User-configured blocked** — loaded from `config.windows_blocked_paths`;
   mutable at runtime via `add_blocked` / `remove_blocked`.
3. **User-configured allowed** — loaded from `config.windows_allowed_paths`;
   defaults to `Documents\`, `Desktop\`, `Downloads\` when the config list is
   empty. Operations must match at least one allowed prefix.

**Path normalization:** `os.path.normcase(os.path.abspath(path)) + os.sep`
prevents path traversal (`..`) bypass and handles case-insensitivity on Windows.

**Constructor:** `__init__(config: AppConfig)`

**Key methods:**

| Method | Returns | Notes |
|--------|---------|-------|
| `validate(path) -> str \| None` | Error message or `None` | `None` = allowed |
| `add_allowed(path)` | — | Deduplicates |
| `remove_allowed(path) -> bool` | `True` if removed | |
| `add_blocked(path)` | — | Deduplicates |
| `remove_blocked(path) -> bool` | `True` if removed, `False` if system path | Non-removable system paths always return `False` |
| `allowed_paths` (property) | `list[str]` | Current allowed list (normalized) |
| `blocked_paths` (property) | `list[str]` | Current user blocked list |
| `system_blocked_paths` (property) | `list[str]` | Sorted non-removable blocked paths |

**Config persistence:** Callers that mutate the guard at runtime persist changes
via `dataclasses.replace(ctx.config, windows_allowed_paths=tuple(guard.allowed_paths))`
followed by `ctx.config_manager.save(new_cfg); ctx.config = new_cfg`.

---

### `windows/audit.py` — `WindowsAuditLog`

**Purpose:** Persistent JSONL audit log that records every Windows MCP tool call
— succeeded, failed, confirmed, or cancelled — to a rolling log file.

**Storage:** `$XDG_STATE_HOME/anythink/logs/windows_audit.log`
(default: `%LOCALAPPDATA%\anythink\logs\windows_audit.log`).
Rolling rotation: 10 MB per file, 5 backup files retained (50 MB total).

**Constructor:** `__init__(log_path: str)` — creates parent dirs, configures a
`logging.handlers.RotatingFileHandler` with JSONL formatter.

**Log record format** (one JSON object per line):

```json
{
  "timestamp": "2025-06-18T14:32:11.421Z",
  "session_id": "a1b2c3d4",
  "server": "windows-filesystem",
  "tool": "delete_file",
  "tier": 3,
  "arguments": {"path": "C:\\Users\\..."},
  "confirmation_status": "confirmed",
  "outcome": "success",
  "duration_s": 0.012,
  "error": null
}
```

**`confirmation_status` values:** `"not_required"` (Tier 1), `"auto"` (Tier 2
in auto mode), `"confirmed"`, `"cancelled"`, `"blocked_by_path_guard"`.

**`outcome` values:** `"success"`, `"error"`, `"blocked_by_path_guard"`,
`"cancelled_by_user"`.

**Key methods:**

| Method | Description |
|--------|-------------|
| `log(session_id, server, tool, tier, arguments, confirmation_status, outcome, duration_s, error=None)` | Appends one JSONL record |
| `get_recent(n=20, tool_filter=None, date_filter=None) -> list[dict]` | Reads log in reverse, parses and filters; `date_filter="today"` matches UTC date prefix |
| `export_to_text(output_path)` | Writes a formatted table of all records to a file |
| `clear()` | Closes handler → truncates file → re-opens handler |
| `log_path` (property) | `str` — absolute path to the current log file |

---

## Windows Built-in Servers

All Windows servers follow these invariants:

- **Windows-only guard:** Every `_dispatch()` begins with
  `if not _WINDOWS_ONLY: return _WIN_ERR` where `_WIN_ERR` reports the current
  platform. The server registers and imports cleanly on non-Windows.
- **Deferred imports:** Every Windows API import (`pywin32`, `psutil`,
  `pygetwindow`, etc.) is deferred inside the method body, wrapped in
  `try/except ImportError` that returns a user-friendly install hint.
- **Audit logging:** Every `call_tool` call is logged to `WindowsAuditLog`
  whether it succeeds, fails, or is blocked by the path guard.
- **Tier classification:** Every `call_tool` calls `safety.get_tier()` before
  execution; the tier is recorded in the audit log.

---

### `builtin/windows_filesystem.py` — `WindowsFilesystemServer`

```
name        = "windows-filesystem"
description = "Full file and folder management on Windows within allowed paths."
```

**Constructor:** `(path_guard: WindowsPathGuard, safety: WindowsSafetyChecker, audit: WindowsAuditLog)`

All 13 tools validate their path argument(s) through `path_guard.validate()`
before executing. A rejected path returns an error immediately with outcome
`"blocked_by_path_guard"` in the audit log.

**Tools exposed (13 total):**

| Tool | Tier | Description |
|------|------|-------------|
| `list_dir` | 1 | List directory contents with icons, types, and sizes. `show_hidden: bool = False` |
| `read_file` | 1 | Read text file content (max 50,000 chars, truncation notice appended) |
| `get_file_metadata` | 1 | Size, created/modified/accessed timestamps, read/write permissions |
| `search_files_by_name` | 1 | `os.walk` + `fnmatch`, depth ≤ 5, max 200 results |
| `search_files_by_content` | 1 | Case-insensitive substring search, text-extension filter, depth ≤ 5 |
| `write_file` | 2/3 | Write text (10 MB cap). Tier 2 if new file; Tier 3 if overwriting |
| `create_file` | 2 | Create empty file; creates parent dirs if needed |
| `create_folder` | 2 | `mkdir(parents=True)`; `exist_ok: bool = True` |
| `copy_file` | 2/3 | `shutil.copy2`. Tier 2 if new destination; Tier 3 if overwriting |
| `move_file` | 3 | `shutil.move` — validates source path; creates destination parent |
| `rename_file` | 3 | Renames within the same directory; `new_name` must be filename only |
| `delete_file` | 3 | `Path.unlink()` — permanent deletion |
| `delete_folder` | 3/4 | Tier 3 if empty (`rmdir`); Tier 4 if `recursive=True` (`shutil.rmtree`) |

**Module-level constant:** `_TOOL_NAMES: frozenset[str]` — all 13 tool names for
test assertions.

---

### `builtin/windows_explorer.py` — `WindowsExplorerServer`

```
name        = "windows-explorer"
description = "Open and navigate Windows File Explorer; open files with their default applications."
```

**Constructor:** `(path_guard: WindowsPathGuard, safety: WindowsSafetyChecker, audit: WindowsAuditLog)`

All four tools are Tier 2. Paths are validated through `path_guard` before
any shell interaction.

**Tools exposed (4 total):**

| Tool | Description | Implementation |
|------|-------------|----------------|
| `open_folder_in_explorer` | Open folder in a new File Explorer window | `subprocess.Popen(["explorer.exe", path])` |
| `navigate_explorer_to_path` | Open Explorer navigated to a path | `subprocess.Popen(["explorer.exe", path])` (new window) |
| `open_file_with_default_app` | Open file with its registered default app | `os.startfile(path)` (ShellExecute `"open"` verb) |
| `select_files_in_explorer` | Open Explorer with files pre-selected | `win32com.shell.shell.SHOpenFolderAndSelectItems`; fallback to `/select,` flag |

---

### `builtin/windows_apps.py` — `WindowsAppsServer`

```
name        = "windows-apps"
description = "Launch installed Windows applications by name."
```

**Constructor:** `(safety, audit, blocked_apps=(...defaults...), cache_ttl_minutes=60)`

**Tools exposed (2 total):**

| Tool | Tier | Description |
|------|------|-------------|
| `list_installed_apps` | 1 | Discover and list installed applications |
| `launch_app` | 2 | Launch by name using fuzzy matching |

**App discovery** (`list_installed_apps`): Reads from four sources and
deduplicates:

1. `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` (MSI apps)
2. `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` (user-scope apps)
3. `HKLM\SOFTWARE\WOW6432Node\...` (32-bit apps on 64-bit Windows)
4. `%PATH%` directories (all `.exe` executables found)

Results are cached in-memory with a TTL (default 60 minutes). Call
`server.invalidate_cache()` to force a rebuild.

**Fuzzy launch** (`launch_app`): Uses `difflib.get_close_matches(name,
app_names, n=3, cutoff=0.6)`. Falls back to case-insensitive substring matching
if no fuzzy results. Applications in `blocked_apps` are rejected even if matched.

---

### `builtin/windows_window.py` — `WindowsWindowServer`

```
name        = "windows-window"
description = "List, focus, resize, and interact with open Windows application windows."
```

**Constructor:** `(safety, audit, gui_mode: bool = False)`

**Tools exposed (7 total):**

| Tool | Tier | Description |
|------|------|-------------|
| `list_open_windows` | 1 | All visible windows with title and state (Normal/Minimized/Maximized) |
| `bring_to_foreground` | 2 | Focus and raise a window |
| `minimize_window` | 2 | Minimize to taskbar |
| `maximize_window` | 2 | Fill screen |
| `restore_window` | 2 | Return to normal size |
| `close_window` | 3 | Send `WM_CLOSE` via `win32api.SendMessage` |
| `send_text_to_window` | 3 | Type text via `pyautogui.typewrite`. **GUI mode required.** Returns error when `gui_mode=False` |

**Window matching:** `pygetwindow.getWindowsWithTitle(title)` exact match first;
falls back to case-insensitive substring scan of all windows via `getAllWindows()`.

---

### `builtin/windows_process.py` — `WindowsProcessServer`

```
name        = "windows-process"
description = "List, start, and stop Windows processes."
```

**Constructor:** `(safety, audit, blocked_apps=(...defaults...))`

**Tools exposed (4 total):**

| Tool | Tier | Description |
|------|------|-------------|
| `list_processes` | 1 | All running processes via `psutil.process_iter`, sorted by CPU% descending, top 50 shown |
| `get_process_info` | 1 | CPU%, RAM, username, command line for a specific process by PID or name |
| `start_process` | 2 | `subprocess.Popen` with optional `working_dir` and `detached` mode; returns PID |
| `kill_process` | 3 | SIGTERM → 5s wait → SIGKILL if `force=True`; rejects system-account processes |

**System process protection:** Processes owned by `NT AUTHORITY\SYSTEM`,
`NT AUTHORITY\LOCAL SERVICE`, or `NT AUTHORITY\NETWORK SERVICE` are always
protected — `kill_process` returns an error without attempting termination.
This protection is non-configurable.

**Blocked apps:** `start_process` checks the executable basename against
`blocked_apps` (same list as `WindowsAppsServer`) before launching.

---

### `builtin/windows_system.py` — `WindowsSystemServer`

```
name        = "windows-system"
description = "Read system hardware and OS information: CPU, RAM, disk, network, battery, and installed software."
```

**Constructor:** `(audit: WindowsAuditLog)` — no safety checker or path guard
needed (all tools are Tier 1 read-only).

**Tools exposed (8 total):**

| Tool | Description | Primary dependency |
|------|-------------|-------------------|
| `get_cpu_info` | Core count, speed, per-core usage | `psutil` |
| `get_ram_info` | Total/used/free RAM and swap | `psutil` |
| `get_disk_info` | All drives with total/used/free/filesystem | `psutil` |
| `get_battery_info` | Charge level, charging state, time remaining | `psutil` |
| `get_network_info` | All adapters with IPv4/IPv6/MAC and UP/DOWN status | `psutil` |
| `get_windows_version` | Edition, version string, build number, architecture | `platform`, `sys.getwindowsversion()` |
| `get_hardware_info` | CPU model, RAM total, BIOS vendor/version | `winreg`, `psutil` |
| `get_installed_apps` | Registry-sourced app list (quick read, unfiltered) | `winreg` |

---

### `builtin/windows_settings.py` — `WindowsSettingsServer`

```
name        = "windows-settings"
description = "Read and change Windows system settings: volume, display brightness, power plan, and time zone."
```

**Constructor:** `(safety, audit)`

**Tools exposed (11 total):**

| Tool | Tier | Description | Implementation |
|------|------|-------------|----------------|
| `get_volume` | 1 | Current volume 0–100 and mute state | PowerShell COM / `AudioEndpointVolume` |
| `set_volume` | 3 | Set volume 0–100 | `IAudioEndpointVolume` via PowerShell |
| `mute_audio` | 3 | Mute or unmute system audio | `IAudioEndpointVolume.SetMute()` via PowerShell |
| `get_brightness` | 1 | Display brightness 0–100 | WMI `WmiMonitorBrightness` |
| `set_brightness` | 3 | Set brightness 0–100 | WMI `WmiMonitorBrightnessMethods` |
| `get_power_plan` | 1 | Active power plan name and GUID | `powercfg /getactivescheme` |
| `list_power_plans` | 1 | All available power plans | `powercfg /list` |
| `set_power_plan` | 3 | Switch power plan by name | `powercfg /s <GUID>` |
| `get_timezone` | 1 | Current system time zone name | `tzutil /g` |
| `set_timezone` | 3 | Change time zone (requires admin) | `tzutil /s <name>` — returns clear error if not admin |
| `get_display_info` | 1 | Resolution, refresh rate, GPU name for all monitors | WMI `Win32_VideoController` via PowerShell |

---

### `builtin/windows_clipboard.py` — `WindowsClipboardServer`

```
name        = "windows-clipboard"
description = "Read from and write to the Windows clipboard."
```

**Constructor:** `(safety, audit)`

All clipboard operations use `win32clipboard.OpenClipboard(0)` /
`win32clipboard.CloseClipboard()` in a `try/finally` block to guarantee the
clipboard handle is released even on exception.

**Tools exposed (3 total):**

| Tool | Tier | Description | Notes |
|------|------|-------------|-------|
| `read_clipboard` | 1 | Read current text content | Non-text content returns a descriptive message; empty clipboard returns `"Clipboard is empty."` |
| `write_clipboard` | 2 | Write text (max 1 MB in UTF-16-LE encoding) | Audit logs first 100 characters of written text |
| `clear_clipboard` | 2 | Clear clipboard contents | `EmptyClipboard()` |

**Size cap:** `write_clipboard` rejects content where
`len(text.encode("utf-16-le")) > 1_048_576` with a helpful error.

---

### `builtin/windows_screenshot.py` — `WindowsScreenshotServer`

```
name        = "windows-screenshot"
description = "Capture screenshots of the full screen or a specific window and use them as conversation context."
```

**Constructor:** `(safety, audit, vision_capable: bool = False, gui_mode: bool = False, max_px: int = 1920, path_guard: WindowsPathGuard | None = None)`

`vision_capable` is set at startup by `_check_vision_capable(config)` in
`app/context.py`, which checks `config.default_model_alias` against known
vision-capable model ID fragments (Claude, GPT-4o, Gemini).

**Tools exposed (3 total):**

| Tool | Tier | GUI required | Description |
|------|------|-------------|-------------|
| `take_screenshot` | 2 | Yes | Full screen → inject into conversation |
| `take_window_screenshot` | 2 | Yes | Specific window by title → inject into conversation |
| `save_screenshot` | 2 | No | Capture screen → save to allowed file path |

**Screenshot pipeline:**

1. `PIL.ImageGrab.grab()` (full screen) or `ImageGrab.grab(bbox=...)` (window
   via `pygetwindow` bounds).
2. Auto-scale to `max_px` width (default 1920) using `Image.LANCZOS`.
3. If `vision_capable`: JPEG-encode → base64 → return `"[IMAGE_BASE64]data:image/jpeg;base64,..."`.
4. If not `vision_capable`: OCR via `pytesseract.image_to_string()` (if
   installed) → return extracted text.

`take_screenshot` and `take_window_screenshot` return error when `gui_mode=False`.
`save_screenshot` works in headless mode; path is validated through `path_guard`.

---

### `builtin/windows_notification.py` — `WindowsNotificationServer`

```
name        = "windows-notification"
description = "Send Windows desktop toast notifications on the user's behalf."
```

**Constructor:** `(safety, audit, app_name: str = "Anythink")`

`app_name` appears as the application name in the Windows notification center.
Set from `config.windows_notification_app_name` at startup.

**Scheduled notifications** are backed by `asyncio.Task` objects stored in
`self._scheduled: dict[str, asyncio.Task[None]]`. They persist for the session
duration only — not across Anythink restarts.

**Tools exposed (4 total):**

| Tool | Tier | Description |
|------|------|-------------|
| `send_notification` | 2 | Immediate toast notification. Uses `winotify` (preferred) → `win10toast` fallback → PowerShell WinRT fallback |
| `send_scheduled_notification` | 2 | Schedule a notification via `delay_seconds` or `at_time` string (see below) |
| `list_scheduled_notifications` | 1 | Show all pending tasks with IDs and status |
| `cancel_scheduled_notification` | 2 | Cancel a pending asyncio task by ID |

**`at_time` parsing** (`send_scheduled_notification`): Supports three formats:
- `"14:30"` — 24-hour HH:MM
- `"2:30 PM"` / `"9:00 AM"` — 12-hour with AM/PM suffix
- `"tomorrow 14:30"` / `"tomorrow 9:00 AM"` — adds one calendar day

Past times (without `"tomorrow"` prefix) roll to the next occurrence (+ 86400 s).
Invalid strings return `-1.0` and the tool returns an error.

---

## AppConfig — Windows Fields

Ten new fields added to `AppConfig` in `config/schema.py` control Windows MCP
behavior. All are `frozen=True` dataclass fields; mutation uses
`dataclasses.replace(ctx.config, field=val)` followed by `save` and reassign.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `windows_enabled` | `bool` | `False` | Master switch; `False` → no Windows servers registered |
| `windows_gui_mode` | `bool` | `False` | Enables GUI-only tools (`send_text_to_window`, screenshot injection) |
| `windows_allowed_paths` | `tuple[str, ...]` | `()` | AI-accessible paths; guard defaults to `Documents/Desktop/Downloads` when empty |
| `windows_blocked_paths` | `tuple[str, ...]` | `()` | User-added blocked paths; guard adds `AppData/Microsoft` when empty |
| `windows_blocked_apps` | `tuple[str, ...]` | `("regedit.exe", "cmd.exe", "powershell.exe", "mmc.exe")` | Apps that cannot be launched or started |
| `windows_audit_log_enabled` | `bool` | `True` | Enable/disable the audit log |
| `windows_audit_log_path` | `str` | `""` | Override audit log path; empty → XDG state dir default |
| `windows_screenshot_max_px` | `int` | `1920` | Maximum screenshot width before auto-scaling |
| `windows_notification_app_name` | `str` | `"Anythink"` | Name shown in Windows notification center |
| `windows_apps_cache_ttl_minutes` | `int` | `60` | How long the installed apps list is cached |

---

## TUI Integration

### The `/mcp` Slash Command — Full Sub-command Table

All `/mcp` sub-commands are dispatched from `_mcp()` in `commands/handlers.py`:

| Sub-command | What happens |
|-------------|-------------|
| `/mcp status` | `mgr.list_servers()` → formatted table |
| `/mcp list` | Same with more detail |
| `/mcp tools` | `mgr.list_tools()` → tool/server/description table |
| `/mcp call <tool> [key=value…]` | Returns `action="mcp_call_request"` with tool and parsed args |
| `/mcp connect <name> <transport> <cmd/url>` | Builds `MCPConnectConfig`, awaits `mgr.connect()` |
| `/mcp disconnect <name>` | Awaits `mgr.disconnect(name)` |
| `/mcp server status` | Reports running/stopped state |
| `/mcp server start` | Creates and starts `AnythinkMCPServer`, returns `action="mcp_server_started"` |
| `/mcp windows …` | Dispatches to `_mcp_windows()` — see below |

### The `/mcp windows` Sub-namespace

`_mcp_windows(ctx, rest, state)` in `commands/handlers.py` handles all
Windows-specific management. Path guard and audit log are accessed via
`ctx.mcp_manager._builtins.get("windows-filesystem")._path_guard` etc.

| Sub-command | Behaviour |
|-------------|-----------|
| `status` (or empty) | Windows server list: name, tool count, enabled/disabled |
| `mode gui` / `mode headless` | Updates `windows_gui_mode` config, saves, reassigns |
| `paths list` | Shows allowed and blocked lists from `WindowsPathGuard` |
| `paths allow <path>` | `guard.add_allowed()`, persist via config replace |
| `paths remove <path>` | `guard.remove_allowed()`, persist |
| `paths block <path>` | `guard.add_blocked()`, persist |
| `paths unblock <path>` | `guard.remove_blocked()` — fails for system paths |
| `apps` | `await mgr.call_tool("list_installed_apps", {})` |
| `apps refresh` | `server.invalidate_cache()` |
| `apps block <name>` / `apps unblock <name>` | Updates `windows_blocked_apps` tuple, saves |
| `audit [--n N] [--tool T] [--date today]` | `audit.get_recent(...)` |
| `audit --export` | `audit.export_to_text(export_path)` |
| `audit clear` | Returns `action="windows_audit_clear_confirm"` — requires TUI confirmation |
| `screenshot` | Returns `action="mcp_call_request"` for `take_screenshot` |
| `clip read` | Direct `await mgr.call_tool("read_clipboard", {})` |
| `clip write <text>` | Direct `await mgr.call_tool("write_clipboard", {"text": …})` |
| `notify <message>` | Direct `await mgr.call_tool("send_notification", {…})` |

### Action Signals to the TUI

| `CommandResult.action` | TUI behaviour |
|------------------------|---------------|
| `"mcp_call_request"` | `exec_mode == "auto"`: fires `_run_mcp_tool()` worker immediately. `"ask"`: shows confirmation prompt. Tool name and arguments in `extra`. |
| `"mcp_server_started"` | Logs server address from `extra["address"]`. |
| `"windows_audit_clear_confirm"` | Sets pending confirmation state; user types `"yes"` to execute `audit.clear()`. |

### MCP Tool Execution Worker

`ui/textual/app.py:_run_mcp_tool()` is a background worker that:

1. Shows a `"Calling MCP tool '<name>'…"` system bubble.
2. Calls `await self._ctx.mcp_manager.call_tool(tool_name, dict(arguments))`.
3. Formats output with header `"🔌  <tool> [<server>] (<duration>s)"`.
4. Appends result to `state.history` and renders a new bubble.

---

## Architecture Diagram

```
AppContext (startup)
│
├── MCPManager(_builtins, _externals, _tool_index)
│   │
│   ├── register_builtin(FilesystemServer())          in-process, no SDK
│   ├── register_builtin(SessionsServer(sm))          in-process, no SDK
│   ├── register_builtin(RAGServer(rag, emb))         in-process, no SDK
│   ├── register_builtin(SearchServer(reg))           in-process, no SDK
│   │
│   │   ── Windows servers (only on win32 + windows_enabled=True) ─
│   ├── register_builtin(WindowsFilesystemServer)  ─┐
│   ├── register_builtin(WindowsExplorerServer)    ─┤ all share:
│   ├── register_builtin(WindowsAppsServer)        ─┤  WindowsPathGuard(config)
│   ├── register_builtin(WindowsWindowServer)      ─┤  WindowsSafetyChecker()
│   ├── register_builtin(WindowsProcessServer)     ─┤  WindowsAuditLog(path)
│   ├── register_builtin(WindowsSystemServer)      ─┤
│   ├── register_builtin(WindowsSettingsServer)    ─┤
│   ├── register_builtin(WindowsClipboardServer)   ─┤
│   ├── register_builtin(WindowsScreenshotServer)  ─┤
│   └── register_builtin(WindowsNotificationServer)─┘
│
│   (on /mcp connect)
│   └── connect(MCPConnectConfig)
│       └── MCPClient(stdio | sse)                    requires mcp SDK
│           ├── connect() → session.list_tools()
│           └── call_tool() → session.call_tool()
│
│   (on /mcp server start)
│   └── AnythinkMCPServer(mcp_manager)                requires mcp SDK
│       └── start() → FastMCP("Anythink")
│           ├── tool: call_anythink_tool(name, args_json)
│           └── tool: list_anythink_tools()
│
└── ctx.mcp_manager.call_tool(name, args)
    │
    ├── _tool_index[name] → server_name  (O(1))
    ├── _builtins[server_name].call_tool(...)     ← built-in path (no SDK)
    └── _externals[server_name].call_tool(...)    ← external path (SDK)

Windows cross-cutting (injected into every Windows server)
│
├── WindowsPathGuard   — path allow/block validation, traversal prevention
├── WindowsSafetyChecker — Tier 1–4 classification, dynamic overrides
└── WindowsAuditLog    — JSONL audit trail, 10 MB rotating, 5 backups
```

---

## Optional Dependencies

| Feature | Requires |
|---------|---------|
| Built-in servers (filesystem, rag, search, sessions) | No extra dependency |
| External server connections (stdio / SSE) | `pip install anythink[mcp]` |
| Running Anythink as an MCP server | `pip install anythink[mcp]` |
| Windows OS MCP servers (all 10) | `pip install anythink[windows]` + Windows OS + `windows_enabled = True` |

**Windows package contents** (`pip install anythink[windows]`):

| Package | Min version | Purpose |
|---------|-------------|---------|
| `pywin32` | ≥ 306 | Clipboard, registry, volume, power plans, WM_CLOSE |
| `psutil` | ≥ 5.9 | Process list, CPU/RAM/disk/battery/network |
| `pygetwindow` | ≥ 0.0.9 | Window enumeration, focus, minimize/maximize/restore |
| `pyautogui` | ≥ 0.9.54 | `typewrite()` for `send_text_to_window` |
| `Pillow` | ≥ 10.0 | `ImageGrab.grab()` for screenshots |
| `winotify` | ≥ 1.1.0 | Windows 10/11 toast notifications (primary) |
| `win10toast` | ≥ 0.9 | Toast notification fallback |

All Windows-only imports are deferred inside method bodies — missing packages
surface as `MCPCallResult(is_error=True)` with an install hint, never as an
`ImportError` at module load time.

---

## Error Handling

All `call_tool` methods in both built-in servers and `MCPClient` catch all
exceptions and return them as `MCPCallResult(is_error=True, content=str(exc))`.
This means `MCPManager.call_tool()` **never raises** — it always returns an
`MCPCallResult`. Callers check `result.is_error` to decide how to present the
output.

`MCPError` (from `anythink.exceptions`) is raised for configuration and
connectivity problems that should abort the operation before any tool call is
attempted (e.g. missing SDK, bad transport name, empty command/URL). These
propagate to the TUI's `_run_mcp_tool` worker and are displayed as error
bubbles.

**Windows-specific error surfaces:**

| Condition | Response |
|-----------|----------|
| Non-Windows platform | `"This tool requires Windows. Current platform: <sys.platform>"` |
| Missing `[windows]` package | `"<package> not installed. Run: pip install anythink[windows]"` |
| Path guard rejection | `MCPCallResult(is_error=True)` with path and reason; outcome `"blocked_by_path_guard"` in audit |
| `set_timezone` without admin | Clear error explaining privilege requirement; outcome `"error"` in audit |
| System-account process kill | Protected — `kill_process` rejects without attempting termination |

---

## How to Add a New Built-in MCP Server

1. Create `src/anythink/mcp/builtin/<name>.py` subclassing `BuiltinMCPServer`.
2. Set `name` and `description` class attributes.
3. Implement `list_tools()` returning `list[MCPTool]` with correct
   `input_schema` dicts and `server_name=self.name`.
4. Implement `async call_tool()` following the try/except pattern:
   measure `t0 = time.monotonic()`, call a `_dispatch()` helper, return
   `MCPCallResult` with `duration_s=round(time.monotonic()-t0, 3)`.
5. Register in `app/context.py` in the `MCPManager(builtin_servers=[...])` list.
6. Add an entry point in `pyproject.toml` under
   `[project.entry-points."anythink.mcp_servers"]`.

**For Windows-only servers,** additionally:

- Add a `_WINDOWS_ONLY = sys.platform == "win32"` guard at module level.
- Check `if not _WINDOWS_ONLY: return _WIN_ERR` at the start of `_dispatch()`.
- Inject `WindowsPathGuard`, `WindowsSafetyChecker`, and/or `WindowsAuditLog`
  from `app/context.py:_build_windows_servers()`.
- Wrap all Windows API imports in `try/except ImportError` returning install hints.
- Add the new server to `_build_windows_servers()` and the `_STATIC_TIERS`
  table in `windows/safety.py`.
