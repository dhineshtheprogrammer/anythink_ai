# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Anythink is a universal AI terminal workstation (`pip install anythink`) built in Python 3.11+. It provides a full-featured TUI powered by **Textual**, with LLM providers, session management, slash commands, RAG, agentic tools (exec, browse, MCP), voice input, desktop notifications, a 4-panel dashboard, a plugin system, a full V3 automation layer (spend tracking, templates, comparison, export, scheduling, batch processing, diagnostics, self-update, config backup), a V3.2 debug mode system for deep request inspection, an enhanced multi-backend web search system, and an MMWE (Multi-Model Workflow Engine) for multi-stage AI pipelines.

## Commands

```bash
# Install for development (editable; use .[all,dev] for full optional deps)
pip install -e ".[dev]"
pip install -e ".[all,dev]"   # includes sentence-transformers, whisper, playwright, mcp

# Run the CLI
anythink                     # start chat (simple mode)
anythink --dashboard         # start in 4-panel Dashboard mode
anythink --debug             # start with debug mode pre-enabled
anythink --version

anythink keys list|add|show|update|delete|test
anythink model list|add|remove
anythink plugins list|info|install|remove

# V3 CLI
anythink run --file prompts.txt --output results.md   # batch processing
anythink doctor                                        # diagnostics
anythink scheduler start [--poll 60]                   # foreground schedule loop
anythink scheduler run <name>                          # run one schedule now
anythink scheduler list                                # show all schedules

# All four CI gates
ruff check src/
black --check src/ tests/
mypy src/anythink
bandit -r src/anythink -c pyproject.toml

# Tests — must set keyring backend to avoid OS keychain prompts
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/ -v

# Single test file
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/test_cli.py -v

# Single test by name/keyword
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/ -k "test_voice_model_valid"

# Build PyPI distribution
python -m build
```

Coverage minimum is 80% (`--cov-fail-under=80`). `ui/input.py`, `ui/textual/app.py`, and `ui/textual/panels/file_browser.py` are excluded from coverage (TUI entry points tested via Pilot).

## Architecture

### Dependency injection via AppContext

`app/context.py:AppContext` is the single DI container constructed once at startup and threaded through the entire call stack. Every subsystem lives here — no module-level globals exist. Tests inject `Console(file=StringIO())` through this container.

Key fields: `config`, `paths`, `theme`, `key_manager`, `provider_registry`, `model_registry`, `persona_manager`, `session_manager`, `search_registry`, `search_cache`, `search_orchestrator`, `plugin_manager`, `rag_manager`, `embedding_registry`, `tool_runner`, `mcp_manager`, `notifier`, `spend_tracker`, `template_manager`, `schedule_manager`, `debug_manager`.

**Mutating frozen config at runtime** — `AppConfig` is frozen; use `dataclasses.replace` and reassign `ctx.config`:
```python
from dataclasses import replace
new_config = replace(ctx.config, exec_mode="auto")
ctx.config_manager.save(new_config)
ctx.config = new_config
```

### Chat state

`app/chat.py:ChatState` is the mutable per-session state. Critical invariant: `history` and `bookmarks` always point to the **active branch's** lists (shared reference set up in `__post_init__`). Switching branches calls `BranchManager.switch_to()`, which swaps these references — code that reads `state.history` therefore always sees the active branch without knowing about branches.

`state.gen_params` (V3) carries the active alias's `GenerationParams`; passed directly to `stream_chat()` in both the simple chat loop and the TUI `_stream_response()` worker.

`state.search_enabled` (bool, default `False`) and `state.search_mode` (`"general"` | `"news"`) are **session-only** — they are NOT persisted to config and NOT read back from YAML. They initialise from `config.search_default_enabled` in `_resolve_state()`.

`_build_session(state)` in `app/chat.py` is the branch-aware serialisation helper. TUI workers that autosave call `ctx.session_manager.save(_build_session(state))`.

### Registry pattern (providers, search, embeddings, commands)

Every extensible subsystem uses the same pattern:
1. An ABC in `*/base.py` (e.g. `BaseProvider`, `BaseSearchBackend`, `BaseEmbeddingBackend`)
2. A `Registry` class that discovers implementations via a named entry-point group
3. `from_entry_points()` classmethod that reads `pyproject.toml` entry points at runtime
4. `get_available(preferred)` returns the preferred backend if available, else the first available

