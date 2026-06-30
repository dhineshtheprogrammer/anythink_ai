# Batch Processing Module — `anythink.batch`

The `batch` package implements Anythink's **headless, parallel batch processing** pipeline. It lets you send a list of prompts to an LLM provider concurrently, collect the results in their original order, and persist them as Markdown or JSON — all without starting the TUI.

---

## Directory Layout

```
src/anythink/batch/
├── __init__.py      # Package marker (no public re-exports)
├── runner.py        # Core async runner + BatchResult dataclass
└── writers.py       # Markdown and JSON output writers
```

---

## `runner.py`

### Constants

| Name | Value | Purpose |
|---|---|---|
| `_MAX_PARALLEL` | `20` | Hard cap on concurrent provider calls to avoid rate-limit hammering |

---

### `BatchResult`

```python
@dataclass
class BatchResult:
    index: int
    prompt: str
    response: str
    usage: TokenUsage | None
    error: str | None
    elapsed_s: float
```

Returned for every prompt regardless of success or failure. Fields:

| Field | Type | Description |
|---|---|---|
| `index` | `int` | Zero-based position of this prompt in the original input list |
| `prompt` | `str` | The exact prompt string that was sent |
| `response` | `str` | Full concatenated text from the provider stream; empty string on error |
| `usage` | `TokenUsage \| None` | Token counts from the final stream chunk; `None` on error or when the provider does not report usage |
| `error` | `str \| None` | Human-readable error message; `None` on success |
| `elapsed_s` | `float` | Wall-clock seconds from request start to stream completion; `0.0` on error |

`TokenUsage` is imported from `anythink.providers.base` and carries `prompt_tokens`, `completion_tokens`, and `total_tokens`.

---

### `_run_single_prompt(ctx, index, prompt, alias_name, system_prompt) → BatchResult`

**Private** coroutine. Executes one prompt against a provider and returns a `BatchResult`. Never raises — all exceptions are caught and returned as `BatchResult(error=str(e))`.

**Resolution order:**

1. Resolve the model alias:
   - Uses `alias_name` if provided, otherwise falls back to `ctx.config.default_model_alias`.
   - Returns an error `BatchResult` immediately if no alias is resolvable.
2. Build the message list:
   - Prepends `ChatMessage(role="system", ...)` if `system_prompt` is given.
   - Appends `ChatMessage(role="user", content=prompt)`.
3. Look up the provider class from `ctx.provider_registry`. Returns an error `BatchResult` if the provider is not registered.
4. Fetch the API key from `ctx.key_manager`.
5. Instantiate the provider and stream the response via `provider.stream_chat(messages, alias.model_id, gen_params=alias.gen_params)`.
6. Accumulate chunk text into `full_text`; track the last non-`None` `chunk.usage` as `final_usage`.
7. Return a success `BatchResult` with the accumulated text, usage, and elapsed time.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `ctx` | `AppContext` | The application DI container |
| `index` | `int` | The prompt's original list position |
| `prompt` | `str` | The user prompt string |
| `alias_name` | `str \| None` | Override model alias; `None` uses the configured default |
| `system_prompt` | `str \| None` | Optional system message prepended to every request |

---

### `run_batch(ctx, prompts, *, parallel, alias, system_prompt) → list[BatchResult]`

**Public** async entry point. Runs all prompts concurrently and returns results sorted by original index.

```python
async def run_batch(
    ctx: AppContext,
    prompts: list[str],
    *,
    parallel: int = 1,
    alias: str | None = None,
    system_prompt: str | None = None,
) -> list[BatchResult]:
```

**Concurrency model:**

- Creates an `asyncio.Semaphore(capped)` where `capped = max(1, min(parallel, _MAX_PARALLEL))`.
- Wraps each `_run_single_prompt` call in a `_guarded` coroutine that acquires the semaphore before proceeding.
- Fires all tasks simultaneously with `asyncio.gather(*tasks)` — the semaphore ensures at most `capped` tasks are in-flight at any moment.
- Results from `asyncio.gather` arrive in completion order; the final `sorted(..., key=lambda r: r.index)` restores original order before returning.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `ctx` | `AppContext` | — | Application DI container |
| `prompts` | `list[str]` | — | Ordered list of prompt strings |
| `parallel` | `int` | `1` | Desired concurrency; silently clamped to `[1, 20]` |
| `alias` | `str \| None` | `None` | Model alias override for all prompts |
| `system_prompt` | `str \| None` | `None` | System message prepended to every request |

**Return value:** `list[BatchResult]` sorted ascending by `index`, always the same length as `prompts`. Never raises.

---

## `writers.py`

Stateless output serialisers. Both functions create missing parent directories via `Path.mkdir(parents=True, exist_ok=True)` and write UTF-8 encoded text.

---

### `write_markdown(results, output) → None`

Writes a human-readable Markdown file.

**Structure produced:**

```markdown
# Batch Run Results

## Prompt 1

**Input:** <prompt text>

**Response:**

<response text>

_Tokens: 120 prompt + 340 completion — 2.3s_

---

## Prompt 2

**Input:** <prompt text>

**Error:** <error message>

---
```

- Each prompt gets an `## Prompt N` section (1-based numbering).
- Success: prints response text followed by a token/timing italic footer when `usage` is not `None`.
- Failure: prints an `**Error:**` line with the error message; no response block.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `results` | `list[BatchResult]` | Ordered list of results from `run_batch` |
| `output` | `Path` | Destination `.md` file path |

