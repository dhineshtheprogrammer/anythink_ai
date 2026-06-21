# Anythink — V2.1 UI/UX Refinement Build

> A focused polish build addressing real-world usability issues found after building and using Anythink V2.
> This build does not introduce new major features — it fixes interaction gaps, corrects a data accuracy bug,
> and adds the small but essential conveniences that make a terminal AI tool feel truly production-grade.

---

## Table of Contents

1. [Hard Reset for `/clear`](#1-hard-reset-for-clear)
2. [Slash Command Drop-Up Menu](#2-slash-command-drop-up-menu)
3. [Contextual Real-Time Loading States](#3-contextual-real-time-loading-states)
4. [Accurate Token Counting](#4-accurate-token-counting)
5. [Input History Navigation](#5-input-history-navigation)
6. [Startup Logo Behavior](#6-startup-logo-behavior)
7. [Persistent HUD Confirmation](#7-persistent-hud-confirmation)
8. [Interactive `/settings` Menu](#8-interactive-settings-menu)
9. [Actionable Error Messages](#9-actionable-error-messages)
10. [Copy Response / Copy Code Shortcut](#10-copy-response--copy-code-shortcut)
11. [Open Session in Notepad Shortcut](#11-open-session-in-notepad-shortcut)
12. [Stop Response Generation Shortcut](#12-stop-response-generation-shortcut)
13. [Responsive HUD on Terminal Resize](#13-responsive-hud-on-terminal-resize)
14. [Shortcut Key Hint Bar](#14-shortcut-key-hint-bar)
15. [Rotating Tips Bar](#15-rotating-tips-bar)
16. [Summary of Touchpoints Changed](#16-summary-of-touchpoints-changed)

---

## 1. Hard Reset for `/clear`

### 1.1 The Fix

`/clear` becomes a true **hard reset** of the active conversation. Once executed:

- The in-memory conversation history is wiped completely — nothing remains for the AI to reference in future turns.
- The visible chat area is wiped completely — scrolling up shows nothing from before the clear. The screen behaves exactly like a brand-new session with zero messages.
- The HUD's context window indicator resets to `0 / <max>` immediately, reflecting the true, empty state.

### 1.2 Preserving History Despite the Clear

Even though the live conversation is wiped, **nothing is actually lost**. Before the clear executes, the full conversation up to that point is automatically saved (or appended, if already auto-saving) to the plain text session file on disk exactly as it stood. This file remains fully intact, searchable via `/history search`, and reachable via `/history open <id>` — completely independent of what's currently visible on screen.

This means `/clear` serves its real purpose: giving the AI a clean context window to reduce token usage and avoid context window overflow, while guaranteeing the user never loses a past exchange. The old content is one `/history` command away, never gone.

### 1.3 Confirmation Before Clearing

Because this is now a destructive action on the visible session, `/clear` shows a brief confirmation prompt before executing:

```
╭─ Clear Conversation? ──────────────────────────────────╮
│  This will reset your visible conversation to empty.   │
│  Your message history up to now is saved and can be    │
│  reopened anytime with /history.                       │
│                                                         │
│  [Y] Clear   [N] Cancel                                │
╰─────────────────────────────────────────────────────────╯
```

### 1.4 Post-Clear State

After confirming, the chat area shows the standard empty-session placeholder, and a brief one-line confirmation appears:

```
 ✓ Conversation cleared. Previous messages saved to session history.
```

---

## 2. Slash Command Drop-Up Menu

### 2.1 Why Drop-Up, Not Drop-Down

Because the input box is anchored at the **bottom** of the terminal, a traditional dropdown (expanding downward) would either get clipped by the screen edge or overlap the input itself. Anythink instead uses a **drop-up menu** — opening upward from the input box, directly above where the user is typing — exactly matching the interaction pattern from Claude Code's CLI.

### 2.2 Trigger and Live Filtering

The moment the user types `/` as the first character of their message, the drop-up appears instantly above the input box, listing all available slash commands. As the user continues typing (e.g., `/mo`), the list **filters live**, narrowing down to only matching commands (`/model`, `/model list`, `/model add`, `/model remove`) with each keystroke. The filtering matches against the command name, not the description.

### 2.3 Visual Layout

Each entry in the drop-up shows the command on the left and a short, single-line description on the right, separated by a soft divider — mirroring Claude Code's style:

```
╭─────────────────────────────────────────────────────────╮
│  /model              Switch or view the active model    │
│  /model list          List all configured model aliases │
│  /model add           Add a new model alias              │
│  /model remove        Remove a model alias               │
╰─────────────────────────────────────────────────────────╯
 / mo▋
```

The currently **highlighted entry** (the one that would be selected) is visually distinguished using the active theme's accent color as a background or left-edge marker.

### 2.4 Navigation and Selection

- **Up / Down arrows** — move the highlight through the filtered list, wrapping at the top/bottom.
- **Tab or Enter** — selects the highlighted command and inserts it into the input box, replacing what was typed (or, if the command takes arguments, completes the command name and leaves the cursor ready for arguments).
- **Escape** — dismisses the drop-up and returns to normal free-text typing without inserting anything.
- **Continuing to type past a full match** — if the user keeps typing after the filtered list narrows to one exact result, the drop-up simply stays open showing that one match until they press Tab/Enter or Escape, or until they delete back past the `/` character (which closes the drop-up entirely and returns to plain text mode).

### 2.5 Empty Results State

If the typed text after `/` matches no known command, the drop-up shows a single muted line: `No matching commands` — and pressing Enter at that point sends the text as a literal message rather than attempting to run a command.

---

## 3. Contextual Real-Time Loading States

### 3.1 The Core Behavior

From the moment a message is submitted to the moment the first token of the AI's response arrives, Anythink shows a **single-line animated status indicator** directly above the input area (or in place of where the upcoming response bubble will appear). This status is never static — it visibly communicates that work is happening and roughly what kind of work.

### 3.2 Phrase Pool

A pool of **12+ rotating phrases** is used for the general "model is thinking" state, cycling every 1.5–2 seconds while waiting, so the indicator always feels alive rather than frozen:

```
Thinking…
Pondering…
Drafting a response…
Connecting the dots…
Mulling it over…
Reasoning it through…
Composing thoughts…
Gathering ideas…
Working it out…
Sketching a reply…
Putting it together…
Considering the angles…
```

### 3.3 Contextual Overrides

The generic pool is overridden by **specific, accurate phrases** whenever Anythink knows exactly what kind of work is happening — these take priority over the generic rotation and do not cycle randomly, since they reflect real, current activity:

| Active Operation | Phrase Shown |
|---|---|
| Web search triggered | `Searching the web…` |
| Reading a fetched page | `Reading the page…` |
| RAG index active and retrieving | `Retrieving context…` |
| Reading an attached file | `Reading file…` |
| Code execution running | `Running code…` |
| MCP tool call in progress | `Calling [tool name]…` |
| Waiting on a local LLM (Ollama, etc.) | `Warming up local model…` |
| Long context being processed | `Processing context…` |

When a multi-step operation occurs (e.g., search → read page → think), the indicator transitions smoothly through each contextual phrase in the actual order those steps occur, rather than picking randomly — giving the user a real-time narrative of what the AI agent is doing.

### 3.4 Visual Style

The status text is paired with a small animated spinner glyph (cycling through frames) directly to its left, styled in the theme's accent color:

```
 ◐ Retrieving context…
```

The phrase and spinner disappear the instant the first token of the actual response begins streaming in, at which point the response bubble takes over the same screen space.

---

## 4. Accurate Token Counting

### 4.1 Root Cause Framing

The "stuck at 0%" issue is a data-sourcing gap, not a rendering bug — the HUD context bar was built to display token data, but the underlying token counting was never properly wired to real numbers. This build fixes the data pipeline feeding the HUD.

### 4.2 Primary Source — Provider-Reported Usage

For every provider that returns usage statistics in its API response (prompt tokens, completion tokens, total tokens — which includes Groq, Gemini, OpenAI, Anthropic, Mistral, and Cohere), Anythink reads this usage data directly from each API response and treats it as the **source of truth**. This is the most accurate count available since it reflects the provider's own tokenizer.

This usage data accumulates turn over turn for the session: every new exchange's prompt and completion tokens are added to a running session total, which is what populates the HUD's "used" number against the model's known maximum context window.

### 4.3 Fallback — Client-Side Estimation

For providers or local runtimes that do not return usage statistics (some local LLM servers, certain streaming configurations), Anythink falls back to a **client-side token estimator**. This estimator approximates token count from the raw text of each message (system prompt, user messages, AI responses, file content, RAG-injected context) using a consistent, well-known approximation method appropriate for the model family in use (different tokenization schemes are approximated differently — e.g., GPT-style BPE approximation vs. SentencePiece-style approximation for models that use it).

Estimated counts are visually marked as **approximate** in the HUD (e.g., a `~` prefix before the number) so the user always knows whether they're looking at an exact, provider-reported count or a best-effort estimate.

### 4.4 What Counts Toward the Total

The running total includes everything actually sent to and received from the model in that session:

- The system prompt / active persona
- Every user message
- Every AI response
- Any file content injected into context
- Any RAG-retrieved chunks injected into context
- Any web search/page content injected into context

### 4.5 Reset Behavior

The token count resets to `0` only when the context is genuinely reset — on `/clear` (hard reset, per Section 1) or `/new` (new session). It does **not** reset on model switch alone; switching models recalculates the percentage against the new model's max context size while keeping the accumulated token count from the carried-over conversation, since that history is still being sent to the new model.

---

## 5. Input History Navigation

### 5.1 Scope — Current Session Only

Pressing the **Up arrow** while the input box is empty (or at the start of typing) recalls the user's most recent sent message in the **current session**. Pressing Up again steps further back through their message history, oldest direction. Pressing **Down arrow** steps forward again, toward the most recent message, and pressing Down past the most recent returns to a blank input box.

This history is scoped strictly to messages the user has sent in the **active session only** — it does not reach into other saved sessions, keeping the behavior predictable and tied to what's actually visible on screen.

### 5.2 Editable Recall

When a past message is recalled via arrow keys, it is placed into the input box as fully **editable text** — not sent immediately. The user can modify it before pressing Enter, or press Enter as-is to resend it unchanged. This matches familiar shell history behavior.

### 5.3 Interaction with Multi-Line Messages

If a recalled message was originally multi-line, the full multi-line content is restored into the input editor exactly as it was composed, preserving line breaks.

### 5.4 Interaction with the Slash Command Drop-Up

If the user is in the middle of an active slash command drop-up (Section 2), Up/Down arrows are reserved for **navigating the drop-up list**, not message history — history recall via arrows only applies when the drop-up is closed.

---

## 6. Startup Logo Behavior

### 6.1 Confirming Original Intent

This restores and clarifies the original V1 design that was lost during the V2 build: the **full ASCII block logo** is shown exactly once per app launch — at startup, before the first message is sent — for every user, every time, regardless of whether they're new or returning. (Returning users still get the quick one-liner status text alongside/after the logo, but the visual logo block itself appears on every launch, not just first-run.)

### 6.2 Logo Placement Relative to the HUD

The logo is rendered **above the HUD**, as the very first thing the user sees when the terminal opens, followed immediately by the HUD's two lines, followed by the conversation area. The logo is a one-time decorative welcome — it is not part of the persistent, pinned HUD system.

### 6.3 Logo Scroll Behavior

Because the logo is part of the normal conversation scroll content (not pinned), it **scrolls away naturally** as the conversation grows and the user scrolls down — exactly like the first message in any chat app. If the user scrolls back up to the very top of the session, the logo is still there, sitting above the first message. The HUD, in contrast, never moves and is always visible regardless of scroll position (see Section 7).

### 6.4 What Appears in the Logo Block

The logo block includes the ASCII wordmark, the tagline, version number, and — for returning users — the quick status line summarizing active model, provider, and context size, all bundled together as the single startup moment before the persistent HUD takes over ongoing state display.

---

## 7. Persistent HUD Confirmation

This item is confirmed as already working correctly with no further changes needed: the HUD reliably stays pinned to the top of the terminal at all times while the conversation scrolls beneath it, in Simple Chat Mode. No regression has been found here. (See Section 13 for the one related resize-specific issue that does need fixing.)

---

## 8. Interactive `/settings` Menu

### 8.1 Menu Structure

`/settings` opens a **full interactive, arrow-key-navigable menu** — not a static printout, and not a series of separate sub-commands to memorize. The menu opens as an overlay panel, visually consistent with the active theme, replacing the input area temporarily while open.

### 8.2 Settings Categories Shown

The menu lists every setting as a navigable row, grouped logically:

```
╭─ ⚙ Settings ───────────────────────────────────────────╮
│                                                         │
│   Appearance                                            │
│    ▸ Theme                          Midnight             │
│                                                         │
│   Model & Defaults                                      │
│    ▸ Default model alias            google2              │
│                                                         │
│   Tools & Agent Behavior                                 │
│    ▸ Web search (default)           ON                  │
│    ▸ RAG default behavior           Always-on when loaded│
│    ▸ Code execution approval         Ask every time      │
│    ▸ Web browsing approval           Ask every time       │
│                                                         │
│   Context & Warnings                                     │
│    ▸ Context warning threshold       85%                 │
│                                                         │
│   Notifications                                          │
│    ▸ Desktop notifications           ON                  │
│                                                         │
│  ↑↓ Navigate   Enter Select   Esc Close                 │
╰─────────────────────────────────────────────────────────╯
```

### 8.3 Navigation and Editing Pattern

The user moves through rows with **Up/Down arrows**. Pressing **Enter** on a row opens that specific setting's editor inline:

- For options with a **fixed set of choices** (Theme, approval modes, on/off toggles) — pressing Enter cycles open a small inline selector (e.g., a mini horizontal list: `Midnight  Aurora  Ember  Arctic`) navigable with Left/Right arrows and confirmed with Enter.
- For **numeric values** (context warning threshold) — pressing Enter allows direct numeric entry or Left/Right arrow stepping in small increments (e.g., 5%).
- For **the default model alias** — pressing Enter opens the same model alias selection menu used elsewhere in the app.

### 8.4 Immediate Effect

Every setting change takes effect **immediately** upon confirming the new value — there is no separate "save" step. The HUD and relevant indicators update live if the changed setting affects something currently displayed (e.g., changing the theme instantly re-colors the entire UI, including the open Settings menu itself).

### 8.5 Closing the Menu

Pressing **Escape** at the top level of the menu closes it and returns focus to the input box, with the conversation area exactly as it was before `/settings` was invoked.

---

## 9. Actionable Error Messages

### 9.1 The Problem Being Fixed

Generic error messages ("Something went wrong", "Request failed") leave the user without a clear next step. Every error surface in Anythink is upgraded to follow a consistent three-part structure: **what happened**, **why**, and **what to do about it** — with the fix offered as a direct, runnable command whenever possible.

### 9.2 Error Bubble Structure

```
╭─ ❌ Error ──────────────────────────────────────────────╮
│  Groq request failed: Invalid API key                  │
│                                                         │
│  Your stored key for Groq was rejected by the provider.│
│                                                         │
│  Suggested fix:                                         │
│   → Run /keys update groq to enter a new key             │
│                                                         │
╰─────────────────────────────────────────────────────────╯
```

### 9.3 Examples Across Common Failure Types

| Error Type | Suggested Fix Shown |
|---|---|
| Invalid/expired API key | `/keys update <provider>` |
| Local model server unreachable (Ollama, etc.) | Check that the server is running; shows the expected host/port and a `/keys test <provider>` retry suggestion |
| Rate limit hit | Suggests waiting, or switching models with `/model`, listing alias alternatives |
| Context window exceeded | Suggests `/clear` to reset, or `/model` to switch to a larger-context alias |
| Network/timeout failure | Suggests checking internet connection, with a retry suggestion |
| RAG index source folder missing/moved | Suggests `/rag rebuild <name>` or `/rag info <name>` to inspect the index |
| Code runtime not found (e.g., Python not in PATH) | States exactly what's missing and how execution mode can be changed via `/settings` |

### 9.4 One-Key Quick Action

Where the suggested fix is a simple command, the error bubble offers a one-key shortcut to run it immediately without retyping — e.g., pressing a designated key runs the suggested `/keys update groq` flow directly from the error bubble.

---

## 10. Copy Response / Copy Code Shortcut

### 10.1 Copy Last Response

A dedicated keyboard shortcut copies the **full text of the most recent AI response** (plain text, Markdown stripped of bubble borders/decorations but preserving code block formatting) directly to the system clipboard. A brief confirmation flashes on screen: `✓ Response copied to clipboard`.

### 10.2 Copy Last Code Block

A separate, distinct keyboard shortcut copies **only the most recent code block** from the latest AI response (if one exists) — useful when a response contains both explanation text and a code snippet, and the user only wants the runnable code. If no code block exists in the latest response, a brief message indicates this: `No code block found in the last response`.

### 10.3 Shortcut Visibility

Both shortcuts are listed in the persistent shortcut hint bar (Section 14) so the key bindings are always visible and discoverable without needing to memorize them.

---

## 11. Open Session in Notepad Shortcut

### 11.1 What It Does

A dedicated keyboard shortcut opens the **current session's full plain text history file** — exactly as stored on disk, including everything from before any `/clear` resets in this launch — in the user's default system text editor (Notepad on Windows, TextEdit on macOS, the user's `$EDITOR` or a sensible default like gedit/nano on Linux).

### 11.2 Why This Matters

Since `/clear` now hard-resets the visible chat (Section 1) but preserves everything in the underlying file, this shortcut becomes the user's window into their **complete** conversation — including content no longer visible in the live chat — letting them read, search, copy, or save portions of it using their own familiar editor tools rather than terminal scrollback.

### 11.3 Behavior

The file opens in a separate, independent application window — Anythink itself is completely unaffected and remains fully interactive in the terminal while the file is open elsewhere. The file is opened read/write in the external editor (the user could technically edit it there), but Anythink always treats its own in-memory session state as the source of truth going forward and does not re-read the file unless the session is explicitly reopened via `/history open`.

---

## 12. Stop Response Generation Shortcut

### 12.1 What It Does

While an AI response is actively streaming, a dedicated keyboard shortcut **immediately halts generation**. The underlying API request is cancelled, no further tokens are received, and the response bubble is finalized with exactly the partial content that had streamed in up to that point.

### 12.2 Visual Indication

The interrupted response bubble is clearly marked as incomplete, so the user isn't confused later about why a response seems to cut off mid-thought:

```
╭─ google2 ─────────────────────── Gemini · 14:32:11 ─╮
│  BERT uses bidirectional attention, meaning each      │
│  token attends to all tokens in both directions, un   │
│                                                       │
│  ⏹ Stopped by user                                    │
╰────────────────────────────────────────────────────────╯
```

### 12.3 Conversation State After Stopping

The partial response **is still saved** as part of the conversation history and session file — it counts as that turn's AI response, just incomplete. The user can immediately follow up, ask the AI to continue, or move on with a new message; the partial content remains valid context for the next turn either way.

### 12.4 Token Counting on Stopped Responses

Whatever tokens were actually generated and received before the stop count toward the HUD's running context total — the same accurate accounting rules from Section 4 apply, just based on the truncated content rather than what the full response would have been.

---

## 13. Responsive HUD on Terminal Resize

### 13.1 The Bug Being Fixed

Currently, when the terminal window is resized smaller, the HUD's **second line** (Model, Provider, Context Bar, Search Status, RAG Index) disappears entirely instead of adapting — leaving only the first line visible and the user without critical live status information.

### 13.2 The Fix — Graceful Reflow, Not Disappearance

On resize, the HUD must always remain **fully present and fully readable** — both lines, always. Instead of hiding content when space is limited, the HUD content reflows intelligently:

- At comfortably wide terminal widths, both HUD lines render exactly as designed, full detail, single line each.
- As the terminal narrows, lower-priority HUD elements **abbreviate** before anything is dropped — for example, the raw model name in parentheses (`gemini-2.0-flash`) shortens or hides while the alias (`google2`) always remains; the context bar's visual bar shortens in character width while the numeric count/percentage remains fully intact; the provider status dot remains but its text label may shorten.
- If the terminal becomes extremely narrow (below a reasonable minimum usable width), the HUD wraps onto **additional lines** rather than ever truncating or hiding information outright — the HUD is allowed to grow taller, but its content is never lost.

### 13.3 Priority Order for Reflow

When space must be conserved, elements are deprioritized in this order (least important shortened/wrapped first): theme name label → raw model identifier in parentheses → provider text label (dot indicator always stays) → search/RAG status labels (icon-only fallback if extremely tight). The session name, branch indicator, model alias, and context token count/percentage are always preserved in full — these are considered essential and are never abbreviated.

### 13.4 Live Redraw on Resize Event

The HUD listens for terminal resize events and redraws itself immediately and smoothly when a resize is detected, with no flicker, no leftover artifacts from the previous size, and no need for the user to manually refresh or scroll to trigger the redraw.

---

## 14. Shortcut Key Hint Bar

### 14.1 Placement and Purpose

A slim, single-line **shortcut hint bar** is added directly **below the input box**, persistently visible at all times (except when a modal like `/settings` or the slash command drop-up is open, where it's temporarily replaced by that overlay's own contextual hints). This mirrors the always-visible shortcut hints found in Claude Code's CLI, so users always have a lightweight reference for available actions without needing to memorize them or run `/help`.

### 14.2 Content Shown

The hint bar shows the most commonly used shortcuts as compact key + label pairs, separated by simple dividers:

```
 Ctrl+C copy response   Ctrl+V open in notepad   Esc stop response   / commands
```

### 14.3 Context-Sensitive Hints

The exact set of hints shown can shift slightly based on current state — for example, while a response is actively streaming, the "stop response" shortcut is emphasized or highlighted since it's the most relevant action available in that moment; once the response finishes, the hint bar returns to its standard resting set (copy, notepad, commands).

### 14.4 Styling

The hint bar uses the theme's most muted color — it is intentionally unobtrusive, sitting quietly below the input as a reference rather than competing visually with the conversation or the HUD above.

---

## 15. Rotating Tips Bar

### 15.1 Placement and Purpose

A second slim line, the **tips bar**, appears directly **above the input box** (distinct from the shortcut hint bar below the input) and is shown specifically **while the AI response is being generated** — filling the otherwise idle waiting moment with a useful, rotating piece of guidance about the app itself, exactly matching the pattern used in Claude Code's CLI.

### 15.2 Tip Content Pool

A pool of educational, discoverability-focused tips rotates through this space, each shown for a few seconds before cycling to the next, for example:

```
 💡 Tip: Use /model to switch between your saved models.
 💡 Tip: Press Ctrl+C to copy the last response to your clipboard.
 💡 Tip: Use /branch to explore an alternate path without losing your original conversation.
 💡 Tip: Type /rag use <name> to load a saved knowledge index.
 💡 Tip: Press Esc while a response is generating to stop it early.
 💡 Tip: Use /bookmark to save important responses for later.
 💡 Tip: Try /persona to give the AI a custom role for this session.
 💡 Tip: Press Up/Down arrows to recall your previous messages.
 💡 Tip: Use /settings to change your theme and default behaviors.
 💡 Tip: Type /search <query> for a quick one-off web search.
```

### 15.3 Timing Behavior

The tips bar is only active during the waiting/generation window — the same window in which the contextual loading phrases (Section 3) are shown elsewhere. Once the response completes and the input box is ready for the next message, the tips bar disappears and the space above the input returns to being empty/idle until the next generation cycle begins.

### 15.4 Relationship to the Loading Indicator

The tips bar (above the input, general app guidance) and the contextual loading indicator (Section 3, shown in the conversation area where the response will appear) run simultaneously but serve different purposes — one teaches the user about the app's capabilities, the other reports live status on the current request. They are visually distinct in placement and styling so they don't read as duplicates of each other.

---

## 16. Summary of Touchpoints Changed

For quick reference, this build touches the following areas of the application without altering its underlying feature set from V2:

| Area | Nature of Change |
|---|---|
| `/clear` command | Behavior fix — true hard reset with guaranteed history preservation |
| Slash command input | New interaction — live-filtered drop-up with keyboard navigation |
| Response waiting state | New interaction — contextual animated loading phrases |
| Token counting | Bug fix — real provider usage data wired in, with estimation fallback |
| Input history | New interaction — Up/Down arrow recall within current session |
| Startup sequence | Bug fix — restored full ASCII logo on every launch |
| HUD | Confirmed stable; resize behavior fixed |
| `/settings` | New feature — full interactive settings menu |
| Error handling | Consistency fix — actionable, suggestion-driven error bubbles |
| Keyboard shortcuts | New — copy response, copy code, open in notepad, stop generation |
| HUD resize behavior | Bug fix — graceful reflow instead of information loss |
| Hint and tips bars | New UI elements — persistent shortcut hints and rotating educational tips |

---

*Anythink — Think anything. Ask anything.*

*Version described: 2.1.0 (V2.1 — UI/UX Refinement Build)*
*Document last updated: June 2025*