Entry-point groups: `anythink.providers`, `anythink.search_backends`, `anythink.slash_commands`, `anythink.embedding_backends`, `anythink.tools`, `anythink.mcp_servers`.

### Adding a new LLM provider

1. Create `src/anythink/providers/<name>.py` subclassing `BaseProvider`
2. Implement `stream_chat()`, `list_models()`, `test_connection()`, `supports_vision`, `requires_api_key`
3. Import the SDK lazily inside methods only — never at module level
4. Register in `pyproject.toml` under `[project.entry-points."anythink.providers"]`
5. Add the SDK to the matching optional extra and to `all`

### Adding a new slash command

1. Write an `async def _my_cmd(ctx, args, state, registry) -> CommandResult` handler in `commands/handlers.py`
2. Register it in `register_commands()` with a `SlashCommand("name", "desc", _my_cmd, "/usage")`
3. If the command needs TUI-layer work (approval flows, background workers), return a `CommandResult` with `action="my_action"` and put parameters in `extra: dict`. The TUI `_dispatch_command()` in `app.py` checks `result.action` and dispatches accordingly.

**Complete action signal list** (checked in `_dispatch_command`):
| `action` value | TUI behaviour |
|---|---|
| `"undo_request"` | Sets `_pending_undo = True`, shows confirmation prompt |
| `"branch_confirm"` | Sets `_pending_branch_create = True`, shows confirmation prompt |
| `"branch_switch:<name>"` | Immediately calls `_switch_branch(name)` |
| `"branch_hud_update"` | Refreshes HUD branch field |
| `"rag_hud_update"` | Refreshes HUD RAG field |
| `"rag_rebuild:<name>"` | Fires `_rebuild_rag_index(name)` worker |
| `"rag_new_request"` | Shows interactive RAG creation message |
| `"exec_request"` | Runs code immediately (auto) or prompts (ask); params in `extra` |
| `"browse_request"` | Fetches URL/query immediately or prompts; params in `extra` |
| `"mcp_call_request"` | Calls MCP tool immediately or prompts; tool name and kwargs in `extra` |
| `"voice_request"` | Starts microphone recording |
| `"mcp_server_started"` | Logs server address; address in `extra` |
| `"compare_request"` | Stores aliases in `_pending_compare_aliases`; next user message triggers `_run_comparison` worker |
| `"template_send"` | Injects `extra["rendered"]` into the Input widget for editing before send |
| `"update_confirm"` | Sets `_pending_update = True`; user types `y` to run upgrade in background thread |
| `"schedule_run"` | Fires `_run_schedule(extra["schedule_name"])` worker immediately |
| `"debug_display"` | Renders formatted debug output in an overlay; content in `extra["content"]` |
| `"debug_panel_toggle"` | Shows/hides the `DebugPanel` right-side widget |
| `"debug_hud_update"` | Refreshes the HUD debug indicator (`[DEBUG L2]`) |
| `"replay_stream"` | Replays a stored `RequestDebugRecord` through a provider; params in `extra` |
| `"search_hud_update"` | Refreshes HUD search mode field after `/search on\|off\|news\|toggle` |

### Textual TUI shell

`ui/textual/app.py:AnythinkApp(App[int])` is the main shell. The widget tree is always fully composed; dashboard panels are hidden via CSS `display: none` and revealed by `_apply_dashboard_layout(True)`.

**Interactive mode state flags** (checked in order in `on_input_area_submitted`):
`_pending_resume` → `_naming_mode` → `_pending_undo` → `_pending_branch_create` → `_pending_exec_data` → `_pending_browse_data` → `_pending_mcp_data` → `_pending_voice` → `_pending_clear` → `_pending_compare_pick` → `_pending_update`

**Debug panel** — `DebugPanel` is a right-side widget composed into the layout at startup and hidden by default. It is toggled via `_dispatch_command` when action is `"debug_panel_toggle"`. The HUD permanently shows `[DEBUG L2]` (or the active level) whenever `debug_manager.is_active()` is true.

