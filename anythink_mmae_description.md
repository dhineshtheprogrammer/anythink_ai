# Anythink — Multi-Model Answering Engine (MMAE)

> A real-time query intelligence layer that sits alongside the existing
> single-model chat. When activated per session, it intercepts every user
> message, detects whether it spans multiple specialist domains, routes
> sub-questions to the right models sequentially, quality-gates every response,
> combines everything into a single unified answer, and optionally formats the
> output — all within one conversational turn. The user sees one clean answer
> with a collapsible section showing exactly what happened underneath.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [How MMAE Differs from MMWE](#2-how-mmae-differs-from-mmwe)
3. [Per-Session Toggle](#3-per-session-toggle)
4. [The Built-In Category System](#4-the-built-in-category-system)
5. [Category-to-Model Registry](#5-category-to-model-registry)
6. [The Router Model](#6-the-router-model)
7. [Question Analysis & Category Detection](#7-question-analysis--category-detection)
8. [Question Splitting](#8-question-splitting)
9. [Context Preservation During Splitting](#9-context-preservation-during-splitting)
10. [Sequential Specialist Execution](#10-sequential-specialist-execution)
11. [Temporary Response Storage](#11-temporary-response-storage)
12. [Quality Gate — 50% Threshold](#12-quality-gate--50-threshold)
13. [The Combiner Model](#13-the-combiner-model)
14. [Combiner Modes — Stitch vs Intelligent Merge](#14-combiner-modes--stitch-vs-intelligent-merge)
15. [The Output Formatter Model](#15-the-output-formatter-model)
16. [Supported Output Formats](#16-supported-output-formats)
17. [User Visibility — Expandable Response Section](#17-user-visibility--expandable-response-section)
18. [Debug Panel Integration](#18-debug-panel-integration)
19. [Fallback Model System](#19-fallback-model-system)
20. [Single-Model Passthrough](#20-single-model-passthrough)
21. [The `/smart` Command Namespace](#21-the-smart-command-namespace)
22. [Settings Integration](#22-settings-integration)
23. [New Files & Architecture](#23-new-files--architecture)
24. [Integration With Existing Anythink Systems](#24-integration-with-existing-anythink-systems)

---

## 1. System Overview

### 1.1 What the MMAE Does

The Multi-Model Answering Engine (MMAE) is a per-session, toggleable query
intelligence layer that enhances every conversational response when active.
On receiving a user message, it performs the following sequence entirely
within a single response turn:

```
User message received
        │
        ▼
Router Model — Analyse the question
        │
        ├── Single category or unclassifiable?
        │         └── Route to one specialist (or fallback)
        │
        └── Multiple categories detected?
                  └── Split into 2–5 sub-questions
                            │
                            ▼
                  Sequential Specialist Execution
                    (one model per sub-question, in order)
                            │
                            ▼
                  Quality Gate (50% threshold per response)
                            │
                            ▼
                  Temporary Response Storage
                            │
                            ▼
                  Combiner Model
                  (Stitch or Intelligent Merge — user setting)
                            │
                            ▼
                  Formatter Model (only if user requests a format)
                            │
                            ▼
                  Final unified response to user
                  + Collapsible specialist detail section
```

### 1.2 The Single-Turn Constraint

Everything the MMAE does happens within **one response turn**. The user
sends one message, receives one response. There are no intermediate
messages, no multi-turn plan review, no workflow stages visible in
the chat. The user sees a single clean answer with an optional expandable
section showing what happened internally.

This is the fundamental design difference from the MMWE — the MMAE
is fast, invisible, and turn-scoped. The MMWE is deliberate, user-guided,
and multi-turn.

---

## 2. How MMAE Differs from MMWE

| Dimension | MMAE | MMWE |
|---|---|---|
| **Activation** | Per-session toggle | Explicit `/workflow run` command |
| **Turn scope** | Single conversational turn | Multiple turns across a long task |
| **User control** | Automatic — user only sees output | User reviews, edits, approves plan |
| **Stage types** | Route → Specialist → Combine → Format | Planner, MCP, LLM, Loop, Condition, etc. |
| **MCP tool calls** | None — LLM-only | First-class pipeline stages |
| **Best for** | Complex questions needing specialist depth | Complex tasks needing tool execution |
| **Integration** | Standalone, alongside single-model chat | Standalone workflow system |
| **Output** | One unified chat response per turn | Multi-stage results + execution log |

Both systems are completely independent and do not share execution paths.
A user can have MMAE toggled on and use `/workflow run` independently in
the same session without either system affecting the other.

---

## 3. Per-Session Toggle

### 3.1 Default State

MMAE is **off by default** at the start of every session. The user must
explicitly enable it. This matches the design of the web search toggle —
a deliberate opt-in per session rather than an always-on background process.

A global default can be set in `/settings` → Smart Engine → Default state
(off/on), which controls what the toggle starts as when a new session begins.

### 3.2 Enabling and Disabling

```
/smart on         Enable MMAE for this session
/smart off        Disable MMAE — return to standard single-model chat
/smart toggle     Toggle between on and off
/smart status     Show current MMAE configuration for this session
```

### 3.3 HUD Indicator

When MMAE is active, the HUD displays a persistent indicator on its
second line alongside the existing Search and RAG indicators:

```
 Model: local1  │  Provider: Ollama ●  │  Context: ░░  │  🔍 Search: OFF  │  ✦ Smart: ON
```

The `✦ Smart: ON` indicator uses the theme's accent color when active
and the theme's muted color when off — consistent with every other
status indicator in the HUD.

---

## 4. The Built-In Category System

### 4.1 Nine Built-In Categories

The MMAE ships with nine pre-defined categories that the router recognises
out of the box. Each category has a name, a description used in the router's
system prompt to aid detection, and a default model assignment slot:

| # | Category Name | Internal Key | Description |
|---|---|---|---|
| 1 | **Math / Calculations** | `math` | Arithmetic, algebra, calculus, statistics, numerical reasoning, unit conversions |
| 2 | **Code / Programming** | `code` | Writing code, debugging, explaining code, code review, algorithms, technical implementation |
| 3 | **Writing / Creative** | `writing` | Essays, stories, emails, blog posts, copywriting, persuasive writing, creative prose |
| 4 | **Reasoning / Logic** | `reasoning` | Logical deduction, argument analysis, philosophical questions, structured thinking, multi-step reasoning |
| 5 | **Research / Factual** | `research` | Factual lookups, historical facts, definitions, explanations of concepts, "what is" and "how does" questions |
| 6 | **Data Analysis** | `data` | Interpreting datasets, trends, statistics, charting suggestions, spreadsheet logic, pattern identification |
| 7 | **Translation** | `translation` | Translating text between languages, language detection, multilingual paraphrasing |
| 8 | **Summarization** | `summarization` | Condensing long content, extracting key points, producing abstracts, TL;DR requests |
| 9 | **General / Conversational** | `general` | Greetings, casual chat, ambiguous questions, questions not fitting any other category |

### 4.2 The General Category as Fallback

`general` is a special category. Every question that the router cannot
classify into one of the other eight categories is automatically assigned
to `general`. The model assigned to `general` is the session-wide fallback
model that answers everything the router cannot confidently route elsewhere.

### 4.3 Category Detection Is Dynamic

The router does not apply simple keyword matching to detect categories.
It uses its own LLM inference to understand the semantic intent of the
question and match it against the category descriptions. A question like
"Is O(n log n) sort always faster than O(n²)?" is correctly classified
as `math` + `reasoning` + `code` through semantic understanding, even
though the words "math", "code", and "reasoning" do not appear in it.

---

## 5. Category-to-Model Registry

### 5.1 What It Is

The Category-to-Model Registry is a configuration table that maps each
of the nine categories to one or more model aliases. It is stored in:

```
$XDG_CONFIG_HOME/anythink/smart_registry.yaml
```

### 5.2 Default Registry (Auto-Populated)

When the user first enables MMAE, the registry is automatically populated
by reading the Model Capability Registry from MMWE and matching capability
tags to category keys:

| Tag (from MMWE registry) | Maps to Category |
|---|---|
| `math` | `math` |
| `code`, `code-review` | `code` |
| `writing` | `writing` |
| `reasoning` | `reasoning` |
| `research`, `factual` | `research` |
| `data`, `analysis` | `data` |
| `translation` | `translation` |
| `summarization` | `summarization` |
| `general`, `conversational` | `general` |

The alias with the highest tag-overlap for each category is assigned as
the primary model. All other aliases that partially match become secondary
candidates for fallback within that category.

### 5.3 User Override Per Category

The user can override any category's model assignment at any time:

```
/smart registry                      Open the interactive registry menu
/smart registry set math local-math-model
/smart registry set code local-coder
/smart registry set general local1   (sets the main fallback)
/smart registry show                 Show full category → model mapping
/smart registry show math            Show assignment for one category
/smart registry reset math           Reset one category to registry default
/smart registry reset all            Reset all to registry-driven defaults
```

### 5.4 One Model Can Cover Multiple Categories

A single model alias can be assigned to more than one category. For example,
a strong general-purpose 13B model might be assigned to `reasoning`,
`research`, and `general`. A specialized coder model is assigned only
to `code`. The registry stores whichever assignment the user or the
auto-population has set — no restriction on how many categories one
alias covers.

### 5.5 Combiner Model Assignment

The combiner is also assigned in the smart registry as a special slot:

```
/smart registry combiner local-general   Assign the combiner model
/smart registry combiner show            Show current combiner assignment
```

The combiner should always be a general-purpose model — strong at following
instructions, producing coherent prose, and merging information from multiple
sources. It should not be the same alias as any specialist.

---

## 6. The Router Model

### 6.1 What the Router Is

The router is a designated local model whose only job in the MMAE pipeline
is to **analyse the user's question, detect all applicable categories, and
produce a structured routing plan** — a compact JSON object listing which
categories were detected, which model handles each, and how the question
should be split (if at all).

The router is a very fast, lightweight model — its output is small and
structured, so it does not need to be the largest or most capable model
available. It runs before any specialist model and its latency directly
affects the user's perceived response time.

### 6.2 Router Model Assignment

```
/smart registry router local-planner
```

The router can share the same alias as the MMWE planner if that model
is well-suited (it typically is — both need structured reasoning and
output). The user can assign a different alias specifically for routing
if they prefer.

### 6.3 Router System Prompt

The router receives:

**Part 1 — Role definition:** A concise instruction to analyse the incoming
question, identify all applicable categories from the fixed list, determine
whether splitting is needed, generate rewritten sub-questions per category,
and output a structured routing JSON.

**Part 2 — Category catalogue:** The full list of nine categories with
their descriptions, so the router understands exactly what each category
covers.

**Part 3 — Current model assignments:** The live category-to-model map
from the smart registry, so the router knows which model is assigned to
each category and can reference them by alias in its output.

**Part 4 — Output schema:** The exact JSON format the router must produce.
Invalid or non-conforming output triggers a structured retry — the router
is called again with an error message explaining what was wrong in its
previous output.

### 6.4 Router Output Schema

The router always outputs a JSON object with this structure:

```json
{
  "complexity": "single",
  "categories_detected": ["code"],
  "routing_plan": [
    {
      "sub_question": "Give me Python code to call an API endpoint and return the JSON response.",
      "category": "code",
      "model_alias": "local-coder",
      "context_included": true
    }
  ],
  "reasoning_summary": "The question asks for a Python implementation. This is a pure code task. No splitting needed."
}
```

For a multi-category question:

```json
{
  "complexity": "multi",
  "categories_detected": ["math", "code"],
  "routing_plan": [
    {
      "sub_question": "What is 2 + 2?",
      "category": "math",
      "model_alias": "local-math",
      "context_included": true
    },
    {
      "sub_question": "Write Python code to make an HTTP GET request to an API and print the JSON response.",
      "category": "code",
      "model_alias": "local-coder",
      "context_included": true
    }
  ],
  "reasoning_summary": "The question has two independent parts: an arithmetic calculation and a code request. Split into 2 sub-questions and route to math and code specialists respectively."
}
```

The `reasoning_summary` field is what gets shown in the debug panel
(Section 18). It never appears in the user's final answer.

---

## 7. Question Analysis & Category Detection

### 7.1 Single vs Multi-Category Detection

The router's first determination is whether the question belongs to one
category or multiple. This is not a binary flag set by rules — it is a
judgment the router model makes based on the semantic content of the question:

- **Single category:** The entire question is best answered by one specialist.
  No splitting occurs. The question is sent as-is (with context) to that
  specialist.
- **Multi-category:** The question clearly contains two or more independent
  sub-problems that each require different specialist knowledge. Splitting occurs.
- **Unclassifiable:** The question does not meaningfully fit any of the eight
  non-general categories. No splitting occurs. The question is routed directly
  to the `general` fallback model.

### 7.2 Detection Is Semantic, Not Keyword-Based

The router does not use keyword lists or rule-based category matching.
It uses its own language understanding to detect category membership.
This means:

- A question entirely in French is classified as `translation` if it asks
  to be translated — not `general` just because it is non-English
- A question about "time complexity" is classified as `reasoning` + `code`,
  not `general`, even though it doesn't contain the words "reason" or "code"
- A casual greeting like "Hey, what's up?" is classified as `general` even
  though it could theoretically fit other categories

### 7.3 Confidence-Based Classification

The router assigns a confidence level to each detected category as part
of its internal reasoning. Categories detected with low confidence are not
included in the routing plan — the router favours fewer high-confidence
classifications over many uncertain ones. This prevents over-splitting
ambiguous questions into too many sub-questions.

---

## 8. Question Splitting

### 8.1 Maximum Split Count: 3–5

A single user question can be split into a maximum of **five sub-questions**.
If the router detects more than five distinct categories, it consolidates
the lowest-priority or most-related categories to stay within the limit.
The router's system prompt explicitly instructs it never to produce more
than five routing plan entries.

For the overwhelming majority of real-world questions, the split count
will be 2 or 3. Five is the ceiling for genuinely complex multi-domain
questions.

### 8.2 Sub-Question Rewriting

Each sub-question in the routing plan is a **rewritten version of the
relevant part of the original question**, optimised for the receiving
specialist. The rewrite makes the sub-question self-contained and clear,
removes references to other sub-topics that don't apply to this specialist,
and uses terminology and framing appropriate for that category.

Examples:

| Original Question | Specialist | Rewritten Sub-Question |
|---|---|---|
| "What is 2+2 and give me Python code to hit an API" | Math | "What is 2 + 2?" |
| "What is 2+2 and give me Python code to hit an API" | Code | "Write Python code to make an HTTP GET request to an API and return the JSON response." |
| "Summarize this text and translate it to French" | Summarization | "Summarize the following text in 3–4 sentences: [text]" |
| "Summarize this text and translate it to French" | Translation | "Translate the following English text to French: [text]" |

### 8.3 No Overlap Between Sub-Questions

The router ensures that no sub-question contains content that belongs to
another specialist's sub-question. Each sub-question covers exactly one
category's scope. This prevents the combiner from receiving duplicate or
redundant information about the same topic from different models.

---

## 9. Context Preservation During Splitting

### 9.1 Full Context Always Included

Every sub-question sent to a specialist is accompanied by the **full original
user message** as additional context — even when the sub-question is a
rewritten, focused version of only one part of the original. This ensures
that specialists always understand the broader intent behind their specific task.

For example, if the user asked "Give me Python code to hit a weather API
and explain what the response JSON means", the code specialist receives:

```
[ORIGINAL QUESTION]
Give me Python code to hit a weather API and explain what the response JSON means.

[YOUR TASK]
Write Python code to make an HTTP GET request to a weather API endpoint and
print the JSON response. Use the requests library. Include error handling.
```

The code specialist sees both — the full original and its specific sub-task.

### 9.2 Conversation History Is Always Included

Beyond the original question, each specialist also receives the relevant
recent conversation history (last 3–5 turns) as context — the same history
that the existing single-model chat uses. This ensures specialists are not
blind to what was discussed before and can produce contextually appropriate
responses.

### 9.3 Context Ordering Per Specialist Prompt

The specialist's prompt is structured in this order:

1. System prompt defining the specialist's role and what it is optimised for
2. Recent conversation history (last 3–5 turns)
3. The full original user question (labeled `[ORIGINAL QUESTION]`)
4. The specialist's specific rewritten sub-question (labeled `[YOUR TASK]`)
5. Any format instruction if the user explicitly requested a format

---

## 10. Sequential Specialist Execution

### 10.1 One at a Time, in Order

Specialists execute **strictly sequentially** — one after the other, in
the order listed in the routing plan. The next specialist does not start
until the previous one has completed and its response has passed the
quality gate (Section 12).

The order in the routing plan follows the natural logical sequence:
foundational or definitional answers come before dependent ones,
simpler tasks before more complex tasks within the same turn.

### 10.2 Why Sequential, Not Parallel

Sequential execution is the right choice for this system for three reasons:

**Quality over speed:** Local models (3B–8B) share hardware resources. Running
two models simultaneously on the same machine causes both to be slower and
produce lower-quality output than running them one at a time. Sequential
execution lets each specialist use the full available compute.

**Quality gate compatibility:** The quality gate (Section 12) may need to
retry a specialist with a different model if the first attempt scores below
the threshold. Retries are clean and predictable in sequential execution.

**Temporary storage simplicity:** Each specialist's complete, quality-checked
response is stored before the next starts. The combiner receives a clean,
ordered list of finalized responses. No race conditions, no partial results.

### 10.3 Execution Order Display

While specialists are executing, the live display (Section 17) shows which
specialist is currently running and which are queued:

```
╭─ ✦ Smart Engine ─────────────────────────────────────────────────╮
│  ✓ Router:   2 categories detected (math, code) in 0.8s         │
│  ✓ Specialist 1/2:  local-math (math) — answered in 1.4s        │
│  ◐ Specialist 2/2:  local-coder (code) — generating…            │
│  ─ Combiner:  (waiting)                                          │
╰──────────────────────────────────────────────────────────────────╯
```

---

## 11. Temporary Response Storage

### 11.1 What It Stores

As each specialist completes and passes the quality gate, its response is
stored in a **per-turn temporary response store** — an in-memory structure
that holds all specialist responses for the current turn until the combiner
processes them.

Each entry in the store contains:

| Field | Content |
|---|---|
| `slot` | Sequential position (1, 2, 3…) matching the routing plan order |
| `category` | The category this specialist answered |
| `model_alias` | The alias of the model that produced this response |
| `sub_question` | The rewritten sub-question that was sent to the specialist |
| `response` | The full text response from the specialist |
| `quality_score` | The score assigned by the quality gate |
| `retry_count` | How many retries were needed (0 for first-attempt success) |
| `duration_s` | Time taken by this specialist in seconds |

### 11.2 Combiner Receives the Full Store

When all specialists have completed, the entire temporary store is passed
to the combiner as a structured, attributed input — not just raw text.
The combiner sees every response alongside its metadata, so it knows which
model produced which part, in what order, and how confident the quality
gate was in each response.

### 11.3 Store Is Discarded After the Turn

The temporary response store exists only for the duration of one turn.
Once the combiner produces its output and the response is shown to the
user, the store is cleared. It is not persisted between turns. The raw
specialist responses are only accessible via the collapsible detail section
in the UI (Section 17) for as long as the session is open.

---

## 12. Quality Gate — 50% Threshold

### 12.1 What the Quality Gate Does

After each specialist model generates its response, the quality gate
evaluates the response and decides whether it is good enough to pass
to the temporary store or whether it should be retried.

The quality gate is not a separate LLM inference call — it is a set of
heuristic evaluations applied locally and instantly to the response text.
It runs in milliseconds and does not add meaningful latency.

### 12.2 Quality Score Calculation

The quality gate computes a composite score (0–100) from the following
heuristic checks:

| Check | Description | Weight |
|---|---|---|
| **Response length** | Is the response meaningfully long given the question complexity? Extremely short responses to complex questions lose points. | 20% |
| **Non-refusal** | Does the response actually attempt to answer the question, or does it refuse, express inability, or only acknowledge the question? Refusals score 0 on this check. | 30% |
| **Category coherence** | Does the response content match the category it was assigned? A `code` specialist returning only prose explanation scores low; one returning code blocks scores high. | 30% |
| **Completion signal** | Does the response end naturally (not mid-sentence, not cut off by token limit)? Truncated responses lose points. | 20% |

The composite score is a weighted sum of all four checks. The default
**pass threshold is 50%** — a score at or above 50 passes. Below 50 triggers
a retry.

### 12.3 Retry Behavior

When a response fails the quality gate:

**Step 1 — Retry with the same model (once):** The specialist is called
again with the same prompt. Transient issues (model warm-up, resource
contention) often resolve on a second call.

**Step 2 — Retry with the next available model for this category:** If the
same model fails twice, the quality gate checks the smart registry for
other models assigned to this category (secondary candidates). It tries
each one in order of registry priority.

**Step 3 — Fallback model:** If all category-specific models fail, the
quality gate routes this sub-question to the `general` fallback model.

**Step 4 — Accept and flag:** If even the fallback model fails the quality
gate, its response is accepted regardless and flagged with a
`⚠ low confidence` marker that the combiner and the user's expandable
section will display. The workflow never completely fails because of a
quality gate — it always produces some output.

### 12.4 Quality Score Visible in Debug Panel

The quality score for each specialist response is logged in the debug
panel (Section 18) when debug mode is active — showing the score, which
checks passed or failed, and whether a retry occurred.

---

## 13. The Combiner Model

### 13.1 Role of the Combiner

The combiner is a general-purpose model whose job is to take the structured
temporary response store — all specialist responses, with attribution — and
produce one coherent, unified answer. It knows exactly which model answered
which part and uses this information to appropriately weight and order
the content.

The combiner never adds new information from its own knowledge. Its role is
purely synthesizing and unifying what the specialists have already answered.
If a specialist's response is complete and well-formed, the combiner preserves
it faithfully.

### 13.2 The Combiner Is Always a Different Model

The combiner must be assigned a different model alias from any of the
category specialists. This is enforced by the registry — assigning the
same alias to both a category and the combiner slot produces a warning:

```
 ⚠ Combiner and math specialist are both assigned to "local-general".
   Consider assigning a different alias to the combiner for best results.
```

This is a warning, not an error — the user can proceed with the same model
if they choose — but the recommendation is always for a dedicated
general-purpose combiner alias.

### 13.3 Combiner System Prompt

The combiner receives:

1. A role definition explaining that it must combine multiple specialist
   responses into one unified answer, following the mode setting (Stitch
   or Intelligent Merge)
2. The full structured temporary store — each entry formatted as:
   ```
   [Specialist 1 — math — local-math (score: 92)]
   The answer to 2 + 2 is 4.

   [Specialist 2 — code — local-coder (score: 88)]
   Here is the Python code to hit an API:
   ```python
   import requests
   response = requests.get("https://api.example.com/data")
   print(response.json())
   ```
   ```
3. The combiner mode instruction (from the user's setting)
4. A reminder that the output must not reveal which models produced
   which parts — the attribution is internal only

---

## 14. Combiner Modes — Stitch vs Intelligent Merge

### 14.1 Two Modes, One Setting

The combiner operates in one of two modes, toggled in `/settings` →
Smart Engine → Combiner mode:

**Mode 1 — Stitch**
Concatenates specialist responses in the order they appear in the routing
plan, with a minimal transition between sections. The combiner adds
light connective text but does not rewrite or rephrase the specialists'
content. The result reads as clearly delineated sections addressing each
part of the question.

**Mode 2 — Intelligent Merge**
The combiner reads all specialist responses holistically and produces a
single flowing answer that integrates the information naturally. It may
reorder content, merge related points across sections, and write connecting
prose. The result reads as one unified response, not as joined sections.

### 14.2 When to Use Each Mode

**Stitch** is better when:
- The sub-questions are genuinely independent (math answer + code answer)
- The user wants to clearly see each part addressed separately
- Speed matters — Stitch prompts are shorter and produce output faster
- The specialist responses are already well-formed and complete

**Intelligent Merge** is better when:
- The sub-questions are related and share context
- A flowing answer reads better than separate sections
- The user asked a question that feels like one thing but spans categories

### 14.3 Format of the Setting

In `/settings` → Smart Engine → Combiner mode, the toggle shows:

```
 Combiner mode:  ◉ Stitch   ○ Intelligent Merge
```

The user can also switch mid-session:

```
/smart combiner stitch
/smart combiner merge
```

---

## 15. The Output Formatter Model

### 15.1 When the Formatter Runs

The formatter is a **separate, optional model stage** that runs after
the combiner — but only when one of two conditions is true:

**Condition A — User explicitly specifies a format in their message:**
The user's original question contains explicit format instructions, such as:
- "...as a markdown file"
- "...in a table"
- "...as a JSON object"
- "...give me just the code, no explanation"
- "...as a bullet list"

**Condition B — User has set a session-level format default:**
The user has run `/smart format <format>` earlier in the session, setting
a persistent format preference that applies to all MMAE responses until changed.

When neither condition is true, the combiner's output goes **directly to
the user** without any formatter stage. The formatter never runs speculatively.

### 15.2 The Formatter Is a Separate Model

The formatter is assigned its own model alias in the smart registry:

```
/smart registry formatter local-formatter
```

It can share the same alias as the combiner if the user prefers, but a
dedicated formatter alias allows the user to use a faster, lighter model
for this formatting-only task — since formatting does not require deep
reasoning, just instruction-following.

### 15.3 Format Detection From Question

When the user's question contains an explicit format request, the router
detects it during its analysis step and records the requested format in
the routing plan output. The formatter receives this format instruction
at the end of the pipeline. It does not re-read the user's original
question — it receives only the combiner's output and the format instruction.

### 15.4 Auto-Format Detection

When no explicit format is requested and no session default is set, the
formatter does **not** run. There is no auto-detection mode that silently
reformats output — if the user did not ask for a specific format, the
combiner's output is delivered as-is. This prevents the formatter from
unexpectedly restructuring answers the user was perfectly happy to receive
as prose.

---

## 16. Supported Output Formats

The formatter supports all seven user-specified formats. Each format is
detected by keyword from the user's message or by exact name in `/smart format`:

| Format | Trigger Keywords | Description |
|---|---|---|
| **Markdown Prose** | "markdown", "as markdown", "in markdown" | Full markdown with headings, bold, italics, code blocks, and lists |
| **Numbered / Bullet List** | "list", "bullet points", "numbered", "as a list" | Converts the response into a clean list structure |
| **Table** | "table", "as a table", "in a table", "comparison table" | Converts structured or comparative content into a pipe-delimited markdown table |
| **Code Only** | "just the code", "code only", "strip explanation", "no explanation" | Extracts all code blocks from the response and discards all prose explanation |
| **JSON / Structured Data** | "json", "as json", "structured", "as an object" | Converts the response into a valid JSON object or array |
| **Executive Summary** | "brief", "tldr", "summary only", "executive summary", "short" | Produces a 2–4 sentence condensed version of the full response |
| **Detailed Explanation** | "detailed", "verbose", "explain in detail", "full explanation" | Expands the response with additional depth, examples, and reasoning |

### 16.1 Session-Level Format Default

```
/smart format markdown         Set markdown as default for all MMAE responses this session
/smart format table            Set table as default
/smart format off              Remove session format default (formatter only on explicit request)
/smart format show             Show current session format setting
```

---

## 17. User Visibility — Expandable Response Section

### 17.1 What the User Sees

The user always sees one thing at the conversation level: the **final
combined (and optionally formatted) response** as a standard AI response
bubble — no visible routing, no model labels, no section dividers from
the combining process. The response reads as if it came from one model.

Appended below the response, like the sources section in web search, is a
compact single-line expandable detail section:

```
╭─ local-general (MMAE) ──────────────────────────── Ollama · just now ─╮
│                                                                         │
│  The answer to 2 + 2 is **4**.                                         │
│                                                                         │
│  Here is Python code to make an HTTP GET request to an API:            │
│                                                                         │
│  ┌─ python ─────────────────────────────────────────────────────────┐  │
│  │  import requests                                                  │  │
│  │  response = requests.get("https://api.example.com/data")         │  │
│  │  print(response.json())                                           │  │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  ✦ 2 specialists · combined by local-general  [expand]                 │
│                                         Ollama · just now  62 words ·  │
╰─────────────────────────────────────────────────────────────────────────╯
```

### 17.2 Collapsed State

The collapsed summary line shows:

```
 ✦ 2 specialists · combined by local-general  [expand]
```

This tells the user that MMAE was active and how many specialists contributed.
The combiner model is shown so the user knows what produced the final response.
No individual specialist aliases are shown in the collapsed state.

### 17.3 Expanded State

Pressing `[expand]` opens the full detail section showing:

- The router's category detection result
- Each specialist's sub-question, model alias, quality score, and full raw response
- The combiner's mode (Stitch / Intelligent Merge)
- The formatter applied (if any)
- Total MMAE turn duration

```
╭─ ✦ Smart Engine Detail ──────────────────────────────────────────────────╮
│                                                                           │
│  Router: detected 2 categories in 0.8s                        [collapse] │
│    Category 1: math   → local-math (llama3.2:3b)                         │
│    Category 2: code   → local-coder (deepseek-coder:6.7b)               │
│                                                                           │
│  Specialist 1: math · local-math (llama3.2:3b)                           │
│  Sub-question: "What is 2 + 2?"                                           │
│  Quality score: 94%   Duration: 1.4s   Retries: 0                       │
│  ─────────────────────────────────────────────────────────────────────── │
│  The answer to 2 + 2 is 4. This is a simple addition — the result is    │
│  four, which is an even positive integer.                                 │
│                                                                           │
│  Specialist 2: code · local-coder (deepseek-coder:6.7b)                 │
│  Sub-question: "Write Python code to make an HTTP GET request to an API" │
│  Quality score: 88%   Duration: 2.1s   Retries: 0                       │
│  ─────────────────────────────────────────────────────────────────────── │
│  import requests                                                           │
│  response = requests.get("https://api.example.com/data")                 │
│  print(response.json())                                                   │
│                                                                           │
│  Combiner: local-general · mode: Stitch · Duration: 1.2s                │
│  Formatter: not used (no format requested)                                │
│                                                                           │
│  Total MMAE duration: 5.5s                                               │
╰───────────────────────────────────────────────────────────────────────────╯
```

### 17.4 Sticky While Session Is Open

The expandable detail section remains accessible for as long as the session
is open. The user can expand and collapse it freely without affecting the
response content above it. When the session is closed or a new session starts,
the detail data is cleared — it is not persisted between sessions.

---

## 18. Debug Panel Integration

### 18.1 MMAE Events in the Debug Panel

When debug mode is active (`/debug on`), the MMAE streams all its internal
reasoning and decisions to the existing debug side panel as a dedicated
`[SMART]` event category — alongside `[WORKFLOW]`, `[RAG]`, and `[SEARCH]`
events already streamed there.

The debug panel shows MMAE events as they happen in real time — before the
final response appears in the conversation.

### 18.2 Events Streamed to Debug Panel

```
╭─ 🔬 Debug Panel · Level 2 ──────────────────────────────────────╮
│                                                                  │
│  ── [SMART] Turn #7 · 14:52:01 ────────────────────────────── │
│  Router invoked: local-planner                                  │
│  Categories detected: math (conf: 0.97), code (conf: 0.91)    │
│  Complexity: multi → splitting into 2 sub-questions             │
│  Reasoning: "Question contains arithmetic (2+2) and a code     │
│  implementation request. Independent domains. Splitting."       │
│                                                                 │
│  Sub-question 1 → local-math [math]                            │
│  Prompt: "What is 2 + 2?"                                      │
│  Context: included (original + history)                        │
│                                                                 │
│  Response 1 received · Quality score: 94% · PASS              │
│  Duration: 1.4s · Retries: 0                                   │
│                                                                 │
│  Sub-question 2 → local-coder [code]                           │
│  Prompt: "Write Python code to make an HTTP GET request..."    │
│                                                                 │
│  Response 2 received · Quality score: 88% · PASS              │
│  Duration: 2.1s · Retries: 0                                   │
│                                                                 │
│  Combiner invoked: local-general · Mode: Stitch               │
│  Duration: 1.2s                                                │
│                                                                 │
│  Formatter: not invoked (no format requested)                  │
│  Total MMAE: 5.5s                                              │
╰──────────────────────────────────────────────────────────────────╯
```

### 18.3 Reasoning Summary Always in Debug Panel

The router's `reasoning_summary` field from its JSON output is always
shown in the debug panel when debug mode is active. It never appears in
the conversation or in the expandable user section — it is strictly a
debug-mode diagnostic.

### 18.4 Debug Level Behavior

The MMAE events in the debug panel respect the active verbosity level:

- **Level 1:** Total duration, categories detected, model aliases used
- **Level 2:** All events listed in Section 18.2 above
- **Level 3:** Full prompt sent to each specialist, full router JSON output,
  raw quality gate check results per heuristic

---

## 19. Fallback Model System

### 19.1 Three Layers of Fallback

When the optimal model for a category is not available or fails the quality
gate, the system falls back through three layers before accepting a
low-confidence response:

**Layer 1 — Retry same model:** Call the same alias again (once). Handles
transient failures.

**Layer 2 — Secondary category models:** Try other aliases assigned to this
category in the registry (ordered by tag strength from the MMWE capability
registry).

**Layer 3 — General fallback:** Route the sub-question to the model assigned
to the `general` category. This is the final backstop that never fails —
the `general` model is always a broad-purpose model configured to handle
any question.

### 19.2 Fallback Events Are Logged

Every fallback event is:
- Shown in the debug panel (when debug mode is on)
- Noted in the expanded detail section (with a `⚠ fallback used` tag next to
  the specialist entry that triggered it)
- Not shown in the final combined response — the user's answer is unaffected

---

## 20. Single-Model Passthrough

### 20.1 When MMAE Does Not Split

When the router detects that a question belongs to only one category, the
MMAE does **not** introduce unnecessary routing overhead. Instead of
sending the question through the full split → specialist → combine pipeline,
it routes directly to that category's assigned specialist and delivers
the response without a combiner step.

This is called **single-model passthrough**. The specialist's response goes
directly to the formatter (if a format was requested) or directly to the
user (if not). No combiner is invoked.

The expandable detail section in this case shows:

```
 ✦ 1 specialist · local-coder (code)  [expand]
```

### 20.2 When MMAE Passes Through to the Default Session Model

When the router classifies a question as `general` (unclassifiable into
any specialist category), the question is routed to the model assigned to
the `general` category. This is functionally identical to a standard
single-model chat response — except the MMAE toggle is still on and the
response still appears with the `✦ 1 specialist · general model` footer.

---

## 21. The `/smart` Command Namespace

### 21.1 Toggle Commands

```
/smart on                    Enable MMAE for this session
/smart off                   Disable MMAE — return to single-model chat
/smart toggle                Toggle on/off
/smart status                Show full MMAE configuration for this session
```

### 21.2 Registry Commands

```
/smart registry              Open the interactive category registry menu
/smart registry show         Show full category → model mapping
/smart registry show <cat>   Show assignment for one category
/smart registry set <cat> <alias>    Assign a model to a category
/smart registry reset <cat>  Reset a category to registry-driven default
/smart registry reset all    Reset all categories to defaults
/smart registry router <alias>       Assign the router model
/smart registry combiner <alias>     Assign the combiner model
/smart registry formatter <alias>    Assign the formatter model
/smart registry fallback <alias>     Set the general fallback model
```

### 21.3 Combiner Commands

```
/smart combiner stitch       Set combiner mode to Stitch
/smart combiner merge        Set combiner mode to Intelligent Merge
/smart combiner show         Show current combiner mode
```

### 21.4 Format Commands

```
/smart format <format>       Set session-level output format default
/smart format off            Remove session format default
/smart format show           Show current format setting
```

### 21.5 Quality Gate Commands

```
/smart quality <0-100>       Set quality gate threshold (default 50)
/smart quality show          Show current threshold
```

---

## 22. Settings Integration

### 22.1 New Settings Under `/settings` → Smart Engine

The following settings are accessible from the interactive `/settings` menu
under a new **Smart Engine** category:

```
╭─ ⚙ Settings — Smart Engine ─────────────────────────────────────╮
│                                                                   │
│   Smart Engine                                                    │
│    ▸ Default state            OFF                                │
│    ▸ Combiner mode            Stitch                             │
│    ▸ Quality gate threshold   50%                                │
│    ▸ Max splits per question  5                                  │
│    ▸ Session format default   (none)                             │
│    ▸ Show detail section      ON                                 │
│                                                                   │
╰───────────────────────────────────────────────────────────────────╯
```

### 22.2 Show Detail Section Toggle

The `Show detail section` setting controls whether the collapsible
`✦ N specialists` footer appears below MMAE responses. When off, no
footer is shown — the response appears exactly as if it came from a single
model with no MMAE indication. When on (default), the footer is always
present and expandable.

---

## 23. New Files & Architecture

### 23.1 New Folder Structure

```
src/anythink/smart/
├── __init__.py               Package marker
├── models.py                 RoutingPlan, SubQuestion, SpecialistResponse,
│                             TemporaryStore, SmartResult
├── router.py                 RouterModel — invoke router LLM, parse output,
│                             handle schema validation and retry
├── registry.py               SmartRegistry — category-to-model map,
│                             CRUD for category assignments
├── executor.py               SequentialExecutor — run specialists one by one,
│                             interface with quality gate
├── quality.py                QualityGate — score response, manage retries
├── store.py                  TemporaryResponseStore — in-memory per-turn store
├── combiner.py               CombinerModel — invoke combiner LLM in Stitch
│                             or Intelligent Merge mode
├── formatter.py              FormatterModel — detect requested format,
│                             invoke formatter LLM
├── detector.py               FormatDetector — parse format requests from
│                             user message text
└── categories.py             Built-in category definitions, descriptions,
                              and default tag mappings
```

### 23.2 Key Data Models (`smart/models.py`)

| Model | Purpose |
|---|---|
| `RoutingPlan` | Full output of the router — complexity flag, list of SubQuestion, reasoning summary |
| `SubQuestion` | One routed sub-question — category, rewritten question, assigned model alias, context flag |
| `SpecialistResponse` | One specialist's output — alias, category, sub-question, response text, quality score, duration, retry count |
| `TemporaryStore` | In-memory collection of all SpecialistResponses for the current turn |
| `SmartResult` | Final output — combined response text, formatter applied, total duration, store reference for UI |

### 23.3 Integration With AppContext

```
AppContext (startup)
│
├── ctx.smart_registry        ← SmartRegistry (new)
├── ctx.smart_engine          ← SmartEngine (new)
│     ├── RouterModel(registry, model_alias)
│     ├── SequentialExecutor(registry)
│     │     └── QualityGate(threshold=50)
│     ├── TemporaryResponseStore()
│     ├── CombinerModel(registry)
│     └── FormatterModel(registry)
│
└── ctx.smart_enabled         ← bool, per-session toggle state
```

---

## 24. Integration With Existing Anythink Systems

### 24.1 Model Alias System

The MMAE uses the existing model alias system exactly as-is. Every alias
configured by the user is a valid assignment target for any MMAE role
(router, specialist, combiner, formatter, fallback). The MMAE reads
aliases from the same registry as all other Anythink components.

### 24.2 MMWE Model Capability Registry

The MMAE's SmartRegistry auto-populates its default category-to-model
assignments by reading capability tags from the MMWE's Model Capability
Registry. The two registries are separate stored files but share the same
source of truth for model capabilities. Changes to the MMWE capability
registry propagate to the MMAE default assignments on next `/smart registry
reset all`.

### 24.3 Debug Panel

MMAE events are streamed to the existing debug side panel (V3.2) as a
`[SMART]` event category alongside existing event categories. No changes
to the debug panel's structure or rendering are needed.

### 24.4 Spend Tracking

Every LLM call made by the MMAE — router, each specialist, combiner,
formatter — is counted in the existing spend tracker (V3). Each call is
attributed to its specific model alias. The `/cost` command shows MMAE
usage distinctly, so the user can see how many calls the engine made per
session and their cost breakdown.

### 24.5 Session History

The MMAE response stored in session history is the **final combined response
only** — the same text the user sees in the chat. The specialist responses
and routing plan are not stored in the session file. The session remains
a clean, human-readable conversation record.

### 24.6 HUD Integration

The `✦ Smart: ON` HUD indicator and the existing context window counter
are fully compatible. The context window tracker counts tokens used by
each MMAE model call independently and accumulates them into the session
total — exactly as it does for standard single-model responses.

---

*Anythink — Think anything. Ask anything.*

*Version described: Multi-Model Answering Engine (MMAE) — New Standalone Feature*
*Document last updated: June 2025*
