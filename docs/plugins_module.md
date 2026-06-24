# `src/anythink/plugins/` — Plugin Discovery and Management

This module provides Anythink's plugin layer: the data model that represents an
installed plugin, and the manager that discovers, inspects, installs, removes,
and invokes hook points from third-party packages. It is a thin but important
seam between the Anythink core and any external package that extends it.

---

## Folder Structure

```
src/anythink/plugins/
├── __init__.py    # Package marker; single-line docstring
├── models.py      # PluginInfo dataclass — metadata for one installed plugin
└── manager.py     # PluginManager — discovery, pip install/remove, V4 hook invocation
```

---

## File-by-File Reference

---

### `__init__.py`

**Purpose:** Makes `anythink.plugins` a Python package.

**Contents:** A single module-level docstring:

```python
"""Plugin discovery and management for Anythink."""
```

Nothing is re-exported. Callers import directly from submodules:

```python
from anythink.plugins.manager import PluginManager
from anythink.plugins.models import PluginInfo
```

---

### `models.py`

**Purpose:** Defines the `PluginInfo` dataclass — the single data model used
throughout the plugin system to represent one installed plugin package.

#### `PluginInfo` (dataclass)

```python
@dataclass
class PluginInfo:
    name: str
    version: str
    description: str
    author: str
    entry_point_groups: list[str] = field(default_factory=list)
    homepage: str = ""
```

| Field                 | Type        | Required | Description |
|-----------------------|-------------|----------|-------------|
| `name`                | `str`       | Yes      | PyPI / distribution package name (e.g. `"anythink-openai"`) |
| `version`             | `str`       | Yes      | Installed version string (e.g. `"1.2.0"`) |
| `description`         | `str`       | Yes      | One-line summary from the package's `Summary` metadata field |
| `author`              | `str`       | Yes      | Author string from the package's `Author` metadata field |
| `entry_point_groups`  | `list[str]` | No       | All Anythink entry-point groups this package contributes to (populated by `list_plugins`) |
| `homepage`            | `str`       | No       | URL from `Home-page` metadata, empty string if absent |

**Source of data:** `PluginInfo` objects are always built by `PluginManager.list_plugins()` by
reading `importlib.metadata` distribution metadata. They are never constructed
manually in production code.

**Usage:** Returned by `PluginManager.list_plugins()` and `PluginManager.get_plugin()`.
Consumed by the `/plugins list` and `/plugins info` slash commands and by the
`anythink plugins list|info` CLI sub-commands.

---

### `manager.py`

**Purpose:** The core plugin subsystem. `PluginManager` does three things:

1. **Discovery** — scans installed packages via entry points to find plugins.
2. **Package management** — wraps `pip install` / `pip uninstall` so the TUI
   and CLI can install/remove plugins without leaving the terminal.
3. **V4 MMOS hook invocation** — fires `pre_routing` and `post_phase` plugin
   hook points at query time.

#### Module-level constant

```python
_PLUGIN_GROUPS = [
    "anythink.providers",
    "anythink.search_backends",
    "anythink.slash_commands",
    # V4 MMOS hook groups
    "anythink.pre_routing_hooks",
    "anythink.post_phase_hooks",
]
```

This list defines **which entry-point groups are considered "Anythink plugin
groups"**. A package is only recognised as an Anythink plugin if it contributes
at least one entry point to one of these groups. Adding a new extensible
subsystem means adding its group name here.

#### `PluginManager`

No constructor arguments. `PluginManager()` is instantiated once at startup
inside `AppContext` and stored as `ctx.plugin_manager`.

---

##### Discovery methods

**`list_plugins() -> list[PluginInfo]`**

Returns a sorted (by name) list of all installed packages that contribute to at
least one group in `_PLUGIN_GROUPS`.

Algorithm:

```
for each group in _PLUGIN_GROUPS:
    for each entry point in that group:
        if ep.dist is None → skip (built-in or editable with no dist info)
        read dist.metadata["Name"], dist.version, Summary, Author, Home-page
        if name not yet seen → create PluginInfo, add group to entry_point_groups
        if name already seen → append group to existing entry_point_groups (dedup)
return sorted by name
```

Key behaviour:
- A package that contributes to multiple groups (e.g. provides both a provider
  and a slash command) appears **once** with all its groups listed in
  `entry_point_groups`.
- Built-in entry points (where `ep.dist is None`) are skipped — only third-party
  packages appear in the list.
- Returns `[]` when no external plugins are installed.

**`get_plugin(name: str) -> PluginInfo | None`**

Case-insensitive lookup. Calls `list_plugins()` and scans for
`p.name.lower() == name.lower()`. Returns the matching `PluginInfo` or `None`.

---

##### Package-management methods

Both methods use `subprocess.run` in **list-form** (not shell-form) to prevent
command injection. The `# nosec B603` annotation documents that the security
implication is understood — the package name comes from the user (CLI argument
or slash command input) but is passed as a single argument, not shell-interpolated.

**`install(package_name: str) -> tuple[bool, str]`**

Runs:
```
<current python> -m pip install <package_name>
```

Returns `(True, combined_output)` on success (exit code 0), or
`(False, combined_output)` on failure. `combined_output` is `stdout + stderr`
from pip, which callers display to the user.

**`remove(package_name: str) -> tuple[bool, str]`**

Runs:
```
<current python> -m pip uninstall -y <package_name>
```

The `-y` flag suppresses pip's interactive confirmation prompt. Returns the same
`(bool, str)` tuple as `install`.

**Important:** After `install` or `remove` the plugin does **not** take effect
immediately. Entry points are read at import time, so a restart of Anythink is
required. The `/plugins install` and `/plugins remove` slash commands inform the
user of this with "Restart Anythink to load it." / "Restart Anythink to apply
changes."

