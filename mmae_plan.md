MMAE Implementation Plan — Multi-Model Answering Engine

     Context

     The anythink_mmae_description.md defines a new per-session query intelligence layer called the Multi-Model Answering Engine
     (MMAE). When toggled on via /smart on, it intercepts every user message, routes sub-questions to specialist models
     sequentially, quality-gates each response, combines everything into a single unified answer, and optionally formats output —
     all in one conversational turn. The user sees one clean response with an expandable ✦ N specialists footer.

     This is distinct from V4 MMOS (src/anythink/optimize/) and MMWE (src/anythink/workflow/). No existing module is reused as MMAE
     logic; we build src/anythink/smart/ from scratch, following the same patterns as debug/, optimize/, and workflow/.

     ---
     Critical Files to Modify (existing)

     ┌───────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────
     ┐
     │               File                │                                       What changes
     │
     ├───────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────
     ┤
     │ src/anythink/config/schema.py     │ Add MMAE group to AppConfig (10 new fields)
     │
     ├───────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────
     ┤
     │ src/anythink/exceptions.py        │ Add SmartError subclass
     │
     ├───────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────
     ┤
     │ src/anythink/app/context.py       │ Add smart_registry, smart_engine, smart_enabled fields + wiring in create()
     │
     ├───────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────
     ┤
     │ src/anythink/commands/handlers.py │ Call register_smart_commands(registry) at bottom of register_commands()
     │
     ├───────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────
     ┤
     │ src/anythink/ui/hud.py            │ Add smart_enabled: reactive[bool] + _line2() rendering block
     │
     ├───────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────
     ┤
     │ src/anythink/ui/textual/app.py    │ Intercept user messages when ctx.smart_enabled; add smart_hud_update action handler; add
     │
     │                                   │  expandable footer to AIBubble calls
     │
     ├───────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────
     ┤
     │ src/anythink/ui/bubbles.py        │ Add finalize_with_smart(text, smart_result) and collapsible specialists footer
     │
     └───────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────
     ┘

     New Files (all under src/anythink/smart/)

     src/anythink/smart/
     ├── __init__.py
     ├── categories.py       Built-in 9-category definitions + tag-to-category map
     ├── models.py           RoutingPlan, SubQuestion, SpecialistResponse, TemporaryStore, SmartResult
     ├── registry.py         SmartRegistry — YAML-backed category→model map, CRUD, auto-populate
     ├── router.py           RouterModel — invoke router LLM, parse/validate JSON, retry on schema error
     ├── quality.py          QualityGate — composite heuristic score, retry/fallback logic
     ├── store.py            TemporaryResponseStore — in-memory per-turn store
     ├── executor.py         SequentialExecutor — run specialists, interface with quality gate
     ├── combiner.py         CombinerModel — Stitch / Intelligent Merge modes
     ├── formatter.py        FormatterModel — invoke formatter LLM when format requested
     ├── detector.py         FormatDetector — extract format instruction from user message text
     ├── engine.py           SmartEngine — main pipeline orchestrator tying all components
     └── commands.py         /smart command namespace (follows debug/commands.py pattern)

     Test files: tests/test_smart/ (one file per module above).

     ---
     Phase 1 — Foundation: Models, Categories, Config, Exception

     Goal: Define every data type the pipeline uses; add config fields; register exception.

     1.1 src/anythink/smart/categories.py

     @dataclass(frozen=True)
     class Category:
         key: str          # e.g. "math"
         name: str         # e.g. "Math / Calculations"
         description: str  # used in router system prompt

     CATEGORIES: dict[str, Category]  # keyed by key, 9 entries
     TAG_TO_CATEGORY: dict[str, str]  # e.g. {"code-review": "code", "factual": "research"}

     All 9 categories from spec section 4.1. general is included.

     1.2 src/anythink/smart/models.py

     @dataclass
     class SubQuestion:
         sub_question: str
         category: str
         model_alias: str
         context_included: bool = True

     @dataclass
     class RoutingPlan:
         complexity: str          # "single" | "multi"
         categories_detected: list[str]
         routing_plan: list[SubQuestion]
         reasoning_summary: str

     @dataclass
     class SpecialistResponse:
         slot: int
         category: str
         model_alias: str
         sub_question: str
         response: str
         quality_score: int       # 0–100
         retry_count: int
         duration_s: float
         low_confidence: bool = False

     @dataclass
     class TemporaryStore:
         entries: list[SpecialistResponse] = field(default_factory=list)

     @dataclass
     class SmartResult:
         combined_text: str
         formatter_applied: str | None    # None if formatter not run
         total_duration_s: float
         routing_plan: RoutingPlan
         store: TemporaryStore
         combiner_model: str
         combiner_mode: str

     1.3 src/anythink/config/schema.py — MMAE group

     Add after the MMWE fields:

     # MMAE
     smart_default_state: bool = False
     smart_combiner_mode: str = "stitch"          # "stitch" | "merge"
     smart_quality_threshold: int = 50            # 0–100
     smart_max_splits: int = 5
     smart_session_format: str = ""               # "" means no default format
     smart_show_detail: bool = True
     smart_router_model: str = ""                 # alias; "" = use default_model_alias
     smart_combiner_model: str = ""
     smart_formatter_model: str = ""
     smart_registry_file: str = ""                # "" = default XDG path

     1.4 src/anythink/exceptions.py

     class SmartError(AnythinkError):
         pass

     Tests: tests/test_smart/test_models.py — construct each dataclass, check field defaults.

     ---
     Phase 2 — Smart Registry

     Goal: Persistent YAML file mapping category keys to model aliases. CRUD + auto-populate from MMWE capability registry.

     src/anythink/smart/registry.py

     class SmartRegistry:
         def __init__(self, registry_file: Path): ...
         def load(self) -> None: ...            # reads YAML, falls back to defaults
         def save(self) -> None: ...

         # Category CRUD
         def get(self, category: str) -> str | None: ...   # primary model alias
         def set(self, category: str, alias: str) -> None:
         def reset(self, category: str) -> None: ...       # back to auto-populated default
         def reset_all(self) -> None: ...
         def all_assignments(self) -> dict[str, str]: ...

         # Special slots
         def get_router(self) -> str | None: ...
         def set_router(self, alias: str) -> None: ...
         def get_combiner(self) -> str | None: ...
         def set_combiner(self, alias: str) -> None: ...
         def get_formatter(self) -> str | None: ...
         def set_formatter(self, alias: str) -> None: ...

         # Auto-populate from MMWE WorkflowCapabilityRegistry
         def auto_populate(self, workflow_registry) -> None: ...
         # WorkflowCapabilityRegistry API available:
         #   workflow_registry.aliases_with_tag(tag) -> list[str]
         #   workflow_registry.get_tags(alias) -> list[str]
         # For each MMAE category, resolve TAG_TO_CATEGORY keys → call aliases_with_tag()
         # Assign the alias with highest tag-overlap as primary; rest as secondary candidates

     YAML format:
     categories:
       math: local-math
       code: local-coder
       general: local1
       # ...
     slots:
       router: local-planner
       combiner: local-general
       formatter: local-general

     Tests: tests/test_smart/test_registry.py — load/save round-trip, CRUD, auto-populate with mock workflow registry.

     ---
     Phase 3 — Router Model

     Goal: Call router LLM, parse JSON routing plan, validate schema, retry once on failure.

     src/anythink/smart/router.py

     class RouterModel:
         def __init__(self, registry: SmartRegistry, provider_registry, model_registry): ...

         async def route(
             self,
             user_message: str,
             history: list[ChatMessage],
             format_hint: str | None,
         ) -> RoutingPlan: ...

         def _build_system_prompt(self) -> str: ...
         # Combines: role definition + category catalogue + live model assignments + output schema

         def _parse_response(self, raw: str) -> RoutingPlan: ...
         # Extracts JSON from raw LLM output, validates fields, raises SmartError on bad schema

         async def _call_router(self, prompt: str) -> str: ...
         # Calls provider.stream_chat() with the router model alias, collects full response
         # On SmartError (bad schema): retries once with error message appended

     Router system prompt parts (from spec section 6.3):
     1. Role definition
     2. Category catalogue (from categories.py)
     3. Current model assignments (from registry.all_assignments())
     4. Output JSON schema

     Tests: tests/test_smart/test_router.py — mock LLM, test schema validation, test retry on bad JSON, test single vs multi
     category output.

     ---
     Phase 4 — Quality Gate + Temporary Store

     Goal: Heuristic scoring (0–100) with retry/fallback logic. In-memory per-turn store.

     src/anythink/smart/quality.py

     @dataclass
     class QualityCheckResult:
         score: int                      # 0–100 composite
         length_score: int               # 0–20
         nonrefusal_score: int           # 0–30
         coherence_score: int            # 0–30
         completion_score: int           # 0–20
         passed: bool                    # score >= threshold
         checks_detail: dict[str, str]

     class QualityGate:
         def __init__(self, threshold: int = 50): ...

         def evaluate(self, response: str, category: str, sub_question: str) -> QualityCheckResult:
             # Length check (20%): compare len(response) to expected_min_length(sub_question)
             # Non-refusal check (30%): detect refusal phrases / empty content
             # Category coherence (30%): e.g. code category → look for code blocks
             # Completion signal (20%): detect mid-sentence cutoff, truncation markers
             ...

     src/anythink/smart/store.py

     class TemporaryResponseStore:
         def __init__(self): ...
         def add(self, entry: SpecialistResponse) -> None: ...
         def all(self) -> list[SpecialistResponse]: ...
         def clear(self) -> None: ...

     Tests: tests/test_smart/test_quality.py — test each heuristic independently, test threshold pass/fail.
     tests/test_smart/test_store.py — add/retrieve/clear.

     ---
     Phase 5 — Sequential Executor

     Goal: Run specialists one by one in routing plan order, applying quality gate + fallback.

     src/anythink/smart/executor.py

     class SequentialExecutor:
         def __init__(
             self,
             registry: SmartRegistry,
             quality_gate: QualityGate,
             provider_registry,
             model_registry,
         ): ...

         async def execute(
             self,
             routing_plan: RoutingPlan,
             original_message: str,
             history: list[ChatMessage],
             store: TemporaryResponseStore,
             on_progress: Callable[[str, int, int], None] | None = None,
             # on_progress(status_msg, current_slot, total_slots)
         ) -> None: ...

         async def _run_specialist(
             self,
             sq: SubQuestion,
             slot: int,
             original_message: str,
             history: list[ChatMessage],
         ) -> SpecialistResponse: ...
         # Builds specialist prompt (spec section 9.3 ordering)
         # Calls provider.stream_chat()
         # Runs quality gate
         # On fail: retry same model once, then try secondary aliases, then general fallback
         # Returns SpecialistResponse with low_confidence=True if all attempts fail

         def _build_specialist_prompt(
             self, sq: SubQuestion, original_message: str, history: list[ChatMessage]
         ) -> str: ...
         # System prompt → recent history → [ORIGINAL QUESTION] → [YOUR TASK]

     Retry chain (spec section 12.3):
     1. Same model, same prompt (once)
     2. Secondary aliases for this category from registry (ordered)
     3. General fallback model
     4. Accept with low_confidence=True

     Tests: tests/test_smart/test_executor.py — mock provider, test normal path, test retry on quality fail, test fallback chain.

     ---
     Phase 6 — Combiner + Formatter + Format Detector

     Goal: Combine specialist responses in Stitch or Merge mode; optionally reformat.

     src/anythink/smart/combiner.py

     class CombinerModel:
         def __init__(self, registry: SmartRegistry, provider_registry, model_registry): ...

         async def combine(
             self,
             store: TemporaryResponseStore,
             mode: str,       # "stitch" | "merge"
         ) -> str: ...

         def _build_combiner_prompt(self, store: TemporaryResponseStore, mode: str) -> str: ...
         # Formats store entries as:
         # [Specialist N — {category} — {alias} (score: {q})]
         # {response}
         # Adds mode instruction (Stitch vs Merge)

     src/anythink/smart/detector.py

     FORMAT_KEYWORDS: dict[str, list[str]]   # format_name → trigger keyword list (spec section 16)

     def detect_format(message: str) -> str | None:
         # Scans message for format trigger keywords
         # Returns format name (e.g. "markdown", "table", "code_only") or None

     src/anythink/smart/formatter.py

     class FormatterModel:
         def __init__(self, registry: SmartRegistry, provider_registry, model_registry): ...

         async def format(
             self,
             combined_text: str,
             format_name: str,
         ) -> str: ...

         def _build_formatter_prompt(self, combined_text: str, format_name: str) -> str: ...

     Tests: tests/test_smart/test_combiner.py, tests/test_smart/test_detector.py, tests/test_smart/test_formatter.py.

     ---
     Phase 7 — SmartEngine Orchestrator

     Goal: Wire all components into a single run() method that executes the full pipeline.

     src/anythink/smart/engine.py

     class SmartEngine:
         def __init__(
             self,
             registry: SmartRegistry,
             provider_registry,
             model_registry,
             debug_manager,
             spend_tracker,
         ): ...

         # Sub-components (constructed in __init__)
         # self._router: RouterModel
         # self._gate: QualityGate (threshold from config)
         # self._store: TemporaryResponseStore
         # self._executor: SequentialExecutor
         # self._combiner: CombinerModel
         # self._formatter: FormatterModel

         async def run(
             self,
             message: str,
             history: list[ChatMessage],
             session_id: str,
             combiner_mode: str,
             quality_threshold: int,
             session_format: str,
             on_progress: Callable[[str], None] | None = None,
         ) -> SmartResult: ...
         # Full pipeline:
         # 1. detect_format(message) → format_hint
         # 2. router.route(message, history, format_hint) → routing_plan
         # 3. emit [SMART] debug events for routing
         # 4. store.clear()
         # 5. executor.execute(routing_plan, message, history, store, on_progress)
         # 6. combiner.combine(store, combiner_mode) → combined_text
         # 7. if format_hint or session_format: formatter.format(combined_text, format) → final_text
         # 8. record spend for each LLM call (router + each specialist + combiner + formatter)
         # 9. return SmartResult(...)

         def _emit_debug(self, event: str, level: int = 2) -> None: ...
         # Calls debug_manager if active — emits as [SMART] category

         def _record_spend(self, alias: str, usage: TokenUsage) -> None: ...
         # Calls spend_tracker.record() for the given alias

     Tests: tests/test_smart/test_engine.py — mock all sub-components, verify full pipeline, verify debug events, verify spend
     recording.

     ---
     Phase 8 — /smart Command Namespace

     Goal: All commands from spec section 21, following the /debug pattern exactly.

     src/anythink/smart/commands.py

     async def _smart_handler(ctx, args, state, registry) -> CommandResult:
         parts = args.strip().split(None, 1)
         sub = parts[0].lower() if parts else ""
         rest = parts[1].strip() if len(parts) > 1 else ""

         # Toggle
         if sub == "on":     ctx.smart_enabled = True;  return CR(action="smart_hud_update", ...)
         if sub == "off":    ctx.smart_enabled = False; return CR(action="smart_hud_update", ...)
         if sub == "toggle": ctx.smart_enabled = not ctx.smart_enabled; return CR(action="smart_hud_update")
         if sub in ("", "status"): return _handle_status(ctx)

         # Registry subnamespace
         if sub == "registry": return await _handle_registry(ctx, rest)

         # Combiner
         if sub == "combiner": return _handle_combiner(ctx, rest)

         # Format
         if sub == "format": return _handle_format(ctx, rest)

         # Quality threshold
         if sub == "quality": return _handle_quality(ctx, rest)

         return CommandResult(error=True, message="Usage: /smart [on|off|toggle|status|registry|combiner|format|quality]")

     def register_smart_commands(registry) -> None:
         registry.register(SlashCommand("smart", "Multi-Model Answering Engine", _smart_handler, "/smart [on|off|...]"))

     src/anythink/commands/handlers.py — add at bottom of register_commands():

     from anythink.smart.commands import register_smart_commands
     register_smart_commands(registry)

     New TUI action signals (add to _dispatch_command in ui/textual/app.py):

     "smart_hud_update"   → hud.smart_enabled = ctx.smart_enabled

     Tests: tests/test_smart/test_commands.py — test each subcommand handler, test HUD action returned.

     ---
     Phase 9 — AppContext + Config + HUD Integration

     src/anythink/app/context.py

     Add three fields to AppContext:
     smart_registry: SmartRegistry
     smart_engine: SmartEngine
     smart_enabled: bool          # per-session, starts from config.smart_default_state

     In create(), after debug_manager is constructed:
     smart_registry_path = _smart_registry_path(paths, config)
     smart_registry = SmartRegistry(smart_registry_path)
     smart_registry.load()
     # Auto-populate if file was empty/missing
     if not smart_registry.has_any_assignments():
         smart_registry.auto_populate(workflow_registry)

     smart_engine = SmartEngine(
         registry=smart_registry,
         provider_registry=provider_registry,
         model_registry=model_registry,
         debug_manager=debug_manager,
         spend_tracker=spend_tracker,
     )
     smart_enabled = config.smart_default_state

     src/anythink/ui/hud.py

     Add reactive field:
     smart_enabled: reactive[bool] = reactive(False)

     Add watcher:
     def watch_smart_enabled(self, val: bool) -> None:
         self._refresh_hud()

     Add to update_from_state():
     self.smart_enabled = ctx.smart_enabled

     Add to _line2() (after workflow indicator):
     if self.smart_enabled:
         line.append_text(sep)
         line.append("✦ Smart: ON", style=ha)   # ha = theme accent

     ---
     Phase 10 — TUI Integration

     ui/textual/app.py — message interception

     on_input_area_submitted() has 21 priority guards checked in order. MMAE inserts at priority 19.5 — after
     _pending_compare_aliases (priority 19) but before the existing V4 MMOS check (priority 20, ctx.config.mmos_enabled):

     # priority 19.5 — NEW (after compare-aliases, before MMOS)
     if self._ctx.smart_enabled and not text.startswith("/"):
         self.run_worker(self._run_smart_response(self._state, text), exclusive=False, exit_on_error=False)
         return

     If MMAE is on it handles the message; if not, MMOS handles it if enabled — they never interfere.

     New worker _run_smart_response(state, query) — mirrors _run_mmos_query structure:
     async def _run_smart_response(self, state: ChatState, query: str) -> None:
         # 1. Add user bubble to history
         # 2. Mount AIBubble(model_alias="SMART") + ThinkingWidget
         # 3. on_progress callback updates ThinkingWidget phrase
         # 4. result = await ctx.smart_engine.run(query, state.history, session_id, ...)
         # 5. bubble.finalize_with_smart(result.combined_text, result)
         # 6. Append assistant ChatMessage(combined_text) to state.history ONLY (no specialist responses)
         # 7. Record spend (engine already records per-call; worker records overall)
         # 8. Autosave session via _build_session(state)

     Add "smart_hud_update" to _dispatch_command():
     elif result.action == "smart_hud_update":
         self.query_one(HUDWidget).smart_enabled = self._ctx.smart_enabled

     Debug panel events from SmartEngine

     DebugPanel (at ui/textual/panels/debug_panel.py) has three async methods:
     - begin_request(request_id, ts) — add divider
     - append_event(label, detail) — add ▸ label  detail line
     - finalize_request(record, level) — add summary line

     MMAE streams events by calling _debug_panel.append_event("[SMART] <label>", detail) directly. The [SMART] prefix is the
     convention (not enforced by the panel — it accepts any string). Events to emit:
     - "[SMART] Router invoked", detail = router model alias
     - "[SMART] Categories detected", detail = comma-joined list + confidence (L2+)
     - "[SMART] Specialist N/M", detail = alias + category + duration
     - "[SMART] Quality gate", detail = score + PASS/FAIL
     - "[SMART] Combiner invoked", detail = alias + mode + duration
     - "[SMART] Formatter invoked" (L2+)
     - "[SMART] Total duration", detail = elapsed_s

     The SmartEngine receives debug_panel as a constructor arg (passed in from AppContext.create() after the Textual app mounts the
     panel, OR SmartEngine emits via DebugManager and the TUI worker forwards to the panel — use the same pattern as MMOS: the
     worker calls _debug_panel.append_event(...) from the progress callback, not from inside the engine class itself).

     ui/bubbles.py — MMAE footer on AIBubble

     Add method finalize_with_smart(text: str, result: SmartResult) to AIBubble:
     - Sets _smart_result: SmartResult | None
     - Calls _redraw() which now includes a specialists footer block in extra_parts

     Footer collapsed state (plain Rich Text):
     ✦ {n} specialist{"s" if n>1 else ""} · combined by {result.combiner_model}  [expand]

     For the expand/collapse: add a _smart_expanded: bool = False flag. When the footer [expand] is clicked (via mouse event on the
     Static), toggle _smart_expanded and redraw. Expanded state renders the full detail block (each specialist's sub-question,
     alias, quality score, response, combiner mode, formatter applied, total duration) as Rich Text inside extra_parts. This avoids
     requiring AIBubble to switch to a Collapsible widget — the toggle is a simple flag + redraw.

     ---
     Phase 11 — Tests

     Create tests/test_smart/ with one test file per module:

     ┌────────────────────┬────────────────────────────────────────────────────────────────────────┐
     │     Test file      │                             Key scenarios                              │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_categories.py │ All 9 categories present, TAG_TO_CATEGORY coverage                     │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_models.py     │ Dataclass construction, defaults                                       │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_registry.py   │ load/save round-trip, CRUD, auto-populate from mock MMWE registry      │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_router.py     │ JSON parse success, retry on bad schema, single vs multi output        │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_quality.py    │ Each heuristic check independently, threshold pass/fail                │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_store.py      │ add/retrieve/clear                                                     │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_executor.py   │ Normal path, quality retry, secondary alias fallback, general fallback │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_combiner.py   │ Stitch vs merge prompt construction, mock provider                     │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_detector.py   │ All 7 format keyword triggers, None on no match                        │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_formatter.py  │ Format prompt construction, mock provider                              │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_engine.py     │ Full pipeline with mocks, debug events emitted, spend recorded         │
     ├────────────────────┼────────────────────────────────────────────────────────────────────────┤
     │ test_commands.py   │ Each subcommand, action returned, error on unknown sub                 │
     └────────────────────┴────────────────────────────────────────────────────────────────────────┘

     Coverage goal: ≥ 80% on all new smart/ modules. Use xdg_dirs fixture for any file I/O. Mock providers via
     unittest.mock.AsyncMock.

     ---
     Verification

     1. ruff check src/anythink/smart/ — no lint errors
     2. black --check src/anythink/smart/ tests/test_smart/ — formatted
     3. mypy src/anythink — no new type errors
     4. bandit -r src/anythink/smart/ -c pyproject.toml — no security issues
     5. PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/test_smart/ -v — all pass
     6. PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/ --cov=src/anythink/smart --cov-fail-under=80 —
     coverage gate passes
     7. Manual: anythink → /smart on → HUD shows ✦ Smart: ON → ask a multi-domain question → see ✦ N specialists [expand] footer →
     expand to see specialist detail

     ---
     Implementation Order

     Phases 1–11 are strictly sequential. Each phase's tests must pass before starting the next. No phase requires external packages
     beyond what Anythink already imports (httpx, yaml, filelock, rich, textual).