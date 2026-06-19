# Anythink — Implementation Plan

## Context

The repository contains only a comprehensive spec document (`anythink_app_description.md`) and a `.gitignore`. No source code exists yet. This plan translates the spec into a phased, buildable implementation for **Anythink** — a universal AI-powered CLI chatbot (Python 3.11+, PyPI package `anythink`, CLI command `anythink`).

---

## Architectural Principles

- **Async-first I/O**: All provider/search calls are `async`; the chat loop runs under `asyncio.run()`.
- **Protocol-based abstraction**: `typing.Protocol` for search backends (no import dependency on core); `ABC` for providers (shared retry/fallback logic in base class).
- **Dataclasses for models**: `ChatMessage`, `Session`, `ModelAlias`, `Persona` — no Pydantic (avoids startup weight; simple YAML validation is sufficient).
- **Entry-points plugin system from day one**: Built-in providers, search backends, and slash commands are all registered via `pyproject.toml` entry points, identical to third-party plugins. One discovery code path.
- **Dependency injection via `AppContext`**: A mutable `AppContext` dataclass holds provider, config, console, session manager, command registry, history, etc. Sub-systems receive it; no module-level globals.
- **Rich `Console` as a singleton**: Created at startup, injected everywhere. Tests inject `Console(file=StringIO())` for capture.

---

## Target Directory Structure

```
src/anythink/
├── cli.py                   # Typer entry point + `keys` + `model` sub-apps
├── app.py                   # Chat loop orchestrator
├── context.py               # AppContext dataclass
├── exceptions.py            # Exception hierarchy
├── config/
│   ├── manager.py           # XDG Paths, load/save config.yaml
│   ├── schema.py            # AppConfig frozen dataclass + defaults
│   ├── models.py            # ModelAlias + ModelRegistry (models.yaml)
│   └── personas.py          # Persona + PersonaManager (personas.yaml)
├── providers/
│   ├── base.py              # BaseProvider ABC, ChatMessage, StreamChunk, ContentPart, TokenUsage
│   ├── registry.py          # Entry-point discovery
│   ├── groq.py / openai.py / anthropic.py / gemini.py / mistral.py / cohere.py
│   ├── ollama.py            # httpx-based (no SDK)
│   └── lm_studio.py         # Subclass of OpenAIProvider with custom base_url
├── ui/
│   ├── theme.py             # Theme dataclass + 4 constants (MIDNIGHT/AURORA/EMBER/ARCTIC)
│   ├── banner.py            # print_banner(console, theme, version, alias, provider)
│   ├── renderer.py          # StreamRenderer (Live) + ResponseRenderer (Markdown)
│   ├── input.py             # prompt_toolkit PromptSession: Shift+Enter multiline, slash completion
│   ├── status.py            # ContextStatusBar with color thresholds
│   └── console.py           # make_console(theme, file=None) factory
├── commands/
│   ├── registry.py          # CommandRegistry with entry-point discovery
│   ├── parser.py            # "/cmd arg1 arg2" → (cmd, args), respects quotes
│   └── handlers.py          # All 30+ built-in slash commands + register_commands()
├── session/
│   ├── manager.py           # SessionManager: new/save/load/list/search/delete
│   ├── models.py            # Session, SessionSummary dataclasses
│   └── serializer.py        # Plain-text read/write (delimiter-based, grep-friendly)
├── files/
│   ├── reader.py            # FileReader: text injection with token estimate
│   └── image.py             # ImageReader: base64 + vision capability check
├── search/
│   ├── base.py              # BaseSearchBackend Protocol, SearchResult dataclass
│   ├── registry.py          # Entry-point discovery
│   ├── serpapi.py           # SerpAPI implementation
│   └── duckduckgo.py        # Zero-config fallback (duckduckgo-search library)
├── keys/
│   └── manager.py           # KeyManager wrapping keyring; keyring_index.yaml for list()
├── plugins/
│   └── loader.py            # PluginLoader: discover_all(), load_provider(), load_commands()
└── wizard/
    ├── setup.py             # SetupWizard: 8-step orchestrator
    └── steps.py             # WelcomeStep, ThemeStep, ProviderStep, ApiKeyStep, ...
tests/
├── conftest.py              # xdg_dirs fixture (patches all XDG_ env vars to tmp_path)
└── test_providers/ test_config/ test_commands/ test_session/ test_ui/ test_files/ test_search/ test_wizard/
```

