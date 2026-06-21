# Contributing to Anythink

Thank you for your interest in contributing!

## Development Setup

```bash
git clone https://github.com/dhineshtheprogrammer/anythink_ai
cd anythink_ai
pip install -e ".[all,dev]"
```

## Running Tests

The keyring backend must be set to avoid OS keychain prompts during tests:

```bash
# Full test suite
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/ -v

# Single test file
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/test_cli.py -v

# Single test by keyword
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/ -k "test_spend"
```

Coverage minimum is **80%**. New code must be covered by tests in the matching `tests/` directory.

## CI Gates

All four gates must pass before merging:

```bash
ruff check src/
black --check src/ tests/
mypy src/anythink
bandit -r src/anythink -c pyproject.toml
```

## Architecture Notes

### Dependency injection
All state lives in `AppContext` (`app/context.py`). No module-level globals. Tests inject `Console(file=StringIO())` through the container.

### Adding a new slash command
1. Write `async def _my_cmd(ctx, args, state, registry) -> CommandResult` in `commands/handlers.py`
2. Register it in `register_commands()` with `SlashCommand("name", "desc", _my_cmd, "/usage")`
3. For TUI-layer work (confirmation prompts, background workers), return `CommandResult(action="my_action", extra={...})`
4. Handle the action string in `_dispatch_command()` in `ui/textual/app.py`

### Adding a new manager (YAML-backed store)
Follow the `PersonaManager` pattern in `config/personas.py`:
- YAML file, lazy-load via `_load()`, `_dirty` flag, `add/remove/get/list_all/exists/save` methods
- Wire the new manager into `AppContext` (field + `create()` initialization)
- Add a `@property` to `Paths` for the backing file path

### Adding a new LLM provider
1. Create `src/anythink/providers/<name>.py` subclassing `BaseProvider`
2. Implement `stream_chat()`, `list_models()`, `test_connection()`, `supports_vision`, `requires_api_key`
3. Call `_resolve_params(gen_params, temperature, max_tokens)` at the top of `stream_chat()` and forward the supported subset to the SDK
4. Import the SDK lazily inside methods only — never at module level
5. Register in `pyproject.toml` under `[project.entry-points."anythink.providers"]`
6. Add the SDK to the matching optional extra and to `all`

## Submitting Changes

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes with tests (maintain 80%+ coverage)
4. Ensure all four CI gates pass
5. Open a pull request

## Plugin Development

Anythink is extensible via Python entry points. You can contribute:
- **Provider plugins** — `anythink.providers`
- **Search backends** — `anythink.search_backends`
- **Slash commands** — `anythink.slash_commands`
- **Embedding backends** — `anythink.embedding_backends`
- **Tools** — `anythink.tools`
- **MCP servers** — `anythink.mcp_servers`
