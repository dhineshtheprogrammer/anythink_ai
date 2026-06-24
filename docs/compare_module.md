# `src/anythink/compare` — Multi-Model Comparison Module

## Purpose

The `compare` package implements Anythink's multi-model comparison mode. It sends the same prompt to multiple model aliases simultaneously, collects all responses in parallel, renders them side-by-side in the TUI, and lets the user pick one winner whose response is committed to the chat history for the conversation to continue from.

The package is intentionally minimal — just two files — because the comparison logic itself is straightforward. The complexity lives in the TUI integration (interception of the next user message, sequential result rendering, and the pick/commit flow).

| File | Responsibility |
|---|---|
| `__init__.py` | Package marker |
| `runner.py` | `CompareResult` dataclass + `_run_single()` + `run_comparison()` |

---

## File: `__init__.py`

```python
"""Multi-model comparison mode for Anythink."""
```

Empty beyond its module docstring. Makes `src/anythink/compare/` a Python package. No symbols are re-exported here.

---

## File: `runner.py`

**Full path:** `src/anythink/compare/runner.py`

Contains everything the comparison engine needs: a result dataclass, a private single-model runner, and the public parallel orchestrator. All imports from `AppContext` are deferred under `TYPE_CHECKING` to avoid circular imports.

---

### `CompareResult`

```python
@dataclass
class CompareResult:
    alias: str
    provider_name: str
    model_id: str
    text: str
    usage: TokenUsage | None
    cost_usd: float
    elapsed_s: float
    error: str | None = None
```

**Location:** `runner.py:17`

Holds the complete result for one model in a comparison run. One instance is produced per alias regardless of whether the run succeeded or failed.

| Field | Type | Description |
|---|---|---|
| `alias` | `str` | The model alias name as provided by the user (e.g. `"claude-3"`) |
| `provider_name` | `str` | Provider identifier (e.g. `"anthropic"`, `"openai"`). `"unknown"` if alias resolution failed. |
| `model_id` | `str` | Raw model ID string (e.g. `"claude-opus-4-8"`). `"unknown"` if alias resolution failed. |
| `text` | `str` | Full accumulated response text. Empty string `""` on any error. |
| `usage` | `TokenUsage \| None` | Token usage reported by the provider on the final stream chunk. `None` if the provider did not report usage or if an error occurred. |
| `cost_usd` | `float` | Estimated USD cost calculated from `usage` via `spend.pricing.estimate_cost()`. `0.0` if usage is `None`. |
| `elapsed_s` | `float` | Wall-clock seconds from the first API call to the last token received, measured with `time.monotonic()`. On timeout, set to the `timeout` parameter value. On non-timeout errors, set to `0.0`. |
| `error` | `str \| None` | Human-readable error message if the run failed; `None` on success. The presence of a non-`None` `error` is the canonical way to check whether a result represents failure — the TUI checks `r.error` to decide whether to render an error bubble or a success bubble. |

**Distinguishing success from failure:**

```python
if r.error:
    # failed — text is "" and usage/cost are 0
else:
    # succeeded — text, usage, cost_usd, elapsed_s are all valid
```

---

### `_run_single(ctx, alias_name, messages, timeout) -> CompareResult`

**Location:** `runner.py:30`  
**Async:** yes  
**Private** — not exported; called only by `run_comparison()`.

Runs a single model alias against the given message list and returns a `CompareResult`. **Never raises.** Every possible failure — alias not found, provider not registered, timeout, any exception — is caught and converted into a `CompareResult` with `error` set and empty `text`.

**Full execution sequence:**

**Step 1 — Alias resolution**
```python
alias = ctx.model_registry.get(alias_name)
```
If `None` (alias does not exist in the model registry), returns immediately with:
```python
CompareResult(alias=alias_name, provider_name="unknown", model_id="unknown",
              text="", usage=None, cost_usd=0.0, elapsed_s=0.0,
              error=f"Alias '{alias_name}' not found")
```

**Step 2 — Provider resolution**
```python
api_key = ctx.key_manager.get_key(alias.provider)
prov_cls = ctx.provider_registry.get(alias.provider)
```
If `prov_cls` is `None` (provider not registered), returns with:
```python
CompareResult(..., error=f"Provider '{alias.provider}' not registered")
```

**Step 3 — Provider instantiation**
```python
provider = prov_cls(api_key=api_key)
```

**Step 4 — Streaming with timeout**

