# `src/anythink/schedule` — Scheduled Prompt Automation Module

## Purpose

The `schedule` package implements Anythink's prompt automation system. It lets users define named prompts that run automatically on a cron schedule — for example, a daily morning digest, a weekly report, or a recurring code review. Schedules persist across sessions in a YAML file, execute through the full provider stack (same path as manual chat), and can be triggered from three different surfaces: the TUI slash command, the CLI, and the foreground scheduler daemon.

The package has four source files:

| File | Responsibility |
|---|---|
| `__init__.py` | Package marker |
| `models.py` | `ScheduledPrompt` dataclass — the single unit of configuration |
| `manager.py` | `ScheduleManager` — YAML-backed CRUD store for all schedules |
| `runner.py` | `ScheduleRunner` + `_is_due()` — cron evaluation and prompt execution |

---

## File: `__init__.py`

```python
"""Scheduled prompt automation for Anythink."""
```

Empty beyond its module docstring. Makes `src/anythink/schedule/` a Python package. No symbols are re-exported.

---

## File: `models.py`

**Full path:** `src/anythink/schedule/models.py`

Defines the single data structure that represents one scheduled task.

---

### `ScheduledPrompt`

```python
@dataclass
class ScheduledPrompt:
    name: str
    cron_expr: str
    prompt: str
    alias: str | None = None
    output_file: str | None = None
    enabled: bool = True
    last_run: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
```

**Location:** `models.py:11`

A named prompt that runs automatically on a cron schedule. One instance corresponds to one entry in `schedules.yaml`.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | Unique human-readable identifier (e.g. `"morning-digest"`). Used as the dict key in `ScheduleManager` and as the YAML entry's primary key. |
| `cron_expr` | `str` | required | Standard 5-field cron expression (minute hour day month weekday). Examples: `"0 9 * * 1"` (Monday 09:00), `"*/30 * * * *"` (every 30 minutes), `"0 8 * * 1-5"` (weekdays at 08:00). Evaluated by `croniter` (optional dep). |
| `prompt` | `str` | required | The full prompt text sent to the model. No template substitution is performed — the text is used verbatim. |
| `alias` | `str \| None` | `None` | Model alias name to use for this schedule. If `None`, falls back to `ctx.config.default_model_alias` at execution time. |
| `output_file` | `str \| None` | `None` | Absolute or relative path to a file where results are appended. If `None`, the result is shown via desktop notification only. Appended in the format `"\n\n--- <ISO timestamp> ---\n<result>\n"`. |
| `enabled` | `bool` | `True` | If `False`, the schedule is loaded but skipped by `_is_due()` and never fired by the runner. Toggled by `/schedule enable` and `/schedule disable`. |
| `last_run` | `datetime \| None` | `None` | UTC datetime of the most recent successful execution. `None` if the schedule has never run. Used by `_is_due()` to determine whether the schedule is overdue. |
| `created_at` | `datetime` | `datetime.utcnow()` | UTC datetime when the schedule was first created. Used for display ordering in `ScheduleManager.list_all()`. |

#### `to_dict() -> dict[str, Any]`

Serialises the object for YAML. Optional fields (`alias`, `output_file`, `last_run`) are omitted from the dict if they are `None`, keeping the YAML clean. `datetime` values are stored as ISO-8601 strings.

#### `from_dict(data: dict[str, Any]) -> ScheduledPrompt` (classmethod)

Deserialises from a YAML-loaded dict. Safe defaults:
- `enabled` defaults to `True` if absent.
- `alias`, `output_file` default to `None` via `dict.get()`.
- `created_at` defaults to `datetime.utcnow()` if the key is missing.
- `last_run` is `None` if the key is absent or its value is falsy.

---

## File: `manager.py`

**Full path:** `src/anythink/schedule/manager.py`

Contains `ScheduleManager`, the persistent CRUD store for all schedules. One instance lives at `AppContext.schedule_manager` for the entire application lifetime, constructed from a single YAML file path.

---

### `ScheduleManager`

```python
class ScheduleManager:
    def __init__(self, path: Path) -> None:
```