---

##### V4 MMOS hook methods

These two methods represent the V4 Multi-Modal Orchestration System (MMOS) hook
layer. They call functions registered by plugins under two entry-point groups.
Both methods silently swallow all plugin errors (`# nosec B110`) so that a
broken plugin never blocks a user query.

**`invoke_pre_routing_hooks(query: str, intent: dict[str, Any]) -> dict[str, Any]`**

Called before the routing decision is made for a query.

- Iterates all entry points under `"anythink.pre_routing_hooks"`.
- Loads and calls each hook function as `hook_fn(query, intent)`.
- If the return value is a `dict`, merges it into an accumulator `hints` dict
  (later hooks can override earlier ones via `dict.update`).
- Returns the accumulated `hints` dict (empty `{}` when no hooks are registered
  or all fail).

**Hook function signature** expected by this method:
```python
def my_pre_routing_hook(query: str, intent: dict) -> dict:
    # inspect or augment routing intent
    return {"preferred_provider": "openai"}
```

**`invoke_post_phase_hooks(phase: dict[str, Any], output: str) -> str`**

Called after a reasoning/generation phase completes.

- Iterates all entry points under `"anythink.post_phase_hooks"`.
- Loads and calls each hook function as `hook_fn(phase, result)` where `result`
  starts as the original `output` and is replaced by each hook's return value if
  it returns a `str`.
- Non-string return values are ignored (original text is preserved).
- Returns the final (possibly transformed) output string.

**Hook function signature** expected by this method:
```python
def my_post_phase_hook(phase: dict, output: str) -> str:
    # transform or annotate the output
    return output + "\n[post-processed by MyPlugin]"
```

---

## Where `PluginManager` is Used

| Location | Usage |
|----------|-------|
| `app/context.py:187` | Instantiated once as `PluginManager()` and stored in `ctx.plugin_manager` |
| `commands/handlers.py` | `/plugins list`, `/plugins info`, `/plugins install`, `/plugins remove` slash commands call the four public methods |
| `cli.py` | `anythink plugins list|info|install|remove` CLI sub-commands each create a local `PluginManager()` instance |
| `config/validator.py` | Calls `ctx.plugin_manager.list_plugins()` during diagnostics (`anythink doctor`) to report installed plugin count |

---

## Error Handling

`PluginManager` itself does **not** raise `PluginError`. It returns
`(False, output)` on pip failures and `None` from `get_plugin` when not found.

`PluginError` (from `anythink.exceptions`) is raised by **other subsystems**
when they fail to load an entry point that a plugin was supposed to provide —
for example, `providers/registry.py` raises `PluginError` when
`ep.load()` fails for a registered provider. This distinction matters:

- Plugin management (install/remove/list) → graceful `(bool, str)` returns.
- Plugin consumption (loading a provider class at runtime) → `PluginError`.

---

## How to Write an Anythink Plugin

An Anythink plugin is a standard Python package published to PyPI. It extends
one or more Anythink subsystems by declaring entry points in its
`pyproject.toml`.

### Minimal example: adding a new LLM provider

```toml
# my-plugin/pyproject.toml
[project]
name = "anythink-myprovider"
version = "0.1.0"

[project.entry-points."anythink.providers"]
myprovider = "anythink_myprovider.provider:MyProvider"
```

### Minimal example: adding a slash command

```toml
[project.entry-points."anythink.slash_commands"]
mycommand = "anythink_myprovider.commands:MyCommand"
```

### Minimal example: a V4 pre-routing hook

```toml
[project.entry-points."anythink.pre_routing_hooks"]
myhook = "anythink_myprovider.hooks:pre_routing"
```

```python
# anythink_myprovider/hooks.py
def pre_routing(query: str, intent: dict) -> dict:
    if "weather" in query.lower():
        return {"preferred_provider": "openai"}
    return {}
```

### Installation

```bash
# Via CLI
anythink plugins install anythink-myprovider

# Via pip directly
pip install anythink-myprovider
```

Then restart Anythink for the new entry points to be discovered.

---

## Supported Entry-Point Groups

| Group | Consumed by | Purpose |
|-------|-------------|---------|
| `anythink.providers` | `ProviderRegistry` | Register new LLM providers |
| `anythink.search_backends` | `SearchRegistry` | Register new web search backends |
| `anythink.slash_commands` | `CommandRegistry` | Register new `/` slash commands |
| `anythink.pre_routing_hooks` | `PluginManager.invoke_pre_routing_hooks` | Influence routing before a query is dispatched (V4) |
| `anythink.post_phase_hooks` | `PluginManager.invoke_post_phase_hooks` | Transform or annotate generation output after a phase (V4) |

---

## Key Design Decisions

- **`PluginManager` has no state** — it re-reads entry points on every call.
  This is intentional: installs done outside the running process (e.g. a
  separate `pip install` in another terminal) are picked up after restart
  without needing to re-initialise.
- **Silent hook failures** — `invoke_pre_routing_hooks` and
  `invoke_post_phase_hooks` catch all exceptions per hook so that a buggy
  plugin can never break a user's query. Errors are discarded, not logged,
  to keep the hot path zero-overhead when no debug mode is active.
- **List-form subprocess for pip** — `subprocess.run([...], ...)` rather than
  `subprocess.run("pip install " + name, shell=True)` prevents shell injection.
  The `# nosec B603` annotation on each call makes the security review explicit.
- **No plugin sandboxing** — Plugins run in the same process with full access.
  Users are responsible for trusting the packages they install.
- **`ep.dist is None` guard** — Built-in entry points (editable installs without
  a proper distribution, or namespace packages) don't have a `.dist` attribute.
  Skipping them keeps the plugin list clean of Anythink's own internals.
