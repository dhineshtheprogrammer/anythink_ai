# `anythink/optimize` — Multi-Model Optimization System (MMOS) Module

**Introduced in:** Anythink V4  
**Purpose:** Pools all available models (free-API and local) into a unified compute fabric. Intelligently routes, mixes, and orchestrates work across them to produce better answers than any single model could deliver alone.

When `AppConfig.mmos_enabled = False` (the default), this entire module is bypassed and Anythink behaves exactly as it did in V3. Enabling MMOS inserts a full pipeline between the user's query and the model call.

---

## Module Map

```
optimize/
├── __init__.py             Package marker
├── models.py               All shared V4 dataclasses (source of truth for types)
├── registry.py             Model Capability Registry (bundled + user overlay)
├── settings_manager.py     Persists /optimize panel settings to YAML
├── rate_limit.py           Per-model RPM/TPM/RPD counter and gate
├── classifier.py           Zero-latency keyword-based intent classifier
├── rules.py                User-defined YAML routing rules loader
├── router.py               Routing engine — picks model(s) and strategy
├── context_engine.py       History selection — semantic or recency modes
├── plan.py                 Plan Mode dataclasses + text serialisation
├── plan_engine.py          Generates ExecutionPlan from a fast model
├── plan_runner.py          Executes a plan phase-by-phase, rate-limit-aware
├── mixing.py               Orchestrates the four mixing strategies
├── commands.py             /optimize + /mode slash command handlers
└── attribution.py          Pure Rich Text response attribution headers
```

---

## How the Pieces Connect (Query Pipeline)

When a user sends a message and MMOS is enabled, the TUI worker `_run_mmos_query` in `app.py` runs this pipeline:

```
User query
    │
    ▼
classifier.py          → extract_override_flags()       strip --model / --speed etc.
    │                  → classify()                      detect intent category
    │
    ▼
context_engine.py      → select_relevant_history()      trim history to token budget
    │
    ▼
router.py              → decide()                        pick strategy + model(s)
    │
    ├─ plan_mode=True ──→ plan_engine.py  generate_plan()
    │                     plan_runner.py  execute() phase-by-phase
    │
    └─ plan_mode=False ─→ mixing.py      execute()
           ├─ "routing"   → single model call
           ├─ "ensemble"  → parallel calls, attributed concat
           ├─ "chaining"  → draft → critique → refine
           └─ "decompose" → delegates back to plan_engine + plan_runner
    │
    ▼
TurnMMOSMetadata        stored in ChatMessage.metadata["mmos"]
    │
    ▼
attribution.py          render header line above bubble
```

**AppContext fields wired at startup:**
- `mmos_registry` → `ModelCapabilityRegistry`
- `mmos_settings` → `OptimizeSettingsManager`
- `rate_limit_manager` → `RateLimitManager`
- `routing_engine` → `RoutingEngine`
- `context_engine` → `ContextRelevanceEngine`
- `plan_engine` → `PlanEngine`
- `plan_runner` → `PlanRunner`
- `mixing_orchestrator` → `MixingOrchestrator`

---

## File-by-File Reference

---

### `__init__.py`

Empty package marker. Exists so `anythink.optimize` is a proper Python package.

---

### `models.py`

**The single source of truth for all V4 dataclasses.** Every other file in this module imports from here. All dataclasses implement `to_dict()` / `from_dict()` for JSON/YAML round-tripping.

#### `ModelCapability`

Stores constraint and capability metadata for one model entry in the registry.

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Registry key, format `"provider/model_id"` e.g. `"groq/llama3-70b-8192"` |
| `provider` | `str` | Provider name: `"groq"`, `"ollama"`, `"gemini"`, etc. |
| `display_name` | `str` | Human-readable label shown in the TUI |
| `tier` | `str` | `"local"` (Ollama) or `"free-api"` (cloud free tier) |
| `context_window` | `int` | Max total tokens (prompt + completion) |
| `max_output_tokens` | `int` | Max tokens in one completion |
| `rpm_limit` | `int \| None` | Requests per minute cap; `None` = unlimited (local) |
| `tpm_limit` | `int \| None` | Tokens per minute cap |
| `rpd_limit` | `int \| None` | Requests per day cap |
| `strength_categories` | `list[str]` | e.g. `["coding", "reasoning", "math"]` |
| `speed_class` | `str` | `"fast"`, `"medium"`, or `"slow"` |
| `quality_class` | `str` | `"high"`, `"medium"`, or `"low"` |
| `supports_system_prompt` | `bool` | Whether the model accepts a system role |
| `supports_streaming` | `bool` | Whether streaming responses are available |
| `requires_network` | `bool` | `False` for local models |
| `notes` | `str` | Free-text notes (user-editable) |

