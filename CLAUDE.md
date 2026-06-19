# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Anythink is a universal, AI-powered CLI chatbot (`pip install anythink`) built in Python 3.11+. The full implementation is present: providers, chat loop, session management, slash commands, file/image attachments, web search, plugin system, and UI theming.

## Commands

```bash
# Install for development (editable, with all dev tools)
pip install -e ".[dev]"

# Run the CLI
anythink                    # start chat session
anythink --version
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

Coverage minimum is 80% (enforced via `--cov-fail-under=80` in `pyproject.toml`). `src/anythink/ui/input.py` is excluded from coverage.

## Architecture

### Dependency injection via AppContext

`app/context.py:AppContext` is the single DI container constructed once at startup and threaded through the entire call stack. It holds every subsystem: `config`, `console`, `theme`, `key_manager`, `provider_registry`, `model_registry`, `persona_manager`, `session_manager`, `search_registry`, and `plugin_manager`. No module-level globals exist. Tests inject `Console(file=StringIO())` through this container.

### Chat loop

`app/chat.py:ChatApp.run()` is the async event loop: banner → prompt → (optional search/attachments) → `provider.stream_chat()` → `StreamRenderer.stream()` → append to history → repeat. State lives in `ChatState` (provider, model_id, history, pending_attachments, etc.). On clean exit it autosaves the session when `config.session_autosave` is True.

### Provider system

`providers/base.py` defines `BaseProvider` (ABC) with three required async methods: `stream_chat()`, `list_models()`, `test_connection()`. Providers are **pure**: they never fetch their own API key; the caller passes `api_key` at construction. SDKs are imported lazily inside methods (guarded by `TYPE_CHECKING`) so missing optional packages fail loudly only when the provider is actually used.

`providers/registry.py:ProviderRegistry` discovers providers via the `anythink.providers` entry point group at runtime. Same pattern for `search/registry.py:SearchRegistry` (group `anythink.search_backends`) and `commands/registry.py:CommandRegistry` (group `anythink.slash_commands`).

### Slash command system

`commands/base.py` defines `SlashCommand` (name, description, handler, usage) and `CommandResult` (should_exit, message, error). All built-in commands live in `commands/handlers.py:register_commands()`. The registry dispatches `/cmd args` by splitting on whitespace and routing to the async handler.

### Session persistence

`session/manager.py:SessionManager` saves/loads/lists sessions as YAML files under `$XDG_DATA_HOME/anythink/sessions/`. `find_by_name_or_id()` matches exact name first, then ID prefix.

### Key management

`keys/manager.py:KeyManager` wraps the OS keychain via the `keyring` library. Service name is `anythink-{provider}`.

### Config & storage (XDG)

All paths resolved in `config/manager.py:_resolve_paths()`:

| File/Dir | Location |
|---|---|
| Main config | `$XDG_CONFIG_HOME/anythink/config.yaml` |
| Model aliases | `$XDG_CONFIG_HOME/anythink/models.yaml` |
| Personas | `$XDG_CONFIG_HOME/anythink/personas.yaml` |
| Sessions | `$XDG_DATA_HOME/anythink/sessions/` |
| Logs | `$XDG_STATE_HOME/anythink/logs/` |

`AppConfig` (`config/schema.py`) is a frozen dataclass. Valid themes: `midnight`, `aurora`, `ember`, `arctic`.

### Plugin system

Plugins are third-party PyPI packages. `plugins/manager.py:PluginManager` discovers them by inspecting installed packages for entry points in any `anythink.*` group. Install/remove delegates to `pip` via subprocess.

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
```

Always raise the most specific subclass. `user_message` is what gets printed to the terminal.

### Testing conventions

The `xdg_dirs` fixture in `tests/conftest.py` redirects all four XDG env vars to `tmp_path` subdirectories and returns a `Paths` object. Every test touching the filesystem must use `xdg_dirs` (or `config_manager` which builds on it). The `PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring` env var must be set whenever a test imports keyring code.