**Location:** `manager.py:15`

Backed by a single YAML file at `$XDG_CONFIG_HOME/anythink/schedules.yaml`. Schedules are stored as a YAML list of dicts, one per schedule, sorted by `created_at` on every save.

#### Internal state

| Attribute | Type | Initial value | Description |
|---|---|---|---|
| `_path` | `Path` | constructor arg | Path to `schedules.yaml` |
| `_schedules` | `dict[str, ScheduledPrompt] \| None` | `None` | In-memory cache; `None` means not yet loaded. Key is `schedule.name`. |
| `_dirty` | `bool` | `False` | Tracks whether unsaved changes exist. `save()` is a no-op when `False`. |

#### Lazy loading: `_load() -> dict[str, ScheduledPrompt]`

**Private.** Called at the start of every public method. Implements load-once caching:

1. If `_schedules` is not `None`, returns the cached dict immediately.
2. If the YAML file does not exist, sets `_schedules = {}` and returns it (empty store, no error).
3. Reads and parses the YAML file with `yaml.safe_load()`. If parsing fails, raises `ScheduleError`.
4. Builds the in-memory dict: `{entry["name"]: ScheduledPrompt.from_dict(entry) for entry in raw if "name" in entry}`. Entries missing a `"name"` key are silently skipped.

**Thread safety note:** `_load()` is not thread-safe. The scheduler daemon runs in a single `asyncio` event loop thread, and the TUI is also single-threaded, so this is not a practical issue.

---

#### `save() -> None`

Persists the current in-memory state to disk. Short-circuits immediately if `_dirty` is `False`.

1. Creates parent directories if needed (`parents=True, exist_ok=True`).
2. Sorts all schedules by `created_at` ascending before writing.
3. Serialises each via `to_dict()` and dumps as YAML with `default_flow_style=False, sort_keys=False`.
4. Resets `_dirty = False`.

`save()` is called internally at the end of every mutating method (`add`, `remove`, `enable`, `disable`, `update_last_run`), so the file is always up-to-date after any write. There is no explicit "commit" step — every mutation is immediately persisted.

---

#### `add(schedule: ScheduledPrompt) -> None`

Adds or replaces a schedule. If a schedule with the same `name` already exists it is overwritten without warning. Sets `_dirty = True` and calls `save()`.

---

#### `remove(name: str) -> None`

Deletes a schedule by name. Raises `ScheduleError(f"Schedule '{name}' not found.")` if the name does not exist. Saves immediately.

---

#### `get(name: str) -> ScheduledPrompt | None`

Returns the `ScheduledPrompt` for the given name, or `None` if it does not exist. Read-only; does not set `_dirty`.

---

#### `list_all() -> list[ScheduledPrompt]`

Returns all schedules sorted by `created_at` ascending (oldest first). Read-only. Used by `ScheduleRunner.run_all_due()` to enumerate candidates and by `/schedule list` for display.

---

#### `exists(name: str) -> bool`

Returns `True` if a schedule with that name exists. Thin wrapper over `name in self._load()`.

---

#### `enable(name: str) -> None`

Sets `enabled = True` on the named schedule using `dataclasses.replace()` (immutable replacement pattern, since `ScheduledPrompt` is a mutable dataclass but the replacement is used to keep usage consistent). Raises `ScheduleError` if not found. Saves immediately.

---

#### `disable(name: str) -> None`

Sets `enabled = False`. Otherwise identical to `enable()`. A disabled schedule remains in the YAML file and can be re-enabled at any time.

---

#### `update_last_run(name: str, dt: datetime) -> None`

Updates the `last_run` field to `dt` for the named schedule. Called by `ScheduleRunner.run_once()` after every successful execution to record when the schedule last fired. This is the mechanism that prevents `_is_due()` from re-firing the same schedule within the same cron window. Raises `ScheduleError` if not found. Saves immediately.

---

## File: `runner.py`

**Full path:** `src/anythink/schedule/runner.py`

Contains the cron evaluation logic and the execution engine. This file is the entry point for both the CLI foreground daemon and the TUI `/schedule run` flow.