---

## Implementation Phases

### Phase 1 — Project Skeleton
**Deliverable:** `pip install -e .` works; `anythink --version` prints version; CI pipeline runs lint + type check on the empty skeleton.

- Create `pyproject.toml` with `hatchling`, all optional extras (`[groq]`, `[gemini]`, `[openai]`, `[anthropic]`, `[mistral]`, `[cohere]`, `[all]`), all entry point groups declared
- Core deps: `typer[all]`, `rich>=13.7`, `prompt_toolkit>=3.0`, `keyring>=25`, `pyyaml>=6`, `httpx>=0.27`
- `src/anythink/__init__.py` (exports `__version__`), `cli.py` (stub), `exceptions.py` (full hierarchy)
- `tests/conftest.py` with the `xdg_dirs` tmp fixture (foundational for all tests)
- `.github/workflows/ci.yml`: lint (ruff + black), mypy, pytest matrix (3.11/3.12/3.13), bandit, build
- `.github/workflows/publish.yml`: OIDC trusted publishing to PyPI on `v*.*.*` tags

**Exception hierarchy:**
```
AnythinkError → ConfigError, ProviderError (Auth/RateLimit/Unavailable/NotFound), SessionError, KeychainError, PluginError, SearchError
```

### Phase 2 — Config System (XDG)
**Deliverable:** Config loading/saving, ModelRegistry, PersonaManager all work and are fully tested.

- `config/manager.py`: `Paths` dataclass resolves `XDG_*` env vars; `ConfigManager.load()` → frozen `AppConfig`; `ConfigManager.save()`
- `config/schema.py`: `AppConfig` frozen dataclass with all fields and defaults
- `config/models.py`: `ModelAlias` dataclass; `ModelRegistry` backed by `models.yaml` (lazy-load + dirty flag)
- `config/personas.py`: `Persona` dataclass; `PersonaManager` backed by `personas.yaml`
- **Key decision:** config uses simple manual type checking (not Pydantic); `validate_config()` returns a `list[ConfigError]` (all errors at once, not raise-on-first)

### Phase 3 — Provider Abstraction + All Providers
**Deliverable:** All 9 providers implemented; smoke-testable against mocked HTTP.

- `providers/base.py`: `BaseProvider` ABC with `stream_chat() → AsyncIterator[StreamChunk]`, `list_models()`, `test_connection()`, `supports_vision`, `requires_api_key`; `ChatMessage`, `StreamChunk`, `ContentPart` (TextPart/ImagePart union), `TokenUsage`
- `providers/registry.py`: `importlib.metadata.entry_points(group="anythink.providers")`
- All provider implementations; LM Studio/llama.cpp subclass `OpenAIProvider` (custom `base_url`); Ollama uses `httpx` directly against `/api/chat`
- Each provider maps its SDK exceptions to `AnythinkError` subclasses
- Provider `__init__` takes `api_key` and `base_url` — keys are passed by the caller, not fetched inside
- Tests: `pytest-httpx` (or `respx`) mocks; test streaming, error mapping, each provider independently

### Phase 4 — Terminal UI (Rich + prompt_toolkit)
**Deliverable:** Full UI shell: banner, themes, multi-line input, two-phase streaming renderer, context status bar.