---

#### `OptimizeSettings`

The complete state of the `/optimize` panel. Persisted to `optimize_settings.yaml` by `OptimizeSettingsManager`.

| Field | Default | Description |
|---|---|---|
| `enabled` | `True` | Master switch for the whole MMOS engine |
| `mode` | `"auto"` | `"online"`, `"offline"`, or `"auto"` |
| `microprompt_enabled` | `True` | Show the per-query intent selector |
| `orchestration_mode` | `"auto"` | `"deterministic"`, `"meta_llm"`, or `"auto"` |
| `routing_strategy` | `"combined"` | `"category"`, `"token_length"`, or `"combined"` |
| `priority` | `"quality"` | `"quality"`, `"reliability"`, or `"hybrid"` |
| `override_allowed` | `True` | Whether user can use `--model` / `--strategy` flags |
| `history_mode` | `"semantic"` | `"semantic"`, `"recency"`, or `"model_decides"` |
| `history_max_tokens` | `2048` | Maximum token budget for included history |
| `summarisation_model` | `""` | Model to use for history summarisation (empty = auto) |
| `mixing_mode` | `"routing"` | `"routing"`, `"ensemble"`, `"chaining"`, or `"decompose"` |
| `ensemble_count` | `2` | Number of models used in ensemble mode |
| `plan_mode_enabled` | `True` | Whether Plan Mode can trigger |
| `plan_approval_required` | `True` | User must approve plan before execution |
| `queue_mode` | `"auto"` | `"auto"` paces; `"manual"` waits for user |
| `fallback_order` | `[]` | Ordered list of model IDs to try on rate-limit |

---

#### `RoutingDecision`

The output produced by `RoutingEngine.decide()` for a single query. Consumed by `MixingOrchestrator`.

| Field | Description |
|---|---|
| `strategy` | Which mixing strategy to use: `"routing"`, `"ensemble"`, `"chaining"`, `"decompose"` |
| `primary_model` | The single best model ID (used by routing and chaining draft step) |
| `phase_models` | List of model IDs for ensemble or chaining steps |
| `recombination_model` | Model used to synthesise decompose outputs; `None` for other strategies |
| `plan_mode` | Whether Plan Mode was triggered |
| `confidence` | Float 0–1; below 0.5 triggers meta-LLM fallback (stubbed in V4.0) |
| `reason` | Human-readable explanation of how the decision was made |

---

#### `QueryIntent`

Classification of the current user query. Set either by the micro-prompt (user-selected) or `IntentClassifier` (system-inferred).

| Field | Values |
|---|---|
| `category` | `"Coding"`, `"Reasoning"`, `"Creative"`, `"Factual"`, `"Research"`, `"Math"`, `"Other"` |
| `format_preference` | `"detailed"`, `"concise"`, `"step_by_step"`, `"bullet"`, `"code_only"` |
| `priority_override` | `"quality"`, `"speed"`, or `None` (use session default) |
| `from_user` | `True` if user selected via micro-prompt; `False` if system-inferred |

---

#### `TurnMMOSMetadata`

Attached to every AI response turn as `ChatMessage.metadata["mmos"]`. Stores the full provenance of how that response was produced. Serialised via `to_dict()` so it survives session save/load.

| Field | Description |
|---|---|
| `strategy` | Which strategy was used for this turn |
| `model_ids` | List of model IDs that contributed to the response |
| `intent` | The `QueryIntent` (user or system) for this query |
| `routing_decision` | The `RoutingDecision` that drove model selection |
| `total_tokens` | Estimated total tokens consumed |
| `elapsed_s` | Wall time from query dispatch to response ready |
| `plan_session_id` | UUID of the `ExecutionPlan` if Plan Mode was used; `None` otherwise |
| `phase_outputs` | List of per-phase dicts `{phase_num, title, model, output, elapsed_s}` |

**How to read it from a message:**
```python
mmos_raw = msg.metadata.get("mmos")
if mmos_raw:
    meta = TurnMMOSMetadata.from_dict(mmos_raw)
```

---

### `registry.py`

**`ModelCapabilityRegistry`** — A merged, two-layer view of all known models.

**Two layers:**
1. **Bundled base** — `src/anythink/data/model_registry.json`, shipped with the package. Read-only; never written. Loaded via `importlib.resources` when no explicit path is given.
2. **User overlay** — `$XDG_CONFIG_HOME/anythink/model_registry_user.json`. User additions and overrides. When a model ID appears in both layers, the user overlay wins on every field.

**Key methods:**

