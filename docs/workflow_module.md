

  What is MMWE?

  The Multi-Model Workflow Engine (MMWE) is Anythink's orchestration system for turning a
  natural-language task into a structured, multi-step AI pipeline. Instead of sending a single
  prompt to one model, MMWE lets an LLM decompose the task into discrete stages — each stage can
  call a different model, invoke MCP tools, loop over collections, apply conditional branching,
  request user approval, or reformat data — and then executes all those stages in sequence (or in
  parallel).

  The entire subsystem lives under src/anythink/workflow/. It is self-contained and interacts with
  the rest of the app only through AppContext and well-defined callbacks.

  ---
  Architecture at a Glance

  User types: /workflow run "send a weekly digest email"
                  │
                  ▼
       commands.py  ──────────────────► action signal ──► TUI (app.py)
                                                                │
                                                                ▼
                                                      WorkflowEngine.plan_task()
                                                                │
                                                       WorkflowPlanner.plan()
                                                                │  LLM call
                                                      (reads CapabilityManifest)
                                                                │
                                                WorkflowPlan (stages list)
                                                                │
                                                      WorkflowEngine.run()
                                                           │
                  ┌────────────────────────────────────────┤
                  │  for each Stage:                       │
                  │   _dispatch_stage()                    │
                  │        │                              │
                  │   ┌────┴──────────────────────────┐  │
                  │   │ LLM_SPECIALIST  → llm_specialist.py │
                  │   │ MCP_CALL        → mcp_call.py      │
                  │   │ CONDITION       → condition.py      │
                  │   │ FORMATTER       → formatter.py      │
                  │   │ USER_APPROVAL   → user_approval.py  │
                  │   │ LOOP            → loop.py ──► LoopExecutor │
                  │   └────────────────────────────────────┘
                  │              │ StageResult
                  │   WorkflowState.store_result()
                  │   WorkflowLogger.record_stage()
                  │   WorkflowCallbacks.on_stage_complete()
                  └────────────────────────────────────────┘
                                  │
                      WorkflowLogger.finalize()  → .log file
                      WorkflowLog returned to TUI

  ---
  File-by-File Reference

  __init__.py

  A single-line docstring identifying the package as "Multi-Model Workflow Engine (MMWE) —
  standalone orchestration layer." No code — just marks the directory as a Python package.

  ---
  models.py — The Data Layer

  Everything in the MMWE is typed here. Every other file imports from this module.

  Enumerations

  ┌──────────────────────┬───────────────────────────────────────────┬─────────────────────────┐
  │         Enum         │                  Values                   │         Purpose         │
  ├──────────────────────┼───────────────────────────────────────────┼─────────────────────────┤
  │ StageType            │ PLANNER, MCP_CALL, LLM_SPECIALIST,        │ The kind of work a      │
  │                      │ USER_APPROVAL, CONDITION, FORMATTER, LOOP │ stage does              │
  ├──────────────────────┼───────────────────────────────────────────┼─────────────────────────┤
  │ AccumulationStrategy │ APPEND, MERGE, STRUCTURED_LIST            │ How loop iterations     │
  │                      │                                           │ collect results         │
  ├──────────────────────┼───────────────────────────────────────────┼─────────────────────────┤
  │ WorkflowStatus       │ PENDING, RUNNING, PAUSED, COMPLETED,      │ Lifecycle state of a    │
  │                      │ ABORTED, FAILED                           │ running workflow        │
  ├──────────────────────┼───────────────────────────────────────────┼─────────────────────────┤
  │ UserDecision         │ APPROVED, SKIPPED, ABORTED                │ What the user decided   │
  │                      │                                           │ at an approval gate     │
  └──────────────────────┴───────────────────────────────────────────┴─────────────────────────┘

  Key Dataclasses

  LoopDefinition — configuration for a LOOP stage. Holds a input_collection_ref (a dot-path like
  "stage_1.email_list" pointing to an upstream list), a sub_stages list (the stages to run per
  item), and an accumulation_strategy.

  Stage — a single pipeline step. Fields are type-specific: model_alias + task_instruction for
  LLM_SPECIALIST; tool_name + tool_params for MCP_CALL; condition_expr + branch_a + branch_b for
  CONDITION; loop_def for LOOP; approval_message for USER_APPROVAL. Cross-cutting flags:
  is_destructive (always triggers auto-approval guard), is_parallel (runs concurrently with
  adjacent parallel stages). Data-flow fields: output_field (names this stage's output), input_refs
  (dot-path references to upstream outputs).

  WorkflowPlan — the complete parsed plan: a name, the original trigger string, the stages list,
  models_used, mcp_servers_used, and optional timing estimates.

  StageResult — the output of executing one stage. Contains named output fields (available to
  downstream stages), raw_content (full text), timing, which model/tool was used, whether a
  fallback was triggered, and any error.

  WorkflowState — mutable runtime state for a running workflow. Holds the current plan, status,
  current_stage_id, all completed_stages, and the central accumulated_results dict (keyed as
  "stage_id.field_name"). Provides resolve_ref(ref) for dot-path lookups and store_result(result)
  which indexes outputs into accumulated_results.

  WorkflowLog — the complete record written to disk after every execution: all stage records, loop
  iterations, final output, models/MCP servers used.

  ClarificationRequest — returned by the planner instead of a plan when the task is ambiguous.
  Contains a list of questions and a round counter (after round 2, the planner produces a partial
  plan rather than asking again).

  WorkflowCallbacks — a dataclass of async function references that the engine calls to communicate
  with the TUI or CLI layer. The four callbacks are: on_stage_start, on_stage_complete,
  on_approval_needed (returns a decision string), on_loop_progress.

  All dataclasses implement to_dict() / from_dict() for JSON round-trips. Stage.from_dict() and
  LoopDefinition.from_dict() are recursive, handling nested branch_a, branch_b, and sub_stages.

  Project connection: Every other file in this package imports from models.py. AppContext stores
  WorkflowPlan instances via WorkflowStorage. The TUI in app.py receives WorkflowLog at the end of
  a run and reads WorkflowState for live status.

  ---
  engine.py — WorkflowEngine

  The top-level orchestrator. It owns the full execution lifecycle of a WorkflowPlan.

  Constructor takes injected subsystems: WorkflowPlanner, MetaRouter, StageOutputOptimizer,
  LoopExecutor, WorkflowLogger, and WorkflowStorage.

  run(plan, ctx, callbacks) → WorkflowLog
  The main entry point. Creates a WorkflowState, calls _execute_stages(), catches unexpected
  exceptions to log as FAILED, and calls WorkflowLogger.finalize() to write the log file.

  plan_task(task, planner_alias) → WorkflowPlan | ClarificationRequest
  Delegates to WorkflowPlanner.plan(). Called by the TUI before presenting a plan to the user.

  dry_run(plan, ctx) → str
  Produces a human-readable summary of what the plan would do, without executing any stage. Used by
  /workflow run --dry-run.

  _execute_stages(stages, ...)
  The core dispatch loop. It processes stages one at a time unless consecutive stages have
  is_parallel=True, in which case they are gathered into a group and run via asyncio.gather. After
  each CONDITION stage, it recursively calls _execute_stages on the appropriate branch (branch_a or
  branch_b). Any stage returning UserDecision.ABORTED immediately sets state.stop_requested =
  True.

  _run_one_stage(stage, ...)
  Fires callbacks.on_stage_start, then — if the stage has is_destructive=True — auto-injects a
  USER_APPROVAL guard stage before the real stage runs. Delegates the actual work to
  _dispatch_stage() from stages/__init__.py.

  Project connection: AppContext constructs one WorkflowEngine at startup and stores it as
  ctx.workflow_engine. The TUI's _dispatch_command calls ctx.workflow_engine.run() and
  ctx.workflow_engine.plan_task() inside background workers.

  ---
  planner.py — WorkflowPlanner

  Converts a free-text task description into a WorkflowPlan by calling an LLM with a carefully
  constructed system prompt.

  System prompt is built from three parts: _ROLE_DEFINITION (rules: only use listed models/tools,
  insert USER_APPROVAL before destructive calls, use LOOP for collections, ask for clarification
  when ambiguous), the capability manifest text loaded from CapabilityManifest.load(), and
  _OUTPUT_SCHEMA (exact JSON format the model must output — either a clarification object or a full
  plan).

  plan(task, planner_alias) → WorkflowPlan | ClarificationRequest
  Selects the planner model (first alias with the planning or reasoning tag, or the first alias
  overall), calls _call_planner(), and parses the response.

  plan_with_answers(task, clarification_answers, planner_alias)
  Used for the second round of planning after the user answered clarification questions. Appends
  the answers to the user message.

  _call_planner() instantiates a provider from the provider registry, constructs a two-message
  conversation (system + user), streams the response, and passes the concatenated chunks to
  _parse_response().

  _parse_response(raw) uses _extract_json() to strip markdown fences or locate the outermost {...}
  block, then calls json.loads() and WorkflowPlan.from_dict(). Returns a ClarificationRequest if
  clarification_needed is true.

  parse_plan_json(json_text) → WorkflowPlan (static)
  Parses a raw JSON string directly into a WorkflowPlan without an LLM call. Used when loading a
  saved plan that was stored as JSON.

  Project connections:
  - Reads CapabilityManifest.load() to give the LLM context.
  - Calls ProviderRegistry.instantiate() and KeyManager.get_key() — the same pattern used by normal
  chat.
  - Uses GenerationParams(temperature=0.2) — low temperature for deterministic structured output.
  - Raises WorkflowPlanError (from exceptions.py) on parse failure.

  ---
  router.py — MetaRouter

  Selects the best model alias for a workflow stage based on capability tags.

  Selection priority (spec §7.2):
  1. Must carry ALL required tags (exact match)
  2. Context window must be ≥ estimated input tokens
  3. Local providers (Ollama, LM Studio, LlamaCpp, etc.) preferred over cloud
  4. Largest context window as final tie-break

  When no alias has all required tags, the router relaxes to a partial match (most tags matched).
  When nothing matches, returns None.

  select_model(required_tags, estimated_input_tokens) → str | None
  Returns the single best alias name.

  select_with_fallback(alias, required_tags, estimated_input_tokens) → list[str]
  Returns the full ordered candidate list: the specified alias first, then its fallback chain from
  WorkflowCapabilityRegistry, then any remaining aliases as last-resort options. Used by
  LLM_SPECIALIST stages to build their retry chain.

  rank_candidates(required_tags, estimated_input_tokens) → list[dict]
  Returns all candidates with their score, exact-match flag, and locality flag. Used by /workflow
  registry commands for display.

  Scoring (_score()): tag fraction (0–1) + local bonus (0.5) + context window bonus (0–0.1). Tag
  fraction dominates, so a local model with fewer tags can still beat a cloud model with all tags
  in edge cases.

  Project connections:
  - Reads from WorkflowCapabilityRegistry (for tags and fallback chains) and ModelRegistry (for
  context window and provider info).
  - MetaRouter is constructed in AppContext and passed to WorkflowEngine. It is not currently
  called directly by stages — llm_specialist.py builds its own candidate chain using
  WorkflowCapabilityRegistry.get_fallback_chain() directly. The router is available to the engine
  for future use.

  ---
  manifest.py — CapabilityManifest

  Builds the plain-text document that the WorkflowPlanner model reads as part of its system prompt.
  It tells the planner what models exist, what MCP tools are available, and what stage types it
  can use.

  build(model_registry, mcp_manager, workflow_registry, workflow_storage) → str
  Generates five sections (without writing to disk):
  1. [LOCAL MODELS] / [CLOUD MODELS] — all configured aliases with their model ID, provider,
  context window, capability tags, and fallback chain.
  2. [MCP TOOLS] — all tools from all running MCP servers, grouped by server. Each tool shows its
  description and parameter schema. Destructive tools (matching _DESTRUCTIVE_TOOL_FRAGMENTS) are
  flagged with DESTRUCTIVE: requires user confirmation.
  3. [ANYTHINK CAPABILITIES] — built-in Anythink features the planner can reference: RAG search,
  web search, session history, notifications, clipboard, screenshot.
  4. [STAGE TYPES] — short description of all seven stage types.
  5. [SAVED WORKFLOWS] — names and trigger summaries of all previously saved workflows (so the
  planner can reuse them).

  refresh() calls build() and writes the result to workflow_manifest.txt in the config directory.
  Called once at startup (in AppContext) and on demand via /workflow manifest refresh.

  load() → str reads the current manifest from disk. Returns an empty string if the file doesn't
  exist yet.

  _is_destructive(tool_name) scans the tool name against a hardcoded fragment list (write_file,
  delete_file, send_email, kill_process, etc.). Used to annotate MCP tools in the manifest.

  Project connections:
  - Reads ModelRegistry.list_all(), MCPManager.list_tools(), WorkflowCapabilityRegistry.get_tags()
  and get_fallback_chain(), WorkflowStorage.list_summaries().
  - Written to $XDG_CONFIG_HOME/anythink/workflow_manifest.txt.
  - Consumed only by WorkflowPlanner._call_planner().

  ---
  registry.py — WorkflowCapabilityRegistry

  Stores per-alias workflow capability tags and fallback chains, backed by
  workflow_capabilities.yaml in the user config directory.

  Tag inference — if a user never sets tags for an alias, the registry infers them from the model
  name using _TAG_INFERENCE_TABLE (glob patterns: "claude*" → ["reasoning", "writing", "analysis",
  "long-context"], "gpt-4*" → ["reasoning", "code", "planning", "analysis"], etc.). Explicit user
  tags override inferred tags entirely.

  Predefined tag set (PREDEFINED_TAGS): planning, reasoning, summarization, extraction, code,
  code-review, classification, translation, writing, analysis, long-context, multimodal, fast,
  high-quality.

  Tag management: get_tags(alias), set_tags(alias, tags), add_tag(alias, tag), remove_tag(alias,
  tag). All write operations call save() immediately.

  Fallback chain: set_fallback(alias, fallback_alias), get_fallback_chain(alias). The chain
  traversal detects cycles and caps at 10 hops.

  Listing: all_aliases() returns {alias, tags, fallback, inferred} dicts. aliases_with_tag(tag)
  returns all names carrying a given tag.

  Lazy loading — _entries is None on init. The first access calls _load() which reads and parses
  the YAML file. Subsequent calls use the in-memory cache.

  Project connections:
  - Consumed by CapabilityManifest (to generate the models section), MetaRouter (tag-based
  scoring), llm_specialist.py (fallback chains), and SmartRegistry.auto_populate() (MMAE seeds from
  MMWE tags).
  - Managed via /workflow registry commands.
  - Stored at $XDG_CONFIG_HOME/anythink/workflow_capabilities.yaml.

  ---
  storage.py — WorkflowStorage

  CRUD persistence for named WorkflowPlan objects. Each plan is stored as a YAML file at
  <config_dir>/workflows/<name>.yaml. Backup files use .yaml.bak.

  save(name, plan) — creates or overwrites. Calls plan.to_dict() then yaml.dump.

  load(name) → WorkflowPlan — reads and calls WorkflowPlan.from_dict(). Raises WorkflowError if the
  file is missing or corrupt.

  delete(name) — removes the YAML and its .bak file.

  rename(old_name, new_name) — loads the old plan, updates its name field, saves under the new
  name, then removes the old file.

  backup(name) — writes a .bak copy. Called before edits.

  list_names() → list[str] — alphabetical list of workflow names (excludes .bak files).

  list_summaries() → list[dict] — lightweight {name, trigger, stage_count, models_used} for each
  workflow. Corrupt files are silently skipped. Used by
  CapabilityManifest._section_saved_workflows().

  _slugify(name) — converts workflow names to filesystem-safe filenames (lowercase, hyphens, max 80
  chars).

  Project connections:
  - Stored at $XDG_CONFIG_HOME/anythink/workflows/.
  - Used by WorkflowEngine (passed to WorkflowLogger for log output), CapabilityManifest, and all
  /workflow subcommands (list, show, edit, delete, rename).
  - Available directly on AppContext as ctx.workflow_storage.

  ---
  log.py — WorkflowLogger

  Writes structured plain-text execution logs to disk.

  begin(plan) → WorkflowLog — allocates a new WorkflowLog with the current UTC time.

  record_stage(log, result) — appends a StageResult and updates the models_used /
  mcp_servers_called lists on the log.

  record_loop_iteration(...) — appends a LoopIterationRecord with item ID, index, duration, and
  summary.

  finalize(log, status, final_output) → Path — sets end_time, writes the rendered log to
  <log_dir>/YYYY-MM-DD_HHMMSS_<workflow-name>.log, and returns the file path.

  _render(log) — produces a human-readable log with a header block, per-stage blocks (model/tool
  used, duration, decision, output), a loop summary table (if applicable), an errors section, and a
  final output block.

  list_logs() / latest_log() — used by /workflow logs commands to show or open log files.

  Project connections:
  - Log files written to $XDG_DATA_HOME/anythink/workflow_logs/ (configurable via
  AppConfig.workflow_log_dir).
  - WorkflowEngine calls logger.begin(), logger.record_stage(), and logger.finalize() during every
  run.
  - /workflow logs, /workflow logs last, and /workflow logs show <n> commands access
  ctx.workflow_engine._logger.

  ---
  loop.py — LoopExecutor

  Iterates a sub-stage pipeline over every item in a collection. Called by stages/loop.py.

  run(loop_def, collection, state, ctx, callbacks, stage_runner) → StageResult

  For each item in collection:
  1. Respects state.stop_requested and spins on state.paused.
  2. Writes loop.current_item and loop.current_index into state.accumulated_results so sub-stages
  can reference the current item.
  3. Runs all loop_def.sub_stages in order through stage_runner (which is _dispatch_stage). Stops
  the iteration early if a sub-stage returns an error.
  4. Calls _accumulate() to add the iteration's output to the running list.
  5. Calls callbacks.on_loop_progress(current, total, last_result).

  Returns a single StageResult with output={"results": [...], "final": <serialised>}.

  Accumulation strategies:
  - APPEND — each iteration's output is appended as-is (default).
  - MERGE — dict outputs are merged into a single dict (last value wins on conflict).
  - STRUCTURED_LIST — string outputs are JSON-parsed first; useful for structured per-item
  responses.

  Project connections:
  - Instantiated by AppContext and injected into WorkflowEngine.
  - Called indirectly via stages/loop.py.
  - The stage_runner callback it receives is _dispatch_stage, creating a recursive execution
  context (loop sub-stages can themselves be any stage type, including nested loops).

  ---
  optimizer.py — StageOutputOptimizer

  Transforms the output of a completed stage into the optimal input context for the next stage.
  Pure Python — no I/O, no external calls.

  transform(result, next_stage, state) → dict
  Always returns a dict with at least "content", "output", and "refs". Dispatches to one of six
  per-type handlers:

  - _for_llm — prepends task_instruction and a format hint to the content. Uses resolved input_refs
  as the primary text payload.
  - _for_mcp — resolves {{stage_N.field}} template placeholders in tool_params from
  state.accumulated_results.
  - _for_formatter — detects the incoming content type (JSON, CSV, markdown, prose) and passes it
  alongside the target format.
  - _for_loop — resolves the input_collection_ref to get the actual list and attaches it as
  "collection".
  - _for_approval — attaches the approval_message and a summary of the last three completed stages
  for context.
  - _for_condition — attaches the condition_expr and a copy of all accumulated_results.

  _primary_text(ctx) — picks the best single-text payload: resolved refs first, then raw_content,
  then a JSON-serialised output dict.

  Project connections:
  - Injected into WorkflowEngine but not yet called inside the engine's execution path. The
  optimizer is available for future use to pre-process stage inputs before dispatch.

  ---
  commands.py — /workflow Slash Commands

  Registers the entire /workflow command namespace with Anythink's CommandRegistry.

  register_workflow_commands(registry) — registers one top-level SlashCommand("workflow", ...) with
  _workflow_handler as its async handler.

  _workflow_handler(ctx, args, state, registry) — routes the subcommand word to the appropriate
  function:

  ┌───────────────────────────┬──────────────┬─────────────────────────────────────────────────┐
  │        Subcommand         │   Handler    │                  What it does                   │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ run "<task>"              │ _wf_run      │ Returns action="workflow_run_request" with      │
  │                           │              │ {"task": ..., "is_named": False}                │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │                           │              │ Loads saved workflow, returns                   │
  │ run <name>                │ _wf_run      │ action="workflow_run_request" with {"name":     │
  │                           │              │ ..., "is_named": True}                          │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ run ... --dry-run         │ _wf_run      │ Same but action="workflow_dry_run_request"      │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ new                       │ —            │ Returns action="workflow_new_wizard"            │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ list                      │ _wf_list     │ Reads ctx.workflow_storage.list_names(),        │
  │                           │              │ formats output                                  │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ show <name>               │ _wf_show     │ Loads and pretty-prints the plan                │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ edit <name>               │ _wf_edit     │ Verifies existence, returns                     │
  │                           │              │ action="workflow_edit_request"                  │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ delete <name>             │ _wf_delete   │ Calls ctx.workflow_storage.delete() immediately │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ rename <old> <new>        │ _wf_rename   │ Calls ctx.workflow_storage.rename()             │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ stop / pause / resume /   │ —            │ Returns the matching action signal              │
  │ status / panel            │              │                                                 │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ logs [last / show <n>]    │ _wf_logs     │ Lists logs or returns                           │
  │                           │              │ action="open_file_in_editor"                    │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ manifest show / refresh / │ _wf_manifest │ Loads, rebuilds, or prints the manifest path    │
  │  path                     │              │                                                 │
  ├───────────────────────────┼──────────────┼─────────────────────────────────────────────────┤
  │ registry list / tags /    │              │                                                 │
  │ add-tag / remove-tag /    │ _wf_registry │ Manages ctx.workflow_registry entries           │
  │ fallback / fallback-chain │              │                                                 │
  └───────────────────────────┴──────────────┴─────────────────────────────────────────────────┘

  None of the command handlers execute workflows directly — they all return CommandResult objects
  with action strings that the TUI picks up in _dispatch_command.

  Project connections:
  - Imported and called in commands/handlers.py alongside all other slash command registrations.
  - The action signals it emits are handled in ui/textual/app.py:_dispatch_command (lines
  ~1651–1745).

  ---
  stages/ Sub-Package

  stages/__init__.py — _dispatch_stage()

  The single routing function for all stage execution. Takes a Stage, WorkflowState, AppContext,
  and WorkflowCallbacks. All executor imports are deferred inside the function body (rather than at
  module level) to prevent circular import cycles. Returns a StageResult with an error if no
  executor is registered for the stage type.

  ---
  stages/llm_specialist.py — LLM_SPECIALIST Executor

  Streams a response from a specific model alias, with automatic fallback support.

  _build_candidate_chain(stage, ctx) — if the stage specifies a model_alias, returns that alias
  plus its fallback chain from WorkflowCapabilityRegistry. If no alias is set, falls back to all
  configured aliases in registry order.

  _build_content(stage, state) — assembles the prompt from task_instruction + resolved input_refs.
  Falls back to the previous stage's raw_content if no refs are found.

  execute() — iterates through candidates. For each: gets the API key, instantiates the provider,
  streams stream_chat(), records spend via ctx.spend_tracker.record(), and returns a StageResult.
  On exception, continues to the next candidate. If all candidates fail, returns a StageResult with
  error set and fallback_chain listing all attempted aliases.

  Project connections:
  - Uses ProviderRegistry.instantiate(), KeyManager.get_key(), ModelRegistry.get() — same provider
  infrastructure as normal chat.
  - Records spend to SpendTracker with session_id="workflow".
  - Uses WorkflowCapabilityRegistry.get_fallback_chain() for resilience.

  ---
  stages/mcp_call.py — MCP_CALL Executor

  _resolve_params(tool_params, state) — scans all param values. Any string in the form
  {{stage_1.email_list}} is replaced with the actual value from state.accumulated_results.

  execute() — calls ctx.mcp_manager.call_tool(stage.tool_name, resolved_params). The result's
  is_error flag determines whether to return success or an error StageResult. The tool name (e.g.
  "gmail.list_inbox") is stored in StageResult.tool_name for the logger.

  Project connections:
  - Calls MCPManager.call_tool() — the same method used by the /mcp call command in normal chat.
  The MCP tool index (MCPManager._tool_index) dispatches to the correct server transparently.

  ---
  stages/condition.py — CONDITION Executor

  _safe_eval(expr, context) — evaluates a boolean expression against state.accumulated_results.
  Uses Python's ast module to parse the expression, then _eval_node() to recursively evaluate it.
  Allowed constructs: constants, name lookups, attribute-style dot-path access
  (stage_1.email_count), comparison operators (all Python comparison ops), boolean operators (and,
  or, not), subscripts (results[0]). Disallowed: function calls, imports, assignments — any
  unsupported node returns None.

  execute() — calls _safe_eval(stage.condition_expr, state.accumulated_results). Returns a
  StageResult with output={"branch": "a", "condition_result": True} (true) or {"branch": "b",
  "condition_result": False} (false). The engine's _execute_stages() reads result.output["branch"]
  to pick which branch list to recurse into.

  Security note: The safe evaluator deliberately refuses function calls and imports. There is no
  eval() or exec() anywhere in the evaluator — it walks the AST node tree with an explicit
  whitelist.

  ---
  stages/formatter.py — FORMATTER Executor

  Pure Python format conversion — no LLM call, no external dependencies.

  Supported formats: markdown, plain_text, json, csv, html, numbered_list.

  _gather_input(stage, state) — resolves input_refs, falls back to the previous stage's
  raw_content.

  Converters:
  - _to_markdown — passthrough if already Markdown; otherwise re-joins paragraphs.
  - _to_plain — strips **bold**, ## headers, [links](url), and `code` with regex.
  - _to_json — tries json.loads first; on failure wraps as {"content": text}.
  - _to_csv — if input is a JSON list of dicts, uses csv.DictWriter; otherwise one row per line.
  - _to_html — converts #-headers, -  / *  lists, and bare paragraphs.
  - _to_numbered_list — strips existing numbers/bullets and renumbers from 1.

  Project connections: Standalone — no AppContext fields needed. Called by _dispatch_stage().

  ---
  stages/user_approval.py — USER_APPROVAL Executor

  execute() — invokes await callbacks.on_approval_needed(message) and waits. The TUI's
  _dispatch_command handler wires this callback to an interactive prompt. The returned string is
  parsed as a UserDecision enum; any unrecognised string defaults to APPROVED.

  Returns a StageResult with user_decision set. The engine checks this field — ABORTED stops the
  entire workflow; SKIPPED skips the stage and continues.

  Project connections:
  - Also called directly from WorkflowEngine._run_one_stage() when injecting an auto-guard for
  is_destructive=True stages.
  - The callbacks.on_approval_needed is implemented in the TUI layer.

  ---
  stages/loop.py — LOOP Executor (Wrapper)

  A thin wrapper that:
  1. Resolves the input_collection_ref from state.accumulated_results.
  2. Constructs an inner _run_sub_stage function that calls back to _dispatch_stage.
  3. Delegates entirely to LoopExecutor().run().

  All imports (LoopExecutor, _dispatch_stage) are deferred inside the function body to break the
  circular dependency chain (loop.py → __init__.py → loop.py).

  ---
  Project-Level Integration Map

  AppContext (app/context.py)
    ├── ctx.workflow_registry    → WorkflowCapabilityRegistry (registry.py)
    ├── ctx.workflow_storage     → WorkflowStorage (storage.py)
    ├── ctx.workflow_manifest    → CapabilityManifest (manifest.py)
    └── ctx.workflow_engine      → WorkflowEngine (engine.py)
          ├── _planner           → WorkflowPlanner (planner.py)
          ├── _router            → MetaRouter (router.py)
          ├── _optimizer         → StageOutputOptimizer (optimizer.py)
          ├── _loop_executor     → LoopExecutor (loop.py)
          ├── _logger            → WorkflowLogger (log.py)
          └── _storage           → WorkflowStorage (storage.py)

  commands/handlers.py
    └── register_workflow_commands() ← commands.py

  ui/textual/app.py (_dispatch_command)
    ├── "workflow_run_request"  → ctx.workflow_engine.plan_task() + .run()
    ├── "workflow_dry_run_request" → ctx.workflow_engine.dry_run()
    ├── "workflow_stop/pause/resume" → state.stop_requested / state.paused
    ├── "workflow_panel_toggle" → WorkflowPanel (panels/workflow_panel.py)
    └── "open_file_in_editor"  → opens log files from WorkflowLogger

  Outbound calls from stages:
    llm_specialist.py → ProviderRegistry, KeyManager, ModelRegistry, SpendTracker
    mcp_call.py       → MCPManager.call_tool()
    condition.py      → (self-contained safe evaluator)
    formatter.py      → (self-contained pure Python)
    user_approval.py  → WorkflowCallbacks.on_approval_needed (TUI)

  exceptions.py
    └── WorkflowError → WorkflowPlanError (planner.py)
                      → WorkflowStageError (condition.py, engine.py)

  smart/registry.py (MMAE)
    └── SmartRegistry.auto_populate(workflow_registry)
        (seeds MMAE model assignments from MMWE capability tags)

  ---
  Storage Locations

  ┌─────────────────────┬────────────────────────────────────────────────────────────────────┐
  │      Artifact       │                                Path                                │
  ├─────────────────────┼────────────────────────────────────────────────────────────────────┤
  │ Workflow plans      │ $XDG_CONFIG_HOME/anythink/workflows/<name>.yaml                    │
  ├─────────────────────┼────────────────────────────────────────────────────────────────────┤
  │ Capability tags     │ $XDG_CONFIG_HOME/anythink/workflow_capabilities.yaml               │
  ├─────────────────────┼────────────────────────────────────────────────────────────────────┤
  │ Capability manifest │ $XDG_CONFIG_HOME/anythink/workflow_manifest.txt                    │
  ├─────────────────────┼────────────────────────────────────────────────────────────────────┤
  │ Execution logs      │ $XDG_DATA_HOME/anythink/workflow_logs/YYYY-MM-DD_HHMMSS_<name>.log │
  └─────────────────────┴────────────────────────────────────────────────────────────────────┘

  ---
  What Is Not Yet Implemented

  - StageOutputOptimizer.transform() is instantiated and injected into WorkflowEngine but its
  transform() method is not yet called in the engine's dispatch loop. Stage inputs are built
  directly by each executor (llm_specialist._build_content, formatter._gather_input, etc.) rather
  than going through the optimizer first.
  - The MetaRouter is injected into WorkflowEngine but is not yet called by the engine during stage
  dispatch. The llm_specialist executor builds its own candidate chain using
  WorkflowCapabilityRegistry directly.
  - StageType.PLANNER is defined in the enum and described in the manifest but has no executor
  registered in stages/__init__.py._dispatch_stage.