---

### Module-level constant

```python
_POLL_INTERVAL_S = 60
```

Default number of seconds between schedule checks in `ScheduleRunner.start()`. Overridable via `anythink scheduler start --poll <seconds>`.

### Module-level logger

```python
log = logging.getLogger(__name__)
```

Used for `INFO` (successful completion) and `ERROR` (per-schedule failure) log messages. Controlled by the standard Python logging configuration.

---

### `_is_due(schedule: ScheduledPrompt, now: datetime) -> bool`

**Location:** `runner.py:26`

Determines whether a schedule should fire at the given moment. This is the core cron evaluation logic.

**Algorithm:**

1. If `schedule.enabled` is `False` → return `False` immediately.
2. Import `croniter` lazily. If unavailable (`ImportError` or any other exception), logs a warning and returns `False`.
3. Construct `croniter(schedule.cron_expr, now)` and call `cron.get_prev(datetime)` to get `prev` — the most recent time the cron expression *should have* fired before `now`.
4. If `schedule.last_run is None` → the schedule has never run → return `True` (fire immediately).
5. Normalise both `last_run` and `prev` to UTC-aware datetimes (add `UTC` tzinfo if naive) for safe comparison.
6. Return `last_run < prev` — the schedule is due if its most recent expected firing time has not yet been recorded as executed.

**Due-check semantics explained:**

The check `last_run < prev` means: "the most recent cron window has not yet been serviced." For example, with cron `"0 9 * * *"` (daily at 09:00) and `now = 09:05`:
- `prev = today 09:00`
- If `last_run = yesterday 09:00` → `yesterday 09:00 < today 09:00` → **due**
- If `last_run = today 09:00` → `today 09:00 < today 09:00` is `False` → **not due**

**Missed-run catch-up:** If the daemon was offline for multiple cron windows, only the most recent one is checked. The schedule fires once on the next poll, not once per missed window. This is intentional — it avoids flooding on restart.

**Error handling:** Any exception during the `croniter` check (invalid cron expression, import failure) is caught, logged as a warning with the schedule name, and returns `False`. A bad cron expression never crashes the runner.

**`croniter` is an optional dependency.** The module is importable without it. Callers only encounter an error at cron-check time if the package is missing.

---

### `ScheduleRunner`

**Location:** `runner.py:61`

```python
class ScheduleRunner:
    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
```

Holds a reference to the live `AppContext`. This gives it access to the full provider stack (model registry, key manager, provider registry), the notification system, and the schedule manager — exactly what is needed to execute a prompt as if the user had typed it.

---

#### `async run_once(schedule: ScheduledPrompt) -> str`

**Location:** `runner.py:69`

Executes one schedule immediately and returns the complete response text. This is the single execution unit used by all three trigger surfaces.

**Full execution sequence:**

1. **Resolve alias** — `alias_name = schedule.alias or ctx.config.default_model_alias`. Raises `ValueError` if neither is set.
2. **Resolve model alias object** — `ctx.model_registry.get(alias_name)`. Raises `ValueError` if not found.
3. **Fetch API key** — `ctx.key_manager.get_key(alias.provider)`.
4. **Get provider class** — `ctx.provider_registry.get(alias.provider)`. Raises `ValueError` if not registered.
5. **Instantiate provider** — `prov_cls(api_key=api_key)`.
6. **Build message list** — `[ChatMessage(role="user", content=schedule.prompt)]`. Single-turn, no history.
7. **Stream the response** — `async for chunk in provider.stream_chat(messages, alias.model_id, gen_params=alias.gen_params)`. Accumulates all chunk text into `full_text`. Uses the alias's configured `gen_params` (temperature, max_tokens, etc.).
8. **Capture UTC completion time** — `now = datetime.now(UTC)`.
9. **Write output file** (if `schedule.output_file` is set):
   - Creates parent directories if needed.
   - Opens in append mode (`"a"`) so previous runs are preserved.
   - Writes `"\n\n--- <ISO timestamp> ---\n<full_text>\n"`.