| Method | What it does |
|---|---|
| `get(model_id)` | Return `ModelCapability` or `None` |
| `all()` | All models (bundled + user, merged) |
| `available_online()` | Only `tier == "free-api"` models |
| `available_offline()` | Only `tier == "local"` models |
| `by_strength(category)` | Models that list *category* in `strength_categories` |
| `add_user_entry(cap)` | Add/replace in user overlay; persists immediately |
| `remove_user_entry(model_id)` | Remove from user overlay; bundled entry re-appears |
| `reset_to_bundled(model_id)` | Alias for `remove_user_entry` |
| `export_json(path)` | Export merged registry to a JSON file |
| `import_json(path)` | Import entries from a JSON file into user overlay; returns count |

**Lazy-load pattern:** The merged dict is built once on first access and cached in `_data`. Any mutation (`add_user_entry`, `remove_user_entry`) invalidates `_data = None` so the next read re-merges.

---

### `settings_manager.py`

**`OptimizeSettingsManager`** — YAML-backed persistence for `OptimizeSettings`.

Follows the same lazy-load + dirty-flag pattern as `ScheduleManager`. The file is never written unless a change is made, and reading before any change doesn't create the file.

| Method | What it does |
|---|---|
| `get()` | Return the current `OptimizeSettings` (loads on first call) |
| `update(**kwargs)` | Apply field changes via `dataclasses.replace`, persist, return new settings |
| `reset()` | Replace with a fresh default `OptimizeSettings`, persist |
| `save()` | No-op if `_dirty=False`; otherwise dumps YAML |

**Storage file:** `$XDG_CONFIG_HOME/anythink/optimize_settings.yaml`

**Used by:** Every `/optimize` subcommand handler in `commands.py`, the `_sync_mmos_hud()` helper in `app.py`, and the routing engine (which reads settings at query time via `ctx.mmos_settings.get()`).

---

### `rate_limit.py`

**`RateLimitManager`** — Tracks per-model RPM, TPM, and RPD usage; gates requests; auto-switches models.

#### `ModelRateWindow` (dataclass)

Holds the live counters for one model:

| Field | Description |
|---|---|
| `requests_in_window` | Requests made in the current 60-second window |
| `tokens_in_window` | Tokens consumed in the current 60-second window |
| `requests_today` | Total requests today (for RPD checking) |
| `window_start` | `time.monotonic()` when the 60s window started |
| `day_start` | `time.monotonic()` when the 24h window started |
| `unavailable` | `True` when marked unreachable (network failure in auto mode) |

Windows auto-reset: the 60-second window resets when `time.monotonic() - window_start >= 60`. The day window resets at 86400 seconds. Both checks happen inside `_get_window()` on every access.

#### `RateLimitManager` methods

| Method | What it does |
|---|---|
| `record_request(model_id, tokens)` | Increment all counters for a completed request |
| `is_at_rpm_limit(model_id)` | True if `requests_in_window >= cap.rpm_limit` |
| `is_at_tpm_limit(model_id, est_tokens)` | True if adding `est_tokens` would exceed `tpm_limit` |
| `is_at_rpd_limit(model_id)` | True if `requests_today >= cap.rpd_limit` |
| `seconds_until_available(model_id)` | Seconds remaining in current RPM window |
| `find_next_available(candidates)` | Walk a list; return first non-exhausted, non-unavailable model |
| `mark_unavailable(model_id)` | Flag a model as unreachable for the session |
| `get_status()` | All `ModelRateWindow` objects (ensures windows exist for every registry entry) |
| `reset_counters()` | Clear all in-memory windows and delete the state file |
| `save()` | Persist current windows to `rate_limit_state.json` |

