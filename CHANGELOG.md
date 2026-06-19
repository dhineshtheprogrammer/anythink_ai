# Changelog

All notable changes to Anythink are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
