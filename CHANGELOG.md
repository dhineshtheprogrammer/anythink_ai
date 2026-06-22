# Changelog

All notable changes to Anythink are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.1.0] — 2026-06-22

Anythink 3.1 delivers the **V2.2 Visual Identity & Personalization** build — every theme becomes a complete, full-screen visual identity; users gain direct control over bubble style, density, avatars, and timestamps; and two long-standing visual bugs are fixed for good.

### Added — V2.2 Visual Identity

#### Per-Theme Background Fill
- Each of the 4 themes (Midnight, Aurora, Ember, Arctic) now defines a `background` and `surface` hex color applied to the full screen canvas
- `Theme` dataclass gains 3 new fields: `background` (full-screen tint), `surface` (bubble surface lift), `info` (4th semantic color)
- `theme_css_vars()` (theme_bridge.py) now returns a `dict` and emits `$background`, `$surface`, `$panel`, `$info` alongside existing vars
- `AnythinkApp.get_css_variables()` merges theme vars with Textual's built-in palette so `$foreground` and framework vars remain intact
- `_apply_theme_background()` sets `Screen.styles.background` and `ConversationView.styles.background` at runtime; called on mount and on theme change

#### Bubble Style Toggle — Boxed / Minimal
- `AppConfig.bubble_style: str = "boxed"` — new field (`"boxed"` | `"minimal"`)
- `UserBubble` and `AIBubble` refactored: `_render_boxed()` (bordered Rich Panel) and `_render_minimal()` (thin `▎` accent bar, no border, full-width layout for both roles)
- Minimal mode: user bar colored `theme.primary`, AI bar colored `theme.accent`; footer metadata (word count, RAG sources) preserved

#### Role Avatars
- `AppConfig.show_avatars: bool = False` — new field
- `_user_avatar(theme)` returns `⟨Y⟩` in `theme.primary`; `_ai_avatar(theme)` returns `✦` in `theme.accent`
- Avatars render in both Boxed (panel title) and Minimal (header line) styles when enabled

#### Compact Density Mode
- `AppConfig.density: str = "comfortable"` — new field (`"comfortable"` | `"compact"`)
- Bubbles set `styles.margin` dynamically in `on_mount()` and `_apply_density()`; zero bottom-gap in compact mode
- Propagated retroactively on `density` setting change via `_refresh_all_bubbles()`

#### Relative Timestamps with Absolute Fallback
- New `src/anythink/ui/timestamp.py` — `format_timestamp(dt, config)` with 6 tiers: `just now` / `Xm ago` / `Xh ago` / `Yesterday, HH:MM` / `Mon D, HH:MM` / `Mon D YYYY, HH:MM`; cross-platform day formatting (`%#d` on Windows, `%-d` on POSIX)
- `AppConfig.timestamps: str = "relative"` — new field (`"relative"` | `"absolute"`)
- `UserBubble` and `AIBubble` store `_created_at: datetime` (raw object, not formatted string); timestamp formatted at render time
- 60-second interval timer (`set_interval(60, _tick_timestamps)`) refreshes all visible `UserBubble` / `AIBubble` without user action

#### Live Retroactive Theme Application (bug fix)
- All bubble types (`UserBubble`, `AIBubble`, `LogoBubble`, `SystemBubble`, `CompactNotice`) now implement `refresh_visual(theme, config)` — rebuilds content with updated colors and settings
- `on_settings_menu_changed()` calls `_refresh_all_bubbles()` for any of: `active_theme`, `bubble_style`, `density`, `show_avatars`, `timestamps`, `icon_style`
- Theme switch also calls `refresh_css()` to update Textual CSS variables and `_apply_theme_background()` for the screen background — zero stale colors possible anywhere

#### Unified Monochrome Icon Language
- New `src/anythink/ui/icons.py` — `ICONS_UNICODE` and `ICONS_ASCII` dicts + `get_icon(key, config)` + `get_spinner_frames(config)`
- `AppConfig.icon_style: str = "unicode"` — new field (`"unicode"` | `"ascii"`)
- All emoji replaced across the entire app: `🔍` → `⌕`, `📚` → `⌬`, `📎` → `⎘`, `💡` → `◆`, `✅` → `✓`, `❌` → `✕`, `⚠️` → `▲`, `ℹ️` → `◈`
- `SystemBubble` uses `_KIND_MAP` dict mapping `kind` → `(icon_key, color_role)` for consistent icon+color selection
- HUD line 2 resolves search and RAG icons via `get_icon()`; tips bar prefix via `get_icon()`