- `ui/theme.py`: `Theme` dataclass + 4 color constants; `ThemeManager.get_theme(name)`
- `ui/console.py`: `make_console(theme, file=None)` — tests inject `Console(file=StringIO())`
- `ui/banner.py`: `print_banner(console, theme, version, alias, provider)` — ASCII art as string constant
- `ui/renderer.py`: `StreamRenderer` uses `rich.live.Live`; streams plain text, then `ResponseRenderer` re-renders final `Markdown` in a styled `Panel` (two-phase, per spec)
- `ui/input.py`: `PromptSession` with `Shift+Enter` multi-line, `/`-triggered slash command autocompletion, `FileHistory`
- `ui/status.py`: `ContextStatusBar.render(used, total)` → colored `Text`; thresholds at 60%/85%/95%
- Tests: all via `Console(file=StringIO())`; test banner contains "ANYTHINK"; test status bar color at each threshold

### Phase 5 — Key Management + App Orchestrator
**Deliverable:** First working end-to-end chat: `anythink` opens, user chats, sessions auto-save.

- `keys/manager.py`: `KeyManager` wrapping `keyring`; `keyring_index.yaml` tracks which providers have stored keys (since keyring has no `list_all`)
- `context.py`: `AppContext` mutable dataclass (config, paths, console, theme, provider, active_model_alias, key_manager, session_manager, model_registry, persona_manager, command_registry, search_manager, active_persona, history, context_tokens_used, pending_attachments)
- `app.py` chat loop: banner → status bar → loop(get_input → slash dispatch or message → stream → autosave → update status → check thresholds)
- Fallback on `ProviderError`: display error, `radiolist_dialog` for provider switch, preserve history
- Token count: use `StreamChunk.usage` when available; fall back to `len(text.split()) * 1.3` estimate
- Tests: `MockProvider` fixture; test full loop with mocked streaming; test fallback path

### Phase 6 — Slash Command System
**Deliverable:** All 30+ built-in slash commands work; registry extensible via entry points.

- `commands/parser.py`: `parse_command(text) → (cmd, args) | None`; respects quoted args
- `commands/registry.py`: loads from `entry_points(group="anythink.slash_commands")`; flat `dict[str, SlashCommand]` with alias resolution
- `commands/handlers.py`: `async def handle_X(ctx, args)` for each command; grouped by category; `register_commands() → list[SlashCommand]`
- Handler pattern: each command receives `AppContext` and args; modifies context in place or prints to `ctx.console`
- `/plugins install <name>`: calls `subprocess.run([sys.executable, "-m", "pip", "install", name])`; warns user to restart

### Phase 7 — Session Management
**Deliverable:** Auto-save works; `/history` commands work; sessions are human-readable plain text.

- `session/serializer.py`: delimiter-based plain-text format (`=== USER [timestamp] ===` etc.); `SessionSummary` extracted by reading header lines only (no full file load for listings)
- `session/manager.py`: `new_session()`, `save()` (as `asyncio.to_thread(save_sync, session)` to avoid blocking), `load()`, `list_sessions()`, `search_sessions()` (simple `str.lower() in line.lower()`), `delete()`
- Reuse `xdg_dirs` fixture; test round-trip serialization; test search finds right files

### Phase 8 — File Input & Multimodal Support
**Deliverable:** `/file` and `/image` commands attach content to next message; vision check works.

- `files/reader.py`: `FileReader.read(path) → Attachment`; warns if estimated tokens push context over 80%
- `files/image.py`: `ImageReader.read(path) → Attachment`; validates extension; checks `ctx.provider.supports_vision`
- `AppContext.pending_attachments: list[Attachment]` cleared after each message submission
- Content injection: text → `<file:name>\ncontent\n</file:name>` wrapper; image → `ImagePart(bytes, mime_type)`; each provider maps `ContentPart` list to its own API format

### Phase 9 — Web Search Integration
**Deliverable:** AI-triggered and user-triggered search; source URLs in responses.

- `search/base.py`: `BaseSearchBackend` Protocol; `SearchResult(title, url, snippet, retrieved_at)`
- `search/duckduckgo.py`: zero-config default using `duckduckgo-search` library
- `search/serpapi.py`: requires API key
- Tool-use: search exposed as function/tool in system prompt; `App` detects `finish_reason="tool_calls"` and dispatches; for non-tool-use providers, heuristic keyword trigger ("latest", "current", "today", "news")

