# Anythink — V2.2 Visual Identity & Personalization Build

> This build deepens Anythink's visual identity rather than adding new functional capability. Every theme
> becomes a complete, full-screen visual identity rather than a set of accent colors layered on a default
> black terminal. Users gain direct control over density, bubble style, and avatars, while two real bugs —
> stale theme colors after switching mid-session, and a misleading "0%" context display — are fixed for good.

---

## Table of Contents

1. [Per-Theme Background Fill](#1-per-theme-background-fill)
2. [Bubble Style Toggle — Boxed / Minimal](#2-bubble-style-toggle--boxed--minimal)
3. [Role Avatars](#3-role-avatars)
4. [Live, Retroactive Theme Application](#4-live-retroactive-theme-application)
5. [Relative Timestamps with Absolute Fallback](#5-relative-timestamps-with-absolute-fallback)
6. [Compact Density Mode](#6-compact-density-mode)
7. [Unified Monochrome Icon Language](#7-unified-monochrome-icon-language)
8. [Collapsed Session Naming Confirmation](#8-collapsed-session-naming-confirmation)
9. [Exact Context Percentage Precision](#9-exact-context-percentage-precision)
10. [New `/settings` Additions Summary](#10-new-settings-additions-summary)
11. [How These Features Interconnect](#11-how-these-features-interconnect)

---

## 1. Per-Theme Background Fill

### 1.1 What Changes

Each of the 4 color themes (Midnight, Aurora, Ember, Arctic) now defines a **full-screen background fill**, not just border and text accent colors. Switching themes changes the entire canvas the user is looking at — the empty space behind the HUD, the conversation area, the bottom panel, everything — not just the colored elements drawn on top of it.

### 1.2 Background Tone Per Theme

Each background fill is a very dark, near-black tint carrying the personality of its theme, so the app never looks like plain default-black terminal text with colored borders pasted on — it looks like a deliberately designed space:

| Theme | Background Character |
|---|---|
| **Midnight** | Deep near-black with a cool indigo-violet undertone |
| **Aurora** | Deep near-black with a faint forest-green undertone |
| **Ember** | Deep near-black with a warm charcoal-rust undertone |
| **Arctic** | Deep near-black with a cool steel-blue undertone |

These tints are subtle by design — dark enough to remain comfortable for long reading sessions and to keep text contrast high, but present enough that each theme feels visually distinct the instant the app opens, even before a single message is read.

### 1.3 Bubble Surface Treatment

Message bubbles (and bordered system panels like `/settings`) use a **very slightly lighter shade of the same background hue** — not a contrasting color, just a gentle lift in brightness within the same tint family. This creates soft visual layering and depth (bubbles read as sitting just above the background) without introducing a harsh box-on-black look. This subtle surface tint applies consistently whether the bubble is rendered in Boxed or Minimal style (Section 2).

### 1.4 Terminal Compatibility

Full-canvas background coloring relies on the terminal emulator respecting explicit background color codes, which the overwhelming majority of modern terminals do. For the rare terminal configuration that overrides or ignores background colors (e.g., certain transparency setups), Anythink gracefully falls back to the terminal's own default background — all foreground colors, borders, and accents continue to render correctly regardless, so the app remains fully usable even in that edge case, just without the tinted canvas effect.

---

## 2. Bubble Style Toggle — Boxed / Minimal

### 2.1 Two Styles, One Setting

A new `/settings` option, **Bubble Style**, lets the user choose between:

- **Boxed** — the current style: a fully bordered box per message, user messages right-aligned, AI messages left-aligned, exactly as it works today.
- **Minimal** — a new, flatter style: no border box at all, just a thin colored **accent bar** on the left edge of the message block, with the role label and timestamp on one compact header line, message content directly beneath, full width, left-aligned for both roles.

### 2.2 Minimal Style Layout

```
▎You                                              2m ago
  Explain how BERT's attention mechanism differs from GPT.

▎google2                                  Gemini · just now
  BERT uses bidirectional attention, meaning each token
  attends to all tokens in both directions, unlike GPT's
  left-to-right causal attention.

  127 words · ·
```

The accent bar color distinguishes the two roles — user messages use the theme's primary color, AI messages use the theme's accent color — exactly the same role-color logic already used for Boxed mode's borders, just expressed as a slimmer visual element. Both roles render full-width and left-aligned in Minimal mode; the right/left alignment split is a Boxed-mode-only convention and is intentionally not carried over, since Minimal is designed to feel closer to a flowing, Claude-Code-style transcript.

### 2.3 Consistency Across Both Styles

Every other piece of message metadata — response length indicator, sources footer, RAG retrieval footer, bookmark marker, attachment labels — appears identically in both styles, just laid out to fit each style's structure. Switching styles never hides or loses any information, it only changes how that information is visually framed.

### 2.4 Instant, Whole-Conversation Switching

Changing the Bubble Style setting takes effect **immediately and retroactively** across the entire visible conversation — every message already on screen re-renders in the newly selected style the moment the setting changes, with no need to restart the app or start a new session.

---

## 3. Role Avatars

### 3.1 What This Adds

A new `/settings` option, **Role Avatars**, toggled On or Off, adds a small identifying glyph next to each message's role label — a lightweight visual anchor that makes it easier to tell, at a glance while scanning quickly, who's speaking.

### 3.2 Avatar Design

To stay fully consistent with the monochrome, theme-colorable icon philosophy (Section 7) rather than introducing fixed-color emoji, avatars are simple, theme-colored glyphs rather than pictorial icons:

- **User avatar** — a single bracketed initial, e.g. `⟨Y⟩`, colored in the theme's primary color (matching the user bubble's accent).
- **AI avatar** — the Anythink brand mark `✦` (the same glyph already used in the HUD's "✦ Anythink" and the startup logo), colored in the theme's accent color — reinforcing brand identity consistently everywhere the AI speaks, from the HUD down to every single response.

### 3.3 Avatar Placement Per Bubble Style

**Boxed style, avatars on:**
```
╭─ ✦ google2 ──────────────────── Gemini · just now ─╮
```

**Minimal style, avatars on:**
```
▎✦ google2                                Gemini · just now
```

When the setting is off, the layout is identical minus the glyph — exactly today's text-only role label.

### 3.4 Future-Friendly Design

Because the user avatar is initial-based (`⟨Y⟩` derived from "You"), this design leaves room for a natural future enhancement — a user-set display name whose first letter automatically becomes their avatar initial — without requiring any structural change to how avatars are rendered now.

---

## 4. Live, Retroactive Theme Application

### 4.1 The Bug Being Fixed

Currently, switching themes mid-session only affects **new** messages going forward — every message already rendered in the scrollback keeps the colors of whichever theme was active when it was originally drawn. The result is a visually split conversation: scroll up far enough in a session where the theme was changed partway through, and the user sees two (or more) different color schemes mixed together in the same conversation.

### 4.2 The Fix — Theme as a Pure Rendering Layer

Theme color is changed from something baked into a message at the moment it's created, to something applied purely at **draw time**, every time the screen renders. This means the moment a theme is switched — via `/theme <name>` or through the `/settings` menu — every visible element instantly recolors as a single, unified action:

- Every message bubble already in the visible scrollback (Boxed or Minimal style)
- The persistent HUD, both lines
- The startup ASCII logo, even though it has already scrolled up into history
- All system bubbles (search status, errors, warnings, confirmations)
- The shortcut hint bar and tips bar
- Any open overlay, such as the `/settings` menu itself, recoloring live as the user previews different themes from inside it

There is never a partially-themed state, and there is never any leftover color residue from a previous theme anywhere on screen, regardless of how far back in the conversation the user scrolls.

### 4.3 Session Files Remain Theme-Agnostic

This change is purely visual and has no effect on the underlying plain text session files, which — consistent with the original V1 design — store no color or formatting information at all. A session file always renders using whatever theme is **currently active** at the moment it's being viewed or reopened (via `/history open`), never "remembering" a theme from when it was originally written. This keeps session files universally plain, portable, and readable in any external editor exactly as designed from the start.

---

## 5. Relative Timestamps with Absolute Fallback

### 5.1 What Changes

Message timestamps shift from always showing an absolute clock time (`14:32:11`) to showing a **relative, human-friendly time** for recent messages, automatically transitioning to absolute time once a message is old enough that relative phrasing stops being useful — the same convention used by most modern chat applications.

### 5.2 Timestamp Tiers

| Message Age | Displayed As |
|---|---|
| Under 1 minute | `just now` |
| 1–59 minutes | `Xm ago` |
| 1–23 hours | `Xh ago` |
| Yesterday | `Yesterday, 14:32` |
| Older, same year | `Jun 18, 14:32` |
| Older, previous years | `Jun 18 2025, 14:32` |

### 5.3 Live Updating

Relative timestamps are not fixed at render time — they **update live** while the app is running. A message that initially showed `just now` will silently tick forward to `2m ago`, then `14m ago`, and so on, refreshing periodically in the background without requiring any user action or screen refresh, so the timestamp the user sees is always accurate to the moment, not just the moment the message arrived.

### 5.4 Underlying Data Is Always Absolute

The relative display is purely a presentation choice in the live UI. The actual stored timestamp — written into the plain text session file and used anywhere precision matters (exports, `/history` listings, comparison mode results) — always remains the exact, full-precision absolute timestamp. Nothing about the underlying data changes; only how it's displayed in the live conversation view does.

### 5.5 Optional Override

For users who prefer fixed, absolute timestamps at all times (useful when taking screenshots, or for users who simply find relative time less precise and prefer not to have it), a `/settings` toggle — **Timestamps: Relative / Absolute** — lets the relative behavior be turned off entirely in favor of always showing the exact clock time, exactly as the app behaves today.

---

## 6. Compact Density Mode

### 6.1 What This Adds

A new `/settings` option, **Density**, toggled between **Comfortable** (the current, roomier default) and **Compact**, gives power users control over how much conversation fits on screen at once.

### 6.2 What Changes in Compact Mode

- Internal bubble padding is reduced — less empty space between the border/accent bar and the message text.
- The blank line normally separating consecutive messages is removed or reduced to a thin visual break instead of a full empty line.
- Bubble borders in Boxed style render with a shorter, tighter frame.
- Footer metadata (length indicator, sources, timestamps) sits closer to the message content rather than with generous breathing room beneath it.

The change is purely spatial — no information is hidden, abbreviated, or removed in Compact mode; every element from Comfortable mode is still present, just arranged with tighter spacing so meaningfully more conversation history is visible within the same terminal window height.

### 6.3 Applies Across Both Bubble Styles

Density is an independent setting from Bubble Style (Section 2) — a user can combine Compact with either Boxed or Minimal. Compact + Minimal produces the highest possible information density: a thin accent bar, a single header line, and message text with almost no surrounding whitespace — closest in spirit to a dense, scrollable terminal log.

### 6.4 Scope

This setting affects only the **conversation area**. The persistent HUD remains its standard two-line height regardless of density setting, since it's already a deliberately minimal, fixed-size element and isn't part of the scrolling content this setting is designed to optimize.

### 6.5 Instant Effect

Like Bubble Style and Theme, switching Density takes effect immediately, re-flowing the entire visible conversation without requiring a restart or new session.

---

## 7. Unified Monochrome Icon Language

### 7.1 The Problem Being Fixed

Several icons throughout the app — most visibly the search and RAG indicators in the HUD — are currently rendered using native multi-color emoji. Unlike text and borders, emoji glyphs carry their own fixed, baked-in colors from the font itself and completely ignore the active theme's color palette. The result is a small but real visual inconsistency: every other element on screen obeys the active theme exactly, except these few emoji, which look identical (and oddly colorful) no matter which theme is selected.

### 7.2 The Fix — One Icon Set, Fully Theme-Colorable

Every icon across the entire app — HUD, bubbles, system messages, error bubbles, the shortcut hint bar, the tips bar, the `/settings` menu, and every future feature — is drawn from a single, consistent set of **monochrome, theme-colorable glyphs**, replacing emoji entirely. Each icon is rendered using the active theme's appropriate color role, exactly like every other piece of UI chrome.

### 7.3 Representative Icon Language

| Category | Icon | Color Role Used |
|---|---|---|
| Search active | `⌕` | Accent |
| RAG / knowledge index | `⌬` | Accent |
| File attachment | `⎘` | Muted |
| Image attachment | `▦` | Muted |
| Success / confirmation | `✓` | Success |
| Error | `✕` | Error |
| Warning | `▲` | Warning |
| Branch | `⎇` | Accent |
| Bookmark | `★` | Highlight |
| Notification | `◆` | Accent |
| Code execution / tool | `⚙` | Muted |
| MCP tool call | `▹` | Accent |
| Provider status dot | `●` | Success / Warning / Error, depending on health |
| Voice recording | `●` (pulsing) | Error |
| Settings | `⚙` | Muted |
| Copy action | `⧉` | Muted |
| Stop generation | `■` | Error |
| Loading / thinking spinner | `◐ ◓ ◑ ◒` (rotating) | Accent |

This table is representative of the icon language's intent and coverage, not an exhaustive final glyph list — the guiding principle is what matters: every status, action, and category in the app maps to exactly one consistent glyph, and that glyph is always rendered in a theme color, never a fixed font color.

### 7.4 Semantic Color Roles, Per Theme

To support this, each theme now defines four additional **semantic colors** beyond its existing Primary, Accent, Highlight, and Muted roles — Success, Warning, Error, and Info — each tuned to match that theme's overall personality rather than using one universal red/green/yellow across all four themes:

| Theme | Success | Warning | Error | Info |
|---|---|---|---|---|
| **Midnight** | Mint Green | Amber | Soft Red | Electric Cyan |
| **Aurora** | Lime Green | Amber Yellow | Burnt Orange-Red | Bright Forest Green |
| **Ember** | Warm Gold | Deep Amber | Bright Red-Orange | Soft Gold |
| **Arctic** | Teal Green | Pale Amber | Coral Red | Teal |

This means a success checkmark in Ember looks and feels different from a success checkmark in Arctic, while both are instantly recognizable as "success" — consistent meaning, theme-appropriate expression.

### 7.5 ASCII-Safe Fallback Option

Because not every terminal font fully supports every Unicode symbol used in this icon language, a `/settings` option — **Icon Style: Unicode / ASCII-safe** — lets users switch to a simplified, guaranteed-compatible fallback set (using only the most universally supported characters, like plain brackets, asterisks, and basic punctuation-based glyphs) if they notice any rendering issues (boxes, question marks, or missing glyphs) on their specific terminal or font setup.

---

## 8. Collapsed Session Naming Confirmation

### 8.1 The Fix

The session naming interaction at the start of a new session no longer leaves two separate bordered boxes — the prompt and its confirmation — permanently sitting in the scrollback above the first real message.

### 8.2 New Behavior

Once the user answers the naming prompt (either by typing a name or pressing Enter to auto-name), the **entire prompt box disappears** and is replaced by a single, compact, unbordered confirmation line, styled as a quiet system message using the Success icon and color from the new icon language (Section 7):

```
 ✓ Session named: "What is an LLM? Keep it short"
```

For an auto-generated name (user pressed Enter without typing), the same compact format is used with a small marker distinguishing it as automatic:

```
 ✓ Session named: "Session · Jun 18 · google2" (auto)
```

### 8.3 Result

Scrolling to the very top of any session now shows, at most, one slim line of naming confirmation before the conversation begins — instead of two stacked bordered boxes competing for attention with the actual content the user came to read.

---

## 9. Exact Context Percentage Precision

### 9.1 The Fix

The context window percentage shown in the HUD (and anywhere else it appears, such as the TUI Dashboard's right panel) no longer rounds small, genuinely non-zero usage down to a flat, ambiguous `0%`.

### 9.2 Precision Rule

- **Usage at or above 1%** — displayed as a whole number, exactly as today (e.g., `6%`, `12%`, `47%`) — keeping the common-case HUD display clean and uncluttered.
- **Usage below 1%, but greater than zero tokens** — displayed with one decimal place (e.g., `0.2%`, `0.7%`), so a session that has genuinely started accumulating tokens never visually looks identical to a broken or stalled tracker.
- **Exactly zero tokens used** (a freshly cleared or freshly started session) — displayed plainly as `0%`, which is now unambiguous, since the only way to see a flat `0%` is for the context to genuinely be empty, never as a rounding artifact of real, in-progress usage.

### 9.3 Where This Applies

This precision rule is applied consistently everywhere a context percentage is shown — the HUD's second line, the TUI Dashboard's right panel context bar, and any future surface that reports context usage as a percentage.

---

## 10. New `/settings` Additions Summary

This build adds the following new entries to the interactive `/settings` menu, alongside the existing Theme, Default Model, and approval-mode settings:

| Setting | Options |
|---|---|
| **Bubble Style** | Boxed / Minimal |
| **Role Avatars** | On / Off |
| **Density** | Comfortable / Compact |
| **Timestamps** | Relative / Absolute |
| **Icon Style** | Unicode / ASCII-safe |

Background fill (Section 1) and retroactive theme recoloring (Section 4) are not separate settings — they are automatic, built-in behaviors of the existing **Theme** selector, meaning choosing a theme has always been, and now fully is, a single decision that controls the entire visual identity of the app, background included.

---

## 11. How These Features Interconnect

**Theme + Background Fill + Retroactive Recoloring** combine into a single, coherent promise: choosing a theme is now a complete, instant, whole-screen visual identity change — background, borders, icons, avatars, and every past message — with zero stale or mixed-color states possible.

**Bubble Style + Density** are independent, stackable preferences — together they form a 2×2 spectrum from the current spacious, fully-boxed default, all the way to a dense, flat, Claude-Code-style transcript view, letting each user land wherever they're most comfortable.

**Role Avatars + Icon Language** share the same underlying design principle — every visual mark in the app, whether it's a status icon or a speaker identifier, is monochrome and theme-colored rather than a fixed-color emoji, keeping the entire interface visually unified under one consistent rule rather than a patchwork of styles.

**Exact Context Percentage + Collapsed Naming Confirmation** are both small-but-important trust fixes — neither changes what the app can do, but both remove moments where the interface could make a working feature look broken or cluttered, which matters as much to a polished product as any new capability.

---

*Anythink — Think anything. Ask anything.*

*Version described: 2.2.0 (V2.2 — Visual Identity & Personalization Build)*
*Document last updated: June 2025*