#### Collapsed Session Naming Confirmation (bug fix)
- New `CompactNotice` widget (borderless single-line Static) replaces the stacked double-box confirmation
- `_handle_session_naming()` removes the prompt `SystemBubble` from the DOM then mounts a `CompactNotice`: `✓ Session named: "…"` or `✓ Session named: "…"  (auto)` for auto-generated names

### Fixed

- **Stale theme colors after mid-session theme switch** — every bubble, the HUD, the logo, and all system messages now re-render in the new theme the instant the theme is changed; no mixed-color scrollback possible
- **Misleading `0%` context display** — `_fmt_pct()` in `hud.py` shows `0.3%` for any non-zero sub-1% usage; flat `0%` only when the context is genuinely empty. Applied consistently to HUD, `ContextStatusBar`, and `StatsPanel`

### Changed

- `AppConfig` gains 5 new fields: `bubble_style`, `density`, `show_avatars`, `timestamps`, `icon_style` (all safe defaults preserve V1/V2/V3 behavior)
- `validate_config()` in `config/manager.py` extended with enum checks for all 4 new string fields
- `Theme` dataclass gains `background: str`, `surface: str`, `info: str` fields (all 4 themes updated)
- `theme_css_vars()` return type changed from `str` to `dict[str, str]`; callers updated
- `UserBubble.__init__` gains optional `config: AppConfig | None = None` param; `_timestamp` field replaced by `_created_at: datetime`
- `AIBubble.__init__` gains optional `config: AppConfig | None = None` param; `_timestamp` field replaced by `_created_at: datetime`; `show_error()` uses monochrome warning icon
- `LogoBubble` and `SystemBubble` store message data for `refresh_visual()` rebuilds; `SystemBubble` uses `_KIND_MAP` instead of `_ICONS` emoji dict
- `SettingsMenu` max-height increased from 20 to 26 rows to fit 5 new entries; 5 new `_SETTINGS` entries added (Bubble style, Role avatars, Density, Timestamps, Icon style)
- `AnythinkApp.__init__` now sets `self._ctx` before `super().__init__()` so `get_css_variables()` is available during Textual's CSS initialization
- `_handle_session_naming()` stores `_naming_prompt_bubble` reference for DOM removal; uses `CompactNotice` instead of `SystemBubble`
- All `UserBubble`/`AIBubble` construction sites in `app.py` updated to pass `config=self._ctx.config`
- `TipsBar` gains `set_config(config)` public method for icon style updates
- `_context_bar()` and `ContextStatusBar.render()` use `_fmt_pct()` for precision formatting
- `StatsPanel.update_stats()` uses `_fmt_pct()` for context percentage

### Technical
- 1,161 tests, 1 skipped — all CI gates clean
- 2 new modules: `src/anythink/ui/icons.py`, `src/anythink/ui/timestamp.py`
- 16 files changed, 671 insertions, 156 deletions

[3.1.0]: https://github.com/dhineshtheprogrammer/anythink_ai/releases/tag/v3.1.0

---

## [3.0.0] — 2026-06-22

Anythink 3.0 expands the workstation from a great chat tool into a dependable, scriptable, self-maintaining AI platform — adding cost awareness, automation, reusability, and operational maturity.

### Added — V3 Features

#### Per-Model Generation Parameters
- `GenerationParams` dataclass (temperature, max_tokens, top_p, frequency_penalty, presence_penalty) stored per model alias in `models.yaml`
- `_resolve_params()` helper merges `gen_params` with legacy flat kwargs for full backward compatibility
- All 8 providers updated to forward the supported subset of params to their SDKs (Anthropic/Gemini silently ignore unsupported fields)
- `/params [key=value ...]` — view or set params for the active alias; `/params reset` restores provider defaults
- `ChatState.gen_params` carries the active alias's params through the TUI stream loop

#### Multi-Model Comparison Mode
- `/compare <alias1> <alias2> [alias3 ...]` — sends the next prompt to multiple models simultaneously
- `compare/runner.py`: `run_comparison()` fires providers concurrently via `asyncio.gather` with configurable `max_concurrent` and per-model error isolation
- TUI renders results sequentially with `══ [alias] ══` headers showing elapsed time, token counts, and estimated cost
- Pick prompt lets the user choose which response to continue the conversation with
- All comparison results recorded to `SpendTracker`

