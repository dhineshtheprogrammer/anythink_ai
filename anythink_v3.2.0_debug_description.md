# Anythink — V3.2.0 Debug Build

> V3.2.0 introduces Anythink's complete debugging infrastructure — a unified, toggleable debug
> system that gives developers, power users, and contributors full visibility into every layer
> of how the application generates responses: from the raw prompt payload that leaves the machine,
> to every token that streams back in, to the exact millisecond each stage of a request completes.
> Nothing is hidden. Every decision the system makes is inspectable, replayable, and exportable.

---

## Table of Contents

1. [Debug Mode — The Master System](#1-debug-mode--the-master-system)
2. [Raw Prompt Inspector](#2-raw-prompt-inspector)
3. [Token-by-Token Trace](#3-token-by-token-trace)
4. [Timing Breakdown & Latency Profile](#4-timing-breakdown--latency-profile)
5. [Stop Reason Visibility](#5-stop-reason-visibility)
6. [Raw API Request / Response Log](#6-raw-api-request--response-log)
7. [Request Replay](#7-request-replay)
8. [Latency History Graph](#8-latency-history-graph)
9. [Provider Debug Comparison](#9-provider-debug-comparison)
10. [Context Window Visualizer](#10-context-window-visualizer)
11. [Prompt Diff](#11-prompt-diff)
12. [Effective Prompt Preview](#12-effective-prompt-preview)
13. [RAG Chunk Inspector](#13-rag-chunk-inspector)
14. [Embedding Inspector](#14-embedding-inspector)
15. [RAG Injection Preview](#15-rag-injection-preview)
16. [Tool Call Trace](#16-tool-call-trace)
17. [Agent Decision Log](#17-agent-decision-log)
18. [Tool Output Diff](#18-tool-output-diff)
19. [Toggleable Debug Side Panel](#19-toggleable-debug-side-panel)
20. [Debug Verbosity Levels](#20-debug-verbosity-levels)
21. [Debug Log Export](#21-debug-log-export)
22. [Plugin Trace](#22-plugin-trace)
23. [Config Deep Validation](#23-config-deep-validation)
24. [Tokens Per Second](#24-tokens-per-second)
25. [Session Performance Summary](#25-session-performance-summary)
26. [Debug Command Reference](#26-debug-command-reference)
27. [How the Debug System Fits Together](#27-how-the-debug-system-fits-together)

---

## 1. Debug Mode — The Master System

### 1.1 Philosophy

Every debugging feature in V3.2.0 lives under a **single, unified debug mode** rather than being scattered as independent toggles. Debug mode is a first-class, named state of the application — not an environment variable, not a CLI flag, not a hidden setting buried in config. It is entered with a command, exited with a command, and its state is always clearly communicated to the user through the HUD.

### 1.2 Entering and Exiting Debug Mode

```
/debug on       — activate debug mode
/debug off      — deactivate debug mode
/debug          — toggle (on if off, off if on)
```

From outside an active session, the same can be done at launch:

```
anythink --debug
```

### 1.3 HUD Indicator

When debug mode is active, the HUD's first line gains a **persistent, clearly visible debug indicator** so the user is never uncertain about whether debugging is on:

```
 ✦ Anythink  v3.2.0  [DEBUG L2]  │  Session: "BERT vs GPT research"  │  Branch: main
```

The indicator shows both the debug state and the current verbosity level (described in Section 20), so the user always knows exactly how much data is being captured at a glance.

### 1.4 Debug Mode Does Not Change Behavior

With the single exception of the toggleable debug side panel (Section 19), debug mode is **observational only** — it never changes how requests are made, how the model responds, how tools are called, or how anything else in the application behaves. It only adds visibility. A conversation in debug mode produces exactly the same output as the same conversation without debug mode — it just surfaces everything that was already happening invisibly.

### 1.5 The Debug Command Namespace

Every debug feature is accessible through the `/debug` command namespace, so all debugging tools are discoverable from one starting point:

```
/debug on / off / toggle
/debug prompt
/debug tokens
/debug timing
/debug stopreason
/debug api
/debug replay
/debug latency
/debug compare
/debug context
/debug diff
/debug preview
/debug chunks
/debug embeddings
/debug raginject
/debug tools
/debug agent
/debug tooldiff
/debug panel
/debug level <1|2|3>
/debug export
/debug plugins
/debug validate
/debug tps
/debug perf
```

Each of these is described in detail in the sections below.

---

## 2. Raw Prompt Inspector

### 2.1 What It Shows

```
/debug prompt
```

Displays the **complete, exact payload** that was sent to the provider for the most recent request — not a summary or a reconstruction, but the actual data structure as it left Anythink. This includes every field that was included in the API call:

- The full **system prompt** (including the active persona, any framework boilerplate Anythink adds, and any injected RAG or tool preamble)
- Every **conversation turn** in the current context window, in order, with their exact role labels (system / user / assistant / tool)
- All **RAG-retrieved chunks** that were injected, clearly delimited and labeled with their source
- All **tool definitions** passed to the model (web search, code execution, MCP tools, custom tools) with their full JSON schemas
- Any **file content** that was attached and injected
- Any **web search results** that were pre-injected into context
- The **model identifier**, **generation parameters** (temperature, max tokens, top-p, etc.) and any other API-level fields included in the call

### 2.2 Output Format

The inspector renders the full payload in a **formatted, syntax-highlighted, paginated view** inside the terminal — readable in place, with turn boundaries clearly marked and different content types (system prompt vs. conversation vs. tool schema vs. injected context) visually distinguished by label and indent level:

```
╭─ 🔬 Raw Prompt Payload — Request #4 ─────────────────────────────╮
│                                                                   │
│  Model:       gemini-2.0-flash                                   │
│  Temperature: 0.7   Max Tokens: 4096   Top-p: 0.95              │
│                                                                   │
│  ── SYSTEM ───────────────────────────────────────────────────── │
│  You are an expert Python software engineer with 20 years of...  │
│  [RAG PREAMBLE] The following context was retrieved from the     │
│  index "my-project":                                             │
│    [CHUNK 1 · src/models/transformer.py · lines 42-78]          │
│    class TransformerBlock(nn.Module):...                         │
│                                                                   │
│  ── TURN 1 · user ────────────────────────────────────────────── │
│  Explain how BERT's attention mechanism differs from GPT.        │
│                                                                   │
│  ── TURN 1 · assistant ───────────────────────────────────────── │
│  BERT uses bidirectional attention...                            │
│                                                                   │
│  ── TOOL DEFINITIONS ─────────────────────────────────────────── │
│  web_search: { description: "Search the web...", parameters: ... │
│                                                                   │
│  [Page 1 of 2 — press → for next page, Esc to close]            │
╰───────────────────────────────────────────────────────────────────╯
```

The paginated view handles arbitrarily large payloads without overflowing the terminal — the user pages through it using arrow keys, with Escape returning focus to the conversation.

### 2.3 Auto-Capture Behavior in Debug Mode

When debug mode is active, every outgoing payload is **automatically captured** to an in-memory buffer (and, if debug log export is active per Section 21, to the debug log file) — so even if the user does not run `/debug prompt` after every message, the payload for any past request in the current session can be inspected retroactively using `/debug prompt <request number>`.

---

## 3. Token-by-Token Trace

### 3.1 What It Shows

```
/debug tokens
```

Activates a live **token stream overlay** for the next (or currently streaming) response. Instead of watching final rendered text appear, the user sees each individual token as it arrives, with inter-token timing information, making it possible to directly observe:

- Whether the model is streaming smoothly and consistently
- Where the model pauses between bursts (often indicating internal reasoning or tool call preparation)
- Exactly how a sentence or code block is being assembled token by token
- The difference in streaming behavior between providers and models

### 3.2 Display Format

The token trace renders in the debug side panel (Section 19) when it is open, or as a separate lower band in the conversation area when the panel is not in use:

```
╭─ 🔬 Token Stream Trace ────────────────────────────────────────────╮
│                                                                    │
│  #001  [BERT]          +0ms                                       │
│  #002  [ uses]         +12ms                                      │
│  #003  [ bidirectional]+8ms                                       │
│  #004  [ attention]    +9ms                                       │
│  #005  [,]             +7ms                                       │
│  #006  [ meaning]      +11ms       ← 340ms pause before this token│
│  #007  [ each]         +8ms                                       │
│  ...                                                              │
╰────────────────────────────────────────────────────────────────────╯
```

Pauses significantly above the session's average inter-token timing are **automatically highlighted** (as shown above) so the user can immediately spot where the model is hesitating without having to manually compare timestamps.

### 3.3 Summary After Completion

When the response finishes streaming, the trace summary appends a one-line statistical row:

```
 ▸ 83 tokens   avg 9ms/token   max pause 340ms at token #6   total stream 0.74s
```

---

## 4. Timing Breakdown & Latency Profile

### 4.1 What It Shows

```
/debug timing
```

Displays a **per-stage latency breakdown** for the most recent request — a precise account of exactly how long each phase of request processing took, making it immediately clear where time was spent:

```
╭─ 🔬 Request Timing — Request #4 ──────────────────────────────────╮
│                                                                    │
│  Stage                              Duration     Cumulative        │
│  ───────────────────────────────────────────────────────────────  │
│  Prompt assembly                     14ms          14ms           │
│  RAG retrieval                       82ms          96ms           │
│  Web search                          340ms         436ms          │
│  API call (queue + network)          201ms         637ms          │
│  Time to first token (TTFT)          187ms         824ms          │
│  Token stream duration               742ms        1566ms          │
│  Response rendering                   11ms        1577ms          │
│  ───────────────────────────────────────────────────────────────  │
│  Total wall time                    1577ms                        │
│                                                                    │
│  Slowest stage:  Web search (340ms)                               │
│  Provider:       Gemini ·  TTFT rank: #2 of 4 requests today     │
╰────────────────────────────────────────────────────────────────────╯
```

### 4.2 Stages Tracked

Every stage that Anythink controls or can measure is tracked independently:

- **Prompt assembly** — time to build the full payload from conversation history, persona, RAG chunks, tool schemas, and file content
- **RAG retrieval** — time from query submission to final ranked chunk list (only shown if RAG was active)
- **Web search** — total time from search trigger to results returned (only shown if search was triggered)
- **Code execution** — time from code submission to stdout/stderr returned (only shown if code was run)
- **MCP tool calls** — each MCP tool call individually, with its own timing row
- **API call** — total time from the moment the HTTP request is sent to the moment the first response byte arrives (covers network latency and provider queue time together)
- **Time to first token (TTFT)** — the component of API call time specifically measured as "first byte of generated content received"
- **Token stream duration** — total time from first to last token of the streamed response
- **Response rendering** — time to parse, format, and render the completed response in the terminal

### 4.3 Auto-Display in Debug Mode

When debug mode is active, a compact single-line timing summary is automatically appended beneath every AI response bubble, without needing to run `/debug timing` manually:

```
 ⏱ TTFT 187ms · Stream 742ms · RAG 82ms · Total 1577ms
```

The full breakdown is available via `/debug timing` for the user who wants the expanded view.

---

## 5. Stop Reason Visibility

### 5.1 What It Shows

```
/debug stopreason
```

Displays why the most recent response ended. Provider APIs always return a machine-readable stop reason alongside the response, but this is normally invisible to the user — the response just stops. In debug mode, this information is surfaced.

### 5.2 Stop Reason Categories

| Stop Reason | Meaning |
|---|---|
| `end_turn` | Model naturally completed its response |
| `max_tokens` | Response was cut off because the max token limit was reached |
| `stop_sequence` | A configured stop string was encountered and halted generation |
| `tool_use` | Model stopped to call a tool and is waiting for the result |
| `cancelled` | Generation was stopped by the user via the stop shortcut |
| `error` | Generation ended due to a provider-side error mid-stream |
| `timeout` | Generation halted due to a connection or response timeout |

### 5.3 Display

When debug mode is active, the stop reason is appended as a compact tag in the AI response bubble footer, immediately readable without running a separate command:

```
│                                        127 words · ·· │ stop: end_turn
```

For concerning stop reasons — specifically `max_tokens` (which means the response was silently truncated) — the tag is highlighted in the theme's warning color and a note is shown:

```
│  ⚠ Response was cut off at the token limit. Consider increasing    │
│    max_tokens for this alias via /model params google2 set         │
│    max_tokens 8192, or switch to a model with a longer output cap. │
```

---

## 6. Raw API Request / Response Log

### 6.1 What It Captures

```
/debug api
```

Toggles full **HTTP-level logging** of every provider API call — equivalent to running every request through `curl -v`, capturing the complete network-level interaction:

- Full request headers (Content-Type, Authorization masked by default, any provider-specific headers)
- Full request body (the JSON payload sent to the provider's API endpoint)
- Full response headers (rate limit headers, request IDs, content types, status codes)
- Full response body (the raw JSON response or streaming event stream, exactly as returned)
- HTTP status code
- Total HTTP round-trip time

### 6.2 Credential Masking

The Authorization header (which contains the API key) is **masked by default** in all log output — replaced with `Bearer sk-...***` — so that exporting or sharing the raw API log never accidentally exposes live credentials. An explicit `--show-keys` flag can unmask credentials for users who need to verify the exact key being used, with a clear warning displayed when unmask mode is active.

### 6.3 Log Output Destination

Raw API logs are written to a **dedicated rolling log file** at `$XDG_STATE_HOME/anythink/logs/api_debug.log`, separate from the normal application log. The rolling policy prevents unbounded disk growth — by default, the last 50MB of API log is retained. The user can also stream the live log to the debug side panel (Section 19) in real time.

### 6.4 Useful Scenarios

- Diagnosing auth failures (exact 401/403 response body visible)
- Verifying that generation parameters (temperature, max_tokens) are being sent correctly
- Checking provider-returned request IDs for filing support tickets
- Confirming that streaming is being used vs. non-streaming for a given provider
- Observing provider-side rate limit headers to understand when throttling is occurring

---

## 7. Request Replay

### 7.1 What It Does

```
/debug replay
```

Replays the **exact request** from the most recent exchange — same prompt payload, same model, same generation parameters, same tool definitions — as if the user had sent that message again right now. Replay targets the same provider and model by default.

```
/debug replay --provider groq
/debug replay --model groqfast
```

Re-sends the identical payload to a different provider or model alias, making it possible to isolate whether a bad, unexpected, or failed response was caused by the prompt itself, the model, or the provider infrastructure.

### 7.2 Replay Numbering

Every request in the current session is automatically numbered (Request #1, #2, #3...) in debug mode. A specific past request can be replayed by number:

```
/debug replay 3
/debug replay 3 --provider gemini
```

### 7.3 Replay Display

A replayed response is rendered in the conversation area with a clear label distinguishing it from an original response:

```
╭─ ↺ google2 (Replay of Request #3) ────── Gemini · just now ──╮
│  BERT uses bidirectional attention...                          │
╰────────────────────────────────────────────────────────────────╯
```

Replayed responses are saved into the session file with their replay label, so the history is transparent about which turns were original and which were replayed.

### 7.4 Replay Does Not Advance History

A replay does **not** add a new user turn to the conversation — it re-sends the original user turn's content and appends only the new AI response, tagged as a replay. The conversation context for the next real user message is not affected by replays unless the user explicitly chooses to adopt the replayed response as the canonical response for that turn.

---

## 8. Latency History Graph

### 8.1 What It Shows

```
/debug latency
```

Renders an **ASCII line chart** of response latency (total wall time) across all requests made in the current session — making it possible to spot whether a provider is degrading, whether one request was an anomalous outlier, or whether latency is consistently high or improving over the course of a session.

### 8.2 Chart Format

```
╭─ 🔬 Latency History — Current Session ────────────────────────────╮
│                                                                    │
│  ms                                                               │
│  3000 ┤                                                           │
│  2500 ┤                  ╭╮                                       │
│  2000 ┤                  ││      ╭─╮                              │
│  1500 ┤    ╭─╮           ││      │ │                              │
│  1000 ┤────╯ ╰──╮╭───────╯╰──────╯ ╰──╮                         │
│   500 ┤         ╰╯                     ╰──────                   │
│     0 ┼────────────────────────────────────────                   │
│       #1   #2   #3   #4   #5   #6   #7   #8   #9                 │
│                                                                    │
│  Avg: 1,182ms   Min: 487ms (#9)   Max: 2,611ms (#5)              │
│  Trend: improving ↓                                               │
╰────────────────────────────────────────────────────────────────────╯
```

### 8.3 Multi-Stage Overlay

With a `--breakdown` flag, the chart stacks multiple latency components (RAG, web search, TTFT, stream) as separate labeled lines on the same chart, making it possible to see which stage specifically is driving changes in total latency across requests.

### 8.4 Cross-Session Latency

With `--sessions all` or `--sessions today`, the chart extends across multiple saved sessions, using the stored per-request timing data in session files — giving the user a long-term view of provider performance trends rather than just within a single chat.

---

## 9. Provider Debug Comparison

### 9.1 What It Shows

```
/debug compare google2 groqfast gpt4o
```

A technical complement to the user-facing `/compare` mode — this variant sends the identical payload to multiple providers simultaneously and returns a **structured technical comparison table** alongside the response texts, covering dimensions that are invisible in the user-facing comparison:

| Metric | google2 | groqfast | gpt4o |
|---|---|---|---|
| TTFT | 187ms | 42ms | 314ms |
| Stream duration | 742ms | 198ms | 1,104ms |
| Total wall time | 1,577ms | 387ms | 1,618ms |
| Tokens generated | 83 | 91 | 78 |
| Tokens/second | 111 | 459 | 71 |
| Stop reason | end_turn | end_turn | end_turn |
| Prompt tokens | 1,204 | 1,204 | 1,204 |
| Estimated cost | $0.0012 | $0.0003 | $0.0031 |

This table is shown above the response content comparison, making it a complete side-by-side evaluation of both quality and performance — all in one command.

---

## 10. Context Window Visualizer

### 10.1 What It Shows

```
/debug context
```

Renders a **full breakdown of the current context window's composition** — showing not just how many tokens are used, but exactly what is consuming each portion of the budget, in a visual layout that makes the context window feel concrete and navigable rather than an opaque number.

### 10.2 Visualizer Layout

```
╭─ 🔬 Context Window — google2 · 1,000,000 token max ───────────────╮
│                                                                    │
│  Component                          Tokens     % of Budget        │
│  ─────────────────────────────────────────────────────────────── │
│  System prompt / Persona             312         0.03%            │
│  RAG preamble                         48         0.00%            │
│    ├─ Chunk 1: transformer.py L42     187        0.02%            │
│    ├─ Chunk 2: architecture.md        143        0.01%            │
│    └─ Chunk 3: README.md              97         0.01%            │
│  Tool definitions                    524         0.05%            │
│  ── Conversation Turns ──────────────────────────────────────── │
│    Turn 1 · You                       14         0.00%            │
│    Turn 1 · google2                   83         0.01%            │
│    Turn 2 · You                       11         0.00%            │
│    Turn 2 · google2  (pending)         —          —              │
│  File content                          0         0.00%            │
│  Web search injection                  0         0.00%            │
│  ─────────────────────────────────────────────────────────────── │
│  Total used                        1,419         0.14%            │
│  Remaining                       998,581        99.86%            │
│                                                                    │
│  ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0.14%                        │
╰────────────────────────────────────────────────────────────────────╯
```

Every single contributor to the context window is itemized with its own token count and percentage. RAG chunks are expanded inline with their source file and line range. Tool definitions are shown as a single row but expandable with `/debug context --expand tools`. The conversation turn list grows with every exchange, making it possible to see exactly which old turns are the most expensive and which ones could be pruned first if the context window approaches its limit.

---

## 11. Prompt Diff

### 11.1 What It Shows

```
/debug diff
```

When a model switch or `/clear` occurs mid-session, the prompt payload that would be sent to the **new model** is compared against what was sent to the **previous model** on the last request, rendering a standard unified diff showing exactly what changed:

```
╭─ 🔬 Prompt Diff — Request #4 vs #3 ──────────────────────────────╮
│                                                                    │
│  Context:  google2 → groqfast after /model switch                 │
│                                                                    │
│  - Model: gemini-2.0-flash                                       │
│  + Model: llama3-8b-8192                                          │
│                                                                    │
│  - Temperature: 0.7                                               │
│  + Temperature: 1.0   (groqfast default)                         │
│                                                                    │
│    System prompt: unchanged                                       │
│                                                                    │
│  - [RAG CHUNK 2 · architecture.md] (removed — over context limit) │
│                                                                    │
│    Turn 1 · You:       unchanged                                  │
│    Turn 1 · assistant: unchanged                                  │
│                                                                    │
│  + [NOTE: groqfast does not support tool definitions in payload]  │
│    Tool definitions: removed from payload                         │
│                                                                    │
╰────────────────────────────────────────────────────────────────────╯
```

This makes it immediately clear why a response from the new model might differ — it could be a different temperature default, a dropped RAG chunk, a model that doesn't support the same tool calling format, or simply a different underlying model family — rather than leaving the user guessing about what actually changed.

---

## 12. Effective Prompt Preview

### 12.1 What It Does

```
/preview
```

Available at any time in the input area (not only in debug mode — this is one of the few debug-adjacent features accessible outside debug mode because of its practical pre-send utility), `/preview` shows the **fully assembled prompt** that would be sent if the user pressed Enter right now — without sending it.

### 12.2 What Is Shown

The preview is identical in structure and content to the raw prompt inspector (Section 2) — same format, same paginated view — but rendered from the current in-progress state rather than a past request. If the user has typed a message in the input box before running `/preview`, that message is included as the next user turn in the preview. If the input is empty, the preview shows the context as it stands ready for the next message.

### 12.3 Practical Use

This is the user's last checkpoint before sending a large, expensive, or sensitive request. It answers questions like: "Is my RAG index actually injecting the right content?" "Is my persona still active?" "How many tokens am I about to spend?" "Is the tool I want enabled?" — all before committing to the API call.

---

## 13. RAG Chunk Inspector

### 13.1 What It Shows

```
/debug chunks
```

Reveals the **complete retrieval result set** from the most recent RAG query — not just the chunks that made it into the final context, but every candidate that was evaluated and ranked, including those that were scored but rejected because their relevance fell below the injection threshold.

### 13.2 Inspector Layout

```
╭─ 🔬 RAG Chunk Inspector — Query: "BERT attention mechanism" ──────╮
│                                                                    │
│  Index: my-project   Threshold: 70%   Injected: 3   Rejected: 5  │
│                                                                    │
│  INJECTED (above threshold)                                        │
│  ────────────────────────────────────────────────────────────── │
│  ✓ #1  src/models/transformer.py  L42-78    Score: 94%           │
│        "class TransformerBlock(nn.Module):..."                   │
│                                                                    │
│  ✓ #2  docs/architecture.md  §Attention     Score: 87%           │
│        "The multi-head attention layer..."                        │
│                                                                    │
│  ✓ #3  README.md  L12-19                   Score: 71%            │
│        "This project implements a BERT-style..."                  │
│                                                                    │
│  REJECTED (below threshold)                                        │
│  ────────────────────────────────────────────────────────────── │
│  ✕ #4  src/utils/tokenizer.py  L1-24       Score: 61%            │
│        "class BPETokenizer:..."                                   │
│                                                                    │
│  ✕ #5  tests/test_attention.py  L88-102    Score: 58%            │
│        "def test_attention_mask():..."                            │
│                                                                    │
│  Adjust threshold: /rag threshold <value>                         │
╰────────────────────────────────────────────────────────────────────╯
```

The rejected section is what makes this inspector uniquely useful — it shows the user exactly what relevant content the retrieval system *almost* chose but didn't, enabling precise tuning of the retrieval threshold when results are unexpectedly missing.

---

## 14. Embedding Inspector

### 14.1 What It Shows

```
/debug embeddings
```

Exposes the inner workings of the vector search process that drives RAG retrieval — the layer below chunk scoring — for users who need to understand or tune the retrieval system at a deeper level:

```
╭─ 🔬 Embedding Inspector — Request #4 ─────────────────────────────╮
│                                                                    │
│  Query sent to embedding model:                                   │
│    "BERT attention mechanism differs from GPT"                    │
│                                                                    │
│  Embedding model: text-embedding-3-small                          │
│  Vector dimensions: 1536                                          │
│  Embedding time: 34ms                                             │
│                                                                    │
│  Search type: cosine similarity                                   │
│  Candidates evaluated: 1,247 chunks                               │
│  Score threshold: 0.70                                            │
│  Candidates above threshold: 8                                    │
│  Context budget remaining at retrieval: 127,400 tokens            │
│  Chunks injected (fit within budget): 3                           │
│  Chunks above threshold but dropped (budget full): 0             │
│                                                                    │
│  Query expansion: none (single-query mode)                        │
╰────────────────────────────────────────────────────────────────────╯
```

The inspector surfaces the exact query string that was embedded (which may differ from the user's raw message if query preprocessing is active), the score threshold in its native float form, why some above-threshold chunks may still have been dropped (context budget exhaustion rather than relevance failure), and whether any query expansion or rewriting occurred.

---

## 15. RAG Injection Preview

### 15.1 What It Shows

```
/debug raginject
```

Shows **exactly what was injected into the context** for the last request, formatted precisely as it was sent to the model — not the raw chunk text, but the injection-formatted version including all surrounding boilerplate, delimiters, source labels, and structural markers that Anythink adds to help the model understand the retrieved context.

This distinction matters because the model sees the injected content exactly as formatted, not as the raw file text — understanding this formatting is essential when debugging cases where the model seems to ignore or misuse retrieved context.

---

## 16. Tool Call Trace

### 16.1 What It Shows

```
/debug tools
```

Renders a **chronological trace of every tool invocation** that occurred during the most recent request — the complete record of the AI agent's tool-use activity, in the order the calls were made:

```
╭─ 🔬 Tool Call Trace — Request #4 ──────────────────────────────────╮
│                                                                    │
│  Call #1 · web_search  ── 340ms ──────────────────────────────── │
│  Input:   { "query": "BERT attention mechanism 2017" }           │
│  Status:  ✓ Success                                               │
│  Output:  5 results returned                                      │
│  Used:    ✓ Yes (model referenced result in response)            │
│                                                                    │
│  Call #2 · web_search  ── 289ms ──────────────────────────────── │
│  Input:   { "query": "GPT causal language model attention" }     │
│  Status:  ✓ Success                                               │
│  Output:  4 results returned                                      │
│  Used:    ✓ Yes (model referenced result in response)            │
│                                                                    │
│  Total tool calls: 2   Total tool time: 629ms                    │
│  Tool time as % of total request: 39.9%                          │
╰────────────────────────────────────────────────────────────────────╯
```

The **Used** field is particularly valuable — it indicates whether the model actually referenced the tool's output in its final response, helping identify cases where the model called a tool unnecessarily, ignored results it should have used, or was confused by the tool output format.

---

## 17. Agent Decision Log

### 17.1 What It Shows

```
/debug agent
```

Surfaces the model's **internal tool-use reasoning** for providers that expose it — the "thinking" or "rationale" layer that shows why the model decided to call a tool at a specific point, what it was trying to find, and how it interpreted the results before continuing:

```
╭─ 🔬 Agent Decision Log — Request #4 ──────────────────────────────╮
│                                                                    │
│  [Provider: Anthropic · Extended thinking available]              │
│                                                                    │
│  Pre-tool reasoning:                                              │
│  "The user is asking about differences between BERT and GPT      │
│   attention. I know the general concepts but should search for   │
│   specific technical details and publication dates to be         │
│   precise. I'll search for both separately."                     │
│                                                                    │
│  → Called: web_search("BERT attention mechanism 2017")           │
│                                                                    │
│  Post-tool-1 reasoning:                                           │
│  "The search returned the original BERT paper. The key detail    │
│   I need is the bidirectional masking approach. I'll now search  │
│   for GPT's approach to confirm the contrast."                   │
│                                                                    │
│  → Called: web_search("GPT causal language model attention")     │
│                                                                    │
│  Final reasoning:                                                 │
│  "I now have enough to give a precise comparison. I'll structure │
│   the answer around the directional vs. unidirectional key       │
│   difference with the masking mechanism explained."              │
│                                                                    │
│  [Provider: Groq · Extended thinking not available]              │
│   Decision log not available for this provider.                  │
╰────────────────────────────────────────────────────────────────────╯
```

Where a provider does not expose thinking/reasoning (most non-Anthropic providers currently), the log clearly states this rather than showing empty or fabricated content.

---

## 18. Tool Output Diff

### 18.1 What It Does

```
/debug tooldiff
```

Compares the **raw output of tool calls** between two runs of the same scheduled prompt or two replays of the same request — showing exactly what changed in the tool results between executions:

```
╭─ 🔬 Tool Output Diff — web_search · Run Jun 17 vs Run Jun 18 ─────╮
│                                                                    │
│  Query: "latest transformer architecture papers"                  │
│                                                                    │
│  - Result #1: "Attention Is All You Need (2017)" — arxiv.org     │
│  + Result #1: "FlashAttention-3 released (2025)" — arxiv.org     │
│                                                                    │
│    Result #2: "BERT: Pre-training..." — unchanged                 │
│                                                                    │
│  - Result #3: "Vision Transformer survey (2023)" — paperswithcode│
│  + Result #3: "Mamba-2 architecture (2025)" — arxiv.org          │
│                                                                    │
│  Changes: 2 results replaced, 1 unchanged, 2 new results added   │
╰────────────────────────────────────────────────────────────────────╯
```

This is particularly useful for scheduled prompts (Section 6 of V3) that run the same agent task on a recurring basis — seeing the diff immediately shows whether the world changed in ways that would affect the AI's response, versus a stale output from an index that didn't update.

---

## 19. Toggleable Debug Side Panel

### 19.1 What It Is

The debug side panel is a **dedicated, persistent, resizable vertical panel** added to the right side of the terminal (separate from and alongside the existing TUI Dashboard's right panel), that streams all debug output in real time — live, without requiring the user to run any `/debug <subcommand>` after each message.

### 19.2 Toggling the Panel

```
/debug panel
```

Or via keyboard shortcut at any time. The panel slides in from the right edge of the terminal, narrowing the conversation area to accommodate it, and slides back out the same way when toggled off. The width of the panel is adjustable using `Ctrl+←` and `Ctrl+→` so the user can give more or less screen space to debug output depending on what they're inspecting.

### 19.3 Panel Content — Live Stream

While the panel is open, every debug event streams into it in chronological order as it happens — no need to run commands after each message:

```
╭─ 🔬 Debug Panel · Level 2 ─────────────────────────────╮
│                                                         │
│  ── Request #5 · 14:52:01 ─────────────────────────── │
│  ▸ Prompt assembled       14ms                         │
│  ▸ RAG query started      96ms                         │
│  ▸ RAG retrieved 3 chunks 178ms                        │
│  ▸ API call sent          179ms                         │
│  ▸ TTFT received          366ms                         │
│  ▸ Streaming...           ●●●●●●●●●                    │
│  ▸ Stream complete        1,108ms                       │
│  ▸ Stop reason: end_turn                               │
│  ▸ Tokens: 1,287 in · 91 out · 111 tok/s              │
│  ▸ Cost: ~$0.0014                                      │
│                                                         │
│  ── Request #4 · 14:49:34 ─────────────────────────── │
│  ▸ TTFT: 187ms · Total: 1,577ms                        │
│  ▸ Stop: end_turn · Tokens: 83 · Cost: ~$0.0012       │
│                                                         │
╰─────────────────────────────────────────────────────────╯
```

Past requests are separated by clear labeled dividers with timestamps, so the panel serves as a running event log for the entire session, scrollable independently of the conversation.

### 19.4 Panel Verbosity

The panel respects the active verbosity level (Section 20) — at Level 1 it shows only timing and stop reason; at Level 2 it adds token counts and tool calls; at Level 3 it streams raw API payloads and chunk data inline. The verbosity level is shown in the panel header.

### 19.5 Panel in Dashboard Mode

When the TUI Dashboard mode is active (from V2), the debug side panel docks into the Dashboard's layout as a fourth column, sitting alongside the existing session list, conversation, and model stats panels — fully integrated into the Dashboard's mouse-navigable, resizable panel system.

---

## 20. Debug Verbosity Levels

### 20.1 Three Levels, One Setting

```
/debug level 1
/debug level 2
/debug level 3
```

Debug mode does not generate all possible output simultaneously — the user chooses how much noise they want with three clearly defined verbosity levels:

### 20.2 Level 1 — Timing & Outcomes

The quietest debug mode. Adds a compact summary line under each AI response bubble and streams minimal data to the debug panel. Suitable for casual monitoring without cluttering the conversation.

**What's shown:**
- Per-response compact timing line (TTFT, total time)
- Stop reason tag in the response bubble footer
- Tokens/second per response
- Estimated cost per response

### 20.3 Level 2 — Full Token Counts & Tool Activity

A fuller picture of each request's technical detail. Suitable for investigating why a conversation is behaving unexpectedly or tracking token usage closely.

**Everything in Level 1, plus:**
- Full timing breakdown (all stages)
- Token usage breakdown (prompt in, completion out, total)
- RAG retrieval summary (chunks injected, threshold, retrieval time)
- Tool call summary (which tools were called, how long, success/failure)
- Context window composition summary

### 20.4 Level 3 — Full Technical Depth

The maximum visibility mode. Every data point Anythink captures is surfaced. Suitable for deep debugging of prompt issues, provider behavior, RAG tuning, or plugin development.

**Everything in Level 2, plus:**
- Full raw prompt payload (streamed to side panel)
- Token-by-token stream trace with inter-token timing
- Full RAG chunk inspector output (injected and rejected)
- Embedding inspector data
- Full agent decision log (where provider exposes it)
- Full tool output for every tool call
- Raw HTTP response headers (status codes, rate limit headers)

---

## 21. Debug Log Export

### 21.1 What It Exports

```
/debug export
```

Exports a **complete, structured debug log** for the entire current session to a file — every captured debug event, in chronological order, with full data at the currently active verbosity level. The export can be shared with another developer, used to file a bug report, or archived for later analysis.

### 21.2 Export Contents

The debug log file contains, per request:

- Request number, timestamp, and session ID
- Model alias and provider used
- Full prompt payload (at Level 3) or summary (at Level 1/2)
- All timing measurements, per stage
- Stop reason
- Token counts and cost estimate
- RAG retrieval data (injected chunks, rejected chunks, scores)
- Tool call trace (inputs, outputs, timing, used flag)
- Agent decision log where available
- HTTP response status and headers (with credentials masked)
- Any errors or warnings that occurred

### 21.3 Export Format

The debug log is written as a **structured JSON file** — machine-readable for programmatic analysis, but also human-readable with a consistent, self-documented schema. An optional `--format txt` flag produces a plain-text version formatted similarly to the terminal panel output, for those who want something directly readable in a standard editor without parsing JSON.

---

## 22. Plugin Trace

### 22.1 What It Shows

```
/debug plugins
```

When one or more plugins are active, shows a **complete invocation trace** for every plugin hook that fired during the current session — surfacing exactly when each plugin was called, what it received, and what it returned:

```
╭─ 🔬 Plugin Trace — Request #4 ───────────────────────────────────╮
│                                                                   │
│  Plugin: anythink-provider-anthropic  v1.2.0                     │
│                                                                   │
│  Hook: on_before_request      ──── 2ms ──────────────────────── │
│  Received: {model, messages, tools, parameters}                  │
│  Returned: {modified parameters: max_tokens increased to 8192}   │
│                                                                   │
│  Hook: on_stream_token        ──── <1ms each ────────────────── │
│  Called: 91 times (once per token)                               │
│  Returned: unmodified token (passthrough mode)                   │
│                                                                   │
│  Hook: on_response_complete   ──── 1ms ──────────────────────── │
│  Received: {full response, usage, stop_reason}                   │
│  Returned: none (read-only hook)                                 │
│                                                                   │
╰────────────────────────────────────────────────────────────────────╯
```

This makes plugin development significantly faster — instead of adding print statements or external debuggers to a plugin, the developer simply activates `/debug plugins` and watches exactly when and how their plugin is being called, and whether its return values are being applied correctly.

---

## 23. Config Deep Validation

### 23.1 What It Does

```
/config validate
```

Goes significantly deeper than `/doctor` — rather than just checking whether config files exist and parse correctly, this command **semantically validates the entire configuration** for logical consistency, deprecated fields, conflicting settings, and internal contradictions:

### 23.2 What Is Checked

| Validation Check | What It Catches |
|---|---|
| **Alias consistency** | Every model alias references a real, known provider and model string; no orphaned aliases pointing to deleted providers |
| **Parameter range validity** | Temperature, top-p, and other per-alias parameters are within valid ranges for their respective providers |
| **Deprecated field detection** | Config fields that existed in earlier versions of Anythink but are no longer supported are flagged with migration guidance |
| **Conflicting settings** | e.g., a model alias configured for a provider whose API key is missing; RAG persistence enabled but no writable cache directory |
| **Scheduled prompt validity** | Every scheduled prompt references a real alias, a real RAG index (if configured), and a valid cron-style schedule |
| **Plugin conflict detection** | Multiple installed plugins that register the same hook or command name, which would produce undefined behavior |
| **MCP connection validity** | External MCP server URLs are reachable and return valid MCP handshake responses |
| **Theme completeness** | All four semantic color roles (Success, Warning, Error, Info) are defined for any user-customized theme |

### 23.3 Output Format

Results follow the same structured format as `/doctor` — one row per check, ✓ / ⚠ / ❌, with an actionable suggested fix for every failure — but at a semantic depth that `/doctor` doesn't reach.

---

## 24. Tokens Per Second

### 24.1 What It Shows

Tokens per second (tok/s) is a real-time generation speed metric — the number of output tokens the model is generating per second, measured from the first token to the last in each response. This is the single most useful number for evaluating a local model or comparing raw generation speed across providers.

### 24.2 Where It Appears

When debug mode is active, tok/s is shown in three places:

**During streaming** — a live, updating counter in the debug side panel showing the rolling tok/s rate as tokens arrive, so the user can watch whether a local model is warming up, hitting a bottleneck, or running at full speed.

**After each response** — a compact summary in the response bubble footer:

```
│                127 words · ·· │ 111 tok/s · stop: end_turn
```

**In the performance summary** — `/debug perf` (Section 25) includes aggregate tok/s statistics across the full session.

### 24.3 Local vs. Cloud Interpretation

For **local models** (Ollama, LM Studio, llama.cpp), tok/s is a direct measure of the hardware's inference throughput — useful for comparing the effect of quantization levels, context length, or hardware configuration on generation speed.

For **cloud providers**, tok/s reflects a combination of the provider's infrastructure speed and current load, plus network conditions — useful for comparing providers but not directly comparable to local model tok/s.

---

## 25. Session Performance Summary

### 25.1 What It Shows

```
/debug perf
```

A comprehensive **end-of-session performance report** covering every measurable performance dimension across all requests made in the current session:

```
╭─ 🔬 Session Performance Summary ──────────────────────────────────╮
│  Session: "BERT vs GPT research"  ·  9 requests  ·  47m 12s      │
│                                                                    │
│  Response Time                                                     │
│  ─────────────────────────────────────────────────────────────── │
│  Average TTFT          214ms                                      │
│  Fastest TTFT          42ms    (Request #6, groqfast)             │
│  Slowest TTFT          487ms   (Request #3, google2)              │
│  Average total time    1,182ms                                    │
│  Slowest request       2,611ms (Request #5 — web search active)  │
│                                                                    │
│  Generation Speed                                                  │
│  ─────────────────────────────────────────────────────────────── │
│  Average tokens/second    187 tok/s                               │
│  Fastest response         459 tok/s  (Request #6, groqfast)       │
│  Slowest response          71 tok/s  (Request #8, gpt4o)          │
│                                                                    │
│  Token Usage                                                       │
│  ─────────────────────────────────────────────────────────────── │
│  Total prompt tokens      10,836                                  │
│  Total completion tokens     741                                  │
│  Total tokens             11,577                                  │
│                                                                    │
│  Time Allocation (of total 47m 12s session)                       │
│  ─────────────────────────────────────────────────────────────── │
│  Waiting on providers    10.6s   (37.4% of active time)          │
│  RAG retrieval            0.7s    (2.5%)                          │
│  Web search               2.1s    (7.4%)                          │
│  Local processing         0.2s    (0.7%)                          │
│  User think time         45m 9s   (idle between messages)        │
│                                                                    │
│  Cost                                                              │
│  ─────────────────────────────────────────────────────────────── │
│  Total estimated cost     $0.0087                                 │
│  Most expensive request   $0.0031 (Request #5, gpt4o)            │
│  Cheapest request         $0.0003 (Request #6, groqfast)          │
│                                                                    │
│  Tool Usage                                                        │
│  ─────────────────────────────────────────────────────────────── │
│  Total tool calls         4 (2 web search, 2 RAG)                │
│  Tool call success rate   100%                                    │
│  Total time in tools      2.8s                                    │
╰────────────────────────────────────────────────────────────────────╯
```

---

## 26. Debug Command Reference

Full list of all debug commands introduced in V3.2.0, organized by category:

### Core Debug Control
| Command | Action |
|---|---|
| `/debug on` | Activate debug mode |
| `/debug off` | Deactivate debug mode |
| `/debug level <1\|2\|3>` | Set verbosity level |
| `/debug panel` | Toggle the live debug side panel |
| `/debug export` | Export full debug log to file |

### Response Generation
| Command | Action |
|---|---|
| `/debug prompt` | Inspect the raw payload of the most recent request |
| `/debug prompt <n>` | Inspect the raw payload of request number n |
| `/debug tokens` | View token-by-token stream trace for the last response |
| `/debug timing` | View full per-stage latency breakdown |
| `/debug stopreason` | View stop reason for the most recent response |
| `/preview` | Preview the fully assembled prompt before sending |

### Provider & Network
| Command | Action |
|---|---|
| `/debug api` | Toggle raw HTTP request/response logging |
| `/debug replay` | Replay the most recent request to the same provider |
| `/debug replay <n>` | Replay request number n |
| `/debug replay <n> --provider <alias>` | Replay to a different provider |
| `/debug latency` | Show ASCII latency history chart for this session |
| `/debug compare <alias> <alias> ...` | Technical multi-provider comparison |

### Context & Prompts
| Command | Action |
|---|---|
| `/debug context` | Show full context window composition breakdown |
| `/debug diff` | Show prompt diff vs. previous request |
| `/config validate` | Run deep semantic config validation |

### RAG Debugging
| Command | Action |
|---|---|
| `/debug chunks` | Show all retrieved and rejected RAG chunks with scores |
| `/debug embeddings` | Show embedding search process details |
| `/debug raginject` | Show exactly what was injected into context from RAG |

### Agent & Tools
| Command | Action |
|---|---|
| `/debug tools` | Show full tool call trace for the last request |
| `/debug agent` | Show agent decision log / model thinking |
| `/debug tooldiff` | Diff tool outputs between two runs |

### Performance
| Command | Action |
|---|---|
| `/debug perf` | Show full session performance summary |
| `/perf` | Alias for `/debug perf` |

### Plugin Debugging
| Command | Action |
|---|---|
| `/debug plugins` | Show plugin invocation trace for the last request |

---

## 27. How the Debug System Fits Together

The V3.2.0 debug system is designed as a **single coherent layer** rather than a collection of independent tools, with three guiding principles:

**One entry point, all features.** Every debug capability is accessible through the `/debug` namespace. A user who has never used debug mode before can type `/debug on` and immediately have the side panel open, timing lines appearing under every response, and stop reasons visible in every bubble footer — without reading documentation or discovering individual commands one at a time.

**Verbosity levels as a progressive reveal.** The three verbosity levels are ordered so that each level is a strict superset of the one below it. A user starts at Level 1 (minimal noise) and increases as they need deeper information — they never have to filter out noise at lower levels or hunt for data they're missing at higher ones.

**Debug mode is observational, never behavioral.** The system captures and surfaces what is already happening at every layer of Anythink's operation — prompt assembly, provider communication, tool execution, RAG retrieval — without changing any of it. The conversation a user has in debug mode is byte-for-byte identical to the one they would have without it. This makes debug mode safe to leave on during normal use, not just when something is broken.

---

*Anythink — Think anything. Ask anything.*

*Version described: 3.2.0 (V3.2 — Debug Infrastructure Build)*
*Document last updated: June 2025*