10. **Send desktop notification** — `ctx.notifier.notify("schedule_done", f"Anythink — {schedule.name}", full_text[:120])`. The notification preview is the first 120 characters of the response.
11. **Update last_run** — `ctx.schedule_manager.update_last_run(schedule.name, now)`. This persists to YAML immediately, so a subsequent `_is_due()` check in the same poll will not re-fire.
12. **Log completion** — `log.info("Schedule '%s' completed (%d chars).", schedule.name, len(full_text))`.
13. **Return `full_text`.**

**Error propagation:** `run_once()` does not catch exceptions. All errors bubble up to the caller. In `run_all_due()`, each call is wrapped individually. In the TUI `_run_schedule()` worker, the entire call is wrapped in `try/except` with an error bubble shown to the user. In the CLI `scheduler_run_once`, the exception is caught and printed.

**No RAG, no history, no plugins:** `run_once()` builds a minimal single-message conversation and calls `provider.stream_chat()` directly — bypassing the full `_stream_response()` TUI pipeline. This means RAG context injection, plugin hooks, spend tracking, and debug recording do **not** apply to scheduled runs. The TUI's `_run_schedule()` worker has the same limitation (it also calls `provider.stream_chat()` directly).

---

#### `async run_all_due(*, now: datetime | None = None) -> list[tuple[str, bool, str]]`

**Location:** `runner.py:130`

Checks all enabled schedules and fires any that are due. Called once per poll cycle by `start()`.

**Algorithm:**

1. `now = now or datetime.now(UTC)` — accepts an explicit `now` for testability.
2. `schedules = self._ctx.schedule_manager.list_all()` — loads all schedules.
3. `due = [s for s in schedules if _is_due(s, now)]` — filter to only those that should fire.
4. If `due` is empty, return `[]` immediately.
5. For each due schedule, create an `async def _run(s)` coroutine that:
   - Calls `await self.run_once(s)`.
   - On success: appends `(s.name, True, text[:80])` to `results`.
   - On exception: logs at `ERROR` level; appends `(s.name, False, str(exc))`.
6. Fires all due schedules **concurrently** with `asyncio.gather(*[_run(s) for s in due])`.
7. Returns `results`.

**Concurrency:** All due schedules fire in parallel within the same event loop. There is no semaphore limiting concurrent LLM calls. If many schedules happen to be due at the same time, they all run simultaneously. In practice this is rare (cron windows are infrequent), but a heavily loaded configuration could trigger multiple provider calls concurrently.

**Return value:** A list of `(name: str, success: bool, summary: str)` tuples. `summary` is either the first 80 characters of the response (on success) or the exception message (on failure). Used by `start()` to print a status line per schedule.

---

#### `async start(poll_interval: int = _POLL_INTERVAL_S) -> None`

**Location:** `runner.py:158`

The foreground blocking event loop. Entry point for `anythink scheduler start`. Runs indefinitely until interrupted.

**Algorithm:**

1. Prints a startup banner: how many enabled schedules are loaded and the poll interval.
2. Enters an infinite `while True` loop:
   a. Calls `await self.run_all_due()`.
   b. For each `(name, ok, summary)` in the results, prints a timestamped status line:
      ```
      [09:05:01] ✓ morning-digest: Good morning! Here is your daily...
      [09:05:03] ✗ broken-schedule: ValueError: Provider 'unknown' not registered.
      ```
   c. Calls `await asyncio.sleep(poll_interval)` to wait until the next check.
3. Catches `KeyboardInterrupt` (Ctrl+C from the terminal) and `asyncio.CancelledError` (task cancellation). Prints `"\nScheduler stopped."` and returns cleanly.

**No auto-restart on error:** If `run_all_due()` itself raises an unexpected exception, it propagates out of the loop and terminates the daemon. Per-schedule errors are handled inside `_run()` and never reach the loop.

**One-shot mode:** `run_all_due()` also works without `start()`. The CLI's `anythink scheduler run <name>` bypasses the loop entirely and calls `run_once()` directly.

---

## TUI integration

### `/schedule` slash command