#### Spend Tracking
- `spend/tracker.py`: `SpendTracker` + `SpendRecord` — persists per-response cost estimates to `spend.yaml`
- `spend/pricing.py`: static pricing table for all supported providers; local providers ($0.00); `estimate_cost()` helper
- `/cost [session|today|month|by-model|by-provider]` — view accumulated spend at any granularity
- HUD line 2 shows `~$0.0042` in muted style when session spend > 0
- Optional soft budget limit in config: warning shown at 80% and 100% of the configured period limit
- Spend recorded automatically in `ChatApp.run()` and `_stream_response()` after every response with `TokenUsage`
- Settings menu: "Spend tracking" (on/off) and "Spend budget period" (monthly/daily)

#### Prompt Templates & Snippets
- `config/templates.py`: `PromptTemplate` dataclass with `{{variable}}` placeholder syntax; `TemplateManager` (same YAML pattern as `PersonaManager`)
- `render()` uses simple string replacement; raises `ConfigError` listing any unresolved placeholders
- `/template save|list|show|delete` — full CRUD for the template library
- `/use <name> [key=value ...]` — renders a template with inline args; result injected into input widget via `action="template_send"`

#### Session Export
- `export/formats.py`: `export_markdown()`, `export_json()`, `export_pdf()` (fpdf2, optional)
- Full session or turn-range subset; default output path to `~/.local/share/anythink/exports/`
- `/export [markdown|json|pdf] [path] [--range N-M]`
- New `pdf` optional extra: `pip install anythink[pdf]`

#### Scheduled & Recurring Prompts
- `schedule/models.py`: `ScheduledPrompt` dataclass with cron expression, alias, output file, enabled flag, and last_run tracking
- `schedule/manager.py`: `ScheduleManager` — CRUD + enable/disable/update_last_run
- `schedule/runner.py`: `ScheduleRunner` — `run_once()` streams response, appends to output file, notifies; `run_all_due()` evaluates cron expressions (via `croniter`) and fires due schedules concurrently; `start()` foreground blocking loop
- `/schedule list|add|remove|enable|disable|run`
- CLI: `anythink scheduler start [--poll N]`, `anythink scheduler run <name>`, `anythink scheduler list`
- New `scheduler` optional extra: `pip install anythink[scheduler]`

#### Batch Processing Mode
- `batch/runner.py`: `run_batch()` with `asyncio.Semaphore` (max 20 parallel); per-prompt error isolation
- `batch/writers.py`: `write_markdown()`, `write_json()`
- CLI: `anythink run --file prompts.txt --output results.md [--parallel N] [--alias A] [--format md|json]`
- Exits with code 1 if any prompt errors; clean stdout suitable for piping

#### Self-Update Mechanism
- `updater.py`: `fetch_latest_version()` queries PyPI JSON API; `current_version()` reads `__version__`; `run_upgrade()` runs `pip install --upgrade` in subprocess
- `/update check` — prints current vs. latest version
- `/update` — prompts for confirmation; TUI runs upgrade in background thread; requires restart

#### Diagnostics Command
- `diagnostics.py`: `run_diagnostics()` + per-category check functions
- Checks: Python version (3.11+ requirement), optional dependency availability, API key configuration, provider connectivity (5s timeout each), config file YAML validity, disk free space
- `/doctor` — formatted report with ✓/⚠/❌ per check and a summary line
- CLI: `anythink doctor`

#### Config Backup & Restore
- `config/backup.py`: `export_config()` bundles config, models, personas, templates, schedules into a single JSON file (keys excluded by default); `import_config()` validates, snapshots current config, then restores
- `/config export [path]` — creates portable bundle
- `/config import <path>` — validates and restores; tells user to restart

### Changed