**V3 compare flow**: `/compare alias1 alias2` sets `_pending_compare_aliases`; the user's next message is intercepted (before normal chat), fires `_run_comparison` worker, which calls `compare/runner.py` and renders results sequentially. Pick prompt captured by `_pending_compare_pick` → `_handle_compare_pick()`.

**Background workers** fire for every long-running operation (`_stream_response`, `_run_exec_tool`, `_run_browse_tool`, `_run_mcp_tool`, `_rebuild_rag_index`, `_finish_voice_recording`, `_reload_conversation`, `_run_comparison`, `_run_schedule`, `_replay_debug_stream`). Each worker appends its result to `state.history` and optionally calls `_ctx.notifier.notify(...)`.

**Priority bindings** (`priority=True`) on `Ctrl+D/L/R` override the inner `Input` widget's own key handling.

**Performance guard**: `_prune_history_tracking()` is called after each AI response to cap `_bubble_pairs`, `_undo_checkpoints`, and `_turn_bubbles` at 500 entries.

### Provider system

`BaseProvider` has three required async methods: `stream_chat()`, `list_models()`, `test_connection()`. Providers are **pure** — they never fetch their own API key; the caller passes `api_key` at construction. All SDK imports are deferred inside methods (guarded by `TYPE_CHECKING`) so missing optional packages only fail when actually used.

`stream_chat()` accepts an optional `gen_params: GenerationParams | None = None` kwarg (V3). Call `_resolve_params(gen_params, temperature, max_tokens)` at the top of every provider's `stream_chat()` implementation to merge calling conventions. Each provider only forwards the params its SDK supports — unsupported fields (e.g. `presence_penalty` on Anthropic) are silently ignored.

### Slash command system

`CommandResult.action` carries TUI-layer signals; `CommandResult.extra: dict[str, Any]` carries typed parameters (e.g. `{"language": "python", "code": "print('hi')"}`). The `extra` dict is used by `_dispatch_command` to pass data to background workers without modifying the `CommandResult` dataclass per-command.

### Session persistence

`session/manager.py:SessionManager` saves sessions as YAML under `$XDG_DATA_HOME/anythink/sessions/`. Each file includes `bookmarks` and `branches` for full round-trips. File locking via `filelock.FileLock` prevents concurrent writes. `find_by_name_or_id()` matches exact name first, then UUID prefix.

### RAG system

`rag/manager.py:RAGManager` manages named vector-store indexes. Index metadata in YAML; vector data in gzip-JSON. Retrieval is async and injected into the last user `ChatMessage` as a `TextPart` prefix before `stream_chat()`. The `EmbeddingRegistry` selects the backend: `mock` (zero-dep, deterministic, 64-dim) or `local` (sentence-transformers, `[rag]` extra).

### Tool framework

`BaseTool` / `ToolResult` / `ApprovalMode` (ASK/AUTO) in `tools/base.py`. `ToolRunner.run(tool, ask_fn=None, **kwargs)` calls `ask_fn` in ASK mode; skips it in AUTO mode. Built-in tools:
- `tools/exec.py:CodeExecTool` — `asyncio.create_subprocess_exec` with `shutil.which`; justified `# nosec B603` in module docstring
- `browse/fetch.py:BrowseTool` — two-tier: snippets via `SearchRegistry`, full page via `httpx` or optional Playwright

### MCP

`mcp/manager.py:MCPManager` holds a `_tool_index: dict[str, str]` (tool_name → server_name) for O(1) dispatch. Built-in servers need no SDK. External servers use `MCPClient` with `contextlib.AsyncExitStack` to manage stdio/SSE transport lifetimes.

### Enhanced web search system

Six backends registered under `anythink.search_backends`: `duckduckgo`, `serpapi`, `newsapi`, `bing`, `exa`, `google_cse`. Each subclasses `BaseSearchBackend` and declares capability flags `supports_freshness`, `supports_safe_search`, `supports_news`. `SearchResult` carries `published_date` and `source_domain` in addition to `title`, `url`, `snippet`.

**`SearchCache`** (`search/cache.py`) — TTL-based in-memory cache with TF-IDF cosine semantic matching (threshold 0.85, no ML deps). Keyed by `(query, backend_name)`. `evict_expired()` is called at the start of each search-enabled response.

