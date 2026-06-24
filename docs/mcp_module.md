# `src/anythink/mcp/` — Model Context Protocol Layer

This module implements Anythink's full MCP (Model Context Protocol) integration.
It covers three orthogonal concerns:

1. **Inbound tool use** — built-in servers that expose Anythink capabilities
   (filesystem, RAG, web search, sessions) as MCP tools callable by any
   MCP-aware agent or slash command.
2. **Outbound connections** — `MCPClient` connects to external MCP servers
   (via stdio or SSE), discovers their tools, and proxies calls to them.
3. **Serving** — `AnythinkMCPServer` flips the role: Anythink itself becomes
   an MCP server so external agents can call its built-in tools over SSE.

The `mcp` SDK is an optional dependency (`pip install anythink[mcp]`). All SDK
imports are deferred inside methods so the rest of Anythink works without it.
Built-in servers require no SDK at all — they are pure Python.

---

## Folder Structure

```
src/anythink/mcp/
├── __init__.py              # Package marker
├── models.py                # Shared data models (MCPTool, MCPCallResult, etc.)
├── manager.py               # MCPManager — central registry and dispatcher
├── client.py                # MCPClient — outbound connection to one external server
├── server.py                # AnythinkMCPServer — run Anythink as an MCP server
└── builtin/
    ├── __init__.py          # Builtin sub-package marker
    ├── base.py              # BuiltinMCPServer ABC
    ├── filesystem.py        # FilesystemServer — list_dir, read_file
    ├── rag.py               # RAGServer — rag_search
    ├── search.py            # SearchServer — web_search
    └── sessions.py          # SessionsServer — list_sessions, get_session
```

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
| `description`  | `str`             | Human-readable description shown in `/mcp tools` and `list_anythink_tools` |
| `input_schema` | `dict[str, Any]`  | JSON Schema fragment describing accepted arguments |
| `server_name`  | `str`             | Name of the server that owns this tool (used for display and routing) |

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
`MCPManager.list_servers()`. Consumed by the TUI stats panel and
`/mcp status`.

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
`app/context.py:117` with all four built-in servers pre-registered.

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
3. Awaits `client.connect()` — opens the transport and calls
   `session.list_tools()`.
4. Stores the client in `_externals` and indexes its tools in `_tool_index`.

**`async disconnect(name: str) -> None`**

Disconnects an external server:

1. Raises `MCPError` if `name` is not in `_externals`.
2. Pops the client and awaits `client.disconnect()`.
3. Removes all tools belonging to `name` from `_tool_index` via a dict
   comprehension.

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
    ]
)
```

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
2. Calls `await self._session.call_tool(name, arguments)` with a monotonic
   timer.
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

**TUI wiring:** The `/mcp server start` slash command (in
`commands/handlers.py:1273`) creates an `AnythinkMCPServer(mgr)`, awaits
`srv.start()`, and returns `action="mcp_server_started"` with
`extra={"address": address}`. The TUI's `_dispatch_command` logs the address.

---

### `builtin/__init__.py`

**Purpose:** Makes `anythink.mcp.builtin` a Python package.

**Contents:**
```python
"""Built-in MCP servers that work without the mcp SDK."""
```

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

Also used directly by the TUI file browser panel
(`ui/textual/panels/file_browser.py:40`) outside of the MCP dispatch path —
it instantiates `FilesystemServer()` directly and calls `call_tool("list_dir", ...)`.

---

#### `FilesystemServer(BuiltinMCPServer)`

```
name        = "filesystem"
description = "Read and list local files."
```

**Module-level constant**

```python
_MAX_READ_CHARS = 8_000
```

Maximum characters returned by `read_file` unless overridden by the caller.

---

**Tools exposed**

| Tool name   | Description | Arguments |
|-------------|-------------|-----------|
| `list_dir`  | List files and directories at the given path | `path: str` (default `"."`) |
| `read_file` | Read a text file and return its content | `path: str`, `max_chars: int` (default `8000`) |

---

**`_list_dir(path: str) -> str`** (synchronous, private)

1. Resolves `path` via `Path.expanduser().resolve()`.
2. Raises `FileNotFoundError` if path does not exist.
3. If the path is a file, returns the absolute path string.
4. Sorts directory entries: directories first, then files (case-insensitive
   within each group).
5. Formats each entry as `[D] <name>` or `[F] <name>`.
6. Returns the resolved path on the first line, then entries.

**`_read_file(path: str, max_chars: int) -> str`** (synchronous, private)

1. Resolves `path`; raises `FileNotFoundError` / `IsADirectoryError` on bad input.
2. Reads via `p.read_text(encoding="utf-8", errors="replace")`.
3. Truncates to `max_chars` and appends `"\n[truncated at N chars]"` if the
   file was longer.

**`call_tool` → `_dispatch`:** Routes `"list_dir"` and `"read_file"` to the
respective sync helpers. Unknown names raise `ValueError`, caught by the base
pattern and returned as an error result.

---

### `builtin/rag.py`

**Purpose:** Bridges the active RAG index into the MCP tool space, allowing any
MCP-aware agent to perform semantic search over Anythink's vector store.

---

#### `RAGServer(BuiltinMCPServer)`

```
name        = "rag"
description = "Search the active RAG index for relevant content."
```

**Constructor**

```python
def __init__(
    self,
    rag_manager: RAGManager,
    embedding_backend: BaseEmbeddingBackend | None = None,
) -> None
```

Stores references to the RAG manager and embedding backend (both injected from
`AppContext` at startup).

---

**Tools exposed**

| Tool name    | Description | Arguments |
|--------------|-------------|-----------|
| `rag_search` | Search the active RAG index and return the most relevant chunks | `query: str`, `top_k: int` (default `5`) |

---

**`call_tool` flow for `rag_search`:**

```
1. Check self._rag.is_active
   └── False → error "No RAG index is active. Use /rag use <name> to activate one."

