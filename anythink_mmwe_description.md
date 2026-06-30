# Anythink — Multi-Model Workflow Engine (MMWE)

> A new standalone orchestration system that takes a single user intent and
> decomposes it into a structured, multi-stage pipeline executed by the right
> model at the right stage — local, cloud, or tool-only — with full user
> visibility, mid-execution control, branching support, loop processing for
> large datasets, and a permanent execution log. Every workflow is inspectable
> before it runs, editable before and during execution, and reusable across
> sessions.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [The Capability Manifest File](#2-the-capability-manifest-file)
3. [The Planner Model — Stage 1](#3-the-planner-model--stage-1)
4. [Stage Types](#4-stage-types)
5. [Workflow Structure — Linear, Branching, and Parallel](#5-workflow-structure--linear-branching-and-parallel)
6. [Model Capability Registry](#6-model-capability-registry)
7. [Model Selection & Meta-Router](#7-model-selection--meta-router)
8. [Fallback Chain System](#8-fallback-chain-system)
9. [Context Pipeline Between Stages](#9-context-pipeline-between-stages)
10. [Loop Processing for Large Datasets](#10-loop-processing-for-large-datasets)
11. [Stage Output Optimizer](#11-stage-output-optimizer)
12. [User Visibility — Live Stage Display](#12-user-visibility--live-stage-display)
13. [Intermediate Result Display](#13-intermediate-result-display)
14. [Workflow Execution Log](#14-workflow-execution-log)
15. [User Control During Execution](#15-user-control-during-execution)
16. [Dry-Run Mode](#16-dry-run-mode)
17. [Destructive Operation Guards](#17-destructive-operation-guards)
18. [Dynamic Workflows — Natural Language Trigger](#18-dynamic-workflows--natural-language-trigger)
19. [Named & Reusable Workflows](#19-named--reusable-workflows)
20. [Workflow Editing](#20-workflow-editing)
21. [The `/workflow` Command Namespace](#21-the-workflow-command-namespace)
22. [Integration With Existing Anythink Systems](#22-integration-with-existing-anythink-systems)
23. [New Files & Architecture](#23-new-files--architecture)

---

## 1. System Overview

### 1.1 What the MMWE Is

The Multi-Model Workflow Engine (MMWE) is a new standalone orchestration
layer built into Anythink that treats complex user tasks as **structured
pipelines** — sequences of stages, each handled by the most capable
available resource: a specialist local model, a cloud API model, an MCP
tool call, a condition branch, a user approval gate, or an output formatter.

No single model does everything. The planner reads the user's intent,
decomposes it into a plan, assigns the right model or tool to each stage,
and hands execution over to the engine. The engine runs each stage in order
(or in parallel for independent branches), passes optimized context between
stages, handles large datasets in loops to preserve quality, shows the user
every stage result as it completes, and produces a permanent execution log.

### 1.2 The Core Difference From Existing Single-Model Responses

In a standard Anythink conversation, one model receives a prompt and
generates one response. MCP tools are called as part of that single
model's reasoning. The MMWE is fundamentally different:

- **Multiple different models** handle different stages of one task
- **MCP calls** are first-class pipeline stages, not model tool calls
- **The planner** is a dedicated model whose only job is decomposition
  and routing — it never synthesizes the final answer
- **Specialist models** are selected per stage based on capability tags
- **Branching** allows independent sub-tasks to execute in parallel
- **Loops** allow large datasets to be processed item-by-item without
  quality loss
- **The user can see, edit, stop, and resume** at every stage boundary

### 1.3 Invocation

MMWE is always explicitly invoked. It never activates automatically for
normal single-model chat responses. The user triggers it with:

```
/workflow run "Read the email from my inbox and summarize every email"
```

Everything after `/workflow run` is the natural language task description
passed to the planner.

---

## 2. The Capability Manifest File

### 2.1 What It Is

The Capability Manifest is a structured plain-text file — maintained
automatically by Anythink and updated whenever the user's setup changes —
that describes everything the MMWE can use to complete a task. It is
injected into the planner model's system prompt as its complete knowledge
base of available resources.

The planner reads this file to reason about what's possible. It cannot
use any capability, model, or tool that is not listed in the manifest.
Conversely, anything listed in the manifest is something the planner
is authorized and able to include in a workflow plan.

### 2.2 Manifest File Location

```
$XDG_CONFIG_HOME/anythink/workflow_manifest.txt
```

On Windows: `%APPDATA%\anythink\workflow_manifest.txt`

### 2.3 Manifest Contents — Full Structure

The manifest is regenerated automatically every time Anythink starts,
every time a model alias is added or removed, every time an MCP server
connects or disconnects, and every time a capability is toggled on or off.
The user can also manually trigger regeneration with `/workflow manifest refresh`.

The file contains the following sections:

---

**Section 1 — Available Local Models**

Lists every model alias the user has configured, with its tags from the
Model Capability Registry (Section 6), the underlying model name, the
provider runtime (Ollama / LM Studio / llama.cpp), and its context window:

```
[LOCAL MODELS]
alias: local-planner
  model: llama3.2:8b
  runtime: Ollama
  context_window: 128000
  tags: planning, reasoning, decomposition, routing

alias: local-summarizer
  model: mistral:7b
  runtime: Ollama
  context_window: 32000
  tags: summarization, extraction, condensing

alias: local-coder
  model: deepseek-coder:6.7b
  runtime: Ollama
  context_window: 16000
  tags: code, debugging, code-review, refactoring
```

---

**Section 2 — Available Cloud Models**

Lists every configured cloud provider model alias with its tags, provider,
and fallback chain:

```
[CLOUD MODELS]
alias: google2
  model: gemini-2.0-flash
  provider: Gemini
  context_window: 1000000
  tags: summarization, reasoning, multimodal, long-context
  fallback: local-summarizer

alias: gpt4o
  model: gpt-4o
  provider: OpenAI
  context_window: 128000
  tags: reasoning, code, planning, analysis
  fallback: local-planner
```

---

**Section 3 — Registered MCP Tools**

Lists every tool across every connected MCP server — built-in and external —
with its name, description, server, and input parameters:

```
[MCP TOOLS]
server: filesystem (builtin)
  tool: list_dir
    description: List files in a directory
    params: path (str)

  tool: read_file
    description: Read the contents of a file
    params: path (str)

  tool: write_file
    description: Write content to a file
    params: path (str), content (str)
    DESTRUCTIVE: requires user confirmation

server: gmail (external, SSE)
  tool: list_inbox
    description: List emails from Gmail inbox
    params: max_results (int, default 10)

  tool: read_email
    description: Read the full content of one email
    params: email_id (str)
```

---

**Section 4 — Anythink Built-in Capabilities**

Lists capabilities that Anythink itself provides as first-class workflow
resources — RAG indexing, web search, session history, notifications, etc.:

```
[ANYTHINK CAPABILITIES]
rag_search: Query a loaded RAG index by natural language
web_search: Search the web and return results (requires search toggle on)
session_history: Read previous conversation sessions
desktop_notification: Send a Windows/macOS/Linux desktop notification
clipboard_write: Write text to system clipboard
screenshot: Capture the screen and use as context
```

---

**Section 5 — Stage Types Available**

Lists the stage types the planner may use in a plan:

```
[STAGE TYPES]
PLANNER: Reads intent and produces structured plan (always Stage 1)
MCP_CALL: Executes one or more MCP tool calls — no LLM
LLM_SPECIALIST: Sends context to a specific model for processing
USER_APPROVAL: Pauses and waits for user confirmation to continue
CONDITION: Routes to Branch A or Branch B based on a condition expression
FORMATTER: Converts stage output to a specific format (JSON, Markdown, plain text, etc.)
LOOP: Repeats a sub-pipeline for each item in a list (e.g., each email)
```

---

**Section 6 — Saved Workflows**

Lists all user-saved named workflows so the planner is aware of existing
reusable definitions and can reference or suggest them:

```
[SAVED WORKFLOWS]
name: email-summary
  description: Read all inbox emails and summarize each one
  stage_count: 5
  last_run: 2025-06-18

name: code-review
  description: Read a code file and produce a line-by-line review
  stage_count: 4
  last_run: 2025-06-15
```

---

### 2.4 Manifest Is Planner's Only Source of Truth

The planner model does not use any knowledge of Anythink's capabilities
from its training data. It uses only what is listed in the manifest. This
ensures that the plan it produces is always executable — it never references
a tool that is not connected, a model that is not installed, or a capability
that is not configured.

---

## 3. The Planner Model — Stage 1

### 3.1 What the Planner Does

The planner is a dedicated local model whose sole job is:

1. Read the user's natural language task
2. Read the complete Capability Manifest
3. Understand the full scope of what needs to happen
4. Ask clarifying questions if the task is ambiguous
5. Produce a structured, step-by-step workflow plan
6. Assign a specific model or tool to every stage
7. Define the data flow between stages
8. Identify branches and loops where needed

The planner **never** executes tasks itself. It only plans. Its output is
always a structured plan document — never a final answer.

### 3.2 Planner Model Selection

The planner role requires a model that is strong at reasoning, decomposition,
and structured output. The user assigns the planner model in `/settings` →
Workflow → Planner model. It should have the capability tag `planning` in
the Model Capability Registry.

If no model is explicitly assigned, the Meta-Router (Section 7) selects the
highest-ranked `planning`-tagged model available at the time of invocation.

### 3.3 Planner System Prompt Structure

The planner model receives a system prompt assembled from three parts:

**Part 1 — Role definition:** A concise description of the planner's job,
the stage types it may use, the output format required, and the rules
it must follow (only use manifest-listed resources, assign appropriate
models to stages, identify loops for large datasets, include approval
stages for destructive operations).

**Part 2 — The full Capability Manifest:** The complete text of
`workflow_manifest.txt` injected verbatim.

**Part 3 — Output format specification:** A precise schema for how the
planner must format its output — the structured plan format described
in Section 3.5.

### 3.4 Clarifying Questions Before Planning

If the planner determines that the user's task is ambiguous in a way that
would produce significantly different plans depending on the answer, it
produces a clarification request instead of a plan:

```
╭─ 🧠 Planner — Clarification Needed ──────────────────────────────╮
│                                                                    │
│  Before I can create a plan for "Read the email from my inbox     │
│  and summarize every email", I need to know:                      │
│                                                                    │
│  1. How many emails should be included?                           │
│     [a] All emails in inbox   [b] Last 10   [c] Specify number   │
│                                                                    │
│  2. What format should the summary be in?                         │
│     [a] One sentence per email   [b] Bullet points   [c] Full    │
│                                                                    │
│  3. Should the summaries be saved to a file?                      │
│     [y] Yes   [n] No                                              │
│                                                                    │
│  Answer all three, then I'll produce the plan.                    │
╰────────────────────────────────────────────────────────────────────╯
```

The user answers in chat. The planner receives the answers and produces
the full plan. This clarification loop can go up to 2 rounds — if the task
is still ambiguous after 2 rounds, the planner produces a partial plan
with clearly marked `[NEEDS INPUT]` stages where information is missing.

### 3.5 The Structured Plan Format

The planner's output is a structured plan displayed to the user as an
editable, stage-by-stage document before any execution begins:

```
╭─ 🧠 Workflow Plan — "Read and summarize inbox emails" ────────────╮
│                                                                    │
│  Stage 1 · MCP_CALL                                               │
│  ─────────────────────────────────────────────────────────────── │
│  Tool:    gmail.list_inbox                                        │
│  Input:   max_results=50                                          │
│  Output:  List of email IDs → passed to Stage 2                  │
│                                                                    │
│  Stage 2 · USER_APPROVAL                                          │
│  ─────────────────────────────────────────────────────────────── │
│  Message: "Found N emails. Proceed to read and summarize all?"   │
│  On yes:  Continue to Stage 3                                     │
│  On no:   Abort workflow                                          │
│                                                                    │
│  Stage 3 · LOOP  (one iteration per email ID from Stage 1)       │
│  ─────────────────────────────────────────────────────────────── │
│  ├── Stage 3a · MCP_CALL                                         │
│  │   Tool:   gmail.read_email                                    │
│  │   Input:  email_id (from loop item)                           │
│  │   Output: Raw email content → passed to Stage 3b              │
│  │                                                               │
│  └── Stage 3b · LLM_SPECIALIST                                   │
│      Model:  local-summarizer (mistral:7b)                       │
│      Task:   Summarize this single email in 2–3 sentences        │
│      Input:  Raw email content from Stage 3a                     │
│      Output: One email summary → accumulated to Stage 4          │
│                                                                    │
│  Stage 4 · FORMATTER                                              │
│  ─────────────────────────────────────────────────────────────── │
│  Input:  All accumulated summaries from Stage 3                  │
│  Format: Markdown — numbered list, one summary per email         │
│  Output: Final formatted document → shown to user + saved        │
│                                                                    │
│  Stage 5 · MCP_CALL                                               │
│  ─────────────────────────────────────────────────────────────── │
│  Tool:    filesystem.write_file                                   │
│  Input:   path="~/email_summaries.md", content=Stage 4 output   │
│  ⚠ DESTRUCTIVE: Will write to disk — approval required           │
│                                                                    │
│  ─────────────────────────────────────────────────────────────── │
│  Models used:  local-summarizer (mistral:7b)                     │
│  MCP servers:  gmail, filesystem                                  │
│  Estimated loops:  50 (one per email)                            │
│  Estimated duration:  ~8–12 minutes                              │
│                                                                    │
│  [▶ Run]  [✎ Edit Plan]  [🔬 Dry Run]  [✕ Cancel]               │
╰────────────────────────────────────────────────────────────────────╯
```

### 3.6 Planner Output Is Always Shown Before Execution

The plan is always displayed and always requires an explicit user action
before execution begins. There is no "auto-start" option for the plan
review step — it is a mandatory gate in every workflow, regardless of
the global autonomy mode setting.

---

## 4. Stage Types

### 4.1 PLANNER Stage

Always Stage 1 in every workflow. Handled by the designated planner model.
Never appears anywhere else in the pipeline. Produces the structured plan
and assigns all subsequent stages. Its output is the plan document itself,
not data for the next stage.

---

### 4.2 MCP_CALL Stage

An MCP execution stage with no LLM involvement. The engine calls one or
more MCP tools directly and passes the raw results to the next stage.
Multiple tool calls within one MCP_CALL stage run sequentially by default,
or can be marked as parallel if they are independent of each other.

Each MCP_CALL stage specifies: which tool to call, what parameters to
pass (which may reference output from a previous stage), and what the
output field name is for downstream stages to reference.

---

### 4.3 LLM_SPECIALIST Stage

A model processing stage. The engine sends the optimized context from the
previous stage — along with a task-specific instruction assembled by the
Stage Output Optimizer (Section 11) — to the assigned specialist model.
The model's response becomes the output of this stage, passed to the next.

Each LLM_SPECIALIST stage specifies: which model alias to use, the task
instruction (what the model is being asked to do with the input), and the
expected output format.

---

### 4.4 USER_APPROVAL Stage

An execution pause gate. The workflow halts, displays a message to the user
summarizing what has happened so far and what will happen next, and waits
for an explicit `[Continue]` or `[Abort]` response before proceeding.

USER_APPROVAL stages are:
- Always inserted automatically by the planner before any destructive
  MCP operation (file deletion, sending emails, system setting changes)
- Optionally inserted by the planner at natural decision points
- Available for the user to manually add to any plan during the edit step

The workflow never times out waiting at a USER_APPROVAL stage — it waits
indefinitely until the user responds.

---

### 4.5 CONDITION Stage

A routing stage that evaluates a condition on the previous stage's output
and directs execution to one of two branches (Branch A or Branch B).

The condition is a simple expression the planner defines — for example:
- `output.email_count > 0` → Branch A (proceed), Branch B (no emails found)
- `output.contains_error == true` → Branch A (error handling), Branch B (normal)
- `output.file_type == "pdf"` → Branch A (PDF pipeline), Branch B (text pipeline)

Each branch is an independent sub-pipeline of stages. Branches eventually
merge at a designated MERGE point where their outputs are combined and the
unified result continues to the next main stage.

---

### 4.6 FORMATTER Stage

A transformation stage that takes the previous stage's output and converts
it to a specified format — with no LLM inference and no MCP calls.
Formatting is handled by Anythink's own output transformation layer.

Supported output formats:
- **Markdown** — convert to headings, lists, code blocks, tables
- **Plain text** — strip all markup, produce clean readable text
- **JSON** — structure into key-value pairs or arrays
- **CSV** — convert tabular data to comma-separated values
- **HTML** — convert to basic HTML document structure
- **Numbered list** — produce a clean numbered list from accumulated items

The FORMATTER stage is commonly used as the final stage before showing
results to the user, or before writing output to a file.

---

### 4.7 LOOP Stage

A meta-stage that wraps a sub-pipeline and repeats it for every item in
a collection — for example, every email ID in a list, every file in a
directory, every row in a CSV. The loop runs one iteration at a time,
sequentially. Each iteration's output is accumulated into a growing
results collection that subsequent stages can access.

The LOOP stage specifies: the input collection (from a previous stage's
output), the sub-pipeline stages to repeat per item, and the accumulation
strategy (append, merge, or structured list).

Full loop processing behavior is described in Section 10.

---

## 5. Workflow Structure — Linear, Branching, and Parallel

### 5.1 Linear Workflows

The simplest structure: stages execute one after another in sequence.
Each stage's output feeds directly to the next. This covers the majority
of single-path tasks.

```
Stage 1 → Stage 2 → Stage 3 → Stage 4 → Stage 5
```

### 5.2 Branching Workflows

When the planner identifies that a task has two or more independent paths
based on a condition, it inserts a CONDITION stage. Each branch is a
self-contained sub-pipeline. After all branches complete, their outputs
are merged and execution continues on the main path.

```
Stage 1 → Stage 2 (CONDITION)
                 ├── Branch A: Stage 3a → Stage 4a
                 └── Branch B: Stage 3b
                 ↓
           Stage 5 (MERGE) → Stage 6
```

### 5.3 Parallel Execution

When the planner identifies two or more sub-tasks that are completely
independent of each other — meaning neither needs the other's output to
begin — it can mark them as parallel branches. These run simultaneously,
and execution continues only after all parallel branches complete.

Example: "Read emails AND check today's calendar AND get today's news"
→ Three independent MCP_CALL stages that can all run in parallel:

```
Stage 1 (PLANNER)
      │
      ├──── [parallel] Stage 2a: MCP_CALL (read emails)
      ├──── [parallel] Stage 2b: MCP_CALL (read calendar)
      └──── [parallel] Stage 2c: MCP_CALL (get news)
                              ↓ (all complete)
              Stage 3: LLM_SPECIALIST (synthesize all three)
```

### 5.4 Nested Loops in Branches

A LOOP stage can exist inside a branch, and branches can exist inside a
loop. The planner can construct arbitrarily deep nested pipelines up to
10 stages deep, with each level of nesting clearly visible in the plan
document and the live execution display.

---

## 6. Model Capability Registry

### 6.1 What It Is

The Model Capability Registry is a per-alias tag system stored in
`$XDG_CONFIG_HOME/anythink/model_capabilities.yaml`. Every model alias
the user has configured can have a set of capability tags that describe
what it is good at. These tags are the basis for how the Meta-Router
(Section 7) assigns models to stages.

### 6.2 Capability Tags

Tags are free-form lowercase strings. The following are the pre-defined,
system-recognized tags that the planner and router know how to match
against stage requirements:

| Tag | Stage Affinity | Meaning |
|---|---|---|
| `planning` | PLANNER | Strong at decomposing tasks into structured steps |
| `reasoning` | PLANNER, CONDITION | Strong at logical reasoning and decision-making |
| `summarization` | LLM_SPECIALIST | Strong at condensing long content |
| `extraction` | LLM_SPECIALIST | Strong at pulling specific data from text |
| `code` | LLM_SPECIALIST | Strong at reading, writing, debugging code |
| `code-review` | LLM_SPECIALIST | Specialized for code quality analysis |
| `classification` | LLM_SPECIALIST, CONDITION | Strong at categorizing content |
| `translation` | LLM_SPECIALIST | Strong at language translation |
| `writing` | LLM_SPECIALIST | Strong at composing readable prose |
| `analysis` | LLM_SPECIALIST | Strong at data analysis and insight |
| `long-context` | Any LLM | Can handle very large inputs (100K+ tokens) |
| `multimodal` | LLM_SPECIALIST | Can process images alongside text |
| `fast` | Any LLM | Optimized for speed over quality |
| `high-quality` | Any LLM | Optimized for quality over speed |

Users can also define custom tags freely — the system stores them and
the planner will see them in the manifest, even if they are not in the
pre-defined list.

### 6.3 Managing Tags

Tags are set per alias in the interactive `/workflow registry` menu or
directly in `/settings` → Workflow → Model Registry:

```
/workflow registry                   Open the model capability registry
/workflow registry set local1 summarization reasoning long-context
/workflow registry add local1 extraction
/workflow registry remove local1 fast
/workflow registry show local1       Show tags for one alias
/workflow registry list              Show all aliases and their tags
```

### 6.4 Tag Inheritance

When the user does not assign any tags to a model alias, the registry
infers a default tag set based on the underlying model name — using a
bundled lookup table of well-known model families and their known strengths.
For example, `mistral:7b` defaults to `["summarization", "extraction"]`,
`deepseek-coder:*` defaults to `["code", "code-review"]`, and
`llama3.2:8b` defaults to `["planning", "reasoning", "summarization"]`.

User-assigned tags always override inferred defaults entirely.

---

## 7. Model Selection & Meta-Router

### 7.1 Three Assignment Modes

Every LLM_SPECIALIST stage in a workflow has a model assignment that comes
from one of three sources, in priority order:

**Mode 1 — User-explicit assignment:** The user explicitly names a model
alias for this stage, either in the plan edit step or in a saved workflow
definition. This overrides everything else.

**Mode 2 — Planner assignment:** The planner reads the stage's task, looks
up which available models have matching capability tags, and selects the
best match based on tag overlap and context window suitability. The planner
writes its selection into the plan document for the user to see and optionally
override during the plan edit step.

**Mode 3 — Meta-Router auto-selection:** When the user accepts the plan
without editing model assignments, and the planner has left any stage
unassigned (which should not happen but is handled gracefully), the
Meta-Router selects the best available model using the same tag-matching
logic at runtime.

### 7.2 Meta-Router Selection Logic

The Meta-Router selects a model for a stage using the following decision
sequence:

```
1. Identify the stage's required capability tag(s) from the plan
2. Filter the model registry to aliases that have all required tags
3. From that filtered list:
   a. Remove models whose context window is smaller than the
      estimated input size for this stage
   b. Prefer local models over cloud if both are available
      and the task does not explicitly require cloud quality
   c. Among remaining candidates, prefer the model the user
      has used most recently for this tag type (usage history)
   d. If still tied, prefer the model with the larger context window
4. If no model has all required tags, relax to partial tag match
   and flag the assignment as "best available" in the plan
5. If no model matches at all, insert a USER_APPROVAL stage before
   this stage asking the user to pick a model manually
```

### 7.3 User Can Always Override

At every stage of the plan edit step, the user can change any model
assignment — selecting from a list of all configured aliases with
compatible tags highlighted and incompatible ones shown in muted style.

---

## 8. Fallback Chain System

### 8.1 Per-Alias Fallback

Every model alias in the registry can have an assigned fallback alias.
If a model fails during workflow execution — the local server is down,
the cloud API returns an error, the model is not pulled — the engine
automatically substitutes the fallback and continues without interrupting
the workflow.

Fallbacks are set in the Model Capability Registry:

```
/workflow registry fallback google2 local-summarizer
/workflow registry fallback gpt4o local-planner
```

### 8.2 Fallback Chain Depth

Fallbacks can chain — alias A falls back to alias B, which falls back
to alias C. The engine traverses the chain until a working model is found
or the chain is exhausted.

### 8.3 When All Fallbacks Are Exhausted

If every model in the fallback chain for a stage is unavailable, the engine
pauses at that stage and inserts a runtime USER_APPROVAL prompt showing
the list of all currently available models and asking the user to select
one to use for this stage only:

```
╭─ ⚠ Model Unavailable ─────────────────────────────────────────────╮
│                                                                    │
│  Stage 3b (summarize email) — model "google2" failed:            │
│  Gemini API returned 429 (rate limit).                            │
│  Fallback "local-summarizer" (mistral:7b) — Ollama not running.  │
│                                                                    │
│  Available models:                                                │
│  [1] local-planner (llama3.2:8b)    tags: planning, reasoning    │
│  [2] local-coder (deepseek-coder)   tags: code, code-review      │
│                                                                    │
│  Select a model to use for this stage, or [Abort] to stop.       │
╰────────────────────────────────────────────────────────────────────╯
```

The workflow resumes with the user's selected model. The substitution is
logged in the execution log (Section 14).

---

## 9. Context Pipeline Between Stages

### 9.1 What Gets Passed

Each stage receives exactly one input: the **optimized output of the
previous stage**, processed by the Stage Output Optimizer (Section 11)
to be maximally useful to the receiving model or tool. The original user
message and the planner's plan are not re-sent to every stage — only the
immediately relevant data flows forward.

### 9.2 Named Output Fields

Every stage's output is a named dictionary, not a raw string. This allows
downstream stages and branches to reference specific fields rather than
the entire output blob. For example, an MCP_CALL stage reading emails
produces:

```
{
  "email_list": [...],
  "email_count": 50,
  "fetch_timestamp": "2025-06-18T14:32:00"
}
```

A downstream stage can reference `email_list` specifically rather than
receiving the entire raw output.

### 9.3 Context Quality Over Speed

The MMWE is designed with the explicit principle that **context quality is
never sacrificed for speed**. If passing full, untruncated data to a stage
would exceed its model's context window, the engine does not silently
truncate — it takes one of these actions, in order:

1. Switch to a model with a larger context window (from the same tag group)
2. Split the data and process it in a LOOP stage (Section 10)
3. Summarize only the overflow portion using a fast summarization model,
   keeping the rest intact
4. Ask the user how to proceed

Silent truncation never occurs. Data loss is never acceptable.

---

## 10. Loop Processing for Large Datasets

### 10.1 When Loops Are Used

The planner automatically inserts a LOOP stage when it detects that
the data from an MCP_CALL stage is a collection of items (emails, files,
rows, URLs) and the subsequent LLM_SPECIALIST stage would need to process
each item individually to produce high-quality output.

The email example is the canonical case: reading and summarizing 50 emails
as a single batch would either exceed the model's context window or produce
poor quality summaries due to content mixing. Processing them one at a time
produces a high-quality summary for each individual email.

### 10.2 Loop Execution Behavior

The LOOP stage executes its sub-pipeline once per item in the input
collection. Iterations are strictly sequential — the next iteration does
not begin until the current one completes. This is intentional: it ensures
consistent quality, avoids resource contention on local model servers,
and produces predictable progress reporting.

### 10.3 Loop Progress Display

The live display shows per-iteration progress so the user always knows
exactly where execution is in a long loop:

```
╭─ ⚙ Loop — Stage 3 ────────────────────────────────────────────────╮
│  Processing email 12 of 50                                         │
│  ████████░░░░░░░░░░░░░░░░░░░░  24%                               │
│                                                                    │
│  ✓ Email 11: "Project update from Sarah" — summarized in 1.2s     │
│  ◐ Email 12: "Q3 budget review — attached spreadsheet"            │
│                                                                    │
│  Elapsed: 14m 22s   Estimated remaining: ~45m                     │
│  [Pause]  [Skip this item]  [Stop loop]                           │
╰────────────────────────────────────────────────────────────────────╯
```

### 10.4 Loop Controls

During loop execution, the user has three mid-loop controls available
at all times:

**Pause** — Suspends the loop after the current iteration completes.
The workflow state is fully preserved. The user can resume with `[Continue]`
at any time.

**Skip this item** — Marks the current item as skipped (with a reason
the user can optionally enter) and moves to the next iteration. The
skipped item is noted in the execution log.

**Stop loop** — Ends the loop after the current iteration and passes
all accumulated results so far (complete, not partial) to the next stage.
This allows the user to abort a 50-email loop at email 20 if they have
enough summaries, without losing the 20 that were already completed.

### 10.5 Accumulated Results

After every iteration completes, its output is appended to an accumulator.
The accumulator grows throughout the loop and is the output passed to
the next stage when the loop finishes. It is structured as a list —
one entry per completed iteration — with the item identifier and the
stage output for that iteration.

---

## 11. Stage Output Optimizer

### 11.1 What It Does

Between every two stages, the Stage Output Optimizer transforms the
upstream stage's raw output into the optimal input format for the
downstream stage. It runs automatically — the user never triggers it
manually — and its actions are logged in the execution log.

### 11.2 What the Optimizer Does

The optimizer's job is to ensure that every stage receives exactly the
information it needs in exactly the format that makes it easiest to
process correctly:

**For LLM_SPECIALIST stages:** The optimizer prepends a concise task
instruction to the data — a one- to two-sentence description of what
the downstream model is being asked to do with it, plus what format
the output should be in. This instruction is assembled from the plan's
stage definition and ensures the specialist model understands its role
without needing to see the full original user message.

**For MCP_CALL stages:** The optimizer extracts the specific fields
from the previous stage's output that the MCP tool parameters need,
discarding irrelevant fields, and formats them as clean parameter values.

**For FORMATTER stages:** The optimizer identifies what kind of content
is arriving (prose, list, structured data, mixed) and passes formatting
hints to the formatter.

**For LOOP stages:** The optimizer splits the collection into individual
items and sets up the per-iteration context correctly.

### 11.3 No Silent Information Loss

The optimizer may transform the format of data but never discards content
that might be relevant to the downstream stage. When in doubt about
relevance, it includes rather than excludes. Only clearly irrelevant
metadata (internal timing fields, stage numbers, debug markers) is
stripped from the forward-passed context.

---

## 12. User Visibility — Live Stage Display

### 12.1 The Live Execution Panel

When a workflow is running, a persistent live execution panel occupies
the top portion of the conversation area, above the standard chat
bubbles. It shows the current stage, its status, and a compact summary
of all completed stages:

```
╭─ ▶ Workflow Running — "Read and summarize inbox emails" ──── 14m22s╮
│                                                                     │
│  ✓ Stage 1 · PLANNER          Plan created in 4.2s                │
│  ✓ Stage 2 · MCP_CALL         50 emails fetched from Gmail        │
│  ✓ Stage 2.5 · USER_APPROVAL  User confirmed: proceed             │
│  ◐ Stage 3 · LOOP             Email 12/50 — summarizing...        │
│    ◐ Stage 3a · MCP_CALL      Reading email 12...                 │
│    ─ Stage 3b · LLM_SPECIALIST (pending)                          │
│  ─ Stage 4 · FORMATTER        (pending)                           │
│  ─ Stage 5 · MCP_CALL         (pending)                           │
│                                                                     │
│  [⏸ Pause]  [⏹ Stop]  [📋 View log]                               │
╰─────────────────────────────────────────────────────────────────────╯
```

### 12.2 Stage Status Icons

| Icon | Meaning |
|---|---|
| `◐` (spinning) | Currently executing |
| `✓` | Completed successfully |
| `✕` | Failed — model or tool error |
| `⚠` | Completed with warning or fallback used |
| `⏸` | Paused — waiting for user |
| `─` | Not yet started |
| `↷` | Skipped (loop skip or condition branch not taken) |

---

## 13. Intermediate Result Display

### 13.1 Every Stage Result Is Shown

When each stage completes, its output is shown in the conversation area
as a system bubble before the next stage begins. This gives the user
full visibility into what each stage produced — they never have to wait
for the entire workflow to finish to see what's happening:

```
╭─ ✓ Stage 3b · LLM_SPECIALIST · email 12/50 ─ mistral:7b · 1.2s ─╮
│                                                                    │
│  Summary:                                                          │
│  The Q3 budget review from Finance requests input on the          │
│  department's projected spend for October–December, with a        │
│  deadline of Friday. An attached spreadsheet requires completion. │
│                                                                    │
╰────────────────────────────────────────────────────────────────────╯
```

### 13.2 Collapsed by Default After Accumulation

Once a LOOP stage accumulates more than 5 completed iterations, older
iteration result bubbles collapse automatically to a single-line summary
to keep the conversation area manageable:

```
 ✓ Emails 1–10: summarized  [expand to read]
 ✓ Emails 11–20: summarized  [expand to read]
 ◐ Email 21: summarizing...
```

The collapsed bubbles are always expandable — no results are discarded
from the conversation view.

---

## 14. Workflow Execution Log

### 14.1 What It Is

At the end of every workflow — whether it completes, is aborted, or
fails — Anythink generates a complete **workflow execution log** as a
plain text file. This is a permanent, human-readable record of everything
that happened: every stage, every model call, every MCP tool invocation,
every result, every timing measurement, every fallback, and every user
decision.

### 14.2 Log File Location

```
$XDG_DATA_HOME/anythink/workflow_logs/
  YYYY-MM-DD_HHMMSS_<workflow-name>.log
```

Example: `2025-06-18_143200_email-summary.log`

### 14.3 Log Contents

The log is structured in clearly delimited sections:

**Header block:**
- Workflow name (user-defined or auto-generated)
- Trigger: the original user message
- Start time and end time
- Total duration
- Completion status (completed / aborted / failed)
- Models used (one line each with stage reference)
- MCP servers called

**Per-stage blocks (one per stage, in execution order):**
- Stage number and type
- Stage start and end timestamps
- Duration
- Model used (for LLM stages) or tool called (for MCP stages)
- Input summary (field names and sizes, not full content)
- Full output (complete text, not truncated)
- Any fallback events
- Any user decisions

**Loop block (when a LOOP stage ran):**
- Total iterations planned
- Iterations completed
- Iterations skipped
- Iterations failed
- Per-iteration summary (item identifier + duration + one-line result)

**Error block (if any stage failed):**
- Exact error message
- Whether it was handled by fallback
- Whether user was prompted

**Final output block:**
- The complete final output of the last stage, verbatim

### 14.4 Log Shown to User After Completion

When a workflow completes, the final result is shown in the chat, and
a notification line below it reads:

```
 📋 Full execution log saved: ~/email-summary_2025-06-18.log
    [Open in editor]
```

Pressing `[Open in editor]` opens the log file in the system's default
text editor — using the same mechanism as the `/session open` shortcut
from V2.1.

---

## 15. User Control During Execution

### 15.1 Stopping a Workflow

The user can stop a running workflow at any time with `[⏹ Stop]` in the
live panel, or via the keyboard shortcut configured in the shortcut hint
bar. When Stop is pressed:

1. The current stage completes its current atomic operation (e.g., the
   current MCP call completes, the current model token stream finishes)
2. No further stages start
3. All accumulated results up to the stop point are preserved in the
   execution log
4. The user is shown a summary: "Workflow stopped at Stage 3b (email 12/50).
   12 email summaries were completed and are available in the log."

### 15.2 Pausing and Resuming

`[⏸ Pause]` suspends the workflow after the current stage operation
completes. The workflow state — all accumulated results, the current
loop position, which stages are pending — is fully preserved in memory.
The user resumes with `[▶ Continue]`. There is no timeout on a paused
workflow.

### 15.3 Aborting the Plan Before Execution

At the plan review step (before execution begins), the user can:
- `[▶ Run]` — start execution
- `[✎ Edit Plan]` — modify the plan (Section 20)
- `[🔬 Dry Run]` — see what would happen without executing (Section 16)
- `[✕ Cancel]` — discard the plan entirely and return to normal chat

---

## 16. Dry-Run Mode

### 16.1 What It Shows

Dry-run mode executes the entire planning phase but replaces every MCP
call and LLM inference call with a simulation that shows **exactly what
would happen** without actually doing it:

```
╭─ 🔬 Dry Run — "Read and summarize inbox emails" ─────────────────╮
│                                                                    │
│  Stage 2 · MCP_CALL (simulated)                                   │
│  ─────────────────────────────────────────────────────────────── │
│  Would call: gmail.list_inbox(max_results=50)                     │
│  Expected output: List of ~50 email IDs                           │
│  No actual network request made.                                  │
│                                                                    │
│  Stage 3 · LOOP (simulated — 50 iterations)                       │
│  ─────────────────────────────────────────────────────────────── │
│  Per iteration:                                                   │
│    Stage 3a: Would call gmail.read_email(email_id)               │
│    Stage 3b: Would call mistral:7b to summarize                  │
│  Total MCP calls: 51 (1 list + 50 reads)                         │
│  Total LLM calls: 50                                             │
│                                                                    │
│  Stage 5 · MCP_CALL — ⚠ DESTRUCTIVE (simulated)                 │
│  ─────────────────────────────────────────────────────────────── │
│  Would call: filesystem.write_file                               │
│    path: ~/email_summaries.md                                    │
│    content: [output of Stage 4 — ~5,000 chars estimated]        │
│  WARNING: This would overwrite the file if it already exists.    │
│                                                                    │
│  Estimated duration:  ~8–12 minutes                              │
│  Estimated MCP calls: 51                                         │
│  Estimated LLM calls: 50                                         │
│  Estimated cost:      $0.00 (all local models)                   │
│                                                                    │
│  [▶ Run for real]   [✕ Cancel]                                   │
╰────────────────────────────────────────────────────────────────────╯
```

### 16.2 Dry Run Does Not Execute Anything

No MCP tools are called, no models are invoked, no files are written,
no network requests are made. The simulation uses the plan structure and
expected output shapes to produce the preview.

---

## 17. Destructive Operation Guards

### 17.1 Always-On, Cannot Be Disabled

Destructive operations always require explicit user confirmation —
regardless of the global autonomy mode, regardless of whether the
workflow is in "auto" mode, regardless of whether the user has set
broad permissions elsewhere. This guard cannot be turned off.

### 17.2 What Counts as Destructive

The following MCP tool categories are always treated as destructive:

- File system: `write_file`, `delete_file`, `delete_folder`, `move_file`,
  `rename_file` (overwrite risk), `copy_file` (disk space risk)
- Email: `send_email`, `delete_email`, `move_email`
- Calendar: `create_event`, `delete_event`, `update_event`
- System: any Windows OS tool that changes settings, kills processes,
  or modifies the registry
- Any external MCP tool whose tool definition includes the `DESTRUCTIVE`
  marker in the manifest

### 17.3 The Approval Prompt for Destructive Stages

When workflow execution reaches a stage containing a destructive operation,
it always pauses and shows:

```
╭─ ⚠ Destructive Operation — Approval Required ─────────────────────╮
│                                                                    │
│  Stage 5 is about to:                                             │
│                                                                    │
│  Write file: ~/email_summaries.md                                │
│  Content size: ~5,200 characters                                  │
│  ⚠ This will overwrite the file if it already exists.            │
│                                                                    │
│  [✓ Approve — run this stage]   [↷ Skip — continue without it]   │
│  [⏹ Stop — end workflow here]                                     │
│                                                                    │
╰────────────────────────────────────────────────────────────────────╯
```

Three choices are always available: approve the operation, skip it and
continue the remaining workflow stages, or stop the workflow entirely.

---

## 18. Dynamic Workflows — Natural Language Trigger

### 18.1 One-Off, No Pre-Definition

A dynamic workflow is created on-the-fly from a natural language task
description. The user does not define any stages, models, or structure
ahead of time — the planner creates everything from the task description
and the manifest.

```
/workflow run "Find all Python files in my project folder that have
no docstrings and add a basic docstring to each one"
```

The planner reads this, produces a complete plan, and presents it for
review. If the user runs it once and never again, no workflow definition
is saved.

### 18.2 Save After Run

After a dynamic workflow completes, the user is offered the option to
save the generated plan as a named, reusable workflow:

```
 ✓ Workflow complete.
   [💾 Save as named workflow] to reuse this plan in future sessions.
```

---

## 19. Named & Reusable Workflows

### 19.1 Defining a Named Workflow

Named workflows are created in two ways:

**From a completed dynamic workflow:** Accept the "Save as named workflow"
prompt, enter a name, and the plan is saved exactly as it ran.

**From the wizard:** `/workflow new` opens a step-by-step wizard where
the user defines each stage explicitly — adding stages, assigning models,
defining conditions and branches. The wizard does not require the planner
to run — it is a purely manual definition tool.

### 19.2 Running a Saved Workflow

```
/workflow run email-summary
/workflow run "email-summary"
/workflow run email-summary --dry-run
```

### 19.3 Workflow Storage

Named workflows are stored at:

```
$XDG_CONFIG_HOME/anythink/workflows/<name>.yaml
```

Each YAML file contains the complete stage definitions, model assignments,
fallback chains, condition expressions, and loop configurations for that
workflow. The file is human-readable and editable directly if the user
prefers text editing to the TUI editor.

---

## 20. Workflow Editing

### 20.1 Plan Edit at Runtime

When the user presses `[✎ Edit Plan]` at the plan review step, the plan
opens in an interactive editor with the following operations available
per stage:

- **Change model** — pick a different alias from a filtered list
- **Change tool** — modify which MCP tool is called and its parameters
- **Add stage** — insert a new stage before or after this one
  (choosing from all stage types)
- **Remove stage** — delete a stage from the plan
- **Reorder stages** — move a stage up or down
- **Edit condition** — modify the condition expression for CONDITION stages
- **Edit loop target** — change the collection field a LOOP stage iterates over
- **Edit formatter output** — change the format type for FORMATTER stages

### 20.2 Editing a Saved Workflow

```
/workflow edit email-summary
```

Opens the same interactive editor for a saved workflow. Changes are saved
back to the YAML file when the user confirms. The previous version is
automatically backed up as `<name>.yaml.bak`.

---

## 21. The `/workflow` Command Namespace

### 21.1 Core Commands

```
/workflow run "<task>"         Create and run a dynamic workflow from description
/workflow run <name>           Run a saved named workflow
/workflow new                  Open the named workflow definition wizard
/workflow list                 List all saved named workflows
/workflow show <name>          Display the full stage definition of a workflow
/workflow edit <name>          Open a saved workflow in the interactive editor
/workflow delete <name>        Delete a saved workflow
/workflow rename <old> <new>   Rename a saved workflow
```

### 21.2 Execution Control

```
/workflow stop                 Stop the currently running workflow
/workflow pause                Pause the currently running workflow
/workflow resume               Resume a paused workflow
/workflow status               Show the current running workflow's stage and progress
```

### 21.3 Dry Run & Manifest

```
/workflow run <task/name> --dry-run   Run in dry-run mode (no execution)
/workflow manifest show               Print the current capability manifest
/workflow manifest refresh            Regenerate the manifest from live state
/workflow manifest path               Show the manifest file path
```

### 21.4 Model Registry

```
/workflow registry                    Open the model capability registry menu
/workflow registry list               List all aliases with their tags
/workflow registry show <alias>       Show tags for one alias
/workflow registry set <alias> <tags…>   Replace all tags for an alias
/workflow registry add <alias> <tag>  Add one tag to an alias
/workflow registry remove <alias> <tag>   Remove one tag from an alias
/workflow registry fallback <alias> <fallback>   Set fallback alias
```

### 21.5 Log Access

```
/workflow logs                 List all workflow execution logs
/workflow logs show <name>     Open a specific log in the system editor
/workflow logs last            Open the most recent execution log
```

---

## 22. Integration With Existing Anythink Systems

### 22.1 Model Alias System

The MMWE uses the existing model alias system (V1 core) exactly as-is.
Every alias configured by the user — with its provider, underlying model,
context window, and generation parameters — is a valid assignment target
for any LLM_SPECIALIST stage. The planner reads aliases from the
capability manifest. The engine uses the existing provider abstraction
to invoke whichever model is assigned.

### 22.2 MCP Manager

The MMWE calls MCP tools through `ctx.mcp_manager.call_tool()` — the
same dispatch method used by existing `/mcp call` commands. No new tool
invocation path is introduced. All existing tool error handling, result
formatting, and `MCPCallResult` types apply unchanged.

### 22.3 Session History

Workflow execution is recorded in the session history as a special
workflow entry — not as regular conversation turns. The workflow's trigger
message, final result, and execution log path are stored. The session's
plain text file shows the workflow clearly labeled, separate from
normal chat turns.

### 22.4 Debug Mode

When debug mode (V3.2) is active, the MMWE streams additional debug
data to the debug side panel: per-stage token counts, model latencies,
context sizes going into each stage, optimizer transformations applied,
fallback events, and routing decisions. All MMWE events appear as a
new debug category in the debug side panel labeled `[WORKFLOW]`.

### 22.5 Spend Tracking

Every LLM call made by the MMWE is counted in the existing spend tracker
(V3). The spend display in the HUD and `/cost` command include workflow
LLM usage, attributed to the individual model alias used at each stage.

---

## 23. New Files & Architecture

### 23.1 New Folder Structure

```
src/anythink/workflow/
├── __init__.py               Package marker
├── models.py                 WorkflowPlan, Stage, StageResult, LoopState, etc.
├── manifest.py               CapabilityManifest — build and refresh manifest.txt
├── planner.py                WorkflowPlanner — invoke planner model, parse plan output
├── registry.py               ModelCapabilityRegistry — tags, fallbacks, routing
├── router.py                 MetaRouter — select model for stage based on tags
├── engine.py                 WorkflowEngine — execute a plan stage by stage
├── optimizer.py              StageOutputOptimizer — transform output between stages
├── loop.py                   LoopExecutor — iterate sub-pipelines per item
├── log.py                    WorkflowLogger — write execution log to file
├── storage.py                WorkflowStorage — save/load named workflow YAML files
└── stages/
    ├── __init__.py
    ├── mcp_call.py           MCP_CALL stage executor
    ├── llm_specialist.py     LLM_SPECIALIST stage executor
    ├── user_approval.py      USER_APPROVAL stage gate
    ├── condition.py          CONDITION stage evaluator
    ├── formatter.py          FORMATTER stage transformer
    └── loop.py               LOOP stage wrapper
```

### 23.2 Key Data Models (`workflow/models.py`)

| Model | Purpose |
|---|---|
| `WorkflowPlan` | The complete parsed plan from the planner — list of Stage objects, branch definitions, loop definitions |
| `Stage` | One stage in the plan — type, assigned model or tool, task instruction, input field references, output field name |
| `Branch` | A conditional sub-pipeline — condition expression, list of stages for each branch arm |
| `LoopDefinition` | A loop configuration — input collection field, sub-pipeline stages, accumulation strategy |
| `StageResult` | Output of one stage — named output fields, raw content, timing, model/tool used, fallback used flag |
| `WorkflowState` | Live execution state — current stage index, accumulated results per stage, loop position |
| `WorkflowLog` | The complete log structure, serialized to the log file |

### 23.3 Relationship to Existing Systems

```
AppContext (startup)
│
├── ctx.mcp_manager          ← used by MCP_CALL stage executor (unchanged)
├── ctx.model_registry       ← model alias lookup (existing, unchanged)
├── ctx.workflow_registry    ← NEW: ModelCapabilityRegistry
│
└── ctx.workflow_engine      ← NEW: WorkflowEngine
      ├── WorkflowPlanner(manifest)
      ├── MetaRouter(workflow_registry)
      ├── StageOutputOptimizer()
      ├── LoopExecutor()
      └── WorkflowLogger(log_dir)
```

---

*Anythink — Think anything. Ask anything.*

*Version described: Multi-Model Workflow Engine (MMWE) — New Standalone Feature*
*Document last updated: June 2025*