An inner coroutine `_collect()` is defined as a closure that captures `full_text` and `final_usage` via `nonlocal`. It iterates the provider's token stream:

```python
async def _collect() -> None:
    nonlocal full_text, final_usage
    async for chunk in provider.stream_chat(
        messages, alias.model_id, gen_params=alias.gen_params
    ):
        full_text += chunk.text
        if chunk.usage is not None:
            final_usage = chunk.usage
```

Key points:
- `gen_params=alias.gen_params` — the alias's configured generation parameters (temperature, max_tokens, etc.) are forwarded, so each model runs under its own configured settings.
- `chunk.usage` is captured on every chunk but only the last non-`None` value matters — providers typically emit usage data on the final chunk only.
- `full_text` is built by simple string concatenation, not a list join. This is acceptable because compare runs are bounded by `timeout` and do not need to stream tokens incrementally to the UI.

`_collect()` is wrapped with:
```python
await asyncio.wait_for(_collect(), timeout=timeout)
```

**Step 5 — Cost estimation**
```python
cost = estimate_cost(alias.provider, alias.model_id, final_usage) if final_usage else 0.0
```
Deferred import of `estimate_cost` from `anythink.spend.pricing` happens inside `_run_single` at call time.

**Step 6 — Return success result**
```python
return CompareResult(
    alias=alias_name, provider_name=alias.provider, model_id=alias.model_id,
    text=full_text, usage=final_usage, cost_usd=cost, elapsed_s=elapsed,
)
```

**Error cases handled inside the `try/except`:**

| Exception | `error` value | `elapsed_s` |
|---|---|---|
| `TimeoutError` (from `asyncio.wait_for`) | `f"Timed out after {timeout:.0f}s"` | `timeout` (the limit) |
| Any other `Exception` | `str(e)` | `0.0` |

In both cases `text=""`, `usage=None`, `cost_usd=0.0`.

---

### `run_comparison(ctx, aliases, messages, *, timeout=60.0, max_concurrent=3) -> list[CompareResult]`

**Location:** `runner.py:120`  
**Async:** yes  
**Public** — this is the only exported callable from the package.

Orchestrates running the same message list against multiple aliases in parallel with a concurrency cap.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `ctx` | `AppContext` | required | The live application context. Provides model registry, key manager, provider registry. |
| `aliases` | `list[str]` | required | Ordered list of alias names to compare. Must have at least 2 (enforced by the command handler, not here). |
| `messages` | `list[ChatMessage]` | required | The full message list as assembled by the TUI: trimmed history + the new user message. All models receive the identical list. |
| `timeout` | `float` | `60.0` | Per-model timeout in seconds passed to `asyncio.wait_for()`. A model that does not complete within this window gets a `TimeoutError` result. |
| `max_concurrent` | `int` | `3` | Maximum number of models running at the same time. Prevents flooding multiple providers simultaneously. |

**Algorithm:**

1. Create a semaphore:
   ```python
   semaphore = asyncio.Semaphore(min(max_concurrent, len(aliases)))
   ```
   `min()` ensures the semaphore count never exceeds the actual number of aliases — if there are only 2 aliases but `max_concurrent=3`, the effective concurrency is 2.

2. Define a `_guarded(alias)` coroutine that acquires the semaphore before calling `_run_single()`:
   ```python
   async def _guarded(alias: str) -> CompareResult:
       async with semaphore:
           return await _run_single(ctx, alias, messages, timeout)
   ```

3. Build and fire all tasks concurrently:
   ```python
   tasks = [_guarded(alias) for alias in aliases]
   return list(await asyncio.gather(*tasks))
   ```

**Return value:** A `list[CompareResult]` in the **same order as `aliases`**. `asyncio.gather()` preserves input order. The TUI relies on this to assign sequential display numbers `[1]`, `[2]`, `[3]` that match the user's mental model of "the order I typed them in".

**Error isolation:** Because `_run_single()` never raises, `asyncio.gather()` will never have a partial failure. Every alias always produces exactly one `CompareResult`. A network error on alias `"gpt4"` does not affect the result of `"claude-3"`.

**Semaphore behaviour:** With `max_concurrent=3` and 5 aliases, the first 3 start immediately. As each finishes (or errors), the semaphore slot is released and the next waiting task starts. The total elapsed wall time is driven by the slowest batch, not the sum of all.

---

## TUI integration

The compare flow spans three distinct phases in the TUI (`ui/textual/app.py`). The `compare` package is only involved in Phase 2.