---

### `write_json(results, output) → None`

Writes a machine-readable JSON array.

**Schema per element:**

```json
{
  "index": 0,
  "prompt": "What is the capital of France?",
  "response": "Paris.",
  "error": null,
  "elapsed_s": 1.42,
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 5,
    "total_tokens": 20
  }
}
```

- `usage` is `null` (not omitted) when the provider did not return token counts or when an error occurred.
- Output is indented with 2 spaces and written with `ensure_ascii=False` to preserve Unicode characters.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `results` | `list[BatchResult]` | Ordered list of results from `run_batch` |
| `output` | `Path` | Destination `.json` file path |

---

## CLI Entry Point — `anythink run`

Registered in `cli.py` as the `run` sub-command. Invokes `run_batch` synchronously via `asyncio.run()` — this command never starts the TUI.

```
anythink run --file prompts.txt --output results.md
anythink run --file prompts.txt --output results.json --format json
anythink run --file prompts.txt --output results.md --parallel 5 --alias gpt4
```

**Options:**

| Flag | Short | Default | Description |
|---|---|---|---|
| `--file` | `-f` | _(required)_ | Input text file; one prompt per non-blank line |
| `--output` | `-o` | _(required)_ | Output file path |
| `--parallel` | `-p` | `1` | Concurrency level (clamped to 20 inside `run_batch`) |
| `--alias` | `-a` | `None` | Model alias; falls back to `config.default_model_alias` |
| `--format` | — | `"markdown"` | `"markdown"` or `"json"` |

**Exit codes:**

| Code | Condition |
|---|---|
| `0` | All prompts succeeded |
| `1` | Configuration not initialised, empty input file, or at least one prompt errored |

The CLI prints a summary line to stdout: `Done. N/M succeeded. Written to: <path>`.

---

## Data Flow

```
Input file (--file)
       │
       ▼
  strip blank lines
       │
       ▼
  run_batch(ctx, prompts, parallel=P)
       │
       ├── asyncio.Semaphore(P)
       │
       ├── _guarded(0, prompt_0) ──► _run_single_prompt ──► provider.stream_chat ──► BatchResult(0)
       ├── _guarded(1, prompt_1) ──► _run_single_prompt ──► provider.stream_chat ──► BatchResult(1)
       │   ...                                                                             │
       └── asyncio.gather(*tasks) ◄──────────────────────────────────────────────────────┘
                   │
                   ▼
           sorted(results, key=index)
                   │
           ┌───────┴───────┐
           ▼               ▼
    write_markdown    write_json
    (results.md)    (results.json)
```

---

## Error Handling

The batch layer has a **fail-soft** design: a single prompt failure never aborts the run.

| Failure scenario | Outcome |
|---|---|
| No model alias configured | `BatchResult(error="No model alias configured…")` |
| Provider not in registry | `BatchResult(error="Provider '…' not registered.")` |
| API / network exception | `BatchResult(error=str(e))` caught by bare `except Exception` |
| Empty input file | CLI exits with code `1` before calling `run_batch` |
| App not configured | CLI exits with code `1` before calling `run_batch` |

Successful prompts continue to completion and are written to the output file even if other prompts in the same run fail.

---

## Dependencies

| Dependency | Source | Role |
|---|---|---|
| `asyncio` | stdlib | Semaphore-based concurrency, `asyncio.gather` |
| `time` | stdlib | `time.monotonic()` for elapsed time measurement |
| `json` | stdlib | JSON serialisation in `write_json` |
| `pathlib.Path` | stdlib | Output file path handling |
| `dataclasses.dataclass` | stdlib | `BatchResult` definition |
| `anythink.providers.base.ChatMessage` | internal | Message construction for provider calls |
| `anythink.providers.base.TokenUsage` | internal | Token usage type carried on `BatchResult.usage` |
| `anythink.app.context.AppContext` | internal (TYPE_CHECKING only) | DI container; never imported at runtime to avoid circular imports |

---

## Integration Points

| System | How batch interacts |
|---|---|
| `AppContext.model_registry` | Resolves alias name → `ModelAlias` (holds `provider`, `model_id`, `gen_params`) |
| `AppContext.provider_registry` | Resolves provider name → provider class |
| `AppContext.key_manager` | Fetches the API key for the resolved provider |
| `AppContext.config.default_model_alias` | Fallback when `--alias` is not supplied |
| `anythink.providers.base.BaseProvider.stream_chat` | Async generator that yields `StreamChunk` objects; batch accumulates `.text` and `.usage` |

---

## Usage Examples

**Basic run (sequential):**
```bash
anythink run --file prompts.txt --output results.md
```

**Parallel run with JSON output:**
```bash
anythink run --file prompts.txt --output results.json --format json --parallel 10
```

**Using a specific model alias:**
```bash
anythink run --file prompts.txt --output results.md --alias claude-3-opus
```

**Calling `run_batch` from Python:**
```python
import asyncio
from anythink.app.context import AppContext
from anythink.batch.runner import run_batch
from anythink.batch.writers import write_markdown
from pathlib import Path

ctx = AppContext.create(paths=...)
prompts = ["Summarise X", "Explain Y", "Compare Z"]
results = asyncio.run(run_batch(ctx, prompts, parallel=3))
write_markdown(results, Path("out.md"))
```
