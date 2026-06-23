# Anythink V4 — Multi-Model Optimization System

---

## 1. Overview

V4 introduces the **Multi-Model Optimization System (MMOS)** — Anythink's most significant architectural expansion to date. Where prior versions focused on single-model interactions with provider switching, V4 treats the entire pool of available models (local and free-API-tier) as a **unified compute fabric**, coordinated intelligently to overcome individual model limitations and produce higher-quality, more reliable answers than any single model could deliver alone.

The core insight driving V4 is that free and local models each carry hard constraints — small context windows, low RPM/TPM caps, weak reasoning in specific domains, poor performance with long histories — but these constraints are **non-overlapping**. A fast model with a tiny context window can still answer isolated factual questions. A slow local model with a large context can handle summarisation. A code-specialist model outperforms a general model on architecture questions. V4's job is to know the constraints of every available model and **route, combine, chain, or decompose** work across them so the user always gets the best achievable answer within the available compute.

V4 also introduces a dedicated `/optimize` slash command namespace — the primary control surface for all multi-model settings — and a **Plan Mode** inspired by Claude Code's planning workflow, enabling step-by-step, phase-tracked execution of complex, resource-intensive queries.

---

## 2. What Is New in V4

- **`/optimize` slash command namespace** — complete control surface for all multi-model behaviour
- **`/mode` command** — explicit online/offline mode switching
- **Pre-query intent micro-prompt** — per-message question type and answer format clarification
- **Model Capability Registry** — bundled + user-editable model constraint database
- **Intelligent routing engine** — deterministic rules and/or meta-LLM orchestration
- **Four mixing strategies** — Routing, Ensemble (concatenate with attribution), Chaining, Decompose → Recombine
- **Context relevance engine** — semantic similarity-based history selection with alternative modes
- **Rate limit queue manager** — automatic pacing and model-switching under quota pressure
- **Plan Mode** — multi-phase execution with user approval, editable plan, and live TUI phase tracker
- **Quality vs Reliability priority selector** — user-controlled per session or per query
- **User routing override** — with confirmation and caution prompt
- **Model attribution display** — every response labelled with its source model(s)

---

## 3. The `/optimize` Command Namespace

The `/optimize` command is the primary control surface introduced in V4. It groups every multi-model behaviour into a single discoverable namespace, consistent with the `/debug` namespace pattern established in V3.2. It renders as an interactive panel within the TUI.

### 3.1 Command Structure

```
/optimize                         Open the full optimization panel
/optimize status                  Show current optimization configuration at a glance
/optimize mode                    Alias for /mode (online / offline / auto)
/optimize routing                 Configure routing logic and category rules
/optimize history                 Configure context/history selection strategy
/optimize registry                Open model capability registry viewer/editor
/optimize priority                Set quality vs reliability priority
/optimize plan                    Configure plan mode behaviour
/optimize ensemble                Configure ensemble/mixing strategy
/optimize ratelimit               View current rate limit status across all models
/optimize toggle                  Toggle entire optimization system on or off
/optimize microprompt             Toggle pre-query intent micro-prompt on or off
/optimize reset                   Reset all optimization settings to defaults
```

### 3.2 `/optimize` Panel Layout

When `/optimize` is entered without a subcommand, the TUI renders a full-panel interactive settings view divided into sections. Each section is navigable with arrow keys. Settings update live. The panel is dismissible with `Esc` or `q`.

**Panel sections:**

```
┌─ OPTIMIZATION SETTINGS ──────────────────────────────────────────────────┐
│                                                                           │
│  SYSTEM                                                                   │
│  ● Optimization Engine          [ENABLED]                                 │
│  ● Mode                         [ONLINE]                                  │
│  ● Pre-query Micro-prompt       [ON]                                      │
│  ● Orchestration Intelligence   [AUTO: DETERMINISTIC + META-LLM]          │
│                                                                           │
│  ROUTING                                                                  │
│  ● Routing Strategy             [CATEGORY + TOKEN LENGTH]                 │
│  ● Quality vs Reliability       [QUALITY FIRST]                           │
│  ● User Override                [ALLOWED WITH CONFIRMATION]               │
│                                                                           │
│  HISTORY & CONTEXT                                                        │
│  ● History Selection Mode       [SEMANTIC SIMILARITY]                     │
│  ● Max History Tokens           [2048]                                    │
│  ● Summarisation Model          [ollama/mistral]                          │
│                                                                           │
│  MIXING STRATEGY                                                          │
│  ● Default Mixing Mode          [ROUTING]                                 │
│  ● Ensemble Method              [CONCATENATE WITH ATTRIBUTION]            │
│  ● Plan Mode                    [ON — APPROVAL REQUIRED]                  │
│                                                                           │
│  RATE LIMITING                                                            │
│  ● Queue Mode                   [AUTO-PACE + SWITCH ON LIMIT]             │
│  ● Fallback Order               [groq → together → gemini → ollama]       │
│                                                                           │
│  [Save]  [Reset to Defaults]  [Close]                                     │
└───────────────────────────────────────────────────────────────────────────┘
```

