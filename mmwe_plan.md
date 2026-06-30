MMWE Implementation Plan — Multi-Model Workflow Engine

     Context

     The user has written a detailed feature spec (anythink_mmwe_description.md) for a new standalone orchestration layer called the
     Multi-Model Workflow Engine (MMWE). It allows a user to invoke /workflow run "<task>" and have Anythink automatically decompose the task
     into a multi-stage pipeline — assigning the right model or MCP tool to each stage, running them in order (or in parallel/loop), showing
     live progress, and producing a permanent execution log.

     This is distinct from the existing V4 MMOS (optimize/) which is an auto-selection layer for single-model responses. The MMWE is a fully
     explicit, user-inspectable, multi-stage pipeline system.

     ---
     Architecture Overview

     New Folder

     src/anythink/workflow/
     ├── __init__.py
     ├── models.py           # Core data classes
     ├── registry.py         # WorkflowCapabilityRegistry (tags, fallbacks, YAML)
     ├── manifest.py         # CapabilityManifest.build(ctx) → workflow_manifest.txt
     ├── planner.py          # WorkflowPlanner — LLM plan generation + parsing
     ├── router.py           # MetaRouter — tag-based model selection
     ├── optimizer.py        # StageOutputOptimizer — context transformation between stages
     ├── engine.py           # WorkflowEngine — top-level stage-by-stage orchestration
     ├── loop.py             # LoopExecutor — LOOP stage iteration handler
     ├── log.py              # WorkflowLogger — writes structured .log files
     ├── storage.py          # WorkflowStorage — save/load named workflows as YAML
     └── commands.py         # register_workflow_commands() + all /workflow handlers
         stages/
         ├── __init__.py
         ├── mcp_call.py
         ├── llm_specialist.py
         ├── user_approval.py
         ├── condition.py
         ├── formatter.py
         └── loop.py

     New TUI Panel

     src/anythink/ui/textual/panels/workflow_panel.py  # WorkflowPanel(Widget)

     ---
     Implementation Phases

     Phase 1 — Core Data Models (workflow/models.py)

     Define all dataclasses as frozen where appropriate:

     class StageType(str, Enum):
         PLANNER = "PLANNER"
         MCP_CALL = "MCP_CALL"
         LLM_SPECIALIST = "LLM_SPECIALIST"
         USER_APPROVAL = "USER_APPROVAL"
         CONDITION = "CONDITION"
         FORMATTER = "FORMATTER"
         LOOP = "LOOP"

     @dataclass
     class Stage:
         id: str                       # "stage_1", "stage_2a", etc.
         type: StageType
         label: str                    # display label
         model_alias: str | None       # for LLM_SPECIALIST
         tool_name: str | None         # for MCP_CALL (server.tool format)
         tool_params: dict[str, Any]   # MCP tool parameters
         task_instruction: str         # LLM task prompt
         output_field: str             # named output field for downstream refs
         input_refs: list[str]         # e.g. ["stage_1.email_list"]
         expected_format: str          # for FORMATTER
         condition_expr: str           # for CONDITION
         branch_a: list[Stage]         # for CONDITION
         branch_b: list[Stage]         # for CONDITION
         loop_def: LoopDefinition | None  # for LOOP
         is_destructive: bool          # triggers USER_APPROVAL guard
         is_parallel: bool             # for parallel branch sets
         approval_message: str         # for USER_APPROVAL

     @dataclass
     class LoopDefinition:
         input_collection_ref: str     # e.g. "stage_1.email_list"
         sub_stages: list[Stage]
         accumulation_strategy: str    # "append" | "merge" | "structured_list"

     @dataclass
     class Branch:
         condition_expr: str
         branch_a: list[Stage]
         branch_b: list[Stage]
         merge_stage_id: str | None

     @dataclass
     class WorkflowPlan:
         name: str
         trigger: str                  # original user task description
         stages: list[Stage]
         models_used: list[str]
         mcp_servers_used: list[str]
         estimated_duration_s: int | None
         estimated_loop_iterations: int | None

     @dataclass
     class StageResult:
         stage_id: str
         stage_type: StageType
         output: dict[str, Any]        # named output fields
         raw_content: str
         duration_s: float
         model_alias: str | None
         tool_name: str | None
         fallback_used: bool
         fallback_chain: list[str]
         error: str | None
         skipped: bool
         user_decision: str | None     # "approved" | "skipped" | "aborted"

     @dataclass
     class WorkflowState:
         plan: WorkflowPlan
         current_stage_id: str
         completed_stages: list[StageResult]
         loop_position: int
         loop_total: int
         paused: bool
         stop_requested: bool
         accumulated_results: dict[str, Any]   # stage_id.field → value

     @dataclass
     class WorkflowLog:
         workflow_name: str
         trigger: str
         start_time: datetime
         end_time: datetime | None
         status: str                   # "completed" | "aborted" | "failed"
         stage_records: list[StageResult]
         final_output: str

     Phase 2 — Capability Registry (workflow/registry.py)

     WorkflowCapabilityRegistry — separate from the MMOS ModelCapabilityRegistry. Stores per-alias workflow tags and fallback chains. Persisted
     in $XDG_CONFIG_HOME/anythink/workflow_capabilities.yaml.

     class WorkflowCapabilityRegistry:
         def __init__(self, path: Path) -> None
         def get_tags(self, alias: str) -> list[str]
         def set_tags(self, alias: str, tags: list[str]) -> None
         def add_tag(self, alias: str, tag: str) -> None
         def remove_tag(self, alias, tag) -> None
         def set_fallback(self, alias: str, fallback_alias: str) -> None
         def get_fallback_chain(self, alias: str) -> list[str]
         def all_aliases(self) -> list[dict]    # [{alias, tags, fallback}]
         def infer_tags(self, model_id: str) -> list[str]   # from known model families
         def save(self) -> None

     Tag inference table (bundled): mistral:* → ["summarization","extraction"], deepseek-coder:* → ["code","code-review"], llama3*:* →
     ["planning","reasoning","summarization"], gemini* → ["summarization","reasoning","multimodal","long-context"], gpt-4* →
     ["reasoning","code","planning","analysis"].

     Phase 3 — Storage + Logger (workflow/storage.py, workflow/log.py)

     WorkflowStorage:
     class WorkflowStorage:
         def __init__(self, workflows_dir: Path) -> None
         def save(self, name: str, plan: WorkflowPlan) -> None
         def load(self, name: str) -> WorkflowPlan
         def list_names(self) -> list[str]
         def delete(self, name: str) -> None
         def rename(self, old: str, new: str) -> None
         def backup(self, name: str) -> None   # creates <name>.yaml.bak

     Named workflows stored at $XDG_CONFIG_HOME/anythink/workflows/<name>.yaml.

     WorkflowLogger:
     class WorkflowLogger:
         def __init__(self, log_dir: Path) -> None
         def begin(self, plan: WorkflowPlan) -> WorkflowLog
         def record_stage(self, log: WorkflowLog, result: StageResult) -> None
         def finalize(self, log: WorkflowLog, status: str, final_output: str) -> Path

     Log files at $XDG_DATA_HOME/anythink/workflow_logs/YYYY-MM-DD_HHMMSS_<name>.log.

     Phase 4 — Capability Manifest (workflow/manifest.py)

     CapabilityManifest reads live state from ctx and serializes to workflow_manifest.txt. Regenerated at startup and on /workflow manifest
     refresh.

     class CapabilityManifest:
         def __init__(self, manifest_path: Path) -> None
         def build(self, ctx: AppContext) -> str        # returns the manifest text
         def refresh(self, ctx: AppContext) -> None     # write to manifest_path
         def load(self) -> str                          # read current file

     Sections written:
     1. [LOCAL MODELS] — from ctx.model_registry where provider is Ollama/LM Studio
     2. [CLOUD MODELS] — remaining aliases with cloud providers
     3. [MCP TOOLS] — from ctx.mcp_manager.list_tools() with DESTRUCTIVE markers
     4. [ANYTHINK CAPABILITIES] — hardcoded: rag_search, web_search, session_history, etc.
     5. [STAGE TYPES] — hardcoded from StageType enum
     6. [SAVED WORKFLOWS] — from ctx.workflow_storage.list_names()

     Phase 5 — Planner (workflow/planner.py)

     WorkflowPlanner assembles a structured system prompt (role definition + manifest + output schema) and calls the designated planner model
     LLM. Parses the response into a WorkflowPlan.

     class WorkflowPlanner:
         def __init__(self, manifest: CapabilityManifest, ctx: AppContext) -> None

         async def plan(
             self,
             task: str,
             planner_alias: str,
         ) -> WorkflowPlan | ClarificationRequest

         async def plan_with_answers(
             self,
             task: str,
             clarification_answers: str,
             planner_alias: str,
         ) -> WorkflowPlan

         def _build_system_prompt(self) -> str
         def _parse_plan(self, llm_output: str) -> WorkflowPlan

     The planner model is invoked via ctx.provider_registry using the model alias from config (workflow_planner_model field). The output schema
     instructs the LLM to respond in JSON with the WorkflowPlan structure. Parser uses json.loads() on the LLM response (with fallback parsing
     for partial/wrapped JSON).

     ClarificationRequest is a simple dataclass with questions: list[str].

     Phase 6 — Router + Optimizer (workflow/router.py, workflow/optimizer.py)

     MetaRouter:
     class MetaRouter:
         def __init__(self, registry: WorkflowCapabilityRegistry, ctx: AppContext) -> None
         def select_model(
             self,
             stage: Stage,
             required_tags: list[str],
             estimated_input_tokens: int,
         ) -> str | None           # returns alias or None if no match
         def select_with_fallback(self, stage: Stage) -> list[str]  # ordered candidates

     Selection logic follows spec Section 7.2 exactly: tag match → context window filter → prefer local → usage recency → context window
     tie-break.

     StageOutputOptimizer:
     class StageOutputOptimizer:
         def transform(
             self,
             output: StageResult,
             next_stage: Stage,
         ) -> dict[str, Any]

     Prepends task instruction for LLM stages, extracts fields for MCP stages, passes format hints for FORMATTER stages, splits collection for
     LOOP stages.

     Phase 7 — Stage Executors (workflow/stages/)

     Each executor is an async function with signature:
     async def execute(
         stage: Stage,
         state: WorkflowState,
         ctx: AppContext,
         callbacks: WorkflowCallbacks,
     ) -> StageResult

     WorkflowCallbacks is a dataclass of async callables the engine provides:
     @dataclass
     class WorkflowCallbacks:
         on_stage_start: Callable[[Stage], Awaitable[None]]
         on_stage_complete: Callable[[Stage, StageResult], Awaitable[None]]
         on_approval_needed: Callable[[str], Awaitable[str]]  # returns "approve"|"skip"|"abort"
         on_loop_progress: Callable[[int, int, StageResult], Awaitable[None]]
         on_model_unavailable: Callable[[Stage, list[str]], Awaitable[str]]  # returns alias

     mcp_call.py: Calls ctx.mcp_manager.call_tool(stage.tool_name, resolved_params). Resolves params from state.accumulated_results. Maps
     MCPCallResult to StageResult.

     llm_specialist.py: Gets provider alias from stage.model_alias. Invokes stream_chat(). Records spend via ctx.spend_tracker.record().
     Handles fallback chain from ctx.workflow_registry.

     user_approval.py: Calls callbacks.on_approval_needed(stage.approval_message). Returns immediately with user_decision = "approved" |
     "skipped" | "aborted".

     condition.py: Evaluates stage.condition_expr against state.accumulated_results using a safe eval() sandbox (ast.literal_eval-based, no
     builtins). Returns a StageResult with output["branch"] = "a" | "b".

     formatter.py: Pure Python transformation — no LLM, no MCP. Converts input according to stage.expected_format. Supports: markdown,
     plain_text, json, csv, html, numbered_list.

     loop.py (stage wrapper): Calls LoopExecutor.run(). Returns accumulated StageResult.

     Phase 8 — Engine + LoopExecutor (workflow/engine.py, workflow/loop.py)

     WorkflowEngine:
     class WorkflowEngine:
         def __init__(
             self,
             planner: WorkflowPlanner,
             router: MetaRouter,
             optimizer: StageOutputOptimizer,
             loop_executor: LoopExecutor,
             logger: WorkflowLogger,
             storage: WorkflowStorage,
         ) -> None

         async def run(
             self,
             plan: WorkflowPlan,
             ctx: AppContext,
             callbacks: WorkflowCallbacks,
         ) -> WorkflowLog

         async def dry_run(self, plan: WorkflowPlan, ctx: AppContext) -> str

     Execution loop: iterate plan.stages, resolve stage type → dispatch to executor, handle StageResult.user_decision == "aborted" by stopping,
     handle parallel branches via asyncio.gather, handle LOOP via LoopExecutor. After each stage, call optimizer.transform() and store result
     in state.accumulated_results[stage.output_field].

     LoopExecutor:
     class LoopExecutor:
         async def run(
             self,
             loop_def: LoopDefinition,
             collection: list[Any],
             state: WorkflowState,
             ctx: AppContext,
             callbacks: WorkflowCallbacks,
         ) -> StageResult

     Sequential iteration. Supports pause (via state.paused), skip (via callback signal), stop-early (via state.stop_requested). Accumulates
     results.

     Phase 9 — AppConfig + AppContext Integration

     config/schema.py — Add new field block after Windows MCP fields:
     # --- Workflow (MMWE) ---
     workflow_planner_model: str = ""           # model alias for planner; "" = auto-select
     workflow_log_dir: str = ""                 # override log dir; "" = XDG default
     workflow_autonomy_mode: str = "confirm"    # "confirm" | "auto" (future)

     app/context.py — Add fields to AppContext:
     workflow_registry: WorkflowCapabilityRegistry   # new field
     workflow_storage: WorkflowStorage               # new field
     workflow_engine: WorkflowEngine                 # new field

     AppContext.create() — Wire up after ScheduleManager instantiation:
     workflow_registry = WorkflowCapabilityRegistry(
         path=resolved.config_dir / "workflow_capabilities.yaml"
     )
     workflow_storage = WorkflowStorage(
         workflows_dir=resolved.config_dir / "workflows"
     )
     workflow_manifest = CapabilityManifest(
         manifest_path=resolved.config_dir / "workflow_manifest.txt"
     )
     workflow_planner = WorkflowPlanner(manifest=workflow_manifest, ctx=...)
     workflow_router = MetaRouter(registry=workflow_registry, ctx=...)
     workflow_logger = WorkflowLogger(
         log_dir=resolved.data_dir / "workflow_logs"
     )
     workflow_engine = WorkflowEngine(
         planner=workflow_planner,
         router=workflow_router,
         optimizer=StageOutputOptimizer(),
         loop_executor=LoopExecutor(),
         logger=workflow_logger,
         storage=workflow_storage,
     )

     Note: workflow_manifest.refresh(ctx) is called at the end of create() after all other managers are initialized.

     Phase 10 — Command System (workflow/commands.py)

     def register_workflow_commands(registry: CommandRegistry) -> None:
         registry.register(SlashCommand("workflow", "Multi-model workflow engine", _workflow, "/workflow <subcommand>"))

     The _workflow handler routes on the first word of args:

     ┌────────────────────────────┬──────────────────────┬──────────────────────────────────────────┐
     │         Subcommand         │       Handler        │                  Action                  │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ run "<task>" or run <name> │ _wf_run              │ "workflow_run_request"                   │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ run ... --dry-run          │ _wf_dry_run          │ "workflow_dry_run_request"               │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ new                        │ _wf_new              │ "workflow_new_wizard"                    │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ list                       │ _wf_list             │ Returns formatted message                │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ show <name>                │ _wf_show             │ Returns formatted message                │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ edit <name>                │ _wf_edit             │ "workflow_edit_request"                  │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ delete <name>              │ _wf_delete           │ Returns formatted message (with confirm) │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ rename <old> <new>         │ _wf_rename           │ Returns formatted message                │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ stop                       │ _wf_stop             │ "workflow_stop"                          │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ pause                      │ _wf_pause            │ "workflow_pause"                         │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ resume                     │ _wf_resume           │ "workflow_resume"                        │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ status                     │ _wf_status           │ Returns formatted message                │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ logs                       │ _wf_logs             │ Returns formatted message                │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ logs show <name>           │ _wf_logs_show        │ "open_file_in_editor"                    │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ logs last                  │ _wf_logs_last        │ "open_file_in_editor"                    │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ manifest show              │ _wf_manifest_show    │ Returns manifest text                    │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ manifest refresh           │ _wf_manifest_refresh │ Calls ctx.workflow_manifest.refresh(ctx) │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ manifest path              │ _wf_manifest_path    │ Returns path                             │
     ├────────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
     │ registry                   │ _wf_registry_*       │ Various tag CRUD operations              │
     └────────────────────────────┴──────────────────────┴──────────────────────────────────────────┘

     Register in commands/handlers.py via delegate:
     from anythink.workflow.commands import register_workflow_commands
     register_workflow_commands(registry)

     No new pyproject.toml entry needed — uses the existing delegate pattern.

     Phase 11 — TUI Integration

     workflow/panel.py (WorkflowPanel(Widget)):

     Follows DebugPanel pattern — display: none by default, toggled from app.
     - compose(): header Static, VerticalScroll stage list area, HintBar-style control strip
     - update_stage(stage, status): update stage row icon (◐/✓/✕/⏸/─)
     - update_loop_progress(current, total, last_result): update loop sub-row
     - set_active(plan): populate with plan stages, set display = True
     - clear(): reset content, set display = False

     ui/textual/app.py changes:

     1. Add WorkflowPanel to compose() (hidden, right-side or overlay position)
     2. Add new state flags:
       - _pending_workflow_approval: dict | None — waiting for approve/skip/abort response
       - _running_workflow: WorkflowState | None
     3. Handle in on_input_area_submitted() before normal chat
     4. Add _run_workflow() worker:
     async def _run_workflow(self, plan: WorkflowPlan) -> None:
         # Creates WorkflowCallbacks that use self.call_from_thread() to update WorkflowPanel
         # Uses asyncio.Event for approval gates (sets _pending_workflow_approval, waits on event)
         # Uses SystemBubble.set_message() for live stage results in conversation
     5. Handle actions in _dispatch_command():
       - "workflow_run_request" → planning step → show plan panel → _run_workflow worker
       - "workflow_stop" → set state.stop_requested = True
       - "workflow_pause" → set state.paused = True
       - "workflow_resume" → clear state.paused

     ui/hud.py — Add workflow_active: reactive[bool] = reactive(False) + watcher.

     Plan review display: After planning completes, render a SystemBubble with the full plan text (Rich-formatted to match the spec's box
     display). Show [▶ Run] [🔬 Dry Run] [✕ Cancel] in the control bar. Use _pending_workflow_approval to gate the next user input.

     Phase 12 — Tests

     New test files following existing conventions:
     - tests/test_workflow_models.py — dataclass construction, serialization
     - tests/test_workflow_registry.py — tag CRUD, fallback chain, YAML round-trip (use xdg_dirs)
     - tests/test_workflow_storage.py — save/load/list/rename/backup (use xdg_dirs)
     - tests/test_workflow_manifest.py — manifest build with mock ctx
     - tests/test_workflow_planner.py — plan parsing with sample LLM outputs
     - tests/test_workflow_router.py — tag matching, fallback chain, tie-break ordering
     - tests/test_workflow_optimizer.py — output transformation for each stage type
     - tests/test_workflow_stages.py — each stage executor with mocked ctx
     - tests/test_workflow_engine.py — full plan execution with mocked executors
     - tests/test_workflow_commands.py — command dispatch with mock ctx

     Factory helpers:
     def make_stage(type=StageType.MCP_CALL, **kwargs) -> Stage: ...
     def make_plan(**kwargs) -> WorkflowPlan: ...
     def make_state(**kwargs) -> WorkflowState: ...

     ---
     Key Reuse Points

     ┌──────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────┐
     │                        Existing item                         │                    How MMWE uses it                    │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ ctx.mcp_manager.call_tool() (mcp/manager.py)                 │ mcp_call.py executor                                   │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ ctx.provider_registry + BaseProvider.stream_chat()           │ llm_specialist.py executor                             │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ ctx.spend_tracker.record() (spend/tracker.py)                │ After each LLM_SPECIALIST stage                        │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ ctx.debug_manager.is_active() (debug/manager.py)             │ Guard for [WORKFLOW] debug events                      │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ SystemBubble.set_message() (ui/bubbles.py)                   │ Live stage result display (same pattern as RAG ingest) │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ ConversationView.add_bubble() (ui/textual/conversation.py)   │ Add per-stage result bubbles                           │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ DebugPanel pattern (ui/textual/panels/debug_panel.py)        │ Template for WorkflowPanel                             │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ ThinkingWidget timer pattern (ui/textual/thinking_widget.py) │ Template for loop progress animation                   │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ run_worker() + call_from_thread() (ui/textual/app.py)        │ _run_workflow() background worker                      │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ _pending_* flag pattern (ui/textual/app.py)                  │ _pending_workflow_approval                             │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ AppConfig frozen dataclass pattern (config/schema.py)        │ New workflow fields in versioned block                 │
     ├──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
     │ AppContext.create() wire-up pattern (app/context.py)         │ Add workflow managers after ScheduleManager            │
     └──────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────┘

     ---
     Verification

     1. Run all four CI gates: ruff check src/, black --check src/ tests/, mypy src/anythink, bandit -r src/anythink -c pyproject.toml
     2. Run full test suite: PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/ -v
     3. Manual smoke test:
       - anythink → /workflow list → verify empty list
       - /workflow registry list → verify empty/default output
       - /workflow run "Read a file and summarize it" → verify planner produces a plan
       - At plan review, press Cancel → verify workflow aborted cleanly
       - Run a 2-stage workflow (MCP_CALL + LLM_SPECIALIST) end-to-end
       - /workflow logs last → verify log file created and accessible
       - /workflow manifest show → verify manifest text generated

     ---
     Implementation Order Summary

     ┌─────┬─────────────────────────────────────────────┬───────────────────────────────────┐
     │  #  │                   Module                    │          Key deliverable          │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 1   │ workflow/models.py                          │ All dataclasses                   │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 2   │ workflow/registry.py                        │ Tag CRUD + YAML persistence       │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 3   │ workflow/storage.py                         │ Named workflow save/load          │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 4   │ workflow/log.py                             │ Execution log writer              │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 5   │ workflow/manifest.py                        │ Capability manifest builder       │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 6   │ workflow/planner.py                         │ LLM plan generation + JSON parser │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 7   │ workflow/router.py                          │ Tag-based model selection         │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 8   │ workflow/optimizer.py                       │ Stage output transformation       │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 9   │ workflow/stages/*.py                        │ All 6 stage executors             │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 10  │ workflow/engine.py + loop.py                │ Main orchestration loop           │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 11  │ config/schema.py + app/context.py           │ Config fields + DI wiring         │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 12  │ workflow/commands.py + commands/handlers.py │ /workflow namespace               │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 13  │ ui/textual/panels/workflow_panel.py         │ Live execution panel widget       │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 14  │ ui/textual/app.py + ui/hud.py               │ TUI worker + dispatch + HUD       │
     ├─────┼─────────────────────────────────────────────┼───────────────────────────────────┤
     │ 15  │ tests/test_workflow_*.py                    │ Test coverage ≥ 80%               │
     └─────┴─────────────────────────────────────────────┴───────────────────────────────────┘