---

### Phase 1 — Setup: `/compare` slash command

**Handler:** `commands/handlers.py:_compare()`  
**Trigger:** User types `/compare <alias1> <alias2> [alias3 ...]`

```python
# Validate aliases exist
missing = [a for a in parts if not ctx.model_registry.exists(a)]
if missing:
    return CommandResult(error=True, message=f"Unknown alias(es): ...")

if len(parts) < 2:
    return CommandResult(error=True, message="Comparison requires at least 2 model aliases.")

return CommandResult(
    action="compare_request",
    extra={"aliases": parts},
    message="Comparison mode set for: alias1, alias2\nSend your next message to compare.",
)
```

**TUI dispatch** (`_dispatch_command()`):
```python
if result.action == "compare_request":
    aliases = result.extra.get("aliases", [])
    if aliases:
        self._pending_compare_aliases = list(aliases)
    conv.add_bubble(SystemBubble(result.message, t, kind="info"))
```

At this point the TUI is in a "primed" state: `_pending_compare_aliases` is set and the next user message will be intercepted.

**Also triggered by `/debug compare <alias...>`** — same `action="compare_request"` with an additional `extra={"aliases": rest, "debug_compare": True}` flag. The `debug_compare` flag causes the TUI to render a technical comparison table via `debug.formatters.format_compare_table()` in addition to the normal response bubbles.

---

### Phase 2 — Execution: message interception and `_run_comparison()`

**Trigger:** User submits any message while `_pending_compare_aliases is not None`

The interception check in `on_input_area_submitted()` fires **before** the normal chat flow:

```python
if self._pending_compare_aliases is not None:
    aliases = self._pending_compare_aliases
    self._pending_compare_aliases = None          # clear immediately
    conv.add_bubble(UserBubble(text, t, ...))
    conv.add_bubble(SystemBubble(f"Comparing {len(aliases)} models…", t, kind="info"))
    self.run_worker(
        self._run_comparison(state, text, aliases),
        exclusive=False,
        exit_on_error=False,
    )
    return                                         # normal chat path is bypassed
```

**Background worker: `_run_comparison(state, prompt, aliases)`**

```python
async def _run_comparison(self, state, prompt, aliases):
    from anythink.compare.runner import run_comparison
    from anythink.providers.base import ChatMessage as _CM

    # Build full message list: trimmed history + new user message
    messages = _trim_history(state.history, state.context_window)
    messages = messages + [_CM(role="user", content=prompt)]

    # Run all aliases in parallel — this is the only call into compare.runner
    results = await run_comparison(self._ctx, aliases, messages)

    # Render results sequentially (in alias order)
    for i, r in enumerate(results, 1):
        header = f"[{i}] {r.alias}  ({r.provider_name} / {r.model_id})"
        if r.error:
            conv.add_bubble(SystemBubble(f"{header}\nError: {r.error}", t, kind="error"))
        else:
            meta = f"{r.elapsed_s:.1f}s  •  {r.usage.prompt_tokens}+{r.usage.completion_tokens} tok  •  ~${r.cost_usd:.4f}"
            conv.add_bubble(SystemBubble(f"══ {header}  [{meta}] ══\n{r.text}", t, kind="info"))

            # Record spend for each successful result
            if r.usage is not None and self._ctx.config.spend_tracking:
                self._ctx.spend_tracker.record(
                    session_id=state.session_id,
                    model_id=r.model_id,
                    provider=r.provider_name,
                    usage=r.usage,
                    cost_usd=r.cost_usd,
                )

    # Enter pick mode
    self._pending_compare_results = results
    self._pending_compare_pick = True
    alias_picks = "  ".join(f"[{i}] {r.alias}" for i, r in enumerate(results, 1))
    conv.add_bubble(SystemBubble(
        f"Continue with which response?\n{alias_picks}  [N] Cancel", t, kind="warning"
    ))
```

**Key points:**
- `_trim_history()` is called first — history is trimmed to fit within `state.context_window` before the new message is appended. All models receive the **same trimmed history + new prompt**, so the comparison is fair.
- Results are displayed in **alias order** (the order the user typed them), not arrival order. `asyncio.gather()` guarantees this.
- Spend is recorded for every **successful** result immediately, before the user picks. This is intentional — even unselected responses consumed tokens and incurred real cost.
- The bubble format for a successful result:
  ```
  ══ [1] claude-3  (anthropic / claude-opus-4-8)  [2.3s  •  1024+512 tok  •  ~$0.0123] ══
  <full response text>
  ```
