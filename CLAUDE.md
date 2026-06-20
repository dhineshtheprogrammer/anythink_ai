# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Anythink 2.0 is a universal AI terminal workstation (`pip install anythink`) built in Python 3.11+. It provides a full-featured TUI powered by **Textual**, with LLM providers, session management, slash commands, RAG, agentic tools (exec, browse, MCP), voice input, desktop notifications, a 4-panel dashboard, and a plugin system.

## Commands

```bash
# Install for development (editable, with all extras)
pip install -e ".[all,dev]"

# Run the CLI
anythink                     # start chat (simple mode)
anythink --dashboard         # start in 4-panel Dashboard mode
anythink --version

# Key and model management
anythink keys list|add|show|update|delete|test
anythink model list|add|remove
anythink plugins list|info|install|remove

# Lint
ruff check src/

# Format check (never auto-format in CI; use --check locally too)
black --check src/ tests/

# Type check (strict mypy, src/anythink only)
mypy src/anythink

# Security scan
bandit -r src/anythink -c pyproject.toml

# Tests (must set keyring backend to avoid OS keychain prompts)
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/ -v

# Run a single test file
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/test_cli.py -v

# Build PyPI distribution
python -m build
```

Coverage minimum is 80% (enforced via `--cov-fail-under=80` in `pyproject.toml`). `src/anythink/ui/input.py` and `src/anythink/ui/textual/app.py` are excluded from coverage (TUI entry points, tested via Pilot).

## Architecture

### Dependency injection via AppContext

`app/context.py:AppContext` is the single DI container constructed once at startup and threaded through the entire call stack. It holds every subsystem:

| Field | Type | Description |
|---|---|---|
| `config` | `AppConfig` | Frozen config dataclass |
| `paths` | `Paths` | XDG directory paths |
| `console` | `Console` | Rich console (test: StringIO) |
| `theme` | `Theme` | Active colour theme |
| `config_manager` | `ConfigManager` | Config load/save |
| `key_manager` | `KeyManager` | OS keychain wrapper |
| `provider_registry` | `ProviderRegistry` | LLM provider discovery |
| `model_registry` | `ModelRegistry` | User-defined model aliases |
| `persona_manager` | `PersonaManager` | System-prompt personas |
| `session_manager` | `SessionManager` | Session YAML persistence |
| `search_registry` | `SearchRegistry` | Web search backends |
| `plugin_manager` | `PluginManager` | Plugin discovery/install |
| `rag_manager` | `RAGManager` | Named vector-store indexes |
| `embedding_registry` | `EmbeddingRegistry` | Embedding backends |
| `tool_runner` | `ToolRunner` | Approval-gated tool execution |
| `mcp_manager` | `MCPManager` | Built-in + external MCP servers |
| `notifier` | `Notifier` | Cross-platform desktop notifications |

No module-level globals exist. Tests inject `Console(file=StringIO())` through this container.

### Textual TUI shell

`ui/textual/app.py:AnythinkApp(App[int])` is the main application shell. It supports two modes:

- **Simple mode** (default): HUD + scrollable conversation + input bar
- **Dashboard mode** (`Ctrl+D` or `--dashboard`): adds left sessions panel, right stats panel, and bottom tabbed pane (Files / RAG / Tool Output)

The widget tree is always composed in full; dashboard panels are hidden via CSS `display: none` in simple mode and revealed by `_apply_dashboard_layout(True)`.

Priority bindings (`Binding(..., priority=True)`) on `Ctrl+D/L/R` override Input widget's own key handling.

### Chat state

`app/chat.py:ChatState` is the mutable conversation state threaded through the TUI. Key fields:

- `history: list[ChatMessage]` — always points to the active branch's list (shared reference via `__post_init__`)
- `branches: dict[str, list[ChatMessage]]` — all branch histories keyed by branch name
- `bookmarks: list[Bookmark]` — always the active branch's bookmarks
- `active_branch: str` — current branch name (default: `"main"`)
- `pending_attachments: list[FileAttachment]` — cleared after each send

### Provider system

`providers/base.py` defines `BaseProvider` (ABC) with three required async methods: `stream_chat()`, `list_models()`, `test_connection()`. Providers are **pure**: they never fetch their own API key. SDKs are imported lazily inside methods (guarded by `TYPE_CHECKING`) so missing optional packages fail loudly only when the provider is actually used.

`providers/registry.py:ProviderRegistry` discovers providers via the `anythink.providers` entry point group at runtime. Same pattern for `search/registry.py:SearchRegistry` (`anythink.search_backends`), `commands/registry.py:CommandRegistry` (`anythink.slash_commands`), `embeddings/registry.py:EmbeddingRegistry` (`anythink.embedding_backends`).

### Slash command system

`commands/base.py` defines `SlashCommand` (name, description, handler, usage) and `CommandResult` (should_exit, message, error, action, extra). All built-in commands live in `commands/handlers.py:register_commands()`. The registry dispatches `/cmd args` by splitting on whitespace and routing to the async handler.

`CommandResult.action` carries TUI-layer signals (e.g. `"undo_request"`, `"branch_confirm"`, `"exec_request"`, `"voice_request"`). `CommandResult.extra` carries typed parameters for tool runs.

### Session persistence

