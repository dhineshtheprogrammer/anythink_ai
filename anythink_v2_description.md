# Anythink — V2 Build Description

> The second phase of Anythink transforms the app from a powerful CLI chatbot into a full-featured,
> intelligent terminal AI workstation — with a structured HUD, rich chat UI, RAG, agentic browsing,
> code execution, voice input, a multi-panel TUI dashboard, MCP integration, and deep session management.

---

## Table of Contents

1. [UI & Visual Overhaul](#1-ui--visual-overhaul)
2. [Chat Bubble Interface](#2-chat-bubble-interface)
3. [Structured HUD](#3-structured-hud)
4. [Session Naming & Management](#4-session-naming--management)
5. [Response Length Indicator](#5-response-length-indicator)
6. [Startup Experience](#6-startup-experience)
7. [RAG — Retrieval Augmented Generation](#7-rag--retrieval-augmented-generation)
8. [Agentic Web Browsing](#8-agentic-web-browsing)
9. [Code Execution Tool](#9-code-execution-tool)
10. [Conversation Branching](#10-conversation-branching)
11. [Voice Input](#11-voice-input)
12. [TUI Dashboard Mode](#12-tui-dashboard-mode)
13. [MCP — Model Context Protocol](#13-mcp--model-context-protocol)
14. [Desktop Notifications](#14-desktop-notifications)
15. [Multi-Session Support](#15-multi-session-support)
16. [Undo Last Message](#16-undo-last-message)
17. [Favorites & Bookmarks](#17-favorites--bookmarks)
18. [What Stays the Same from V1](#18-what-stays-the-same-from-v1)

---

## 1. UI & Visual Overhaul

### 1.1 The Core Philosophy Shift

V1 Anythink was clean and functional. V2 is **purposefully structured** — every piece of information the user needs is always visible, always in its place, and the conversation itself takes center stage with a richer visual identity. The terminal is no longer just a text pipe — it is a designed workspace.

The V2 layout is composed of three distinct layers that always coexist on screen:

- **Top Layer** — The persistent structured HUD (always visible)
- **Middle Layer** — The conversation area (the majority of the screen, scrollable)
- **Bottom Layer** — The multi-line input editor (always anchored at the bottom)

In the default **Simple Chat Mode**, these three layers fill the terminal window vertically. In **TUI Dashboard Mode**, the conversation area is split into multiple panels (described in Section 12).

### 1.2 Rendering Engine

V2 upgrades the rendering engine to support:

- Bordered, rounded-corner chat bubbles per message turn
- A persistent structured HUD that redraws on data changes without disrupting the scroll position
- Smooth transition animations between Simple Chat Mode and TUI Dashboard Mode
- Mouse event handling (click, scroll) in TUI Dashboard Mode
- All four V1 color themes applied consistently to every new V2 element

---

## 2. Chat Bubble Interface

### 2.1 Design Overview

Every message in the conversation — user messages and AI responses — is now rendered inside its own **bordered chat bubble**. This replaces the flat left-aligned text from V1. Each bubble is visually distinct by role (user vs AI), contains structured metadata, and clearly separates one turn from the next.

### 2.2 User Message Bubbles

User messages are rendered in a bubble aligned to the **right side** of the terminal, using the theme's primary color for the border. The bubble contains:

- A **"You"** label in the top-left corner of the bubble
- The **timestamp** of when the message was sent, in the top-right corner
- The full message text, supporting multi-line content
- If files or images were attached, a list of attachment labels at the bottom of the bubble (📎 filename, 🖼 image name)

Example (Midnight theme):

```
                        ╭─ You ──────────────────── 14:32:05 ─╮
                        │ Explain how BERT's attention         │
                        │ mechanism differs from GPT.          │
                        │                                      │
                        │ 📎 bert_paper.pdf                    │
                        ╰──────────────────────────────────────╯
```

### 2.3 AI Response Bubbles

AI responses are rendered in a bubble aligned to the **left side** of the terminal, using the theme's accent color for the border. The bubble contains:

- The **model alias** (e.g., `google2`) in the top-left corner
- The **provider name** and **response timestamp** in the top-right corner
- Full rich Markdown-rendered response content (bold, italic, code blocks, tables, lists, etc.)
- A **response length indicator** at the bottom-right corner (described in Section 5)
- If web search was triggered, a compact **sources footer** at the bottom of the bubble
- If RAG retrieval was used, a compact **retrieval footer** at the bottom of the bubble

Example (Midnight theme):

```
╭─ google2 ─────────────────────── Gemini · 14:32:11 ─╮
│                                                       │
│  BERT uses **bidirectional attention**, meaning each  │
│  token attends to all tokens in both directions...    │
│                                                       │
│  ┌─ python ─────────────────────────────────────┐    │
│  │  from transformers import BertModel          │    │
│  │  model = BertModel.from_pretrained("bert")   │    │
│  └──────────────────────────────────────────────┘    │
│                                                       │
│  📚 Retrieved from: bert_paper.pdf (pp. 3–5)         │
│                                        127 words ·✦  │
╰───────────────────────────────────────────────────────╯
```

### 2.4 System & Tool Message Bubbles

Messages that are not conversational — tool outputs, web search status, code execution results, system warnings — are rendered in a **center-aligned, muted-border bubble** with an icon prefix to identify the message type:

- 🔍 Web search result
- ⚙️ Code execution output
- 📚 RAG retrieval notice
- ⚠️ Warning or context window alert
- ✅ Success confirmation
- ❌ Error message

These system bubbles are visually lighter than user and AI bubbles — smaller padding, muted border color — so they don't compete with the conversation but are still clearly readable.

### 2.5 Bubble Spacing & Readability

Between every two bubbles there is one blank line of breathing room. Code blocks inside AI bubbles render exactly as V1 — plain, syntax-highlighted, with a language label and border — no additional wrapping. Long AI responses scroll naturally within the conversation area.

---

## 3. Structured HUD

### 3.1 What the HUD Is

The **HUD (Heads-Up Display)** is a persistent, always-visible information bar pinned to the **top of the terminal**. It never scrolls away. It redraws automatically whenever any of its data changes — model switch, token count update, search toggle, session rename — without interrupting the conversation below.

The HUD is the single source of truth for the user's current session state, replacing all the scattered inline status lines from V1.

### 3.2 HUD Layout

The HUD occupies **two lines** at the top of the terminal.

**Line 1 — Session & Identity**

```
 ✦ Anythink  v2.0.0   │  Session: "BERT vs GPT research"   │  Branch: main   │  Theme: Midnight
```

Fields on Line 1:
- **App name and version** — always present, leftmost
- **Session name** — the user-defined name for the current session (see Section 4)
- **Branch indicator** — shows `main` during normal chat, shows `Branch 2` when inside a conversation branch
- **Active theme name** — shows the currently active color theme

**Line 2 — Model, Provider & Context**

```
 Model: google2 (gemini-2.0-flash)  │  Provider: Gemini ●  │  Context: ████████░░░░  61,200 / 1,000,000  (6.1%)  │  🔍 Search: ON  │  📚 RAG: my-project
```

Fields on Line 2:
- **Model alias and raw model name** — e.g., `google2 (gemini-2.0-flash)`
- **Provider name with status dot** — green dot (●) for healthy, yellow (●) for degraded, red (●) for unreachable
- **Context window progress bar** — a compact inline bar showing tokens used vs total, with the count and percentage; color shifts from green → yellow → orange → red as usage rises
- **Web search status** — `🔍 Search: ON` or `🔍 Search: OFF`
- **Active RAG index** — `📚 RAG: my-project` when an index is loaded, or `📚 RAG: —` when none is active

### 3.3 HUD Divider

Below Line 2, a full-width horizontal divider line (using the theme's muted color) separates the HUD from the conversation area. This divider is always present and helps the eye immediately locate the boundary between system state and conversation content.

### 3.4 HUD Color Behavior

Every HUD field follows the active theme. The app name and version are always in the theme's primary color. Model and provider info are in accent color. The context bar uses the same green→yellow→orange→red gradient as V1. Status indicators (Search ON/OFF, RAG active/inactive) use green for active and muted gray for inactive.

---

## 4. Session Naming & Management

### 4.1 Naming a Session

When a user starts a new session, Anythink asks them — in a single, non-intrusive prompt — whether they want to name the session or use an auto-generated name. This prompt appears before the first message input:

```
╭─ New Session ───────────────────────────────────────────╮
│  Name this session? (press Enter to auto-name)          │
│  > BERT vs GPT research_                                │
╰─────────────────────────────────────────────────────────╯
```

If the user presses Enter without typing, Anythink auto-generates a name using the format: `Session · <date> · <model alias>` (e.g., `Session · Jun 18 · google2`).

After the first AI response, Anythink can also offer to **auto-suggest a session name** based on the topic of the opening exchange — the user can accept, edit, or ignore the suggestion.

### 4.2 Renaming a Session

At any point during a session, the user can rename it using `/rename <new name>`. The HUD updates immediately to reflect the new name. The session file on disk is also renamed to match.

### 4.3 Session Name in History

All session management views (`/history`, the TUI Dashboard left panel) display the **user-defined session name** as the primary label, with the date and model alias shown as secondary metadata. This makes finding past conversations as natural as scrolling through a ChatGPT sidebar.

### 4.4 Session File Naming on Disk

The plain text session file is named using the user-defined session name, slugified:
`YYYY-MM-DD_HHMMSS_<slug>.txt`

Example: `2025-06-18_143022_bert-vs-gpt-research.txt`

If no name is given, the auto-generated name is slugified instead.

---

## 5. Response Length Indicator

### 5.1 What It Shows

After every AI response, a compact **response length indicator** is shown in the **bottom-right corner of the AI response bubble**. It shows two pieces of information:

- **Word count** of the response
- A **length symbol** that visually categorizes how long the response is

### 5.2 Length Categories

| Symbol | Category | Word Range |
|---|---|---|
| · | Brief | 1 – 80 words |
| ·· | Short | 81 – 250 words |
| ··· | Medium | 251 – 600 words |
| ✦ | Long | 601 – 1,200 words |
| ✦✦ | Very Long | 1,201+ words |

### 5.3 Display Example

```
│                                        127 words · ·· │
```

The indicator is styled in the theme's muted color so it is readable but does not compete with the response content. It is the last element in the bubble footer, always right-aligned.

---

## 6. Startup Experience

### 6.1 Returning User Startup

For returning users (any session previously run), the ASCII logo is **not shown**. Instead, a single compact one-liner appears immediately, showing the essential state:

```
 ✦ Anythink v2.0.0  ·  google2 (Gemini)  ·  1,000,000 ctx  ·  Type /help for commands
```

This line is shown for 1.5 seconds (or until the user starts typing), then the HUD takes over as the persistent state display and the input area becomes active.

### 6.2 First-Time User Startup

For first-time users, the full ASCII logo and setup wizard still run exactly as described in V1. No change here.

### 6.3 Session Resume Prompt

If the user's most recent session was left mid-conversation (more than 2 turns, not explicitly closed with `/exit`), Anythink shows a one-line resume prompt below the startup line:

```
 ↩ Resume last session? "BERT vs GPT research"  [Y/n]
```

If the user presses Y or Enter, the previous session loads immediately with full history displayed. If they press N, a new session starts.

---

## 7. RAG — Retrieval Augmented Generation

### 7.1 What RAG Does in Anythink

RAG allows Anythink to give the AI access to the user's own documents and codebases — files that are too large or too numerous to fit in a context window. Instead of pasting file contents manually, the user indexes a folder once, and Anythink automatically retrieves the most relevant chunks from that index for every query, injecting them into the AI's context silently and efficiently.

RAG is always active when an index is loaded. It is not a mode the user toggles — it is a layer that enriches every response automatically as long as an index is selected.

### 7.2 Two Separate RAG Scopes

Anythink manages two types of RAG indexes independently. They are configured, indexed, and selected separately, but both work identically during chat:

**Project Index** — for source code and technical file trees. Designed for indexing a software repository or any structured folder of code files. Supports all common programming language file types, configuration files, and documentation within a codebase.

**Document Library Index** — for documents, research, notes, and reference material. Designed for PDFs, Word documents, Markdown notes, plain text files, and similar content. Multiple document libraries can be maintained (e.g., one for research papers, one for personal notes).

Both types support all the same index management features described below.

### 7.3 Index Persistence Options

When a user creates a new RAG index, Anythink asks them upfront how they want the index to be managed:

**Option A — Rebuild Every Time**
The index is not saved to disk. Every time the user loads this index name, Anythink re-scans and re-indexes the source folder from scratch. This always reflects the latest state of the files but takes time on each startup.

**Option B — Persist on Disk**
The index is saved to disk after the first build and reloaded instantly on future sessions. The user manually triggers a rebuild when they want to refresh the index (via `/rag rebuild <name>`). This is fast on startup but may reflect a slightly older state of the files.

Both options are always available. The user can also change the persistence strategy for an existing index at any time.

### 7.4 Multiple Named Indexes

Users can create and maintain as many named RAG indexes as they want. Each index has:

- A **user-defined name** (e.g., `my-project`, `research-papers`, `company-docs`)
- A **type** (Project or Document Library)
- A **source path** (the folder being indexed)
- A **persistence mode** (Rebuild or Persisted)
- A **creation date** and **last indexed date**
- A **file count** and **total chunk count**

Only **one index is active per session** at a time. The active index is shown in the HUD. The user switches indexes using `/rag use <name>`.

### 7.5 RAG Index Management Commands

| Command | Action |
|---|---|
| `/rag list` | List all named indexes with type, source path, file count, and last indexed date |
| `/rag new` | Interactively create a new index (asks for name, type, path, persistence mode) |
| `/rag use <name>` | Set the active RAG index for this session |
| `/rag off` | Deactivate RAG for this session (no index active) |
| `/rag rebuild <name>` | Rebuild a persisted index from its source folder |
| `/rag info <name>` | Show detailed stats for an index |
| `/rag delete <name>` | Delete a named index (and its persisted data if applicable) |
| `/rag status` | Show the current active index and its health |

### 7.6 RAG Visibility in Responses

When RAG retrieval is used for a response, the AI response bubble shows a detailed **retrieval footer** at the bottom — separate from the main response content, clearly labeled, and collapsed by default with the option to expand.

**Collapsed view** (always shown):

```
│  📚 Retrieved from 3 sources  [expand]                  │
```

**Expanded view** (shown when user presses the expand key or runs `/rag sources`):

```
│  📚 RAG Sources Retrieved:                              │
│                                                         │
│   1. src/models/transformer.py                          │
│      Lines 42–78  ·  Relevance: 94%                    │
│      "class TransformerBlock(nn.Module):"               │
│                                                         │
│   2. docs/architecture.md                               │
│      Section: "Attention Mechanism"  ·  Relevance: 87% │
│      "The multi-head attention layer applies..."        │
│                                                         │
│   3. README.md                                          │
│      Lines 12–19  ·  Relevance: 71%                    │
│      "This project implements a BERT-style encoder..."  │
```

Each source entry shows: the file path, the exact line range or section retrieved, the relevance score, and a short excerpt of the retrieved text (the first line of the chunk). This gives the user complete transparency into what the AI was given as context for each response.

---

## 8. Agentic Web Browsing

### 8.1 Two-Tier Browsing Architecture

Anythink V2 implements web access in two tiers that the user can use independently or together:

**Tier 1 — Search Snippets** (always available when search is ON)
The AI retrieves summaries and snippets from search result pages — fast, lightweight, and sufficient for most factual questions. This is the default behavior inherited and extended from V1.

**Tier 2 — Full Page Fetch** (on demand)
When snippets are not enough, the full content of a specific URL is fetched and fed to the AI as additional context. The user can request this explicitly ("read the full page"), or the AI can suggest it ("I found this page — shall I read it fully?").

Full page fetching uses **raw HTTP by default** — fast and dependency-free, sufficient for most static and server-rendered pages. If the user needs JavaScript-rendered content (SPAs, dynamic dashboards, etc.), they can activate **headless browser mode** — available as an opt-in setting that requires the user to have a compatible headless browser installed. The user can toggle between HTTP and headless modes using `/browse mode http` or `/browse mode headless`.

### 8.2 Two Autonomy Modes

Anythink provides two modes for how aggressively the AI takes browsing actions:

**Ask-First Mode**
Before visiting any URL, the AI pauses and asks the user for permission:

```
╭─ 🔍 Anythink wants to browse ──────────────────────────╮
│  I found a relevant page. Should I open it?            │
│                                                        │
│  URL: https://arxiv.org/abs/1706.03762                 │
│  Source: "Attention Is All You Need" — arXiv           │
│                                                        │
│  [Y] Read full page   [S] Snippet only   [N] Skip      │
╰────────────────────────────────────────────────────────╯
```

**Autonomous Mode**
The AI fetches pages and gathers information without pausing. It reports what it found after completing its research. The user sees a compact activity log during autonomous research:

```
╭─ ⚙️ Browsing ──────────────────────────────────────────╮
│  ✓ Searched: "attention mechanism transformer 2017"    │
│  ✓ Read:     arxiv.org/abs/1706.03762                  │
│  ✓ Read:     paperswithcode.com/method/transformer     │
│  ◌ Reading:  jalammar.github.io/illustrated-transformer│
╰────────────────────────────────────────────────────────╯
```

The user chooses their preferred autonomy mode during first-run setup, but can switch at any time using `/browse mode ask` or `/browse mode auto`.

### 8.3 Sources Footer in Response Bubbles

Every AI response that used web content shows a **sources footer** at the bottom of the response bubble, listing each URL visited with its title and the tier used (snippet or full page):

```
│  🔍 Web Sources:                                        │
│   1. arxiv.org — "Attention Is All You Need" (full)   │
│   2. paperswithcode.com — "Transformer" (snippet)     │
```

---

## 9. Code Execution Tool

### 9.1 Philosophy

Anythink's code execution tool runs code in the **user's own environment** — no Docker, no virtual machines, no remote sandboxes. The code runs using whatever runtime the user already has installed on their machine (Python, Node, Bash, etc.). This keeps the tool simple, dependency-free, and immediately useful.

The trade-off (security and isolation) is accepted by design. Anythink clearly communicates to the user what code will run before running it, and the user has full control over the approval mode.

### 9.2 Supported Languages

Anythink detects and runs code blocks in the following languages, using the runtime available in the user's PATH:

| Language | Runtime Used |
|---|---|
| Python | `python3` |
| Bash / Shell | `bash` |
| JavaScript | `node` |
| SQL | User-configured database client |
| Ruby | `ruby` |
| Go | `go run` |

If the required runtime is not found in PATH, Anythink displays a clear error: *"Python3 not found. Please install it or ensure it is in your PATH."*

### 9.3 Two Execution Approval Modes

Like browsing, code execution has two modes the user chooses from:

**Ask-Every-Time Mode**
Before any code block is run, Anythink shows a confirmation bubble:

```
╭─ ⚙️ Run Code? ──────────────────────────────────────────╮
│  Language: Python                                       │
│                                                         │
│  ┌─ python ──────────────────────────────────────────┐  │
│  │  import math                                      │  │
│  │  print(math.factorial(10))                        │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  [Y] Run   [E] Edit before running   [N] Skip           │
╰─────────────────────────────────────────────────────────╯
```

**Auto-Run Mode**
Code is executed automatically whenever the AI produces a runnable code block. A brief "Executing…" status is shown while running.

The user sets their preferred mode during setup and can switch with `/exec mode ask` or `/exec mode auto`.

### 9.4 Output Display

Code execution output (stdout and stderr) is rendered in a **styled terminal output block** inline in the conversation, immediately below the triggering code block, inside a system message bubble:

```
╭─ ⚙️ Execution Output ─── Python · 0.03s ──────────────╮
│                                                        │
│  ┌─ stdout ───────────────────────────────────────┐   │
│  │  3628800                                       │   │
│  └────────────────────────────────────────────────┘   │
│                                                        │
│  Exit code: 0  ✓                                       │
╰────────────────────────────────────────────────────────╯
```

If there is stderr output, it is shown in a separate labeled block within the same bubble in the theme's warning color. The exit code is always shown. Execution time is shown in the bubble header. If execution exceeds 30 seconds, a timeout warning is shown and the user is asked whether to kill the process or wait longer.

The execution output is then **fed back to the AI** automatically, allowing the AI to comment on the result, debug errors, or suggest next steps.

---

## 10. Conversation Branching

### 10.1 What Branching Means

Conversation branching allows the user to **split off from any point in the conversation** and explore an alternative line of questioning or prompting — without losing the original conversation. The original conversation is always preserved as the `main` branch. Branches are independent and do not merge back.

### 10.2 Creating a Branch

The user creates a branch at any turn in the conversation by typing:

```
/branch
```

When triggered, Anythink shows a branch creation prompt:

```
╭─ 🌿 Create Branch ─────────────────────────────────────╮
│  Creating branch from Turn 7 (current point).          │
│                                                         │
│  Active branches in this session:                       │
│                                                         │
│   main       ·  Started at Turn 1  (current: Turn 7)  │
│                                                         │
│  New branch will be: Branch 1 · from Turn 7            │
│                                                         │
│  [Y] Create branch   [N] Cancel                        │
╰─────────────────────────────────────────────────────────╯
```

After confirming, the conversation switches into Branch 1, starting from Turn 7. The HUD Branch indicator updates from `main` to `Branch 1`.

### 10.3 Branch List Display

At any time, the user can view all branches in the session using `/branch list`:

```
╭─ 🌿 Branches — "BERT vs GPT research" ────────────────╮
│                                                        │
│   Branch       From Turn   Messages   Status          │
│  ─────────────────────────────────────────────────────│
│   main          Turn 1         9      ← current       │
│   Branch 1      Turn 4         3      independent     │
│   Branch 2      Turn 7         6      independent     │
│   Branch 3      Turn 7         1      independent     │
│                                                        │
│  [Switch branch: /branch switch <name>]               │
╰────────────────────────────────────────────────────────╯
```

The table is deliberately simple and easy to read. Each branch is named `Branch N` sequentially and shows exactly which turn it diverged from, how many messages are in it, and its status.

### 10.4 Switching Between Branches

The user navigates between branches using:

```
/branch switch main
/branch switch "Branch 2"
```

When switching, the conversation area clears and redraws with the history of the selected branch. The HUD updates immediately. The user is shown a brief transition indicator:

```
 🌿 Switched to Branch 2 · from Turn 7 · 6 messages
```

### 10.5 Branch Independence

Branches are always independent. There is no merge command. If the user wants to bring a result from a branch into the main conversation, they do so manually — copy-paste the content, or summarize it in their next message on the main branch. This keeps the branching system simple and free of merge conflict complexity.

### 10.6 Branch Storage

All branches of a session are stored together in the same plain text session file, with clear section delimiters marking the start and end of each branch and the turn number at which they diverged.

---

## 11. Voice Input

### 11.1 Activation

Voice input is activated using the slash command:

```
/voice
```

This can be entered at any point in the input area. Upon activation, Anythink immediately begins recording from the system's default microphone.

### 11.2 Recording Status

While recording, a live recording indicator replaces the input prompt:

```
╭─ 🎙 Listening... ─────────── Press Enter to stop ─────╮
│  ▐▌▐▌▐▌ ██▌▐▌▐██▌▐██▌▐▌▐▌ ▐▌  (audio waveform)       │
╰────────────────────────────────────────────────────────╯
```

A simple audio waveform visualization (ASCII amplitude bars) shows that audio is being captured. The user presses Enter to stop recording.

### 11.3 Transcription & Editable Output

After recording stops, the audio is transcribed locally using **OpenAI Whisper** (running locally on the user's machine). The transcribed text is placed **directly into the multi-line input box** — editable, exactly like manually typed text. The user can review and correct the transcription before pressing Enter to send it.

```
╭─ You ──────────────────────────────────────────────────
│ 🎙 Explain how transformers use self attention in
│ natural language processing_
╰────────────────────────────────────────────────────────
```

The 🎙 prefix icon indicates the message was voice-transcribed, but it is purely visual — the sent message is identical to a typed one.

### 11.4 Whisper Model Selection

The user chooses which Whisper model to use. This choice is made during the first `/voice` invocation and saved to config. It can be changed at any time via `/voice model`:

| Whisper Model | Size | Speed | Accuracy |
|---|---|---|---|
| `tiny` | ~39 MB | Fastest | Basic |
| `base` | ~74 MB | Fast | Good |
| `small` | ~244 MB | Moderate | Very good |
| `medium` | ~769 MB | Slow | Excellent |
| `large` | ~1.5 GB | Slowest | Best |
| `turbo` | ~809 MB | Fast | Excellent |

Anythink downloads the chosen model automatically on first use (with a progress indicator) and caches it locally.

### 11.5 Voice Input Language

Whisper supports multilingual transcription. Anythink auto-detects the spoken language by default. The user can also pin a specific transcription language in config for faster, more accurate results when they always speak the same language.

---

## 12. TUI Dashboard Mode

### 12.1 What Dashboard Mode Is

TUI Dashboard Mode transforms Anythink from a linear chat interface into a full **multi-panel terminal workspace**. The same conversation continues — model, session, history all carry over — but the screen is divided into 4 persistent, interactive panels that give the user simultaneous visibility into their session state, conversation, tools, and file/RAG resources.

### 12.2 Entering and Exiting Dashboard Mode

The user switches into Dashboard Mode mid-session using the keyboard shortcut `Ctrl+D`. They return to Simple Chat Mode using `Ctrl+D` again (a toggle). No data is lost on either transition. The switch is instant and animated.

Alternatively, `anythink --dashboard` launches directly into Dashboard Mode on startup.

### 12.3 The Four Panel Layout

The terminal window in Dashboard Mode is divided as follows:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  HUD Line 1: Anythink v2.0.0  │  Session: "BERT vs GPT research"  │  Branch  │
│  HUD Line 2: Model · Provider · Context Bar · Search Status · RAG Index      │
├────────────────────┬─────────────────────────────┬───────────────────────────┤
│                    │                             │                           │
│   LEFT PANEL       │      CENTER PANEL           │     RIGHT PANEL           │
│   Session List     │      Conversation           │     Model & Stats         │
│                    │      (Chat Bubbles)          │                           │
│                    │                             │                           │
│                    │                             │                           │
│                    │                             │                           │
├────────────────────┴─────────────────────────────┴───────────────────────────┤
│                                                                               │
│   BOTTOM PANEL — File Browser / RAG Index Browser / Tool Output              │
│                                                                               │
├───────────────────────────────────────────────────────────────────────────────┤
│  INPUT AREA — Always pinned at bottom                                         │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 12.4 Left Panel — Session List

The left panel shows a scrollable list of all saved sessions, styled like a chat application sidebar. Each entry shows:

- The user-defined session name (primary label)
- Date and time of last activity
- Model alias used
- Number of turns

The currently active session is highlighted. Clicking or keyboard-navigating to a session and pressing Enter opens it in the center panel. The user can also rename or delete sessions from this panel.

The left panel can be **toggled** (hidden/shown) using `Ctrl+L` to give more space to the conversation.

### 12.5 Center Panel — Conversation

The center panel is the main conversation area — the same chat bubble interface described in Section 2, but constrained to the center column. It scrolls independently. The input area at the very bottom spans the full width of the screen and is shared with all panels.

### 12.6 Right Panel — Model & Stats

The right panel provides detailed real-time statistics and model information for the current session:

- **Model details** — alias, raw model name, provider, context window size
- **Token usage breakdown** — system prompt tokens, conversation history tokens, current response tokens, total used
- **Context window bar** — a vertical bar version of the HUD context indicator, larger and more detailed
- **Session stats** — number of turns, total words sent, total words received, session duration
- **Provider health** — latency of last request, average latency, error count this session
- **Active tools** — whether web search and RAG are active, last search query, last RAG retrieval

The right panel can be **toggled** using `Ctrl+R`.

### 12.7 Bottom Panel — File / RAG / Tool Output

The bottom panel is a **tabbed panel** with three tabs the user switches between using `Tab` or by clicking:

**Tab 1 — File Browser**
A simple tree-view browser of the user's filesystem, starting from the current working directory. The user can navigate it with arrow keys or mouse clicks. Pressing Enter on a file attaches it to the next message (same as `/file <path>`). Files can be previewed (first N lines shown inline in the panel).

**Tab 2 — RAG Index Browser**
Shows the contents of the currently active RAG index. The user can browse indexed documents, see which chunks were retrieved in the last response, inspect chunk contents, and trigger an index rebuild. When a retrieval event happens, this tab auto-highlights the retrieved chunks.

**Tab 3 — Tool Output**
Shows the output of the most recent tool invocations — code execution results, web fetch content, search results. Each tool output is shown with a timestamp and the tool type icon. This gives the user a persistent log of all agentic tool activity in the session, separate from the main conversation flow.

### 12.8 Mouse Support

All four panels support mouse interaction in Dashboard Mode:

- **Click** to focus a panel
- **Click** to select a session in the left panel
- **Click** to switch tabs in the bottom panel
- **Scroll** to scroll any panel independently
- **Click** on a file in the File Browser to select it for attachment
- **Click** on a RAG chunk to expand its preview
- **Click** buttons in confirmation prompts

Mouse support is always-on in Dashboard Mode and cannot be disabled per-session (it can be disabled globally in config for users who prefer pure keyboard navigation).

---

## 13. MCP — Model Context Protocol

### 13.1 Dual Role: Client and Server

Anythink V2 implements MCP in both directions:

**As an MCP Client**, Anythink can connect to any external MCP server and use the tools/resources it exposes — giving the AI access to databases, filesystems, APIs, Git repositories, and any other MCP-compatible service.

**As an MCP Server**, Anythink exposes its own capabilities to external tools — meaning another MCP-compatible application can use Anythink's RAG, web search, session history, and model routing as services.

### 13.2 Built-in MCP Servers

Anythink ships with a set of built-in MCP servers that are always available without any external installation:

| Built-in Server | What It Exposes |
|---|---|
| **Filesystem Server** | Read, write, list, search files and directories on the local machine |
| **Session History Server** | Query and retrieve from Anythink's own plain text session history |
| **RAG Server** | Query any loaded RAG index by natural language |
| **Web Search Server** | Perform web searches using the configured search backend |

These built-in servers are enabled by default and are the tools the AI agent uses internally during a normal Anythink session.

### 13.3 External MCP Server Connection

Users can connect Anythink to any external MCP server using:

```
/mcp connect <server-url>
```

Or by adding the server URL to the config file. Once connected, Anythink auto-discovers all tools exposed by that server and makes them available to the AI for the session. External servers can expose anything — a company database, a GitHub integration, a calendar, a custom API.

### 13.4 MCP Management Commands

| Command | Action |
|---|---|
| `/mcp list` | List all active MCP connections (built-in and external) |
| `/mcp connect <url>` | Connect to an external MCP server |
| `/mcp disconnect <name>` | Disconnect from an external MCP server |
| `/mcp tools <name>` | List all tools exposed by a specific MCP server |
| `/mcp status` | Show health and latency of all MCP connections |
| `/mcp server start` | Start Anythink as an MCP server (exposes Anythink's own tools) |
| `/mcp server stop` | Stop the Anythink MCP server |
| `/mcp server status` | Show whether Anythink's own MCP server is running and its endpoint |

### 13.5 MCP Tool Visibility in Chat

When the AI uses an MCP tool, a system bubble appears in the conversation showing which tool was called, which server it came from, and a summary of the result — just like the web search and code execution bubbles. MCP tool activity is also logged in the Tool Output tab of the TUI Dashboard bottom panel.

---

## 14. Desktop Notifications

### 14.1 When Notifications Are Sent

Anythink sends OS desktop notifications for long-running background operations, so the user can switch away from the terminal and be alerted when their task is complete. Notifications are sent for:

- **RAG index build complete** — "✦ Anythink: Index 'my-project' ready (4,312 chunks)"
- **Slow AI response complete** — for responses that take more than 15 seconds: "✦ Anythink: google2 response ready"
- **Autonomous web browsing complete** — "✦ Anythink: Web research done — 4 pages read"
- **Code execution complete** — for executions longer than 10 seconds: "✦ Anythink: Code finished — exit code 0"
- **Provider failure** — "⚠ Anythink: Gemini is unreachable — please select another model"

### 14.2 Platform Support

Notifications use the OS-native notification system:
- **macOS** — macOS Notification Center
- **Linux** — `libnotify` / `notify-send` (compatible with GNOME, KDE, and most desktop environments)
- **Windows** — Windows Toast Notifications

### 14.3 Notification Settings

Notifications can be turned on or off globally in config, or per notification type. They are **on by default**. The user can manage them with `/notify on`, `/notify off`, and `/notify settings`.

---

## 15. Multi-Session Support

### 15.1 True Isolation

Multiple Anythink instances can run simultaneously in separate terminal windows or tabs, each with a completely independent session. There is no shared in-memory state between instances. Each instance:

- Has its own model selection and active provider
- Has its own conversation history in memory
- Has its own active RAG index
- Has its own context window tracking
- Has its own branch state

Two instances can use the same model alias or completely different ones.

### 15.2 Session File Locking

Since all sessions are written to the same `sessions/` directory, Anythink uses file locking to prevent two instances from writing to the same session file simultaneously. Each instance creates its own uniquely named session file from the moment it starts. There is no risk of session data collision.

### 15.3 Live Session Awareness

The TUI Dashboard's Session List panel shows a **live indicator** next to any session that is currently open in another terminal instance:

```
│  ● BERT vs GPT research      Jun 18  14:32  google2  │  ← active in another window
│  ○ Django project review     Jun 17  09:11  groqfast  │
```

This tells the user which sessions are currently live elsewhere so they don't accidentally open the same session in two windows.

---

## 16. Undo Last Message

### 16.1 What Undo Does

The `/undo` command removes the most recent exchange from the conversation — the last user message and the last AI response, together as a pair. This is a single-level undo. After undoing, the conversation is exactly as it was before that message was sent.

The undo operation updates:
- The in-memory conversation history (used for context in the next request)
- The live chat display (the removed bubbles disappear from the screen)
- The plain text session file on disk (the removed turns are deleted)
- The context window token count in the HUD

### 16.2 Undo Prompt

When the user types `/undo`, Anythink shows a confirmation:

```
╭─ ↩ Undo Last Message ─────────────────────────────────╮
│  This will remove:                                     │
│                                                        │
│  Your message:  "Explain how BERT's attention..."      │
│  AI response:   "BERT uses bidirectional attention..." │
│                 (127 words)                            │
│                                                        │
│  [Y] Undo   [N] Cancel                                 │
╰────────────────────────────────────────────────────────╯
```

### 16.3 Undo Limit

Undo is limited to the **last message pair only** (one level deep). There is no multi-level undo in V2. If the user wants to go back further, they can use branching (`/branch`) from an earlier turn and start fresh from that point.

### 16.4 Undo in Branches

Undo works independently within each branch. Undoing in Branch 2 does not affect the main branch. The undo only affects the currently active branch.

---

## 17. Favorites & Bookmarks

### 17.1 What Bookmarks Are

A bookmark is a user-flagged AI response that is saved for later reference. The user can mark any AI response in the current session as a favorite. Bookmarks are stored with the session file and are separately queryable.

### 17.2 Creating a Bookmark

The user bookmarks the most recent AI response using:

```
/bookmark
```

Or a specific turn using:

```
/bookmark <turn number>
```

When a response is bookmarked, a small **bookmark indicator** (✦) appears in the top-right corner of that AI response bubble — permanently, for the rest of the session and in future loads:

```
╭─ google2 ─────────────────────── Gemini · 14:32:11 ✦ ─╮
```

The user can also add a **label** to a bookmark:

```
/bookmark label "key insight on attention"
```

### 17.3 Viewing Bookmarks

The user views all bookmarks in the current session using `/bookmarks`:

```
╭─ ✦ Bookmarks — "BERT vs GPT research" ───────────────╮
│                                                       │
│   #  Turn   Label                    Words   Time     │
│  ────────────────────────────────────────────────────-│
│   1  Turn 4  key insight on attention  127  14:32:11  │
│   2  Turn 9  code example — forward    203  14:51:04  │
│   3  Turn 12 (unlabeled)               89  15:02:33   │
│                                                       │
│  [/bookmark jump <#> to go to that turn]             │
╰───────────────────────────────────────────────────────╯
```

### 17.4 Jumping to a Bookmark

```
/bookmark jump 2
```

Scrolls the conversation area directly to Turn 9 and highlights that bubble momentarily.

### 17.5 Exporting Bookmarks

```
/bookmark export
```

Exports all bookmarked responses from the current session to a separate plain text file — containing only the bookmarked AI responses with their labels, timestamps, and turn numbers. Useful for extracting key insights from a long research session.

### 17.6 Cross-Session Bookmark Search

```
/bookmark search "attention mechanism"
```

Searches bookmark labels across **all saved sessions** and returns matching results, making bookmarks a lightweight personal knowledge base built from past Anythink conversations.

---

## 18. What Stays the Same from V1

The following V1 features carry over into V2 completely unchanged and fully functional:

- All 4 color themes (Midnight, Aurora, Ember, Arctic) — now applied to all new V2 elements
- Full provider support — Groq, Gemini, OpenAI, Anthropic, Mistral, Cohere, Ollama, LM Studio, llama.cpp, and plugins
- Model alias system — user-defined names, alias registry, mid-session switching, fallback prompting
- API key management via system keychain — full CRUD from terminal
- Multi-line input editor — same interaction style
- Token-by-token streaming
- Rich Markdown rendering — all element types
- All V1 slash commands — `/help`, `/clear`, `/new`, `/exit`, `/model`, `/persona`, `/history`, `/keys`, `/theme`, `/plugins`
- Session persistence as plain text files
- Persona / system prompt per session
- Plugin architecture — entry points based, fully extensible
- First-run setup wizard
- PyPI distribution as `anythink` with provider extras (`anythink[groq]`, `anythink[all]`, etc.)
- XDG Base Directory standard for all file storage
- Python 3.11+ requirement
- MIT License / open source
- GitHub Actions CI with lint, type check, test, coverage, security scan, and publish stages

---

*Anythink — Think anything. Ask anything.*

*Version described: 2.0.0 (V2 — Second Build Scope)*
*Document last updated: June 2025*