2. Check self._emb is not None
   └── None → error "No embedding backend available. Install anythink[rag]."

3. Call await self._rag.retrieve(query, self._emb, top_k=top_k)
   └── Exception → error "Retrieval failed: <exc>"

4. Format results:
   └── Empty → "No results found."
   └── Each result: "[<source_path>]\n<chunk_text>\n(relevance: <score:.3f>)"
       joined with "\n\n---\n\n"
```

`RAGManager.retrieve()` returns objects with `.source_path`, `.chunk_text`,
and `.relevance` fields. The `---` separator between chunks makes the output
readable in a terminal or chat context.

---

### `builtin/search.py`

**Purpose:** Bridges the `SearchRegistry` (DuckDuckGo / SerpAPI / any other
backend) into the MCP tool space.

---

#### `SearchServer(BuiltinMCPServer)`

```
name        = "search"
description = "Search the web using the configured search backend."
```

**Constructor**

```python
def __init__(
    self,
    search_registry: SearchRegistry,
    preferred: str = "duckduckgo",
) -> None
```

`preferred` is the name of the backend to try first; falls back to the first
available backend if the preferred one is not installed or configured.
Set from `config.search_provider` at startup.

---

**Tools exposed**

| Tool name    | Description | Arguments |
|--------------|-------------|-----------|
| `web_search` | Search the web and return titles, URLs, and snippets | `query: str`, `max_results: int` (default `5`) |

---

**`call_tool` flow for `web_search`:**

```
1. backend = self._registry.get_available(self._preferred)
   └── None → error "No search backend available. Install anythink[search]."

2. await backend.search(query)
   └── Exception → error "Search failed: <exc>"

3. Format results (up to max_results):
   "<title>\n<url>\n  <snippet[:200]>"
   joined with "\n\n"

4. Empty → "No results for '<query>'."
```

Snippets are truncated to 200 characters per result to keep the output concise
in tool call responses.

---

### `builtin/sessions.py`

**Purpose:** Exposes saved Anythink conversation sessions as MCP tools so
external agents can browse and read past conversations.

---

#### `SessionsServer(BuiltinMCPServer)`

```
name        = "sessions"
description = "List and retrieve saved Anythink conversation sessions."
```

**Module-level constant**

```python
_MAX_MESSAGES = 20
```

Default maximum messages returned by `get_session`.

**Constructor**

```python
def __init__(self, session_manager: SessionManager) -> None
```

Stores a reference to the shared `SessionManager` instance.

---

**Tools exposed**

| Tool name       | Description | Arguments |
|-----------------|-------------|-----------|
| `list_sessions` | List all saved sessions with IDs, names, and message counts | *(none)* |
| `get_session`   | Retrieve recent messages from a session | `id_or_name: str`, `last_n: int` (default `20`) |

---

**`_list_sessions() -> str`** (private, synchronous)

Calls `self._sm.list_sessions()`. Formats output as a right-aligned table:

```
        ID  Messages  Name
----------------------------------------
  3f8a1b2c         5  My first session
  a9c04f11        12  (unnamed)