All `/schedule` subcommands are handled in `commands/handlers.py:_schedule()`. The handler directly calls `AppContext.schedule_manager` methods for read and mutating operations. For `/schedule run`, it does **not** call `ScheduleRunner` — instead it returns a `CommandResult` with `action="schedule_run"` and the name in `extra`.

| Subcommand | Handler action | What actually happens |
|---|---|---|
| `/schedule list` | Inline response | `schedule_manager.list_all()` → formatted table |
| `/schedule add <name> <cron> <prompt>` | Inline response | Constructs `ScheduledPrompt`, calls `schedule_manager.add()` |
| `/schedule remove <name>` | Inline response | `schedule_manager.remove(name)` |
| `/schedule enable <name>` | Inline response | `schedule_manager.enable(name)` |
| `/schedule disable <name>` | Inline response | `schedule_manager.disable(name)` |
| `/schedule run <name>` | `action="schedule_run"` | Signals TUI to fire `_run_schedule()` background worker |

### TUI background worker: `_run_schedule(schedule_name)` in `app.py:2327`

When `result.action == "schedule_run"`, `_dispatch_command()` fires this worker. It duplicates the execution logic of `ScheduleRunner.run_once()` directly in the TUI layer rather than using `ScheduleRunner` — this keeps the TUI's result visible as a conversation bubble.

**TUI worker sequence:**
1. Looks up the schedule via `schedule_manager.get(schedule_name)`.
2. Resolves alias → API key → provider (same resolution as `run_once()`).
3. Streams the response via `provider.stream_chat()`.
4. Appends to output file if configured.
5. Calls `schedule_manager.update_last_run()`.
6. Adds a `SystemBubble("✓ Schedule completed:\n<preview>", kind="success")` to the conversation.
7. Sends a desktop notification via `ctx.notifier.notify("schedule_done", ...)`.
8. On any exception: adds an error bubble.

---

## CLI integration

The CLI (in `cli.py`) exposes a `scheduler` sub-app with two commands:

### `anythink scheduler start [--poll <seconds>]`

```python
runner = ScheduleRunner(AppContext.create(paths=config_manager.paths))
asyncio.run(runner.start(poll_interval=poll))
```

Starts a full `AppContext`, wraps it in a `ScheduleRunner`, and calls `start()` via `asyncio.run()`. Blocks until Ctrl+C. Intended to be run as a background process or system service.

### `anythink scheduler run <name>`

```python
runner = ScheduleRunner(app_ctx)
text = asyncio.run(runner.run_once(schedule))
```

Fetches the named schedule from `schedule_manager`, constructs a `ScheduleRunner`, and executes it immediately via `asyncio.run()`. Prints the first 300 characters of the result or an error. Exits with code 1 on failure.

---

## Full lifecycle example

```
1. User creates a schedule in TUI:
   /schedule add morning-digest "0 9 * * *" "Write a 3-sentence morning briefing."
       ↓
   ScheduleManager.add(ScheduledPrompt(
       name="morning-digest",
       cron_expr="0 9 * * *",
       prompt="Write a 3-sentence morning briefing.",
       enabled=True,
       last_run=None,
   ))
   Writes to $XDG_CONFIG_HOME/anythink/schedules.yaml

2. User starts the daemon in a separate terminal:
   anythink scheduler start --poll 60
       ↓
   ScheduleRunner(ctx).start(poll_interval=60)
   Prints: "Anythink Scheduler — 1 enabled schedule(s) loaded. Checking every 60s."
       ↓
   Every 60 seconds:
     run_all_due(now=datetime.now(UTC))
       ↓
     For each schedule: _is_due(s, now)
       - First check after startup: last_run=None → True
       - After 09:00: cron.get_prev() = today 09:00, last_run=None → True
       - After first run: last_run=today 09:00, cron.get_prev()=today 09:00 → False
       ↓
     run_once(morning-digest):
       alias_name = ctx.config.default_model_alias  (e.g. "claude-3")
       alias = ctx.model_registry.get("claude-3")
       api_key = ctx.key_manager.get_key("anthropic")
       provider = AnthropicProvider(api_key=api_key)
       messages = [ChatMessage(role="user", content="Write a 3-sentence morning briefing.")]
       full_text = ""
       async for chunk in provider.stream_chat(messages, alias.model_id, ...):
           full_text += chunk.text
       ctx.notifier.notify("schedule_done", "Anythink — morning-digest", full_text[:120])
       ctx.schedule_manager.update_last_run("morning-digest", now)
         → schedules.yaml updated with last_run = "2026-06-24T09:00:05+00:00"
   Prints: "[09:00:05] ✓ morning-digest: Good morning! Today is Tuesday..."

3. User triggers manual run from TUI:
   /schedule run morning-digest
       ↓
   CommandResult(action="schedule_run", extra={"schedule_name": "morning-digest"})
       ↓
   TUI _dispatch_command() → self.run_worker(_run_schedule("morning-digest"))
       ↓
   _run_schedule(): same execution path, result shown as SystemBubble in chat
```