- `BaseProvider.stream_chat()` gains optional `gen_params: GenerationParams | None = None` — fully backward compatible; existing callers unchanged
- `ModelAlias` gains `gen_params: GenerationParams | None = None` field with backward-compatible YAML roundtrip
- `AppConfig` gains `spend_tracking`, `spend_budget_soft_limit`, `spend_budget_period` fields (safe defaults preserve V2 behavior)
- `ChatState` gains `gen_params: GenerationParams | None = None` field
- `AppContext` gains `spend_tracker`, `template_manager`, `schedule_manager` fields wired in `create()`
- `Paths` gains `templates_file`, `schedules_file`, `exports_dir`, `spend_log_file` properties; `ensure_dirs()` creates `exports_dir`
- HUD line 2 shows session cost when > 0; `session_cost` reactive field added
- Settings menu extended with V3 spend entries
- `_stream_response()` in TUI now passes `gen_params` to `stream_chat()` and records spend after each response
- New exception types: `SpendError`, `ExportError`, `ScheduleError`, `BatchError`, `UpdateError`
- `pyproject.toml`: new `pdf` and `scheduler` optional extras; both included in `all` and `dev`

### Technical
- 1,157 tests, 86.1% coverage
- All CI gates clean: ruff, black, mypy-strict, bandit
- 74 end-to-end tests in `tests/test_e2e/` covering all V3 command handlers, CLI batch/scheduler/doctor, spend integration, gen_params pass-through, and compare runner

[3.0.0]: https://github.com/dhineshtheprogrammer/anythink_ai/releases/tag/v3.0.0

---

## [2.0.0] — 2026-06-20

Anythink 2.0 transforms the CLI chatbot into a full **AI terminal workstation** with a Textual TUI, RAG, agentic tools, MCP, voice, notifications, and a 4-panel dashboard.

### Added — V2 Features

#### Textual TUI Shell (Phase 1)
- `AnythinkApp(textual.App)` replaces the prompt_toolkit event loop; all V1 features forward-compatible
- **Chat bubbles**: `UserBubble` (right-aligned, primary border), `AIBubble` (left-aligned, streaming → Markdown, length indicator, bookmark ✦, RAG retrieval footer), `SystemBubble` (info/success/error/warning/search/code/rag/mcp icons)
- Persistent two-line **HUD** (`HUDWidget`) with reactive diff-based redraws: app version, session name, branch, theme, model alias, provider status dot, context progress bar, search status, active RAG index
- Response length indicator (`·` / `··` / `···` / `✦` / `✦✦`) based on word count
- **Startup experience**: returning-user detection, mid-conversation session resume prompt, interactive session naming (Enter = auto-name)

#### Session Layer (Phase 2–3)
- **Session file locking** via `filelock.FileLock` — prevents concurrent writes across multiple instances
- **Session naming**: `/rename <name>`, auto-slug filenames, auto-name after first response
- **Undo**: `/undo` — removes last user+AI pair from history, bubbles, disk; single-level, branch-aware
- **Bookmarks** (`bookmarks/manager.py`): `/bookmark [turn]`, `/bookmark label <n> <text>`, `/bookmarks`, `/bookmark export`, `/bookmark search <query>` (cross-session); permanent ✦ in AI bubble titles
- **Conversation branching** (`branch/manager.py`): `/branch` (create), `/branch list`, `/branch switch <name>`; branches stored in session file with diverge-turn metadata; HUD shows active branch

#### RAG — Retrieval-Augmented Generation (Phase 4)
- **Pluggable embeddings registry** (`anythink.embedding_backends` entry-point group): `MockEmbeddingBackend` (64-dim, zero-dep, deterministic), `LocalEmbeddingBackend` (sentence-transformers, `[rag]` extra)
- **VectorStore**: pure-Python cosine-similarity search + gzip-JSON persistence
- **Chunkers**: `chunk_text()` (paragraph/sentence/word boundaries), `chunk_code()` (function/class boundaries), `chunk_file()` (auto-detect by extension)
- **RAGManager**: named indexes (Project / Document Library), Persist/Rebuild modes, `/rag list|new|use|off|rebuild|info|delete|status`
- **Transparent retrieval**: active index auto-retrieves top-k chunks, injects into user message context; AI bubble shows collapsed footer (`📚 Retrieved from N sources`)
- HUD `📚 RAG:` field shows active index name

#### Tool Framework + Code Execution + Agentic Browsing (Phase 5)
- `BaseTool` / `ToolResult` / `ApprovalMode` (ASK/AUTO) — reusable tool abstraction
- `ToolRunner` — approval-gated execution; `ask_fn` callback for TUI approval; auto mode bypasses prompt
- **Code execution** (`tools/exec.py`): runs user code via PATH runtimes (python3, bash, node, ruby, go, sqlite3); 30s timeout; styled output bubble (stdout/stderr/exit/duration); result fed to AI; `/exec <lang> <code>` / `/exec mode ask|auto`
- **Agentic browsing** (`browse/fetch.py`): two-tier (snippets via search backends + full-page httpx default, optional Playwright headless via `[browser]` extra); `/browse <url|query>` / `/browse mode ask|auto|http|headless`