```

Session IDs are truncated to 8 characters for display.

---

**`_get_session(id_or_name: str, last_n: int) -> str`** (private, synchronous)

1. Raises `ValueError` if `id_or_name` is empty.
2. Calls `self._sm.find_by_name_or_id(id_or_name)` — matches exact name first,
   then UUID prefix.
3. Raises `KeyError` if not found (caught by `call_tool` and returned as an
   error result).
4. Takes `session.messages[-last_n:]`.
5. Formats each message as `[ROLE] <content[:300]>…` (content truncated to 300
   characters).
6. Returns `"(empty session)"` if the session has no messages.

---

## TUI Integration

### The `/mcp` Slash Command

`commands/handlers.py` handles all `/mcp` sub-commands using `ctx.mcp_manager`:

| Sub-command | What happens |
|-------------|-------------|
| `/mcp status` | Calls `mgr.list_servers()` and formats a table |
| `/mcp tools` | Calls `mgr.list_tools()` and lists all tools with descriptions |
| `/mcp call <tool> [args…]` | Returns `action="mcp_call_request"` with tool name and parsed args in `extra` |
| `/mcp connect <name> <transport> <cmd/url>` | Builds `MCPConnectConfig`, awaits `mgr.connect()` |
| `/mcp disconnect <name>` | Awaits `mgr.disconnect(name)` |
| `/mcp server status` | Shows whether `AnythinkMCPServer` is running |
| `/mcp server start` | Creates and starts `AnythinkMCPServer`, returns `action="mcp_server_started"` |

### Action Signals to the TUI

| `CommandResult.action` | TUI behaviour |
|------------------------|---------------|
| `"mcp_call_request"` | If `exec_mode == "auto"`: immediately fires `_run_mcp_tool()` worker. If `"ask"`: shows confirmation prompt; user types `y` to proceed. Tool name and arguments are in `extra`. |
| `"mcp_server_started"` | Logs the server address from `extra["address"]` in the conversation. |

### MCP Tool Execution Worker

`ui/textual/app.py:_run_mcp_tool()` is a background worker that:

1. Shows a `"Calling MCP tool '<name>'…"` system bubble.
2. Calls `await self._ctx.mcp_manager.call_tool(tool_name, dict(arguments))`.
3. Formats output with header `"🔌  <tool> [<server>] (<duration>s)"`.
4. Appends result to `state.history` and renders a new bubble.

### Stats Panel

`ui/textual/panels/stats.py` calls `ctx.mcp_manager.list_servers()` to show
built-in and external server counts in the dashboard's stats panel.

---

## Architecture Diagram

```
AppContext (startup)
│
├── MCPManager(_builtins, _externals, _tool_index)
│   │
│   ├── register_builtin(FilesystemServer())    ─── in-process, no SDK
│   ├── register_builtin(SessionsServer(sm))    ─── in-process, no SDK
│   ├── register_builtin(RAGServer(rag, emb))   ─── in-process, no SDK
│   └── register_builtin(SearchServer(reg))     ─── in-process, no SDK
│
│   (on /mcp connect)
│   └── connect(MCPConnectConfig)
│       └── MCPClient(stdio | sse)              ─── requires mcp SDK
│           ├── connect() → session.list_tools()
│           └── call_tool() → session.call_tool()
│
│   (on /mcp server start)
│   └── AnythinkMCPServer(mcp_manager)          ─── requires mcp SDK
│       └── start() → FastMCP("Anythink")
│           ├── tool: call_anythink_tool(name, args_json)
│           └── tool: list_anythink_tools()
│
└── ctx.mcp_manager.call_tool(name, args)
    │
    ├── _tool_index[name] → server_name  (O(1))
    ├── _builtins[server_name].call_tool(...)
    └── _externals[server_name].call_tool(...)
```

---

## Optional Dependency

| Feature | Requires |
|---------|---------|
| Built-in servers (filesystem, rag, search, sessions) | No extra dependency |
| External server connections (stdio / SSE) | `pip install anythink[mcp]` |
| Running Anythink as an MCP server | `pip install anythink[mcp]` |

All mcp SDK imports are guarded by `try/except ImportError` with clear
`user_message` error strings pointing to the install command.

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

---

## How to Add a New Built-in MCP Server

1. Create `src/anythink/mcp/builtin/<name>.py` subclassing `BuiltinMCPServer`.
2. Set `name` and `description` class attributes.
3. Implement `list_tools()` returning `list[MCPTool]` with correct
   `input_schema` dicts and `server_name=self.name`.
4. Implement `async call_tool()` following the try/except pattern:
   measure `t0 = time.monotonic()`, call a `_dispatch()` helper, return
   `MCPCallResult` with `duration_s=round(time.monotonic()-t0, 3)`.
5. Register in `app/context.py` alongside the other built-in servers:
   ```python
   MCPManager(builtin_servers=[..., MyNewServer(dependency)])
   ```

No SDK, no entry points, no restart required — the new server's tools are
indexed immediately at startup.