### 3.3 `/optimize toggle`

Enables or disables the entire optimization engine. When disabled, Anythink reverts to single-model behaviour identical to V3. The TUI status bar reflects the active state with a visible indicator when optimization is running.

### 3.4 `/optimize status`

Displays a compact one-screen summary of the current optimization state — active mode, active models, current rate limit status per model, current mixing strategy, history mode, and plan mode state. Useful for quick inspection without opening the full panel.

---

## 4. Model Capability Registry

The Model Capability Registry (MCR) is a structured database of every model Anythink can use, storing all constraint and capability metadata needed for routing decisions. It ships as a **bundled base registry** (updated via `/update`) and supports **user-defined overrides and extensions**.

### 4.1 Registry Structure (per model entry)

Each model entry stores the following fields:

| Field | Description |
|---|---|
| `id` | Unique internal identifier (e.g. `groq/llama3-70b`) |
| `provider` | Provider name (groq, together, gemini, ollama, etc.) |
| `display_name` | Human-readable label shown in TUI |
| `tier` | `local` or `free-api` |
| `context_window` | Maximum total tokens (prompt + completion) |
| `max_output_tokens` | Maximum tokens in a single completion |
| `rpm_limit` | Requests per minute cap (null = unlimited) |
| `tpm_limit` | Tokens per minute cap (null = unlimited) |
| `rpd_limit` | Requests per day cap (null = unlimited) |
| `strength_categories` | Array: `[coding, reasoning, creative, factual, summarisation, math]` |
| `speed_class` | `fast`, `medium`, `slow` |
| `quality_class` | `high`, `medium`, `low` |
| `supports_system_prompt` | Boolean |
| `supports_streaming` | Boolean |
| `requires_network` | Boolean (false for local models) |
| `notes` | Free-text notes (user-editable) |

### 4.2 Bundled Base Registry

The base registry ships with Anythink and covers common free-tier API models (Groq, Together AI, OpenRouter, Google Gemini free tier, Cohere trial, Hugging Face Inference) and popular local model families via Ollama (Llama 3, Mistral, Gemma, Phi, Qwen, DeepSeek Coder, etc.). It is versioned alongside Anythink and refreshed via `/update`.

### 4.3 User-Editable Overrides

Users can override any field in the base registry or add entirely new model entries. Overrides live in a separate user config layer that is never touched by `/update`, so updates to the base registry do not overwrite user customisations.

Users interact with the registry through:

```
/optimize registry                          View full registry as a scrollable TUI table
/optimize registry add                      Add a new model entry (guided prompts)
/optimize registry edit <model-id>          Edit an existing entry
/optimize registry delete <model-id>        Remove a user-added entry
/optimize registry reset <model-id>         Reset a bundled entry to its base value
/optimize registry export                   Export registry to a JSON file
/optimize registry import <file>            Import from a JSON file
```

When adding a local model, Anythink prompts for each field in sequence, with sensible defaults inferred from the model family name where possible.

### 4.4 Registry Display in TUI

The registry panel renders as a scrollable table with columns: Model ID, Provider, Context Window, RPM, Strengths, Speed, Quality, Tier. Rows are colour-coded by tier (local = one colour, free-API = another). Active models in the current session are highlighted.

---

## 5. Online / Offline Mode — `/mode` Command

### 5.1 Mode Options

```
/mode online        Use only free-API-tier models
/mode offline       Use only local models (Ollama)
/mode auto          Try online first; fall back to local if network unavailable
```

The current mode is always displayed in the TUI status bar. `/mode` is also accessible as `/optimize mode`.

### 5.2 Auto Mode Behaviour

In `auto` mode, Anythink silently checks network reachability at session start and again before each API call. If a request to a free-API provider fails with a network error (not a rate limit error), the system logs the failure, switches affected models to unavailable, and routes the request to local models instead. The user sees a one-line status notification in the TUI when a fallback occurs.

Auto mode does not repeatedly retry network calls — it flags providers as unavailable for the session and promotes local alternatives. The user can manually reset provider availability via `/optimize ratelimit`.

---

## 6. Pre-Query Intent Micro-Prompt

### 6.1 Purpose

Before every query is processed, Anythink presents a short interactive clarification step — the **Intent Micro-Prompt** — that captures two things:

1. **Question category** — what kind of question this is
2. **Answer format preference** — what kind of response the user wants