**`QueryRewriter`** (`search/rewriter.py`) — sends a 1-shot LLM prompt to produce 1–3 concise search queries. Wrapped in `asyncio.wait_for(timeout=5.0)`; falls back to the original string on any failure.

**`SearchOrchestrator`** (`search/orchestrator.py`) — single entry-point for all search logic: checks cache, calls `QueryRewriter`, runs up to `max_searches` queries against the selected backend, deduplicates by URL, applies domain include/exclude post-filters. News mode tries `("newsapi", "bing")` first, then falls back to any backend with `supports_news=True`.

The `/search` command namespace (`commands/handlers.py`) handles: `on|off|news|toggle|status`, one-off queries, `fresh`, `include`/`exclude` domain lists, `cache`, `backends`, and `settings`.

### MMWE — Multi-Model Workflow Engine

`workflow/models.py` defines the full data model for multi-stage AI pipelines (executor not yet implemented — schema layer only).

**Stage types** (`StageType` enum): `PLANNER`, `MCP_CALL`, `LLM_SPECIALIST`, `USER_APPROVAL`, `CONDITION`, `FORMATTER`, `LOOP`.

**Key dataclasses**:
- `WorkflowPlan` — parsed plan: `name`, `trigger`, `stages: list[Stage]`, `models_used`, `mcp_servers_used`.
- `Stage` — a single pipeline step with type-specific fields: `model_alias`/`task_instruction` for `LLM_SPECIALIST`; `tool_name`/`tool_params` for `MCP_CALL`; `condition_expr`/`branch_a`/`branch_b` for `CONDITION`; `loop_def: LoopDefinition` for `LOOP`; `approval_message` for `USER_APPROVAL`.
- `WorkflowState` — mutable runtime state with `accumulated_results: dict[str, Any]` keyed as `"stage_id.field_name"`. `resolve_ref(ref)` resolves dot-path references between stages; `store_result()` indexes output fields.
- `WorkflowCallbacks` — async hooks for engine ↔ TUI/CLI: `on_stage_start`, `on_stage_complete`, `on_approval_needed`, `on_loop_progress`, `on_model_unavailable`.
- `WorkflowLog` — full execution record for disk persistence.

All dataclasses implement `to_dict()` / `from_dict()` for JSON round-trips. `Stage.from_dict()` is recursive (handles `branch_a`, `branch_b`, nested `LoopDefinition.sub_stages`).

### V3 systems

**Spend tracking** — `spend/tracker.py:SpendTracker` persists `SpendRecord` objects to `spend.yaml`. `spend/pricing.py` holds a static pricing table; `estimate_cost(provider, model_id, usage)` computes USD cost per response. Spend is recorded in both `ChatApp.run()` and the TUI `_stream_response()` worker after every response with non-None `TokenUsage`. `SpendTracker.prune(keep_days=90)` is called at startup to bound the log file size.

**Template library** — `config/templates.py:TemplateManager` (same pattern as `PersonaManager`). `PromptTemplate.render(variables)` does simple `str.replace` on `{{key}}` placeholders; raises `ConfigError` for unresolved placeholders. Backed by `templates.yaml`.

**Schedule automation** — `schedule/manager.py:ScheduleManager` (same pattern as `PersonaManager`). `schedule/runner.py:ScheduleRunner` evaluates cron expressions via deferred `croniter` import; `_is_due()` checks `last_run` against the most recent expected cron firing time. `run_once()` streams the prompt, writes output, notifies, and updates `last_run`. `start(poll_interval)` is the foreground blocking loop used by `anythink scheduler start`.

**Comparison mode** — `compare/runner.py:run_comparison()` fires providers concurrently via `asyncio.gather` with a semaphore (default `max_concurrent=3`). Per-model errors return a `CompareResult` with `error` set rather than aborting the others. The TUI intercepts the user's next message when `_pending_compare_aliases` is set.

**Batch processing** — `batch/runner.py:run_batch()` uses an `asyncio.Semaphore` capped at 20. Results are returned sorted by index. `batch/writers.py` writes Markdown or JSON output. The `anythink run` CLI command does NOT start the TUI — uses `asyncio.run()` directly.

