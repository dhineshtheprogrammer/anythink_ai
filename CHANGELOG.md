# Changelog

All notable changes to Anythink are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