This input directly feeds the routing engine, mixing strategy selector, and plan mode trigger logic.

### 6.2 Micro-Prompt UI

The micro-prompt appears as a compact inline selection panel above the input bar, rendered immediately after the user submits their message and before the query is dispatched to any model.

```
┌─ QUERY INTENT ──────────────────────────────────────────────────────────┐
│  Question type:                                                          │
│  [Coding]  [Reasoning]  [Creative]  [Factual]  [Research]  [Other]      │
│                                                                          │
│  Answer format:                                                          │
│  [Detailed]  [Concise]  [Step-by-step]  [Bullet summary]  [Code only]   │
│                                                                          │
│  Priority:   [Quality first]  [Speed first]  (current default: Quality) │
│                                                                          │
│  Press Enter to confirm or Esc to skip (use session defaults)           │
└──────────────────────────────────────────────────────────────────────────┘
```

Selections are navigable via arrow keys and Tab. The user confirms with Enter. If the user presses Esc or does not interact within a configurable timeout, the system falls back to session-level defaults set in `/optimize`.

### 6.3 Toggle

The micro-prompt can be turned off globally via `/optimize microprompt` or within the `/optimize` panel. When off, the system uses session-level defaults for all routing and format decisions without interrupting the user.

The toggle is persistent across sessions and remembered per profile.

### 6.4 System Inference as Fallback

When the micro-prompt is toggled off, or when the user skips it, the system performs its own lightweight inference on the question text using the deterministic rules engine (described in Section 10) to classify question type. This classification is visible in the TUI as a small label on the dispatched query row.

---

## 7. Context and History Management

### 7.1 The Problem

Free and local models have tightly bounded context windows. Sending the full conversation history with every message is often impossible and frequently wasteful — most history is irrelevant to the current question. V4 introduces a **context relevance engine** that selects only the portion of history genuinely needed for the current query, and compresses the rest.

### 7.2 History Selection Modes

Three modes are available, configurable via `/optimize history` or in `/settings`:

#### 7.2.1 Semantic Similarity (Default)

The current question is embedded using a lightweight local embedding model (shipped with Anythink or via Ollama). Past messages are also embedded and stored in a lightweight vector index maintained per session. When a new query arrives, the system retrieves the top-K most semantically similar past messages and includes only those in the context sent to the model.

The value of K is configurable (default: 6 messages, each scored above a similarity threshold). Retrieved messages are ordered chronologically, not by similarity score, to preserve conversational flow.

#### 7.2.2 Recency + Topic Continuity

The system takes the last N messages (configurable, default: 8) and additionally checks whether their topic is continuous with the current question using a simple keyword and phrase overlap heuristic. Messages that are both recent and topically relevant are included. Messages that are recent but off-topic (e.g., from a different task earlier in the session) are excluded.

#### 7.2.3 Model Decides

A fast, low-cost model (preferably a local model to avoid spending API quota) receives a compact prompt listing the session history as short summaries and the current question. It returns the indices of the messages that are relevant to answering the current question. Those messages are then included in the context sent to the primary model.

This mode adds a small latency overhead (one extra model call) but is the most accurate for ambiguous or multi-topic sessions.

### 7.3 History Summarisation

When the selected history segment still exceeds the target model's context window after relevance filtering, Anythink triggers **automatic summarisation**:

1. The relevant history segment is sent to a designated summarisation model (configurable in `/optimize history`, default: a fast local model)
2. The model produces a compact factual summary preserving key decisions, facts, and context established in those turns
3. The summary replaces the raw history turns in the context sent to the primary model
4. The original history is preserved in the session file — summarisation is non-destructive

The user sees a small indicator in the TUI when summarisation was applied to the current query context: `[history summarised: N turns → M tokens]`.

### 7.4 History Token Budget

A configurable token budget for history is set in `/optimize history` (default: 2048 tokens). The system ensures the selected history never exceeds this budget after summarisation. The budget is set relative to the target model's context window — users can set it as a fixed token count or as a percentage of the model's context window.

---

## 8. Rate Limiting and Queue Management

### 8.1 Rate Limit Awareness

Each model entry in the Model Capability Registry stores its RPM, TPM, and RPD limits. The queue manager maintains **live usage counters** per model per session, tracking:

- Requests made in the current 60-second window
- Tokens consumed in the current 60-second window
- Total requests made today (for RPD-limited providers)

These counters are displayed in `/optimize ratelimit` and in the TUI status bar as a compact indicator for the currently active model.

### 8.2 Automatic Pacing

When a request is about to be dispatched and the target model's RPM or TPM window is nearing its limit, the queue manager **paces the request**:

- A dispatch timer is set to the next available slot within the rate window
- The TUI shows a `[queued — dispatch in Xs]` indicator on the pending query
- If the user has multiple requests queued (e.g., during Plan Mode phase execution), they are dispatched in order, spaced to respect the rate window

Pacing is entirely automatic and invisible to the user beyond the dispatch indicator. No user action is required.

### 8.3 Automatic Model Switching

When the primary model for a request has hit its hard rate limit (RPM or RPD exhausted for the window), the queue manager **switches to the next available model** in the configured fallback order rather than waiting. The switch is logged and shown to the user as a one-line notification:

```
[!] groq/llama3-70b at RPM limit — switching to together/llama3-70b for this request
```

The fallback order is configurable in `/optimize ratelimit`. When all models in the fallback chain are at their limits, the system queues and waits, displaying a countdown to the next available dispatch slot.

### 8.4 Rate Limit Status Panel

```
/optimize ratelimit
```

Opens a live-updating TUI panel showing all configured models with their current usage:

```
┌─ RATE LIMIT STATUS ─────────────────────────────────────────────────────┐
│  Model                     RPM        TPM        RPD       Status       │
│  ─────────────────────────────────────────────────────────────────────  │
│  groq/llama3-70b          24/30      45k/60k    800/1000  ● ACTIVE      │
│  together/llama3-70b       0/60      0/100k     120/500   ○ STANDBY     │
│  gemini/gemini-1.5-flash  12/15      0/1M       240/1500  ● ACTIVE      │
│  ollama/mistral            —          —          —         ○ LOCAL       │
│  ollama/deepseek-coder     —          —          —         ○ LOCAL       │
│                                                                          │
│  Fallback order: groq → together → gemini → ollama/mistral              │
│  [Edit Fallback Order]  [Reset Counters]  [Close]                       │
└──────────────────────────────────────────────────────────────────────────┘
```

Counters reset automatically at the appropriate rate window boundary. Manual reset is available for local/test use.

---

## 9. Mixing Strategies

V4 supports four distinct mixing strategies. The system selects among them automatically based on the routing engine's decision, and the user can also force a specific strategy via `/optimize ensemble` or the user override system.

### 9.1 Routing (Single-Best Model Selection)

**What it is:** The routing engine selects the single most appropriate model for the current query and sends the full request to that model. Other models are not involved.

**When it is used:**
- Simple, well-classified queries (factual lookups, short coding tasks, quick creative prompts)
- Speed-first priority queries
- When the user explicitly forces a specific model

**How the model is selected:** The routing engine scores available models against the query's category, the estimated token count, the target model's context window, its strength profile, and the current rate limit state. The highest-scoring available model wins.

**User visibility:** The response header shows `[routed → groq/llama3-70b]`.

---

### 9.2 Ensemble — Concatenate with Attribution

**What it is:** The same query is sent to multiple models simultaneously (or sequentially if rate limits require). Each model's response is collected, then presented side-by-side in the output with clear attribution. The user can read each response and decide which they prefer.

**When it is used:**
- Quality-first priority queries where the question has no single objectively correct answer (reasoning, creative, architecture questions)
- When the user explicitly requests ensemble mode
- When the routing engine has low confidence in selecting a single best model

**Judge Model (future):** In the current V4 implementation, ensemble output is concatenate-with-attribution. When the user has a configured set of higher-quality models available, a **Judge Model** mode will be available as a future upgrade — where a designated judge model reads all responses and synthesises a single best answer. For now, judgement is left to the user.

**Output format:**

```
══════════════════════════════════════════════
  Response 1 of 3  ·  groq/llama3-70b  ·  [fast]
══════════════════════════════════════════════
[Model A's full response here]

══════════════════════════════════════════════
  Response 2 of 3  ·  together/mixtral-8x7b  ·  [quality]
══════════════════════════════════════════════
[Model B's full response here]

══════════════════════════════════════════════
  Response 3 of 3  ·  ollama/mistral  ·  [local]
══════════════════════════════════════════════
[Model C's full response here]
```

The number of models used in ensemble is configurable (default: 2–3). The system automatically skips models that are unavailable, rate-limited, or whose context window cannot fit the query.

---

### 9.3 Chaining

**What it is:** The query passes through a sequence of models, where each model's output becomes input for the next. Each model in the chain performs a distinct role (e.g., first model drafts, second model critiques, third model refines).

**When it is used:**
- Complex queries that benefit from a draft-critique-refine cycle
- Queries where one model has a domain strength in generation but a different model has a strength in review or fact-checking
- Long-form content generation

**Chain definition:** The chain is either selected automatically based on the query category or configured manually via `/optimize ensemble`. A typical default chain:

| Step | Role | Model type |
|---|---|---|
| 1 | Draft generation | Category-best model (e.g. coding specialist) |
| 2 | Critique and gap identification | High-reasoning model |
| 3 | Final refinement | Quality-class model or same as step 1 |

