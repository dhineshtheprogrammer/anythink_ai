# Anythink — V3 Functionality Build

> Where V2 expanded the experience and V2.1 polished the interaction, V3 expands what Anythink can actually
> do. This build focuses on control, cost awareness, reusability, automation, and operational maturity —
> turning Anythink from a great chat tool into a dependable, scriptable, self-maintaining AI workstation.

---

## Table of Contents

1. [Per-Model Generation Parameters](#1-per-model-generation-parameters)
2. [Multi-Model Comparison Mode](#2-multi-model-comparison-mode)
3. [Spend Tracking](#3-spend-tracking)
4. [Prompt Templates & Snippets](#4-prompt-templates--snippets)
5. [Export Formats — Markdown, JSON, PDF](#5-export-formats--markdown-json-pdf)
6. [Scheduled & Recurring Prompts](#6-scheduled--recurring-prompts)
7. [Batch Processing Mode](#7-batch-processing-mode)
8. [Self-Update Mechanism](#8-self-update-mechanism)
9. [Diagnostics Command](#9-diagnostics-command)
10. [Config Backup & Restore](#10-config-backup--restore)
11. [How These Features Interconnect](#11-how-these-features-interconnect)

---

## 1. Per-Model Generation Parameters

### 1.1 What This Adds

Every model alias in the registry gains its own independent set of **generation parameters** — the knobs that control how the underlying LLM produces its output. Instead of relying purely on provider defaults, users can tune each of their saved aliases to behave differently for different purposes, even if two aliases point to the exact same underlying model.

### 1.2 Controllable Parameters

| Parameter | What It Controls |
|---|---|
| **Temperature** | Randomness/creativity of output — lower is more deterministic, higher is more varied |
| **Max tokens** | The maximum length of the model's response |
| **Top-p** | Nucleus sampling threshold — controls diversity of word choice |
| **Frequency penalty** | Discourages the model from repeating the same words/phrases |
| **Presence penalty** | Discourages the model from repeating the same topics, where supported by the provider |

Not every provider supports every parameter (for example, some local runtimes don't expose presence penalty). Anythink only shows and applies the parameters that are actually supported by the active provider for that alias, and silently ignores unsupported ones rather than erroring.

### 1.3 Per-Alias Configuration

When a user creates a model alias, after naming it and selecting the underlying model, Anythink offers an optional step: *"Customize generation parameters for this model? (or use provider defaults)"*. If the user opts in, each parameter is presented with its valid range and the provider's default value pre-filled, which they can adjust or leave as-is.

This means the same underlying model can be saved as multiple aliases with different personalities — for example, `google2-creative` (high temperature, for brainstorming) and `google2-precise` (low temperature, for factual/code tasks) — both pointing to the same `gemini-2.0-flash` model but behaving distinctly.

### 1.4 Managing Parameters After Creation

| Command | Action |
|---|---|
| `/model params <alias>` | View the current parameter values for an alias |
| `/model params <alias> set <param> <value>` | Update a single parameter |
| `/model params <alias> reset` | Reset all parameters back to provider defaults |

### 1.5 Visibility During Use

When a response is generated, the HUD or response bubble footer can optionally indicate that custom parameters are active for the current alias (e.g., a small `⚙ custom` tag), so the user is never confused about why a model is behaving differently from what they expect.

---

## 2. Multi-Model Comparison Mode

### 2.1 What This Adds

Comparison mode allows a single prompt to be sent **simultaneously to two or more model aliases**, with all responses streaming in and displayed together for direct, side-by-side evaluation. This is especially useful for choosing the right model for a recurring task, sanity-checking an important answer across providers, or simply exploring how different models reason differently about the same question.

### 2.2 Triggering Comparison Mode

The user enters comparison mode using:

```
/compare google2 groqfast gpt4o
```

This sets up a one-time comparison across the listed aliases for the **next message** the user sends. Alternatively, `/compare` with no arguments opens an interactive multi-select menu (using the same alias list used elsewhere) for the user to choose which models to include.

### 2.3 Response Layout

All selected models' responses stream in **simultaneously, in parallel**, each in its own labeled section, clearly separated and easy to visually scan against each other. In Simple Chat Mode, responses are stacked vertically with clear model headers. In TUI Dashboard Mode, the center panel can split into side-by-side columns, one per model, for true side-by-side reading.

Each response section includes its own model alias label, token usage for that specific response, response time, and (if spend tracking is active, see Section 3) estimated cost for that specific response — giving the user a complete comparison not just of content, but of cost and performance.

### 2.4 After Comparison

Once all responses have finished streaming, the user is asked which response (if any) they want to **continue the conversation with**:

```
╭─ Continue with which response? ────────────────────────╮
│  [1] google2     [2] groqfast     [3] gpt4o            │
│  [N] Don't continue — stay in comparison view           │
╰─────────────────────────────────────────────────────────╯
```

If a response is selected, that response becomes the canonical AI turn in the conversation going forward (the other responses are still preserved in the session file for reference, but only the chosen one continues as active context). If "Don't continue" is chosen, the user can send another comparison prompt or exit comparison mode with `/compare off`.

### 2.5 Comparison History

All comparison results are saved in the plain text session file with clear labeling, so a user reviewing their history later can see exactly which models were compared, what each said, and which one was ultimately chosen to continue with.

---

## 3. Spend Tracking

### 3.1 What This Adds

Since cloud LLM providers charge per token, Anythink calculates and tracks **estimated real-world cost** of usage — per session, per model alias, and per provider — using known public pricing rates, giving users financial visibility they don't otherwise get from raw token counts alone.

### 3.2 Pricing Data

Anythink maintains an internal, periodically-updatable pricing table mapping each known model to its public per-token (or per-million-token) input and output pricing, as published by each provider. Local models (Ollama, LM Studio, llama.cpp) are always shown as **$0.00 — Local** since there is no per-token API cost. Pricing data can be manually refreshed by the user (`/cost refresh`) to pull the latest published rates, since providers periodically change pricing.

### 3.3 Cost Calculation

For every exchange, using the same token usage data already being captured for the HUD context bar (provider-reported where available, estimated otherwise), Anythink calculates: `(prompt tokens × input rate) + (completion tokens × output rate)` for that specific provider/model — and accumulates this into running totals.

### 3.4 Where Cost Is Shown

- **HUD** — an optional compact cost indicator can be added to the HUD's second line, showing the running cost for the current session (e.g., `💰 $0.0312`)
- **Response bubble footer** — each AI response can optionally show its individual cost alongside the word count and length indicator
- **`/cost` command** — shows a detailed breakdown for the current session: total cost, cost per model used, cost per provider, token counts feeding each figure

### 3.5 Historical & Aggregate Views

```
/cost session     — cost breakdown for the current session only
/cost today       — total cost across all sessions today
/cost month       — total cost across all sessions this calendar month
/cost by-model    — lifetime cost broken down per model alias
/cost by-provider — lifetime cost broken down per provider
```

These aggregate views read across all saved session files, summing the tracked cost data stored in each, giving the user a genuine usage ledger over time without needing to check each provider's own billing dashboard separately.

### 3.6 Estimate Disclaimer

Because Anythink's cost figures are calculated locally from token counts and a maintained pricing table — not pulled directly from the provider's billing system — every cost display is clearly labeled as an **estimate**, with a note that actual provider billing may vary slightly (e.g., due to rounding, promotional credits, or pricing changes not yet reflected in Anythink's table).

### 3.7 Budget Awareness

The user can optionally set a **soft monthly budget** in `/settings` (e.g., $10/month). When cumulative tracked spend crosses 80% and 100% of that budget, Anythink shows a one-time, non-blocking notice in the conversation (and as a desktop notification, if enabled) — informational only, never restricting the user's ability to continue.

---

## 4. Prompt Templates & Snippets

### 4.1 What This Adds

A personal, reusable library of **prompt templates** — pre-written prompt structures with fillable variables — that the user can trigger instantly by name instead of retyping common request patterns from scratch every time.

### 4.2 Template Structure

Each saved template has:

- A **name** used to trigger it (e.g., `code-review`)
- A **template body** containing the prompt text, with **variables** marked using a simple placeholder syntax (e.g., `{{language}}`, `{{code}}`)
- An optional **description** shown when browsing the template library
- An optional **default persona** to apply when the template is used, if relevant

Example template (conceptually, not literal config syntax):

```
Name: code-review
Description: Request a thorough code review with specific focus areas
Body: 
  Please review the following {{language}} code for {{focus_area}}.
  Be specific about issues and suggest concrete improvements.

  {{code}}
```

### 4.3 Creating and Managing Templates

| Command | Action |
|---|---|
| `/template new` | Interactively create a new template — name, description, body with variables |
| `/template list` | List all saved templates with their descriptions |
| `/template edit <name>` | Edit an existing template |
| `/template delete <name>` | Remove a template |
| `/template show <name>` | Preview a template's full body and variables before using it |

### 4.4 Using a Template

The user triggers a template using:

```
/use code-review
```

Anythink detects all variables in the template (`{{language}}`, `{{focus_area}}`, `{{code}}`) and prompts the user for each one in turn, with a clean fill-in interface:

```
╭─ Template: code-review ────────────────────────────────╮
│  language:     Python_                                  │
│  focus_area:   (waiting)                                │
│  code:         (waiting)                                │
╰─────────────────────────────────────────────────────────╯
```

For multi-line variables like `code`, the input editor behaves exactly like the normal multi-line message composer, including the ability to paste in larger blocks or reference an attached file directly (e.g., the user can type `/file main.py` while filling the `code` variable to inject file content into that specific slot).

Once all variables are filled, the fully assembled prompt is shown for a final confirmation before sending, so the user can review exactly what will be submitted.

### 4.5 Quick-Fill Shortcut

For users who already know their variable values, the template can be invoked with inline arguments to skip the step-by-step fill-in entirely:

```
/use code-review language=Python focus_area="security issues"
```

(The `code` variable, being multi-line, would still prompt interactively even in quick-fill mode, unless explicitly piped in via a file reference.)

### 4.6 Template Storage

Templates are stored in the user's config directory as a dedicated template library file, independent of any single session — available across every session and every project, exactly like the persona library.

---

## 5. Export Formats — Markdown, JSON, PDF

### 5.1 What This Adds

Beyond the plain text session files used internally, users can now **export** a session (or a portion of one) into formats better suited for sharing, presenting, or archiving outside the terminal.

### 5.2 Supported Export Formats

| Format | Best For |
|---|---|
| **Markdown (.md)** | Readable, portable, renders nicely on GitHub/Notion/any Markdown viewer; preserves code blocks and formatting |
| **JSON (.json)** | Structured data — for developers who want to programmatically process conversation history, build tooling on top of it, or feed it into another system |
| **PDF (.pdf)** | Polished, presentation-ready document — for sharing a conversation with someone non-technical, archiving formally, or printing |

### 5.3 Export Command

```
/export
```

Opens an interactive export flow asking: which format, what scope (full session / current branch only / a specific turn range / bookmarked responses only — building on the bookmarking system from V2), and the destination file path (defaulting to a sensible location, with the session name pre-filled as the filename).

Direct, non-interactive invocation is also supported for quick use:

```
/export markdown
/export json --range 4-12
/export pdf --bookmarks-only
```

### 5.4 Format-Specific Behavior

**Markdown export** preserves the full conversational structure — user/AI turns clearly labeled with headers, code blocks rendered as proper fenced Markdown code blocks with language tags intact, tables preserved as Markdown tables, and metadata (date, model used, persona) included as a header block at the top of the file.

**JSON export** produces a structured, well-documented schema including every turn as an object with fields for role, content, timestamp, model alias used, token usage, and cost (if spend tracking is active) — making it straightforward for technical users to parse programmatically.

**PDF export** generates a clean, formatted document with proper typography, syntax-highlighted code blocks (rendered as styled blocks, not raw text), a title page showing session name/date/model, and pagination — suitable for printing or sending to a non-technical stakeholder.

### 5.5 Partial Exports

All three formats support exporting a **subset** of the conversation rather than the whole thing — a specific turn range, only bookmarked responses, or only a specific branch — using the same scope selection step from the interactive flow or equivalent command flags.

---

## 6. Scheduled & Recurring Prompts

### 6.1 What This Adds

Anythink can run prompts **automatically on a schedule**, without the user needing to be actively chatting — enabling recurring, hands-off use cases like daily summaries, periodic codebase health checks, or scheduled reports drawn from a RAG index.

### 6.2 Creating a Scheduled Prompt

```
/schedule new
```

Walks the user through an interactive setup:

- **What to run** — either a raw prompt, or a saved prompt template (Section 4) with its variables pre-filled
- **Which model alias** to use for the run
- **Which RAG index** (if any) should be active during the run
- **Schedule** — a recurrence pattern (daily at a specific time, weekly on specific day(s), or a custom interval)
- **Output handling** — where the result should go (see Section 6.4)

Example conceptual setup:

```
╭─ New Scheduled Prompt ──────────────────────────────────╮
│  Name:        Morning email summary                     │
│  Prompt:      "Summarize new emails in this index"       │
│  Model:       google2                                   │
│  RAG Index:   email-inbox                                │
│  Schedule:    Daily at 08:00                              │
│  Output:      Save to file + desktop notification         │
╰─────────────────────────────────────────────────────────╯
```

### 6.3 How Scheduled Runs Execute

Scheduled prompts run as **independent, non-interactive executions** — Anythink does not need to be actively open in a chat session for them to fire. This is implemented as a lightweight background scheduler process that wakes up at the configured times, runs the prompt against the specified model (and RAG index, if set), and handles the output according to the configured destination — entirely separate from any interactive terminal session the user may or may not have open.

### 6.4 Output Handling Options

| Option | Behavior |
|---|---|
| **Save to file** | Result is written to a specified file path (with options for overwrite, append, or timestamped new file each run) |
| **Desktop notification** | A summary or full result is shown as an OS notification when the run completes |
| **Append to a session** | Result is added as a new turn into a designated ongoing session, so a history of recurring runs accumulates and is browsable like any other session |
| **Combination** | Any combination of the above can be selected together |

### 6.5 Managing Scheduled Prompts

| Command | Action |
|---|---|
| `/schedule list` | Show all scheduled prompts, their recurrence, and next run time |
| `/schedule edit <name>` | Modify an existing scheduled prompt |
| `/schedule pause <name>` | Temporarily disable a schedule without deleting it |
| `/schedule resume <name>` | Re-enable a paused schedule |
| `/schedule delete <name>` | Permanently remove a scheduled prompt |
| `/schedule run-now <name>` | Manually trigger a scheduled prompt immediately, outside its normal schedule |
| `/schedule history <name>` | Show past run results, timestamps, and success/failure status for a given schedule |

### 6.6 Reliability Considerations

Each scheduled run logs its outcome (success, failure, and the reason for any failure — e.g., provider unreachable, RAG index missing) to a dedicated schedule log, viewable via `/schedule history`, so the user can trust the automation is working and quickly diagnose any silent failures rather than being surprised by missing output.

---

## 7. Batch Processing Mode

### 7.1 What This Adds

A fully **non-interactive command-line mode** for processing multiple prompts in a single invocation — designed for scripting, automation pipelines, and bulk operations outside of the normal interactive chat experience.

### 7.2 Basic Invocation

```
anythink run --file prompts.txt --output results.md
```

This reads a list of prompts from the input file, runs each one sequentially (or in parallel, if configured) against a specified model, and writes all results to the output file — with no interactive terminal session, no HUD, no chat bubbles — purely a batch job suitable for shell scripts, cron jobs, or CI pipelines.

### 7.3 Input File Format

The input file contains one prompt per entry, with simple delimiters separating individual prompts (so multi-line prompts remain possible). Each entry can optionally specify its own model alias override, persona, or template reference, falling back to command-line flags or config defaults when not specified per-entry.

### 7.4 Command-Line Options

| Flag | Purpose |
|---|---|
| `--file <path>` | Input file containing the list of prompts |
| `--model <alias>` | Model alias to use for all prompts (unless overridden per-entry) |
| `--persona <name>` | Persona to apply across the batch |
| `--rag <name>` | RAG index to use for all prompts in the batch |
| `--output <path>` | Where results are written |
| `--format <md\|json\|pdf>` | Output format, reusing the same export logic from Section 5 |
| `--parallel <n>` | Run up to `n` prompts concurrently instead of strictly sequentially |
| `--continue-on-error` | If one prompt fails (provider error, etc.), continue processing the rest instead of halting the whole batch |

### 7.5 Output Structure

The output file mirrors the structure of a normal export (Section 5) — each prompt and its corresponding response clearly delimited, with metadata (model used, timestamp, token usage, cost if tracked) included per entry — making batch results just as readable and reusable as a regular exported session.

### 7.6 Exit Codes & Scriptability

The batch command returns standard process exit codes — `0` for full success, non-zero for partial or total failure — making it suitable for direct use inside larger automation scripts and CI/CD pipelines where the calling process needs to know whether the batch run succeeded.

### 7.7 Relationship to Scheduled Prompts

Batch mode and scheduled prompts (Section 6) share the same core execution engine — a scheduled prompt is effectively a single-item batch run triggered automatically by the internal scheduler rather than manually by the user, ensuring consistent behavior, output formatting, and reliability handling across both automation paths.

---

## 8. Self-Update Mechanism

### 8.1 What This Adds

Anythink can check for, and install, **its own updates** directly from PyPI, without requiring the user to manually run `pip install --upgrade anythink` themselves.

### 8.2 Checking for Updates

```
/update check
```

Or, automatically: Anythink performs a lightweight, non-blocking check against PyPI once per day (configurable) on startup, and if a newer version is available, shows a single unobtrusive notice rather than interrupting the user's workflow:

```
 ↑ A new version of Anythink is available (v2.1.0 → v3.0.0). Run /update to upgrade.
```

### 8.3 Performing an Update

```
/update
```

Triggers the actual upgrade process: Anythink runs the equivalent of `pip install --upgrade anythink` in the background, shows a progress indicator, and on completion informs the user that a restart is needed for the new version to take effect (since the running process cannot replace its own loaded code mid-execution).

### 8.4 Update Safety

Before updating, Anythink shows the **changelog summary** for the version(s) being jumped to (pulled from the package's published changelog), so the user knows what's changing before they commit to the upgrade. If the update fails partway (network interruption, permission issue), Anythink reports the failure clearly and confirms that the currently running version remains unaffected and fully functional.

### 8.5 Update Channel Control

For users who prefer stability over latest features, `/update channel` allows choosing between:

- **Stable** — only updates to fully released, tagged versions (default)
- **Pre-release** — also offers beta/release-candidate versions for users who want to try upcoming features early

### 8.6 Disabling Auto-Check

Users who prefer not to be notified about updates at all can disable the background check entirely via `/settings`, while still being able to manually run `/update check` whenever they choose.

---

## 9. Diagnostics Command

### 9.1 What This Adds

A single comprehensive health-check command that inspects the entire Anythink installation and environment, surfacing problems before they cause confusing failures mid-conversation.

### 9.2 Running Diagnostics

```
/doctor
```

Or, from outside an active session: `anythink doctor`

### 9.3 What Is Checked

| Check Category | What's Verified |
|---|---|
| **Python environment** | Python version meets the minimum requirement (3.11+); reports the exact version found |
| **Dependency health** | All required packages are installed and at compatible versions; flags any missing or conflicting dependencies |
| **API key validity** | Each stored cloud provider key is tested with a lightweight live call; reports valid/invalid/untested per provider |
| **Local model servers** | Each configured local runtime (Ollama, LM Studio, llama.cpp) is pinged at its configured host/port; reports reachable/unreachable |
| **Config file integrity** | All config files (main config, model registry, personas, templates, schedules) are valid and parse correctly; flags corruption |
| **Disk space & permissions** | Sufficient disk space and write permissions exist for the XDG data/config/cache directories |
| **Keychain access** | The system keychain is accessible and functioning correctly for credential storage |
| **Plugin health** | Each installed plugin loads correctly without errors |
| **MCP connections** | Each configured MCP server (built-in and external) responds correctly |

### 9.4 Report Output

Results are shown as a clean, scannable report with a status icon per check (✓ pass, ⚠ warning, ❌ fail), grouped by category, with a final summary line:

```
╭─ 🩺 Anythink Diagnostics ──────────────────────────────╮
│                                                         │
│  Python Environment                                     │
│   ✓ Python 3.12.3 (meets requirement: 3.11+)            │
│                                                         │
│  API Keys                                                │
│   ✓ Groq — valid                                        │
│   ❌ Gemini — invalid (401 Unauthorized)                 │
│   ⚠ OpenAI — not configured                              │
│                                                         │
│  Local Servers                                           │
│   ✓ Ollama — reachable (localhost:11434)                │
│                                                         │
│  Config Files                                            │
│   ✓ All config files valid                               │
│                                                         │
│  ─────────────────────────────────────────────────────│
│  Summary: 7 passed, 1 warning, 1 failed                 │
│  Suggested fix: Run /keys update gemini                  │
╰─────────────────────────────────────────────────────────╯
```

### 9.5 Actionable Failures

Just like the error message improvements from V2.1, every failed or warning check in the diagnostics report includes a suggested fix command where applicable, keeping the diagnostics tool consistent with the rest of Anythink's error-handling philosophy — never just reporting a problem without pointing toward a resolution.

---

## 10. Config Backup & Restore

### 10.1 What This Adds

A simple way to **export the entire Anythink configuration** as a portable bundle, and **restore it** on the same or a different machine — useful when setting up a new computer, migrating environments, or simply keeping a safety backup of carefully tuned settings.

### 10.2 What's Included in a Backup

A backup bundle includes everything that defines a user's Anythink setup:

- Main configuration (theme, defaults, approval modes, thresholds)
- Model alias registry (aliases, provider mappings, generation parameters)
- Persona library
- Prompt template library
- Scheduled prompt definitions
- Plugin list and their individual settings
- MCP server connection list

**Explicitly excluded by default:** API keys and any other credential data stored in the system keychain — since keychains are machine- and OS-specific and copying raw credentials between machines via a file is a security risk Anythink avoids by default.

### 10.3 Creating a Backup

```
/config export
```

Produces a single portable backup file containing all the above, saved to a user-specified location. The command output clearly states what was included and confirms that credentials were excluded:

```
 ✓ Config exported to anythink-backup-2025-06-18.json
   Included: theme, models, personas, templates, schedules, plugins, MCP servers
   Excluded: API keys (for security) — re-enter these on the new machine with /keys add
```

### 10.4 Including Credentials (Explicit Opt-In)

For users who understand the risk and want a truly complete backup (e.g., backing up to their own encrypted personal storage), credentials can be explicitly included with a clear, deliberate flag:

```
/config export --include-keys
```

This requires an additional confirmation step warning the user that the resulting file will contain sensitive credentials in plain or lightly-encoded form and should be stored securely.

### 10.5 Restoring a Backup

```
/config import <path-to-backup-file>
```

Anythink reads the backup file, shows a summary of what it contains, and asks the user to confirm before applying it — including how to handle conflicts if the target machine already has existing config (overwrite everything, merge and keep existing entries on conflict, or review item-by-item).

### 10.6 Restore Safety

Before applying an import, Anythink automatically creates a **safety snapshot** of the current config (even if the user didn't explicitly request one), so that if an import goes wrong or the user wants to revert, the prior state can be restored with a single follow-up command (`/config restore-previous`).

---

## 11. How These Features Interconnect

Several of these new functionalities are designed to work together rather than as isolated additions:

**Templates + Batch Processing + Scheduling** share the same underlying prompt-execution engine — a template can be the basis of a scheduled prompt, and a batch file can reference saved templates by name instead of writing out full prompt text repeatedly. This consistency means a user who has invested time building a good template library gets to reuse that investment across interactive chat, automated schedules, and scripted batch jobs alike.

**Spend Tracking + Comparison Mode** combine naturally — when comparing multiple models side-by-side, the per-response cost shown for each makes the comparison not just about quality, but about cost-effectiveness for a given task.

**Export Formats + Scheduling** combine for hands-off reporting — a scheduled prompt's output destination can itself be a Markdown, JSON, or PDF export, turning Anythink into a lightweight recurring report generator.

**Diagnostics + Self-Update** are both part of the same operational maturity goal — keeping a long-running, real-world installation healthy and current with minimal manual maintenance burden on the user.

**Config Backup/Restore + Self-Update** work together for safe upgrades — a cautious user can take a config snapshot immediately before running `/update` as an extra safety net, even though updates themselves don't touch config data directly.

---

*Anythink — Think anything. Ask anything.*

*Version described: 3.0.0 (V3 — Functionality Expansion Build)*
*Document last updated: June 2025*