- After all result bubbles are added, the worker sets `_pending_compare_pick = True` and renders the pick prompt, entering Phase 3.

---

### Phase 3 — Pick: `_handle_compare_pick()`

**Trigger:** User submits any message while `_pending_compare_pick` is `True`

The pick check in `on_input_area_submitted()` fires **after** all other pending state checks but **before** normal chat:

```python
if self._pending_compare_pick:
    await self._handle_compare_pick(text)
    return
```

**`_handle_compare_pick(text)`:**

1. Clears `_pending_compare_pick = False` and pops `_pending_compare_results`.

2. **Cancel inputs** (`"n"`, `"no"`, `"cancel"`, `""`):
   ```
   "Comparison closed. No response added to history."
   ```
   The prompt and all responses are discarded. Chat history is unchanged.

3. **Invalid input** (non-integer, or out of range):
   - Shows an error bubble.
   - **Restores** `_pending_compare_results` and `_pending_compare_pick = True`.
   - The user is prompted again — the pick state persists until a valid answer or cancel.

4. **Valid pick** (integer `1` through `len(results)`):
   - Resolves `winner = results[idx]`.
   - If `winner.error` is set, shows an error: cannot continue with a failed response.
   - Otherwise, commits to history:
     ```python
     state.history.append(ChatMessage(role="user", content=winner.text or ""))
     state.history.append(ChatMessage(role="assistant", content=winner.text or ""))
     self._last_response_text = winner.text or ""
     ```
   - Triggers autosave if `config.session_autosave` is `True`.
   - Shows: `"✓ Continuing with [alias] response."`
   - The conversation continues normally from this point — the winner's response is now in history as if the user had received it in a normal chat turn.

**Note on history commit:** Two messages are appended — the user's original prompt (`role="user"`) and the winner's response (`role="assistant"`). This mirrors the structure of a normal chat exchange so subsequent turns see a coherent history.

---

## State machine summary

The compare flow uses three TUI-level boolean/list flags as a simple state machine:

```
IDLE
  │
  │  /compare alias1 alias2
  ▼
PRIMED  (_pending_compare_aliases = ["alias1", "alias2"])
  │
  │  user sends any message
  ▼
RUNNING  (_pending_compare_aliases = None, worker fires)
  │
  │  run_comparison() completes
  ▼
PICKING  (_pending_compare_pick = True, _pending_compare_results = [r1, r2])
  │
  ├── user types "1" → winner committed → IDLE
  ├── user types "N"  → discarded       → IDLE
  └── user types "?"  → invalid         → PICKING (stays in pick mode)
```

The `_pending_compare_aliases` flag is cleared **before** the worker fires (not after it completes), so if the worker errors partway through, the TUI does not get stuck in PRIMED mode.

---

## `/compare` vs `/debug compare` — differences

Both commands use `action="compare_request"` and route through the same `_run_comparison()` worker and `run_comparison()` function. The only difference is the `debug_compare` flag in `extra`:

| | `/compare alias1 alias2` | `/debug compare alias1 alias2` |
|---|---|---|
| `extra["debug_compare"]` | absent / `False` | `True` |
| Response bubbles | Standard `══ [N] alias ══` format | Same + `format_compare_table()` output |
| Purpose | Choose the best response | Technical debugging: TTFT, TPS, stop reason |

---

## Full end-to-end example