**User visibility:** The TUI shows a live chain progress indicator during execution:

```
[Draft ✓] → [Critique ✓] → [Refinement ●] → [Output]
```

Each intermediate output is collapsible in the final response. The user can expand to see what each step produced.

---

### 9.4 Decompose → Recombine

**What it is:** A complex multi-part query is broken down into independent sub-questions by the orchestrator. Each sub-question is routed to the most appropriate model for that sub-question type, potentially executed in parallel (if rate limits allow) or sequentially. The results are then passed to a recombination model that assembles them into a single coherent final response.

**When it is used:**
- Queries with clearly separable parts (e.g., "Explain the theory behind X, show me a code example, and compare it to Y")
- Queries where different parts have different optimal models (e.g., the code part goes to DeepSeek Coder, the explanation part goes to a reasoning model)
- Queries that exceed any single model's context window when answered in full

**Decomposition step:** The query is sent to a fast model (or the deterministic rules engine) with a decomposition prompt. The output is a numbered list of sub-prompts. This list is shown to the user before execution begins (see Plan Mode integration, Section 11).

**Recombination step:** Once all sub-answers are collected, a recombination model receives the original query, all sub-questions, and all sub-answers, and produces a unified, coherent final response.

**User visibility:**

```
[Decomposed into 3 sub-queries]
  Sub-1 → groq/llama3-70b (factual)         [✓ done]
  Sub-2 → ollama/deepseek-coder (coding)     [✓ done]
  Sub-3 → together/mixtral-8x7b (reasoning)  [● in progress]
[Recombination pending]
```

---

## 10. Plan Mode

Plan Mode is the V4 answer to complex, resource-intensive queries that cannot be answered in a single model call — queries that require web search, multi-step reasoning, large code generation, or detailed architectural planning. It is inspired by Claude Code CLI's planning workflow.

### 10.1 What Triggers Plan Mode

Plan Mode is triggered when one or more of the following conditions are met:

- The query is estimated to require more tokens than any single available model's context window
- The query contains research-intensive language (words like "detailed", "comprehensive", "architecture", "full implementation", "compare all", "list all", "step-by-step plan for")
- The query's detected category is `Research` or `Architecture`
- The orchestration engine classifies the query as multi-phase
- The user explicitly requests plan mode via `/optimize plan on` or the `--plan` flag on a query

When Plan Mode triggers, the system does **not** immediately call the primary model for a full answer. Instead, it enters the planning phase.

### 10.2 Plan Generation Phase

The current query (plus minimal relevant context) is sent to a fast model with a structured planning prompt. This model does not generate the final answer — it generates a **plan document**: a numbered sequence of phases, each describing:

- The sub-question or sub-task to address in that phase
- The suggested model to use
- Estimated token budget
- Dependencies on prior phases (if any)
- Expected output type (explanation, code block, comparison table, etc.)

The plan is written to a **plan file** — a lightweight text file stored in the session's temporary directory. This file serves as the execution queue for the phase runner.

### 10.3 Plan Review and Approval

The generated plan is presented to the user in a dedicated TUI panel before any execution begins:

```
┌─ PLAN MODE — REVIEW PLAN ───────────────────────────────────────────────┐
│  Query: "Give me a detailed Architecture to build a React web app        │
│         with Node.js Backend"                                            │
│  ─────────────────────────────────────────────────────────────────────  │
│  Phase 1 of 5: Project structure and folder layout                       │
│    Model: groq/llama3-70b  ·  Est. tokens: ~800  ·  Type: explanation   │
│                                                                          │
│  Phase 2 of 5: Frontend architecture (React, state, routing)             │
│    Model: together/mixtral-8x7b  ·  Est. tokens: ~1200  ·  Type: detail │
│                                                                          │
│  Phase 3 of 5: Backend architecture (Node.js, Express, REST API design)  │
│    Model: together/mixtral-8x7b  ·  Est. tokens: ~1200  ·  Type: detail │
│                                                                          │
│  Phase 4 of 5: Database design and integration strategy                  │
│    Model: groq/llama3-70b  ·  Est. tokens: ~900  ·  Type: detail        │
│                                                                          │
│  Phase 5 of 5: Deployment and CI/CD pipeline overview                   │
│    Model: ollama/mistral  ·  Est. tokens: ~700  ·  Type: explanation    │
│                                                                          │
│  Total estimated tokens: ~4800  ·  Models: 3  ·  Phases: 5              │
│  Estimated time: ~2–4 minutes (subject to rate limits)                  │
│  ─────────────────────────────────────────────────────────────────────  │
│  [Approve & Run]  [Edit Plan]  [Reject]  [Re-generate Plan]             │
└──────────────────────────────────────────────────────────────────────────┘
```