**Persistence:** State is saved to `$XDG_STATE_HOME/anythink/rate_limit_state.json`. On load, day windows older than 24 hours are dropped; minute windows are not restored (they'll be recreated from scratch as stale anyway). This gives cross-restart continuity for RPD tracking within the same calendar session.

---

### `classifier.py`

**`IntentClassifier`** — Zero-latency, zero-model-call query classifier.

Uses `frozenset` keyword sets to score query text against six categories. No network calls, no model calls — runs synchronously in under a millisecond.

**Category keyword sets (module-level constants):**

| Constant | Category | Notes |
|---|---|---|
| `CODING_PATTERNS` | `"Coding"` | ~50 patterns: language names, syntax keywords, tool names |
| `RESEARCH_PATTERNS` | `"Research"` | Weighted ×2; comprehensive/architecture/deep-dive phrases |
| `CREATIVE_PATTERNS` | `"Creative"` | Weighted ×2; story/poem/brainstorm phrases |
| `FACTUAL_PATTERNS` | `"Factual"` | Interrogative patterns: "what is", "who was", "when did" |
| `REASONING_PATTERNS` | `"Reasoning"` | Compare/evaluate/pros-cons phrases |
| `MATH_PATTERNS` | `"Math"` | Weighted ×2; equation/proof/calculus terms |

**Methods:**

| Method | Signature | Description |
|---|---|---|
| `classify` | `(text) → QueryIntent` | Runs keyword scoring; returns intent with `from_user=False` |
| `estimate_tokens` | `(text) → int` | `len(text) // 4`; minimum 1 |
| `should_trigger_plan_mode` | `(text, token_estimate, model_context) → bool` | True if any plan-trigger phrase is present, OR if `token_estimate > 300` and `> 60%` of model context |
| `extract_override_flags` | `(text) → (clean_text, flags_dict)` | Parses `--model`, `--strategy`, `--speed`, `--quality`, `--no-plan`; strips flags from the returned clean text |

**Override flag format:**
```
How do I sort a list? --model ollama/deepseek-coder --speed
```
Returns: `("How do I sort a list?", {"model": "ollama/deepseek-coder", "priority": "speed"})`

---

### `rules.py`

**`RoutingRulesLoader`** + **`RoutingRule`** — User-defined routing rules in YAML.

Rules are evaluated by `RoutingEngine.decide()` after the keyword classification but before deterministic scoring. They let advanced users hard-wire routing decisions for specific conditions.

#### `RoutingRule` fields

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Identifying label |
| `condition` | `str` | Python expression evaluated against a context dict |
| `action` | `str` | What to do when matched |
| `priority` | `int` | Higher priority rules are evaluated first |

**Condition context variables available:**
- `category` — string, e.g. `"Coding"`
- `tokens` — estimated total token count
- `mode` — `"online"`, `"offline"`, or `"auto"`
- `priority` — current session priority setting

**Action syntax:**
- `"strategy=ensemble"` — force a specific mixing strategy
- `"model=groq/llama3-70b-8192"` — route to a specific model
- `"plan=true"` — trigger Plan Mode

**Example `routing_rules.yaml`:**
```yaml
- name: always-ensemble-for-architecture
  condition: "'architecture' in category.lower() or tokens > 2000"
  action: strategy=ensemble
  priority: 10

- name: local-only-for-short-coding
  condition: "category == 'Coding' and tokens < 200"
  action: model=ollama/deepseek-coder
  priority: 5
```

**Storage file:** `$XDG_CONFIG_HOME/anythink/routing_rules.yaml`

**Lazy-load:** Rules are loaded once on first call to `all()` or `evaluate()`, then cached. Call `invalidate()` to force a reload after the file changes.

---

### `router.py`

**`RoutingEngine`** — The core brain that picks a model and strategy for every query.

**Decision order (four-step waterfall):**

1. **User override flags** — `--model`, `--strategy`, `--speed`, `--quality` appended to the query. If a valid model/strategy is specified, return immediately.
2. **YAML routing rules** — Evaluate rules from `RoutingRulesLoader` in priority order. First match wins.
3. **Deterministic scoring** — Score all available models using weighted criteria; pick the best strategy based on intent category and priority setting.
4. **Meta-LLM stub** — If confidence < 0.5 and `orchestration_mode != "deterministic"`, the decision is flagged with `[meta-LLM pending]` in the reason. Full meta-LLM orchestration is a future upgrade; currently the deterministic result is returned with the low-confidence flag.

**Scoring weights (deterministic pass):**

| Criterion | Score |
|---|---|
| Strength category match | +3.0 |
| Quality class high (quality-first priority) | +2.0 |
| Quality class medium | +1.0 |
| Speed class fast (reliability-first priority) | +2.0 |
| Context window fits the query | +1.5 |
| Context window tight (>80% utilised) | −2.0 |
| Context window too small | −4.0 |
| At RPM or RPD limit | −10.0 |
| Model marked unavailable | −20.0 |

**Strategy selection rules (deterministic):**
- Category `Reasoning`, `Research`, or `Creative` + priority `quality` → **ensemble**
- Category `Research` + `plan_mode_enabled` → **decompose** (Plan Mode)
- All other cases → **routing** (single best model)

**`detect_override_conflict(override, decision, token_estimate) → str | None`**  
Returns a human-readable warning string when a user's forced model can't safely handle the query (context overflow, or local-only model selected for an ensemble strategy). Returns `None` when the override is safe.

---

### `context_engine.py`

**`ContextRelevanceEngine`** — Selects a relevant subset of conversation history to include with the current query, respecting the model's token budget.

**Three modes (set via `OptimizeSettings.history_mode`):**

#### `"recency"` (default fallback)
Takes the last 8 messages. Filters out messages that share fewer than 2 words with the current query. Always keeps the last 3 messages regardless of topic match. Trims oldest messages until within budget.

#### `"semantic"` (default when embedding backend is available)
Embeds all history messages and the current query using the configured embedding backend (`BaseEmbeddingBackend`). Computes cosine similarity of each message against the query. Returns top-6 messages above a 0.35 similarity threshold, in chronological order. Falls back to `"recency"` if the embedding call fails.

#### `"model_decides"` (future — currently falls back to recency)
A fast local model would select relevant message indices from a compact summary list. Not yet implemented; falls back to `"recency"`.

**Public API:**

| Method | Description |
|---|---|
| `select_relevant_history(history, query, budget)` | Async; returns filtered `list[ChatMessage]` within token budget |
| `needs_summarisation(messages, budget)` | True if the selected messages still exceed *budget* |

**Token estimation:** `total_chars // 4` (4 chars ≈ 1 token heuristic).

---

### `plan.py`

**All Plan Mode dataclasses plus text-file serialisation.** No business logic lives here — all execution happens in `plan_engine.py` and `plan_runner.py`.

#### Status constants

```python
# Phase statuses
PHASE_STATUS_WAITING  = "waiting"
PHASE_STATUS_RUNNING  = "running"
PHASE_STATUS_DONE     = "done"
PHASE_STATUS_FAILED   = "failed"
PHASE_STATUS_SKIPPED  = "skipped"

# Plan statuses
PLAN_STATUS_PENDING   = "pending"
PLAN_STATUS_APPROVED  = "approved"
PLAN_STATUS_RUNNING   = "running"
PLAN_STATUS_DONE      = "done"
PLAN_STATUS_ABORTED   = "aborted"
```

#### `PlanPhase`

One step in an `ExecutionPlan`.

| Field | Description |
|---|---|
| `phase_num` | 1-based sequence number |
| `title` | Short display title |
| `description` | One or two sentences describing what this phase should answer |
| `model_id` | Registry model ID assigned to this phase |
| `estimated_tokens` | Rough token estimate (100–4096) |
| `depends_on` | Phase numbers whose output this phase needs as context |
| `output_type` | `"explanation"`, `"code"`, `"table"`, or `"detail"` |
| `status` | One of the `PHASE_STATUS_*` constants |
| `output` | The model's response for this phase (filled after execution) |
| `elapsed_s` | Wall time for this phase (filled after execution) |
| `actual_model` | The model that actually ran (may differ from `model_id` if switched by rate limiter) |

#### `ExecutionPlan`

The full plan, with all phases.

| Property | Type | Description |
|---|---|---|
| `total_estimated_tokens` | `int` | Sum of all phase `estimated_tokens` |
| `unique_models` | `list[str]` | Deduplicated model IDs across all phases + recombination |
| `estimated_minutes` | `(float, float)` | `(min_minutes, max_minutes)` based on token estimates |

**Serialisation:**
- `to_dict()` / `from_dict()` — JSON-compatible dict, used for session storage.
- `to_text()` / `from_text()` — Human-readable text format, written to `plans_dir` as `plan_{session_id}_{timestamp}.txt`. Each phase block includes description, model, status, output, and timing.

**Factory:** `ExecutionPlan.new(session_id, original_query, recombination_model)` creates an empty plan with a fresh UUID.

#### `PhaseUpdate`

Progress event emitted by `PlanRunner` to the TUI. Contains `phase_num`, `status`, `elapsed_s`, `queue_wait_s`, `actual_model`, and `error`. Passed via `call_from_thread(phase_tracker.update_phase, update)`.

#### `MixingResult`

The unified result from any `MixingOrchestrator.execute()` call, regardless of strategy.

| Field | Description |
|---|---|
| `strategy` | Which strategy was used |
| `outputs` | List of `(model_id, text, elapsed_s)` tuples, one per model call |
| `final_text` | The text to render in the chat bubble |
| `total_tokens` | Sum of all token estimates |
| `metadata` | `TurnMMOSMetadata` for session storage and attribution |

---

### `plan_engine.py`

**`PlanEngine`** — Generates an `ExecutionPlan` from a user query by calling a fast model.

**How it works:**
1. Selects the fastest available model for plan generation (`_select_planning_model(mode)`). Prefers fast local models in `"offline"` mode.
2. Sends a structured planning prompt (`_PLANNING_SYSTEM_PROMPT`) plus a user prompt listing available models with their capabilities.
3. Parses the numbered `PHASE N: ...` blocks in the response using a regex pattern into `PlanPhase` objects.
4. Falls back to a single-phase plan if the model call fails or the output cannot be parsed.

**`ProviderResolver` type alias:**
```python
ProviderResolver = Callable[[str], tuple[BaseProvider, str] | None]
# Takes a capability model_id like "groq/llama3-70b-8192"
# Returns (instantiated_provider, api_model_id) or None if unavailable
```
This decouples the engine from `AppContext`. The TUI worker supplies the resolver at call time by splitting `model_id` on `/` and instantiating via `ctx.provider_registry`.

**Public methods:**

| Method | Description |
|---|---|
| `generate_plan(query, intent, routing_decision, provider_resolver, session_id, mode)` | Async; returns `ExecutionPlan` in `PLAN_STATUS_PENDING` state |
| `regenerate_plan(original, feedback, provider_resolver, mode)` | Async; sends the original query + rejection reason back to the planning model |

**Planning prompt format expected from the model:**
```
PHASE 1: Short title
  DESCRIPTION: What this phase covers
  MODEL: groq/llama3-70b-8192
  EST_TOKENS: 800
  DEPENDS_ON: none
  OUTPUT_TYPE: explanation

PHASE 2: ...
```

---

### `plan_runner.py`

**`PlanRunner`** — Executes an approved `ExecutionPlan` phase by phase, with full rate-limit awareness.

**Execution flow:**
1. Iterates phases in order.
2. For each phase: calls `_resolve_provider()` — tries the assigned model, then walks the full registry fallback until a non-rate-limited, non-unavailable provider is found.
3. If a model is at its RPM limit, polls with `asyncio.sleep(1.0)` until the window resets, emitting a `"queued"` `PhaseUpdate` to the TUI.
4. Builds a focused phase prompt via `_build_phase_prompt()`, which injects prior phase outputs only for phases listed in `depends_on`.
5. Calls `_collect_text()` to stream and collect the model response.
6. Emits `PhaseUpdate` callbacks on every state transition (`running` → `done`/`failed`).
7. After all phases: calls `_recombine()` which sends all phase outputs to the recombination model for synthesis into a single final answer.
8. Saves the completed plan to `plans_dir/plan_{session[:8]}_{timestamp}.txt`.

**Control signals (via asyncio.Event):**
- `abort_signal` — When set, skips remaining phases, marks plan `PLAN_STATUS_ABORTED`.
- `skip_phase` — Skips the specified phase number.
- `pause_after_phase` — Awaits `abort_signal` after the named phase completes (the TUI resumes it by setting the event).

**Recombination fallback:** If the recombination model is unavailable, concatenates all phase outputs with `**Phase N:**` headers.

**`_emit(callback, update)`** — Module-level helper that calls the `PhaseUpdateCallback` inside `contextlib.suppress(Exception)`. Prevents a misbehaving TUI callback from crashing the worker.

---

### `mixing.py`

**`MixingOrchestrator`** — The top-level dispatcher for all four mixing strategies.

`execute(decision, messages, intent, provider_resolver, session_id, on_phase_update)` routes to one of the four internal methods based on `decision.strategy`.

#### `_routing_mode` — Single model call
Calls one provider, collects text, records to `RateLimitManager`, returns `MixingResult`.

#### `_ensemble_mode` — Parallel multi-model calls
Uses `asyncio.gather` to call all models in `decision.phase_models` concurrently. Each response is wrapped with a attributed header:
```
════════════════════════════════════════════════════════════
Response 1 of 3  ·  groq/llama3-70b  ·  [fast]
════════════════════════════════════════════════════════════
[model response here]
```
The `final_text` is the full concatenated string. `total_tokens` sums all models.

#### `_chaining_mode` — Sequential draft → critique → refine
Iterates `decision.phase_models` (up to 3). Each step uses a different system prompt:
- Step 0 (`_CHAIN_SYSTEM[0]`): Subject-matter expert, produce a draft.
- Step 1 (`_CHAIN_SYSTEM[1]`): Critical reviewer, identify gaps in the draft.
- Step 2 (`_CHAIN_SYSTEM[2]`): Refinement assistant, produce improved final answer.

Each step injects the previous step's output into the user message. The `final_text` is the last step's output.

#### `_decompose_mode` — Full Plan Mode delegation
Extracts the query from the last user message, calls `PlanEngine.generate_plan()`, then `PlanRunner.execute()`. Passes `on_phase_update` through to the runner for TUI progress updates. The `MixingResult.metadata.phase_outputs` contains per-phase output dicts.

---

### `commands.py`

**Slash command handlers for the `/optimize` and `/mode` namespaces.**

Follows the exact same pattern as `debug/commands.py`: one central dispatcher, sub-handlers as private functions, `register_optimize_commands(registry)` at the bottom.

**Called from:** `commands/handlers.py` → `register_commands()` calls `register_optimize_commands(registry)`.

#### `/mode` command

```
/mode online | offline | auto
```
Updates `ctx.mmos_settings.mode`, persists immediately, returns `action="mmos_hud_update"`.

#### `/optimize` subcommands

| Subcommand | Action / Effect |
|---|---|
| `/optimize` (no args) | `action="open_optimize_panel"` → TUI opens `OptimizePanel` |
| `/optimize status` | Prints compact status table: engine state, mode, priority, registry count, rate limits |
| `/optimize toggle` | Flips `enabled`; `action="mmos_hud_update"` |
| `/optimize mode <value>` | Alias for `/mode` |
| `/optimize routing <strategy>` | Sets `routing_strategy` |
| `/optimize history <mode>` | Sets `history_mode` |
| `/optimize history max <n>` | Sets `history_max_tokens` |
| `/optimize priority <value>` | Sets `priority` |
| `/optimize plan on\|off` | Enables/disables Plan Mode |
| `/optimize plan approval on\|off` | Toggles approval gate before plan execution |
| `/optimize ensemble <mode>` | Sets `mixing_mode` |
| `/optimize ensemble count <n>` | Sets `ensemble_count` (2–5) |
| `/optimize ratelimit` | `action="open_ratelimit_panel"` → TUI opens `RateLimitPanel` |
| `/optimize registry` | `action="open_optimize_registry"` → TUI shows registry table |
| `/optimize registry add` | `action="open_optimize_registry_add"` |
| `/optimize registry edit <id>` | `action="open_optimize_registry_edit"` + `extra={"model_id": ...}` |
| `/optimize registry delete <id>` | Removes user overlay entry; persists |
| `/optimize registry reset <id>` | Restores bundled value |
| `/optimize registry export` | Exports merged registry to `exports_dir/model_registry_{ts}.json` |
| `/optimize registry import <file>` | Imports entries from a JSON file |
| `/optimize microprompt` | Toggles `microprompt_enabled` |
| `/optimize reset` | `action="optimize_reset_confirm"` → TUI confirms before resetting |
| `/optimize help` | Lists all subcommands |

**Action strings returned** (handled by `_dispatch_command` in `app.py`):
- `"open_optimize_panel"`, `"open_ratelimit_panel"`, `"open_optimize_registry"`, `"open_optimize_registry_add"`, `"open_optimize_registry_edit"` — open TUI overlays
- `"mmos_hud_update"` — triggers `_sync_mmos_hud()` to refresh HUD reactive fields
- `"optimize_reset_confirm"` — sets `_pending_optimize_reset = True`; TUI waits for `y` confirmation

---

### `attribution.py`

**`AttributionFormatter`** — Pure Rich Text helpers for MMOS response attribution. No Textual dependency; safe in CLI and TUI render paths.

All methods are `@staticmethod`; no instance state.

#### `single_model_header(model_id, strategy, tokens, elapsed_s, *, width=80) → Text`
Used for `routing`, `ensemble`, and `chaining` turns.
```
── groq/llama3-70b  ·  routing  ·  1,243 tokens  ·  0.8s ──────────────
```

#### `plan_mode_header(mmos, *, phase_count=0, width=80) → Text`
Used for `decompose` / Plan Mode turns. Deduplicates provider names from `model_ids`.
```
── Plan Mode  ·  5 phases  ·  groq, together, ollama  ·  4,821 tokens  ·  2m 14s ──
```

#### `ensemble_section_header(model_id, index, total, speed_class, *, width=80) → Text`
Section divider between ensemble responses.
```
════════  Response 2 of 3  ·  together/mixtral-8x7b  ·  [medium]  ════════
```

#### `phase_output_block(phase, *, width=80) → Text`
Section divider for expanded phase output blocks.
```
── Phase 2: Frontend architecture  ·  together/mixtral  ·  3.4s ──────────
```

#### `from_mmos_metadata(mmos, *, width=80) → Text`
Auto-selects the appropriate header. Returns `plan_mode_header` if `strategy in ("decompose", "plan")` and phase outputs exist; otherwise returns `single_model_header`.

**Used in:** `ui/bubbles.py` → `AIBubble.finalize_with_mmos()`, `export/formats.py` → `export_markdown()`.

---

## Configuration Files

| File | Location | Description |
|---|---|---|
| `model_registry.json` | `$XDG_DATA_HOME/anythink/` (bundled) | Read-only base registry shipped with the package |
| `model_registry_user.json` | `$XDG_CONFIG_HOME/anythink/` | User-added and overridden model entries |
| `optimize_settings.yaml` | `$XDG_CONFIG_HOME/anythink/` | Persisted `/optimize` panel state |
| `routing_rules.yaml` | `$XDG_CONFIG_HOME/anythink/` | User-defined YAML routing rules (advanced) |
| `rate_limit_state.json` | `$XDG_STATE_HOME/anythink/` | Session rate limit counters (ephemeral; day-boundary aware) |
| `plan_{session}_{ts}.txt` | `$XDG_DATA_HOME/anythink/plans/` | Human-readable execution log per Plan Mode run |

All paths are exposed as `@property` methods on `config/manager.py:Paths`.

---

## AppConfig V4 Fields

These fields live in `config/schema.py:AppConfig` and control the session-level defaults. The `/optimize` commands update `OptimizeSettingsManager` (per-install settings), not these fields — but `AppConfig.mmos_enabled` is the master gate.

| Field | Default | Description |
|---|---|---|
| `mmos_enabled` | `False` | Master switch — `False` = pure V3 behaviour |
| `mmos_mode` | `"auto"` | Startup default for online/offline/auto |
| `mmos_priority` | `"quality"` | Startup default for quality/reliability/hybrid |
| `mmos_microprompt` | `True` | Startup default for micro-prompt |
| `mmos_history_mode` | `"semantic"` | Startup default for history selection |
| `mmos_history_max_tokens` | `2048` | Startup default for history token budget |
| `mmos_mixing_mode` | `"routing"` | Startup default for mixing strategy |
| `mmos_plan_mode` | `True` | Startup default for Plan Mode |
| `mmos_orchestration` | `"auto"` | Startup default for orchestration mode |
| `mmos_fallback_order` | `()` | Ordered model IDs to try on rate limit |

Enable MMOS by setting `mmos_enabled = True` via `/optimize toggle` (which also persists the change to `optimize_settings.yaml`).

---

## Test Coverage

Tests live in `tests/test_optimize/`:

| Test file | What it covers |
|---|---|
| `test_models.py` | Round-trip `to_dict()` / `from_dict()` for all 5 dataclasses |
| `test_registry.py` | Bundled load, user overlay merge, CRUD operations, export/import |
| `test_settings_manager.py` | Lazy-load, `update()`, `reset()`, persistence, corrupt-file fallback |
| `test_rate_limit.py` | Counter increment, RPM/TPM/RPD gates, fallback selection, reset |
| `test_classifier.py` | All 6 category paths, format detection, plan mode trigger, flag extraction |
| `test_router.py` | Coding → coding model, rate-limited skip, `--model` override, YAML rule |
| `test_context_engine.py` | Recency mode, semantic mode (mocked backend), fallback on error |
| `test_plan.py` | `PlanPhase` / `ExecutionPlan` dict and text round-trips, computed properties |
| `test_plan_engine.py` | Plan parsing, fallback on empty/error response, model selection per mode |
| `test_plan_runner.py` | Single-phase completion, abort signal, skip, callback firing, file save |
| `test_mixing.py` | Routing single call, ensemble parallel calls + attribution, chaining passthrough |
| `test_commands.py` | All `/optimize` and `/mode` subcommands, persistence verification |
| `test_attribution.py` | All four header methods, `from_mmos_metadata` dispatch, elapsed formatting |

---

## Adding a New Model to the Bundled Registry

Edit `src/anythink/data/model_registry.json` and add an entry to the `"models"` array:

```json
{
  "id": "groq/llama3-8b-8192",
  "provider": "groq",
  "display_name": "Llama 3 8B (Groq)",
  "tier": "free-api",
  "context_window": 8192,
  "max_output_tokens": 8192,
  "rpm_limit": 30,
  "tpm_limit": 30000,
  "rpd_limit": 14400,
  "strength_categories": ["coding", "factual"],
  "speed_class": "fast",
  "quality_class": "medium",
  "supports_system_prompt": true,
  "supports_streaming": true,
  "requires_network": true,
  "notes": "Optional notes"
}
```

The `id` field must match the format `"provider/model_id_on_api"`. The provider name must match a registered entry in `anythink.providers` entry points. Users can also add models at runtime via `/optimize registry add`.

---

## Adding a New Mixing Strategy

1. Add the strategy name to `_MIXING_MODES` in `commands.py`.
2. Add a new `_my_strategy_mode()` async method on `MixingOrchestrator` in `mixing.py`.
3. Add a dispatch branch in `MixingOrchestrator.execute()`.
4. Add to the `OptimizeSettings.mixing_mode` enum in `models.py` and to `_ENUM_FIELDS` in `config/manager.py`.
5. Update the `/optimize ensemble` help text in `commands.py`.