**Export** — `export/formats.py` exposes `export_markdown()`, `export_json()`, `export_pdf()`. PDF requires `fpdf2` (`pip install anythink[pdf]`); raises `ExportError` if absent. All formats support a `message_range` tuple for partial exports.

**Diagnostics** — `diagnostics.py:run_diagnostics()` runs 6 check categories and returns `list[DiagResult]`. Provider connectivity checks are wrapped in `asyncio.wait_for(..., timeout=5.0)` to prevent hangs. Results can also be triggered at the CLI level via `anythink doctor`.

**Self-update** — `updater.py` queries `pypi.org/pypi/anythink/json` via `httpx` (already a core dep); `run_upgrade()` calls `pip install --upgrade anythink` as a subprocess. The `/update` handler returns `action="update_confirm"` so the TUI runs the upgrade in a background thread.

**Config backup** — `config/backup.py:export_config()` bundles config, models, personas, templates, schedules as JSON (keys excluded). `import_config()` validates the config section via `validate_config()` before writing, and creates an automatic safety snapshot first.

**Debug mode (V3.2)** — `debug/manager.py:DebugManager` is always present in `AppContext` but zero-cost when inactive. Enabled via `anythink --debug` or `/debug on`. Three verbosity levels (`debug_level` 1–3). Stores up to 100 `RequestDebugRecord` objects in an in-memory deque. Every instrumentation call in `_stream_response()` is guarded by `is_active()`.

`RequestDebugRecord` (`debug/models.py`) captures the full request lifecycle: monotonic timestamps for prompt assembly / RAG / search / API overhead / TTFT / streaming / rendering; token usage + tokens-per-second; stop reason; RAG query and scored retrieval results; tool call traces; plugin hook events; HTTP request/response logs (auth headers masked); and token-by-token stream trace (level 3 only).

`debug/commands.py` registers all subcommands under the `/debug` namespace:
- **Mode**: `on`, `off`, `toggle`, `level <1|2|3>`, `api` (toggle raw HTTP capture)
- **Request inspection**: `prompt [n]`, `timing [n]`, `stopreason`, `tokens`, `tps`, `context`, `diff [n1 n2]`
- **RAG**: `chunks`, `embeddings`, `raginject`
- **Tools/agent**: `tools`, `agent`, `tooldiff [n1 n2]`, `plugins`
- **Advanced**: `replay [n] [--provider alias]`, `latency`, `compare <alias...>`, `perf`, `export [--format txt|json]`, `panel`

`debug/http_logger.py` captures raw HTTP traffic via httpx event hooks and writes a rolling log (max 50 MB) to `$XDG_STATE_HOME/anythink/logs/api_debug.log`. `debug/formatters.py` contains pure Rich Text formatters for all inspection subcommands (no side effects).

### Config & storage (XDG)

| File/Dir | Location |
|---|---|
| Main config | `$XDG_CONFIG_HOME/anythink/config.yaml` |
| Model aliases | `$XDG_CONFIG_HOME/anythink/models.yaml` |
| Personas | `$XDG_CONFIG_HOME/anythink/personas.yaml` |
| Templates (V3) | `$XDG_CONFIG_HOME/anythink/templates.yaml` |
| Schedules (V3) | `$XDG_CONFIG_HOME/anythink/schedules.yaml` |
| Sessions | `$XDG_DATA_HOME/anythink/sessions/` |
| Exports (V3) | `$XDG_DATA_HOME/anythink/exports/` |
| Spend log (V3) | `$XDG_DATA_HOME/anythink/spend.yaml` |
| RAG index metadata | `$XDG_DATA_HOME/anythink/rag/` |
| RAG vector stores | `$XDG_CACHE_HOME/anythink/rag/` |
| Debug exports (V3.2) | `$XDG_DATA_HOME/anythink/debug_exports/` |
| API debug log (V3.2) | `$XDG_STATE_HOME/anythink/logs/api_debug.log` |

`AppConfig` (`config/schema.py`) is frozen. `validate_config()` in `config/manager.py` checks enum fields (`ui_mode`, `browse_mode`, `exec_mode`, `voice_model`, `spend_budget_period`, etc.) and returns a list of `ConfigError`s. Valid themes: `midnight`, `aurora`, `ember`, `arctic`.