**Approve & Run:** Begins phase execution immediately.

**Edit Plan:** Opens an inline editable view of the plan. The user can modify phase descriptions, change the model assignment for a phase, reorder phases, add phases, or delete phases. Changes are saved back to the plan file. After editing, the user can re-approve.

**Reject:** Discards the plan entirely. The user is returned to the input prompt. They can re-enter the query, simplify it, or trigger a different strategy manually.

**Re-generate Plan:** Sends the query back to the planning model with a note that the previous plan was rejected, requesting a revised plan. The user can repeat this cycle until satisfied.

### 10.4 Phase Execution

After approval, the phase runner processes the plan file sequentially:

1. For each phase, the runner constructs a focused sub-prompt from the phase description plus any outputs from prior phases that the current phase depends on
2. The sub-prompt is sent to the assigned model, respecting rate limits (with automatic pacing and model switching as described in Section 8)
3. The phase output is written to the plan file alongside the phase definition (making the plan file a running execution log)
4. The TUI phase tracker updates in real time
5. After all phases complete, a final **recombination call** is made: the recombination model receives the original query plus all phase outputs and produces a single unified final response

Phase outputs from prior phases are included in subsequent phase prompts only when the dependency graph indicates they are needed — this avoids unnecessary token consumption.

### 10.5 Live Phase Tracker (TUI)

During execution, the TUI replaces the normal waiting indicator with a live phase tracker panel:

```
┌─ PLAN MODE — EXECUTING ─────────────────────────────────────────────────┐
│  Query: "Detailed Architecture: React + Node.js"                         │
│                                                                          │
│  ✓  Phase 1 · Project structure          groq/llama3-70b   [done  0:12] │
│  ✓  Phase 2 · Frontend architecture      together/mixtral  [done  0:34] │
│  ●  Phase 3 · Backend architecture       together/mixtral  [running...] │
│  ○  Phase 4 · Database design            groq/llama3-70b   [waiting]    │
│  ○  Phase 5 · Deployment overview        ollama/mistral    [waiting]    │
│                                                                          │
│  ○  Recombination                        ollama/mistral    [waiting]    │
│                                                                          │
│  Progress: ██████████░░░░░░░░░░  2/5 phases complete                    │
│  Elapsed: 0:46  ·  Est. remaining: ~1:30  ·  Rate limit OK              │
│                                                                          │
│  [Pause]  [Skip Phase]  [Abort]                                         │
└──────────────────────────────────────────────────────────────────────────┘
```

**Icons:** `✓` = complete, `●` = in progress (with animated pulse), `○` = waiting, `✗` = failed/skipped.

**Pause:** Pauses after the current phase completes and waits for the user to resume. Useful if the user wants to review intermediate output before continuing.

**Skip Phase:** Marks the current in-progress phase as skipped and moves to the next. The skipped phase's output will be absent from recombination context.

**Abort:** Stops execution. The user is asked whether to (a) discard all output, (b) keep partial output collected so far, or (c) attempt recombination with the phases completed so far.

When a phase encounters a rate limit, the tracker shows the queued state and countdown:

```
│  ●  Phase 3 · Backend architecture  together/mixtral  [queued — 14s]    │
```

---

## 11. Orchestration Intelligence

V4 supports two orchestration modes and can combine them. The mode is configurable in the `/optimize` panel.

### 11.1 Deterministic Rules Engine

A fast, zero-latency rules-based classifier that makes routing and strategy decisions without calling any model. Rules are evaluated in priority order.

**Classification rules (examples):**

| Condition | Action |
|---|---|
| Query contains code blocks or keywords: `function`, `class`, `def`, `import`, `bug`, `error` | Category = `Coding`; route to coding-specialist model |
| Query mentions architecture, system design, or full implementation | Trigger Plan Mode |
| Query token estimate + history > target model context window | Trigger context compression → routing |
| Query is a single factual question, <50 tokens | Category = `Factual`; route to fastest available model |
| Creative keywords: `write a story`, `poem`, `imagine`, `creative` | Category = `Creative`; route to creative-strength model |
| Analysis keywords: `compare`, `pros and cons`, `evaluate`, `which is better` | Category = `Reasoning`; trigger ensemble mode |
| Active model at RPM limit | Switch to next model in fallback order |
| All API models unavailable (offline mode or network failure) | Route to local models only |

Rules are loaded from a configurable YAML rules file, allowing advanced users to define custom routing rules.

### 11.2 Meta-LLM Orchestrator

A fast, low-token-cost model is used as the orchestration brain — it receives the user's current query, the session state summary, and the list of available models with their constraints, and returns a routing decision in structured JSON.