#### MCP — Model Context Protocol (Phase 6)
- **Built-in servers** (no SDK required): FilesystemServer (list_dir, read_file), SessionsServer (list_sessions, get_session), RAGServer (rag_search), SearchServer (web_search)
- **External client** (`mcp/client.py`): stdio and SSE transport via `mcp` SDK (`pip install anythink[mcp]`); lazy import with `MCPError` guidance
- **Anythink as server** (`mcp/server.py`): exposes built-in tools via FastMCP; `/mcp server start|stop|status`
- `MCPManager` — routing table, tool discovery, `call_tool()` dispatch
- `/mcp list|tools|connect|disconnect|status|call <tool> [k=v ...]|server`

#### 4-Panel Dashboard Mode (Phase 7)
- `Ctrl+D` toggles Simple ↔ Dashboard; `anythink --dashboard` launches directly; all panels always composed, hidden via CSS `display: none` in simple mode
- **Left panel** (`SessionListPanel`): scrollable session list with timestamps; click to load session into center; `Ctrl+L` toggles visibility
- **Right panel** (`StatsPanel`): live model, token usage %, branch, MCP server count, RAG index; `Ctrl+R` toggles
- **Bottom tabs** (`TabbedContent`): Files (directory browser via FilesystemServer), RAG (index list with active marker), Tool Output (cumulative tool call log with timestamps)
- Tool call events from exec/browse/MCP workers automatically routed to Tool Output tab

#### Voice Input (Phase 8)
- `VoiceRecorder` — non-blocking `sounddevice.InputStream` callback; float32 NumPy output; `[voice]` extra
- `VoiceTranscriber` — lazy-loads Whisper model; stereo→mono conversion; language pin or auto-detect; empty audio short-circuits model load
- TUI flow: `/voice` → "Recording… press Enter to stop" → `asyncio.to_thread` stop + transcribe → text in Input widget (editable before sending)
- `/voice model tiny|base|small|medium|large|turbo` / `/voice language <code>`

#### Desktop Notifications (Phase 8)
- Cross-platform backends: Windows (PowerShell toast), macOS (`osascript`), Linux (`notify-send`), NullBackend fallback
- Per-type toggles: `rag_build_done`, `slow_response` (≥15s), `exec_done` (≥10s), `browse_done`, `provider_failure`
- `/notify on|off|status` / `/notify type <name> on|off`

### Changed — V1 Features Preserved
- All V1 slash commands intact: `/help`, `/clear`, `/history`, `/tokens`, `/model`, `/persona`, `/session`, `/file`, `/image`, `/files`, `/search`, `/plugins`, `/exit`, `/quit`
- All V1 providers unchanged (Groq, Gemini, OpenAI, Anthropic, Mistral, Cohere, Ollama, LM Studio)
- All V1 key management, model aliases, session persistence, XDG paths unchanged
- `anythink` (no flag) still starts Simple Chat Mode — V1 UX preserved

### Technical
- 937 tests, 80%+ coverage enforced
- ruff / black / mypy-strict / bandit all clean
- CI matrix: Python 3.11, 3.12, 3.13; extras-install verification step
- OIDC trusted publishing via `publish.yml` on `v*.*.*` tags

[2.0.0]: https://github.com/dhineshtheprogrammer/anythink_ai/releases/tag/v2.0.0

---

## [0.1.0] — 2026-06-19

Initial release of Anythink — a universal, AI-powered CLI chatbot.

### Added

#### Core & Configuration
- `AnythinkError` exception hierarchy: `ConfigError`, `ProviderError` (+ `AuthenticationError`, `RateLimitError`, `ProviderUnavailableError`, `ModelNotFoundError`), `SessionError`, `KeychainError`, `PluginError`, `SearchError`, `FileError`
- `AppConfig` frozen dataclass with XDG Base Directory compliant storage
- `ConfigManager` for loading/saving `config.yaml`; `Paths` helper resolving all XDG dirs
- 4 built-in color themes: **Midnight** (default), **Aurora**, **Ember**, **Arctic**