`session/manager.py:SessionManager` saves/loads/lists sessions as YAML files under `$XDG_DATA_HOME/anythink/sessions/`. Each session file includes `bookmarks` and `branches` for full branch-aware round-trips. File locking via `filelock.FileLock` prevents concurrent writes.

### RAG system

`rag/manager.py:RAGManager` manages named vector-store indexes:
- Index metadata persisted as YAML under `$XDG_DATA_HOME/anythink/rag/`
- Vector data persisted as gzip-JSON under `$XDG_CACHE_HOME/anythink/rag/`
- `EmbeddingRegistry` (`anythink.embedding_backends`) selects the backend (mock / local sentence-transformers / API)
- Retrieval is async and injected into the user message context before streaming

### Tool framework

`tools/base.py` defines `BaseTool` (ABC), `ToolResult`, and `ApprovalMode` (ASK/AUTO). `tools/runner.py:ToolRunner` wraps tool execution with approval gating. Built-in tools:
- `tools/exec.py:CodeExecTool` — runs code via PATH runtimes (python3, bash, node, ruby, go, sqlite3); 30s timeout; `# nosec B603` justified in module docstring
- `browse/fetch.py:BrowseTool` — two-tier fetch (snippets via search backends + full-page via httpx / optional Playwright headless)

The TUI handles approval in ask mode via `_pending_exec_data`/`_pending_browse_data` state, then fires `_run_exec_tool`/`_run_browse_tool` workers that inject results into history and stream an AI response.

### MCP (Model Context Protocol)

`mcp/manager.py:MCPManager` is the central routing table for all MCP servers. Built-in servers (no SDK required) are registered at startup from `AppContext.create()`:
- `mcp/builtin/filesystem.py:FilesystemServer` — list_dir, read_file
- `mcp/builtin/sessions.py:SessionsServer` — list_sessions, get_session
- `mcp/builtin/rag.py:RAGServer` — rag_search
- `mcp/builtin/search.py:SearchServer` — web_search

External servers connect via `mcp/client.py:MCPClient` (stdio / SSE transport; requires `pip install anythink[mcp]`). `mcp/server.py:AnythinkMCPServer` exposes Anythink as a FastMCP server.

### Voice input

`voice/recorder.py:VoiceRecorder` — non-blocking `sounddevice.InputStream` callback; `start()` buffers float32 frames; `stop()` returns a concatenated NumPy array (requires `anythink[voice]`).

`voice/transcriber.py:VoiceTranscriber` — lazy-loads a Whisper model; transcribes float32 mono audio to text; empty audio short-circuits before model load.

TUI flow: `/voice` → `_start_voice_recording()` → "Press Enter to stop" → `_finish_voice_recording()` worker via `asyncio.to_thread` → transcribed text in `Input.value`.

### Desktop notifications

`notify/backends.py` — platform-specific backends (Windows PowerShell toast, macOS `osascript`, Linux `notify-send`, NullBackend fallback). All subprocess calls carry `# nosec B603 B607`.

`notify/notifier.py:Notifier` — per-type toggles (rag_build_done, slow_response, exec_done, browse_done, provider_failure), global on/off, `contextlib.suppress` for best-effort delivery.

Trigger points: provider failure → `provider_failure`; response ≥15s → `slow_response`; exec ≥10s → `exec_done`; every browse → `browse_done`; RAG rebuild done → `rag_build_done`.

### Config & storage (XDG)

All paths resolved in `config/manager.py:_resolve_paths()`:

| File/Dir | Location |
|---|---|
| Main config | `$XDG_CONFIG_HOME/anythink/config.yaml` |
| Model aliases | `$XDG_CONFIG_HOME/anythink/models.yaml` |
| Personas | `$XDG_CONFIG_HOME/anythink/personas.yaml` |
| Sessions | `$XDG_DATA_HOME/anythink/sessions/` |
| RAG index metadata | `$XDG_DATA_HOME/anythink/rag/` |
| RAG vector stores | `$XDG_CACHE_HOME/anythink/rag/` |
| Logs | `$XDG_STATE_HOME/anythink/logs/` |

`AppConfig` (`config/schema.py`) is a frozen dataclass. `validate_config()` checks all enum fields. Valid themes: `midnight`, `aurora`, `ember`, `arctic`.

### Exception hierarchy

```
AnythinkError (message + user_message)
  ConfigError
  ProviderError (+ provider name)
    AuthenticationError / RateLimitError / ProviderUnavailableError / ModelNotFoundError
  SessionError
  KeychainError
  PluginError
  SearchError
  FileError
  RAGError
  ToolExecutionError
  BrowseError
  MCPError
  VoiceError
  BranchError
  NotificationError
```

Always raise the most specific subclass. `user_message` is what gets printed to the terminal.

### Testing conventions

The `xdg_dirs` fixture in `tests/conftest.py` redirects all four XDG env vars to `tmp_path` subdirectories and returns a `Paths` object. Every test touching the filesystem must use `xdg_dirs` (or `config_manager` which builds on it). The `PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring` env var must be set whenever a test imports keyring code.

Textual UI tests use `app.run_test(headless=True)` with `Pilot`. Mock contexts for TUI tests must set `ctx.rag_manager.is_active = False` and `ctx.mcp_manager.list_servers.return_value = []` to avoid format errors in `StatsPanel`.

Optional-dependency tests (voice, browse headless) use `patch.dict(sys.modules, {"sounddevice": None, ...})` to simulate missing packages.