```
User: /compare claude-3 gpt4
      ↓
_compare() handler validates both aliases exist
CommandResult(action="compare_request", extra={"aliases": ["claude-3", "gpt4"]})
      ↓
_dispatch_command():
  _pending_compare_aliases = ["claude-3", "gpt4"]
  SystemBubble("Comparison mode set for: claude-3, gpt4 — Send your next message to compare.")

User: "Explain async/await in Python in one sentence."
      ↓
on_input_area_submitted():
  _pending_compare_aliases is not None → intercept
  aliases = ["claude-3", "gpt4"]
  _pending_compare_aliases = None
  UserBubble("Explain async/await in Python in one sentence.")
  SystemBubble("Comparing 2 models for this prompt…")
  run_worker(_run_comparison(state, prompt, aliases))
      ↓
_run_comparison():
  messages = [*trimmed_history, ChatMessage(role="user", content="Explain async/await...")]
  results = await run_comparison(ctx, ["claude-3", "gpt4"], messages)
      ↓
run_comparison():
  semaphore = Semaphore(2)   # min(3, 2)
  asyncio.gather(
    _guarded("claude-3"),    ─┐ both start simultaneously
    _guarded("gpt4"),         ┘ (semaphore allows 2 concurrent)
  )
    → _run_single(ctx, "claude-3", messages, 60.0)
        provider = AnthropicProvider(api_key=...)
        async for chunk in provider.stream_chat(...): full_text += chunk.text
        cost = estimate_cost("anthropic", "claude-opus-4-8", usage)
        → CompareResult(alias="claude-3", text="async/await lets...", elapsed_s=1.4, cost_usd=0.0003)
    → _run_single(ctx, "gpt4", messages, 60.0)
        provider = OpenAIProvider(api_key=...)
        → CompareResult(alias="gpt4", text="async/await enables...", elapsed_s=2.1, cost_usd=0.0008)
      ↓
results = [CompareResult("claude-3",...), CompareResult("gpt4",...)]
      ↓
_run_comparison() renders:
  SystemBubble("══ [1] claude-3  (anthropic / claude-opus-4-8)  [1.4s  •  ...] ══\nasync/await lets...")
  SystemBubble("══ [2] gpt4  (openai / gpt-4-turbo)  [2.1s  •  ...] ══\nasync/await enables...")
  spend_tracker.record(claude-3 usage)
  spend_tracker.record(gpt4 usage)
  _pending_compare_results = results
  _pending_compare_pick = True
  SystemBubble("Continue with which response?\n[1] claude-3  [2] gpt4  [N] Cancel")

User: "1"
      ↓
on_input_area_submitted() → _pending_compare_pick → _handle_compare_pick("1")
  idx = 0
  winner = results[0]  # claude-3
  state.history.append(ChatMessage(role="user", content="async/await lets..."))
  state.history.append(ChatMessage(role="assistant", content="async/await lets..."))
  session_manager.save(...)
  SystemBubble("✓ Continuing with [claude-3] response.")
  _pending_compare_pick = False
  _pending_compare_results = None
      ↓
IDLE — normal chat resumes with claude-3's response in history
```

---

## Key design decisions

- **`_run_single()` never raises** — Every failure path returns a `CompareResult` with `error` set. This is critical because `asyncio.gather()` would propagate an exception from any task and abort the others. By making each task infallible, all models always get a result regardless of what any other model does.

- **Alias order is preserved in the return value** — `asyncio.gather()` guarantees order matching the input list. The TUI assigns display numbers based on position (`[1]`, `[2]`, etc.), so users can reliably type `"1"` to pick the first alias they named. Fastest-arriving order would be confusing.

- **Semaphore caps concurrency at `min(max_concurrent, len(aliases))`** — The `min()` prevents creating a semaphore with a higher count than the number of tasks. A `Semaphore(5)` with 2 tasks would be harmless but misleading; `min()` makes the intent explicit.

- **History is trimmed before distribution** — `_trim_history()` is called once in the worker before `run_comparison()`, so all models receive the same trimmed context. This is fairer than trimming per-model (which could vary if trimming logic depended on model context size), and avoids redundant computation.

- **Spend is recorded for all successful results, not just the winner** — Every successful provider call consumed real tokens and incurred real cost. Recording only the winner's cost would undercount the true spend of a comparison session.

- **The pick prompt re-asserts state on invalid input** — When a user types an out-of-range number, both `_pending_compare_results` and `_pending_compare_pick` are restored before returning. This keeps the state machine in the PICKING state, so the next input is handled by `_handle_compare_pick()` again rather than falling through to normal chat.

- **The user message is not appended to `state.history` during the compare run** — Unlike normal chat where `state.history.append(user_msg)` happens immediately in `on_input_area_submitted()`, the compare flow adds the user bubble visually but does not touch `state.history` until the user picks a winner. This keeps history coherent: only one user+assistant pair is ever committed, not multiple partial attempts.

- **`AppContext` is passed through to `_run_single()`** — The runner does not cache or re-use providers between calls. Each alias gets a freshly instantiated provider, which keeps the pattern consistent with the rest of the codebase (providers are always instantiated with an API key at the call site).

- **`compare` package has no TUI imports** — `runner.py` imports only `ChatMessage`, `TokenUsage`, and `estimate_cost`. All rendering, state management, and history commits happen in `app.py`. This keeps the package independently testable.