#### LLM Providers
- `BaseProvider` ABC with `stream_chat`, `list_models`, `test_connection`, `supports_vision`, `requires_api_key`
- Built-in providers: Groq, Google Gemini, OpenAI, Anthropic, Mistral, Cohere, Ollama, LM Studio
- Optional extras: `pip install anythink[groq|gemini|openai|anthropic|mistral|cohere|all]`
- Provider registry via Python `anythink.providers` entry points

#### Terminal UI
- ASCII logo startup banner (version, model alias, provider)
- `StreamRenderer`: real-time token streaming with Rich markup
- `ContextStatusBar`: live token usage bar with color thresholds (green → yellow → orange → red)
- `make_console` / `make_prompt_session`: theme-aware terminal I/O

#### Chat Loop
- Interactive async chat loop with slash command dispatch and legacy `exit`/`quit` shortcuts
- Persona / system prompt management: `/persona <name>|clear`
- Approaching-context-limit warnings at 60 % / 85 % / 95 % thresholds

#### API Key Management
- OS keychain storage via `keyring` (macOS Keychain, Linux Secret Service, Windows Credential Manager)
- YAML index file tracks configured providers (keyring has no list-by-service API)
- CLI: `anythink keys add|show|update|delete|test <provider>`

#### Model Aliases
- `ModelAlias` + `ModelRegistry` backed by `models.yaml`
- Friendly user-defined names for provider/model pairs with context-window sizes and vision flags
- CLI: `anythink model add|list|remove`

#### Session Management
- `Session` + `SessionManager` with JSON-backed storage in `$XDG_DATA_HOME/anythink/sessions/`
- Automatic session saving after each conversation (configurable via `session_autosave`)
- Session search by name or ID prefix
- `/session save|load|list|delete|rename` slash commands

#### Slash Command System
- `CommandRegistry` with entry-point discovery (`anythink.slash_commands`)
- `CommandResult` pattern (`should_exit`, `message`, `error`) drives the chat loop
- Built-in commands: `/help`, `/clear`, `/history`, `/tokens`, `/model`, `/persona`, `/session`, `/file`, `/image`, `/files`, `/search`, `/plugins`, `/exit`, `/quit`

#### File Input & Multimodal Support
- `TextAttachment` (≤ 1 MB, UTF-8): `.py`, `.js`, `.ts`, `.go`, `.rs`, `.json`, `.yaml`, `.md`, `.txt`, and 20+ more extensions
- `ImageAttachment` (≤ 10 MB): PNG, JPEG, WEBP, GIF with automatic MIME-type mapping
- `read_file()` auto-detects type by extension; `read_text_file()` / `read_image_file()` for explicit type
- Multimodal messages: `TextPart` (file header + content) + `ImagePart` + `TextPart` (user text) via `ChatMessage.content: list[ContentPart]`
- `ChatState.pending_attachments` cleared after each send

#### Agentic Web Search
- `BaseSearchBackend` ABC; `SearchResult` dataclass
- `DuckDuckGoSearch`: free, lazy-imports `duckduckgo-search` (`pip install anythink[search]`)
- `SerpAPISearch`: async `httpx` client, Google results via SerpAPI (requires key)
- `SearchRegistry` with entry-point discovery and `get_available(preferred)` fallback
- Auto-search mode: `/search on|off` injects results as `TextPart` before each user message
- One-off search: `/search <query>` shows title / URL / snippet in terminal
- `AppContext.search_registry` wired at startup (SerpAPI key looked up from keychain)

#### Plugin Architecture
- `PluginInfo` dataclass: name, version, description, author, entry_point_groups, homepage
- `PluginManager.list_plugins()` discovers packages contributing to any `anythink.*` entry point group via distribution metadata
- `PluginManager.install(pkg)` / `remove(pkg)` wrap `pip` via `subprocess`
- `/plugins list|info|install|remove` slash commands
- CLI: `anythink plugins list|info|install|remove`

#### CI/CD
- GitHub Actions `ci.yml`: lint (ruff), format check (black), type check (mypy), security scan (bandit), test matrix (Python 3.11 / 3.12 / 3.13), coverage XML upload, build + `twine check`
- GitHub Actions `publish.yml`: tests → build → `twine check` → PyPI via OIDC trusted publishing (no stored secrets)
- 80 % minimum test coverage enforced (`--cov-fail-under=80`)
- 526 tests across 40+ test files

[0.1.0]: https://github.com/dhineshtheprogrammer/anythink_ai/releases/tag/v0.1.0