### Phase 10 — Plugin Architecture
**Deliverable:** `PluginLoader.discover_all()` works; external plugins install and auto-discover.

- `plugins/loader.py`: `discover_all() → list[PluginInfo]`; cross-references entry points with `importlib.metadata` for version/author; shows safety warning panel before first load of non-built-in plugin (cached in `plugins.yaml`)
- Verify that all built-in providers/search/commands are discoverable through the same entry-point path

### Phase 11 — First-Run Setup Wizard
**Deliverable:** 8-step wizard runs on first launch; injectable `input_fn` makes it fully testable.

- `wizard/steps.py`: `WizardStep` protocol; each step gets/sets `WizardContext` (accumulator)
- `wizard/setup.py`: `SetupWizard.run()`; sequence of steps; writes `config.yaml` + `models.yaml` at end
- Detection in `cli.py`: if `config.yaml` missing → run wizard before `App.run()`
- All interactive prompts injectable via `WizardContext.input_fn` for testing

### Phase 12 — CLI Sub-commands & Error Handling Polish
**Deliverable:** `anythink keys *` and `anythink model *` sub-commands work standalone; errors display beautifully.

- Typer sub-apps for `keys` and `model` in `cli.py`; these only need `ConfigManager` + `KeyManager`, not the full `App`
- Top-level exception handler: `AnythinkError` → friendly Rich `Panel` (red border); unexpected exceptions → traceback saved to `~/.local/state/anythink/logs/error_<datetime>.log`

### Phase 13 — CI/CD & PyPI Release
**Deliverable:** All CI stages green on Python 3.11/3.12/3.13; `pip install anythink` works from PyPI.

- Coverage ≥ 80%; `PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring` in CI for keyring
- OIDC trusted publishing (no long-lived API tokens in GitHub secrets)
- Complete `README.md` with installation, quick start, screenshots; `CHANGELOG.md` with 0.1.0 entry

---

## Critical Files

| File | Why Critical |
|------|-------------|
| `pyproject.toml` | Declares all dependencies, optional extras, and entry points — everything depends on this |
| `src/anythink/providers/base.py` | `BaseProvider`, `ChatMessage`, `StreamChunk`, `ContentPart` — the contract all providers and the UI are built against |
| `src/anythink/app.py` | Chat loop orchestrator — integration point for all subsystems |
| `src/anythink/config/manager.py` | XDG path resolution — touched by every subsystem |
| `src/anythink/ui/renderer.py` | Two-phase streaming renderer — defines the core UX |
| `tests/conftest.py` | XDG fixture — makes all tests hermetic without touching `~/.config` |

---

## Existing Utilities to Reuse

- `rich.live.Live` for streaming display
- `rich.markdown.Markdown` for final response render
- `rich.panel.Panel` for bordered UI elements
- `prompt_toolkit.shortcuts.radiolist_dialog` for interactive model/provider selection
- `importlib.metadata.entry_points` for plugin discovery (Python 3.12+ stdlib; `importlib_metadata` backport for 3.11)
- `asyncio.to_thread` for non-blocking file writes in session auto-save

---

## Verification

1. **Unit tests**: `pytest tests/ --cov=src/anythink --cov-report=term-missing`; target ≥ 80%
2. **End-to-end smoke test**: `pip install -e .[groq]` → `GROQ_API_KEY=xxx anythink` → type a message → verify streaming response, auto-saved session file in `~/.local/share/anythink/sessions/`
3. **Slash commands**: Verify `/help` lists all commands; `/theme aurora` changes colors; `/history` shows saved sessions; `/model list` shows aliases
4. **Plugin system**: Install a toy third-party package with an `anythink.providers` entry point; verify it appears in `/plugins` without code changes
5. **CI**: All GitHub Actions stages green on all three Python versions
6. **PyPI**: `pip install anythink` on a clean virtualenv → `anythink --version` works