**Meta-LLM prompt inputs:**
- Current query text
- Detected question category (from deterministic pre-pass)
- Available model list with constraints
- Current rate limit state
- Session quality/speed priority setting
- History token estimate

**Meta-LLM output (structured JSON):**
```json
{
  "strategy": "decompose_recombine",
  "primary_model": "together/mixtral-8x7b",
  "phase_models": ["groq/llama3-70b", "ollama/deepseek-coder"],
  "recombination_model": "ollama/mistral",
  "plan_mode": true,
  "confidence": 0.87,
  "reason": "Query spans multiple domains; decomposition will yield better coverage"
}
```

The meta-LLM is chosen to be the fastest available low-cost model in the registry (never a rate-limited model). In offline mode, a local model serves as the meta-LLM.

### 11.3 Orchestration Mode Selection

```
/optimize                → Orchestration: [DETERMINISTIC] [META-LLM] [AUTO]
```

- **Deterministic only:** Fast, zero-latency routing. No extra model calls. Best for low-RPM-budget situations.
- **Meta-LLM only:** More intelligent but costs one extra model call per query.
- **Auto (default):** Deterministic rules run first. If the rules produce a high-confidence classification, they are used. If confidence is low or the query is ambiguous, the meta-LLM is invoked to make the final call.

---

## 12. Quality vs Reliability Priority

### 12.1 Priority Modes

**Quality First (default in `/optimize`):**
- The system selects the highest-quality model available for each routing decision
- Ensemble and chaining strategies are preferred over single-model routing
- Plan Mode is triggered more liberally (lower complexity threshold)
- Context is handled more carefully (semantic similarity, summarisation over truncation)
- Accepts higher latency and higher token usage in exchange for better output

**Reliability First:**
- The system selects the fastest available model that can handle the query
- Single-model routing is preferred
- Plan Mode is only triggered for clearly overwhelming queries
- Truncation is preferred over summarisation for speed
- Accepts lower output quality in exchange for fast, guaranteed response

**Hybrid (user can enable):**
- A fast reliability-mode response is generated first and shown to the user immediately
- In the background, a quality-mode response is generated using ensemble or chaining
- When the quality response is ready, the TUI offers to replace the fast response: `[Quality response ready — replace? Y/n]`

### 12.2 Priority Selection Points

Priority can be set at three levels, each overriding the one above:

1. **Session default** — set in `/optimize priority`, persists for the session
2. **Per-query via micro-prompt** — the user selects Speed or Quality in the pre-query intent panel for the current query only
3. **User override** — the user can type `--quality` or `--speed` as flags on any query to force a priority for that query

---

## 13. User Override System

### 13.1 What the User Can Override

Users can manually override the routing engine's decisions at any point:

- **Force a specific model** for the current query
- **Force a specific mixing strategy** (routing / ensemble / chaining / decompose)
- **Force or disable Plan Mode** for a query
- **Force a specific quality/speed priority** for a query

### 13.2 Override Invocation

Overrides are specified as inline flags appended to the query:

```
How do I implement a binary search tree? --model ollama/deepseek-coder
Compare React and Vue for enterprise apps  --strategy ensemble
Build a full REST API in Node.js  --no-plan
Summarise this document quickly  --speed
```

Overrides can also be applied via the `/optimize` panel's **Override** section, which sets a one-query or persistent override.

### 13.3 Caution Prompt and Confirmation

When a user override conflicts with the system's recommendation — for example, forcing a model known to have a smaller context window than the query requires, or disabling Plan Mode for a clearly complex query — the system displays a **caution prompt** before proceeding:

```
┌─ OVERRIDE CAUTION ──────────────────────────────────────────────────────┐
│  ⚠  You've forced: ollama/phi-2                                          │
│                                                                          │
│  This model has a 2048-token context window.                             │
│  Your query + history is estimated at ~3,100 tokens.                    │
│  The response may be truncated or incoherent.                           │
│                                                                          │
│  The recommended model is: groq/llama3-70b (128k context)               │
│                                                                          │
│  [Proceed anyway]  [Use recommended model]  [Cancel]                    │
└──────────────────────────────────────────────────────────────────────────┘
```

Overrides that do not conflict with technical constraints (e.g., preferring a specific model that can handle the query) proceed without a caution prompt — just a confirmation line in the TUI.

---

## 14. User Visibility and Model Attribution

### 14.1 Per-Response Attribution Header

Every response rendered in the TUI includes a compact attribution line at the top:

```
── groq/llama3-70b  ·  Routing  ·  1,243 tokens  ·  0.8s ───────────────
[Response text]
```

For ensemble responses, each section has its own attribution header (as shown in Section 9.2).

For Plan Mode responses, the attribution header lists all models used:

```
── Plan Mode  ·  5 phases  ·  groq, together, ollama/mistral  ·  4,821 tokens total  ·  2m 14s ──
[Final unified response]
[▶ Expand phase outputs]
```

### 14.2 Expandable Phase Outputs (Plan Mode)

Plan Mode final responses include a collapsed section `[▶ Expand phase outputs]`. When expanded, the user can see each phase's raw output alongside its attribution. This is useful for understanding which part of the answer came from which model.

### 14.3 Status Bar Attribution

The TUI status bar shows the currently active model (or orchestration mode) at all times:

```
[ ONLINE · groq/llama3-70b · Quality · Semantic History · 2 models active ]
```

When optimization is active, the status bar includes the optimization mode indicator.

---

## 15. Integration with Existing Anythink Systems

### 15.1 `/settings` Integration

The `/settings` command (introduced in V2.1) is extended with a new **Model Optimization** section. This section provides access to the same settings as `/optimize` but within the unified settings panel. Changes made in `/settings` and `/optimize` are always in sync.

### 15.2 `/debug` Integration

The V3.2 debug infrastructure is extended to support MMOS debugging:

- `plan_mode_trace` — logs the full plan generation prompt, the raw plan output, and each phase prompt/response pair
- `routing_decision_log` — logs every routing decision with the scoring breakdown (for deterministic mode) or the raw meta-LLM response (for meta-LLM mode)
- `history_selection_log` — logs which history turns were selected, their similarity scores, and the token count before and after summarisation
- `rate_limit_log` — logs every rate limit hit, pacing decision, and model switch event

These are accessible via `/debug verbose` or the debug side panel (V3.2).

### 15.3 Export Integration

The V3 export system (Markdown / JSON / PDF) is extended to support Plan Mode exports. When exporting a Plan Mode conversation turn, the export includes:

- The original query
- The generated plan (all phases with model assignments)
- Each phase output with its attribution
- The final recombined response

JSON export includes machine-readable metadata: phase durations, model IDs, token counts per phase, rate limit events.

### 15.4 Session History

The plain-text session history (V1) and the branching system (V2) are both aware of MMOS. Session history stores:

- The strategy used for each turn (routing / ensemble / chaining / decompose / plan mode)
- The model(s) used and token counts
- The plan file contents for Plan Mode turns (stored as an embedded JSON block)

Branching a conversation at a Plan Mode turn clones the plan file into the new branch.

### 15.5 Notification System

The V2 desktop notification system is extended to fire notifications for:

- Plan Mode completion (fires when all phases and recombination finish, especially useful for long-running plans where the user may have switched away from the terminal)
- Rate limit switches (optional, configurable, off by default to avoid noise)
- Model unavailability events (network loss in auto mode)

### 15.6 Plugin Architecture

The V1 plugin system is extended with two new plugin hook points for MMOS:

- `pre_routing_hook` — a plugin can inspect the current query and inject routing hints before the routing engine runs
- `post_phase_hook` — a plugin can process each Plan Mode phase output before it is passed to the next phase (e.g., a formatter, validator, or tool-use plugin)

---

## 16. Summary of New TUI Elements

| Element | Location | Description |
|---|---|---|
| Intent Micro-Prompt panel | Above input bar | Per-query type and format selector |
| `/optimize` settings panel | Full-screen overlay | All optimization settings |
| Rate Limit Status panel | `/optimize ratelimit` | Live model quota display |
| Model Registry table | `/optimize registry` | Scrollable, editable model database |
| Plan Review panel | Full-screen overlay | Plan approval and editing before execution |
| Phase Tracker panel | Replaces wait indicator | Live execution progress during Plan Mode |
| Per-response attribution header | Top of each response | Model, strategy, token, timing info |
| Expandable phase outputs | Collapsed block in response | Per-phase raw output viewer |
| Status bar extension | Status bar | Active model, mode, and optimization state |
| Override caution modal | Inline modal | Conflict warning before user override executes |

---

## 17. Configuration Files Introduced in V4

| File | Format | Purpose |
|---|---|---|
| `model_registry.json` | JSON | Bundled base model capability database |
| `model_registry_user.json` | JSON | User overrides and custom model entries |
| `optimize_settings.toml` | TOML | All `/optimize` panel settings, persistent |
| `routing_rules.yaml` | YAML | Custom deterministic routing rules (advanced) |
| `plan_<session_id>_<timestamp>.txt` | Text | Plan Mode execution log per plan run |
| `rate_limit_state.json` | JSON | Current session rate limit counters (ephemeral) |

---

*Anythink V4 — Multi-Model Optimization System*
*Feature description document. Implementation phase not yet begun.*
*Builds upon: V1, V2, V2.1, V2.2, V3, V3.2, V3.3*