**V3 AppConfig fields**: `spend_tracking` (bool, default `True`), `spend_budget_soft_limit` (float | None), `spend_budget_period` (`"monthly"` | `"daily"`).

**V3.2 AppConfig fields**: `debug_mode` (bool, default `False`), `debug_level` (int, default `2`, clamped 1–3), `debug_api_logging` (bool, default `False`).

**Important**: `debug_mode`, `debug_level`, and `debug_api_logging` are **not parsed by `ConfigManager.load()` from YAML** — they always use their dataclass defaults regardless of what's in `config.yaml`. To test startup with debug pre-enabled, patch `ConfigManager.load` to return `AppConfig(debug_mode=True, ...)` directly.

**Search AppConfig fields** (persisted to config.yaml): `search_default_enabled`, `search_mode`, `search_max_per_response`, `search_query_rewrite`, `search_preview`, `search_preview_delay_s`, `search_cache_enabled`, `search_cache_ttl_minutes`, `search_safe_search`, `search_freshness`, `search_include_domains`, `search_exclude_domains`, `search_max_page_chars`.

### Exception hierarchy

```
AnythinkError (message + user_message)
  ConfigError
  ProviderError (+ provider name)
    AuthenticationError / RateLimitError / ProviderUnavailableError / ModelNotFoundError
  SessionError / KeychainError / PluginError / SearchError / FileError
  RAGError / ToolExecutionError / BrowseError / MCPError / VoiceError
  BranchError / NotificationError
  SpendError / ExportError / ScheduleError / BatchError / UpdateError  ← V3
  DebugError  ← V3.2
  WorkflowError  ← MMWE
    WorkflowPlanError / WorkflowStageError
```

Always raise the most specific subclass. `user_message` is what the terminal shows.

### TUI widget components

Supporting widgets in `ui/textual/` beyond the main app shell:

- `thinking_widget.py:ThinkingWidget` — Animated spinner (`◐◓◑◒`) with rotating contextual phrases shown during generation; `set_context()` overrides the phrase set.
- `tips_bar.py:TipsBar` — Rotating educational tips shown above the input area during streaming; hidden at rest.
- `hint_bar.py:HintBar` — Persistent keyboard shortcut reference bar below the input; switches between "streaming" and "resting" hint sets.
- `slash_menu.py:SlashMenu` — Drop-up autocomplete for slash commands with arrow-key navigation and keyword matching.
- `settings_menu.py:SettingsMenu` — Interactive arrow-key-navigable overlay for live visual settings (`/settings`). Each `_SettingRow` change instantly re-renders all existing messages via `BubbleStyle.retroactive_apply()`.
- `theme_bridge.py:ThemeBridge` — Maps Rich named colors to CSS hex values for Textual widgets; exports `theme_css_vars()`.

### Testing conventions

- **`xdg_dirs`** fixture in `tests/conftest.py` — redirects all four XDG env vars to `tmp_path` subdirs. Every test that touches the filesystem must use it.
- **`PYTHON_KEYRING_BACKEND`** — must be set for any test importing keyring code.
- **Textual Pilot tests** — `async with app.run_test(headless=True) as pilot`. Mock contexts must set `ctx.rag_manager.is_active = False` and `ctx.mcp_manager.list_servers.return_value = []` to prevent `StatsPanel.update_stats` format errors.
- **Optional-dep tests** — use `patch.dict(sys.modules, {"sounddevice": None})` to simulate missing packages.
- **`asyncio_mode = "auto"`** — all `async def` test functions run automatically; no `@pytest.mark.asyncio` needed.
- **Debug tests** — `tests/test_debug_manager.py`, `test_debug_models.py`, `test_debug_formatters.py`, `test_debug_commands.py` cover the V3.2 debug layer. Formatters are pure functions and tested without TUI. Use a factory to build mock `RequestDebugRecord` objects rather than constructing them inline.
- **Workflow tests** — `tests/test_workflow_models.py` covers `workflow/models.py`. All dataclasses have `to_dict()` / `from_dict()` round-trips; test recursive structures (nested stages in `branch_a`/`branch_b`, `LoopDefinition.sub_stages`) explicitly.