---

## Storage location

| Artifact | Path |
|---|---|
| Schedule definitions (all schedules) | `$XDG_CONFIG_HOME/anythink/schedules.yaml` |

YAML format (list of dicts, sorted by `created_at`):

```yaml
- cron_expr: 0 9 * * *
  created_at: '2026-06-24T08:00:00'
  enabled: true
  last_run: '2026-06-24T09:00:05+00:00'
  name: morning-digest
  prompt: Write a 3-sentence morning briefing.
- alias: gpt4-turbo
  cron_expr: 0 18 * * 5
  created_at: '2026-06-24T08:05:00'
  enabled: false
  name: weekly-report
  output_file: /home/user/reports/weekly.md
  prompt: Summarise this week's key events.
```

---

## Key design decisions

- **`ScheduleManager` is write-through, not write-back** — Every mutation (`add`, `remove`, `enable`, `disable`, `update_last_run`) calls `save()` immediately. There is no buffering and no risk of losing a `last_run` update if the process crashes between a run and a save.
- **Lazy load with in-memory cache** — `_load()` reads the YAML file at most once per process lifetime. Subsequent calls return the cached dict. Since all mutations go through the same in-memory dict and save to disk, the cache is always coherent with the file.
- **`_is_due()` is stateless and pure (except for `croniter` import)** — It takes `(schedule, now)` and returns a bool. No side effects. This makes it independently testable by passing a fixed `now`.
- **`croniter` is an optional dependency** — `_is_due()` defers its import to call time. The `schedule` module can be imported and `ScheduleManager` can be used even without `croniter` installed. Only `_is_due()` and `start()` require it. `anythink doctor` checks for `croniter` availability.
- **Concurrent schedule execution with `asyncio.gather()`** — When multiple schedules are due in the same poll window, they fire in parallel. Per-schedule exceptions are isolated and logged; one failing schedule does not prevent others from running.
- **`run_once()` does not bypass `update_last_run()`** — Even if called manually via `/schedule run` or `anythink scheduler run`, `update_last_run()` is always called at the end. This means a manual run "resets the clock" for that schedule, preventing a duplicate automated run in the same cron window.
- **Output file is append-only** — Each run adds a new timestamped block. Old output is never deleted or overwritten, making it safe to point multiple schedules at the same file.
- **No RAG/plugins/spend tracking in scheduled runs** — `run_once()` calls `provider.stream_chat()` directly with a single-message history. It intentionally bypasses the full `_stream_response()` pipeline to keep execution simple and self-contained. This is a known limitation: scheduled prompts cannot use RAG context, plugin hooks, or debug instrumentation.
- **`_dirty` flag prevents unnecessary disk writes** — `save()` is a no-op if no changes have been made since the last save. `list_all()`, `get()`, and `exists()` never set `_dirty`, so read-only access never triggers file writes.
- **Missed-run policy: fire-once on catch-up** — `_is_due()` checks only the most recent expected cron window, not all missed windows since `last_run`. If the daemon was offline for a week, a daily schedule fires exactly once on restart rather than seven times.
