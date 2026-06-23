# Anythink — Glyph Rendering Fix Description

> A targeted fix to make every existing glyph in the Anythink UI render correctly —
> monochrome, single-width, theme-colorable, and layout-stable — across all major
> terminal emulators, without replacing any of the current glyphs with different ones.

---

## Table of Contents

1. [The Root Cause](#1-the-root-cause)
2. [The Two-Class Glyph Problem](#2-the-two-class-glyph-problem)
3. [Fix 1 — Variation Selector-15 (VS15)](#3-fix-1--variation-selector-15-vs15)
4. [Fix 2 — Explicit Cell Width Declaration](#4-fix-2--explicit-cell-width-declaration)
5. [Fix 3 — ANSI Color Application Order](#5-fix-3--ansi-color-application-order)
6. [Fix 4 — Font Fallback Chain](#6-fix-4--font-fallback-chain)
7. [Per-Glyph Fix Map](#7-per-glyph-fix-map)
8. [Validation Approach](#8-validation-approach)

---

## 1. The Root Cause

Every broken, partial, or misaligned glyph in Anythink's current UI comes from one
source: **Unicode's dual presentation system**. Many Unicode characters — particularly
those in the Miscellaneous Technical block (U+2300–U+23FF), the Dingbats block
(U+2700–U+27BF), and surrounding ranges — exist in Unicode with two possible
visual presentations:

- **Text presentation** — monochrome, single terminal cell wide, respects ANSI
  color codes, behaves like any normal character in a terminal layout.
- **Emoji presentation** — full-color, rendered from the system emoji font,
  two terminal cells wide, ignores ANSI color codes entirely.

The Unicode Standard specifies a **default presentation** for each character. Some
glyphs — including `⏱` (U+23F1) and others in Anythink's current icon set — have
**emoji as their default presentation**. When a terminal encounters one of these
characters, it uses the emoji renderer by default, producing a double-wide colored
glyph even though the developer intended a single-width, theme-colored symbol.

The terminal is not misbehaving. It is following the Unicode Standard exactly.
The fix is to override the default presentation at the point where the characters
are written to the terminal output — without changing which characters are used.

---

## 2. The Two-Class Glyph Problem

Before applying fixes, every glyph in Anythink's current icon set needs to be
classified into one of two groups, because each group has a different root problem
and a different primary fix:

### Class A — Emoji-Default Glyphs

These are characters whose Unicode default presentation is **emoji**. They render
double-width and colorful in terminals unless explicitly overridden. The override
mechanism is Variation Selector-15 (described in Section 3). ANSI colors have
no effect on these glyphs until the override is applied.

Identifying characteristics: these characters sit in Unicode blocks that were
originally defined as text symbols but later acquired emoji mappings — the
Miscellaneous Technical block (U+2300–U+23FF), Enclosed Alphanumerics
(U+2460–U+24FF), and Miscellaneous Symbols (U+2600–U+26FF) are the most
common offenders. The `⏱` stopwatch is the visible example in the current UI.

### Class B — Coverage-Gap Glyphs

These are characters whose Unicode default presentation is already **text**, but
which may not exist in the user's active terminal font — causing the terminal to
fall back to a replacement glyph (an empty box □ or a question mark ?) instead
of rendering the intended symbol.

These glyphs do not need VS15. They need a font fallback strategy (Section 6)
and an ASCII-safe alternative that is selected automatically when the intended
glyph is detected as missing.

---

## 3. Fix 1 — Variation Selector-15 (VS15)

### 3.1 What VS15 Is

**Variation Selector-15** is a zero-width Unicode control character, U+FE0E,
formally named TEXT PRESENTATION SELECTOR. When placed **immediately after** a
Unicode character that has an emoji default presentation, it explicitly instructs
the renderer to use the text (monochrome, single-width) presentation instead.

This is an official, standardized Unicode mechanism specifically designed for
this problem. It does not change the character itself, does not affect the
string's semantic content, does not show up as a visible character, and does
not interfere with ANSI color codes applied to the character.

### 3.2 How It Works

A character like `⏱` (U+23F1) rendered alone defaults to emoji presentation.
The same character followed immediately by U+FE0E — rendered as `⏱︎` — forces
text presentation. The two-character sequence is still logically one symbol:
one glyph, one terminal cell, one ANSI colorable unit.

### 3.3 Where VS15 Must Be Applied

VS15 must be appended **at the string construction level** — at the point in
the code where each glyph string constant is defined or assembled — not at the
rendering or display layer. Every place in the codebase where an emoji-default
glyph is written as a string literal or constant must include the VS15 character
immediately after it.

The key is consistency: if a glyph is defined as a constant in one place and
used in forty places throughout the UI, the VS15 needs to be in the constant
definition once — not added at every usage site. A glyph registry or constants
file that centralizes all icon definitions is the right architectural pattern,
because VS15 is then applied in one place, guaranteed across the whole UI.

### 3.4 The Effect on ANSI Color Codes

Before VS15, emoji-presentation glyphs **ignore ANSI color codes** — the system
emoji font paints them in its own fixed colors regardless of what Anythink
instructs. After VS15, the same glyphs respond to ANSI color codes normally,
exactly like any letter or number in the terminal. This means applying VS15 is
not just a layout fix — it is also what makes the theme color system work for
these glyphs. Without VS15, a glyph defined as "accent color" in the theme
will render in whatever color the system emoji font uses, not the theme color.

---

## 4. Fix 2 — Explicit Cell Width Declaration

### 4.1 Why VS15 Alone Is Not Always Enough

VS15 tells Unicode what presentation to use. But the **TUI rendering framework**
(Rich, Textual, urwid, or whichever library renders Anythink's terminal layout)
has its own internal cell-width calculator that it uses to measure strings for
alignment, padding, and border placement. Some frameworks calculate cell widths
before applying the effect of VS15, or have incomplete Unicode width tables that
do not account for VS15 at all.

The result: even with VS15 applied, the framework may still reserve two cells for
the character in its layout calculations, causing a one-cell wide glyph to leave
a trailing empty space, misaligning everything after it on the same line.

### 4.2 The Fix — Overriding Cell Width in the Rendering Layer

The TUI framework must be told, explicitly, that each VS15-modified glyph is
**one cell wide** — not inferred, not calculated, but declared. Most TUI frameworks
provide a mechanism for this: either a custom width hint attached to a styled
string, a monkey-patch to the framework's character-width lookup function, or
a custom rendering wrapper that pre-declares widths before the layout engine runs.

The approach that applies depends on which TUI framework Anythink uses, but the
principle is the same in all cases: **the two-character VS15 sequence
(glyph + U+FE0E) must be treated as exactly one cell wide** in every layout
calculation the framework performs, including padding, alignment, centering,
border fitting, and column width measurement.

### 4.3 Scope of Application

This explicit width declaration must be applied to every glyph that receives
VS15 treatment. A centralized glyph registry (mentioned in Section 3.3) is
again the right pattern — the registry stores not just the glyph string with
VS15 appended, but also its declared display width (always 1 for these glyphs),
which the rendering layer reads rather than computing independently.

---

## 5. Fix 3 — ANSI Color Application Order

### 5.1 A Subtle Ordering Issue

Even after VS15 and explicit width declaration are correctly applied, there is
a third potential rendering defect that can make glyphs appear incorrectly: the
order in which ANSI color escape codes are assembled around the glyph string.

Some terminal output assemblers write the glyph character, then apply color
codes around the composite VS15 sequence — but if the color wrapper splits the
glyph and its VS15 selector into separate styled segments, the VS15 character
may end up isolated in a different style run, which can cause some terminals to
discard or ignore it.

### 5.2 The Rule

The glyph character and its VS15 selector **must always be in the same ANSI
style run** — wrapped together by the color codes, never separated. The ANSI
escape sequence opens, then the glyph character appears, then VS15 immediately
follows it, then the ANSI reset closes — all as a single unbroken styled unit.

This means when building colored glyph output, the glyph string (glyph + VS15)
must be treated as an atomic unit at the color-wrapping stage, not decomposed
character by character before coloring.

---

## 6. Fix 4 — Font Fallback Chain

### 6.1 For Class B Glyphs (Coverage Gaps)

For glyphs whose default presentation is already text but which may not exist
in the user's active terminal font, the fix is a **two-layer strategy**:

**Layer 1 — Font recommendation.** Anythink's documentation and first-run setup
guide should recommend a terminal font with broad Unicode symbol coverage.
Fonts in the Nerd Fonts family (JetBrains Mono Nerd Font, FiraCode Nerd Font,
Hack Nerd Font, etc.) include thousands of extra Unicode symbols specifically
added for terminal application use, covering virtually all the ranges Anythink's
icon set draws from. A user on one of these fonts will see every glyph correctly
without any further intervention.

**Layer 2 — Runtime detection and ASCII-safe fallback.** For users whose font
does not cover a specific glyph, Anythink detects at startup which glyphs from
its icon set are actually renderable in the current terminal environment.
Any glyph detected as missing is silently swapped for its pre-defined ASCII-safe
fallback equivalent — a simpler character guaranteed to exist in every terminal
font — for that specific session.

This detection runs once at startup, costs negligible time, and results in a
config value (`icon_style: unicode` or `icon_style: ascii_safe`) that the
renderer reads for every glyph lookup — exactly the Icon Style toggle described
in the V2.2 settings additions. The user never sees broken boxes; they either
see the intended glyph or its clean fallback, never a rendering failure.

### 6.2 ASCII-Safe Fallback Assignments

Every glyph in Anythink's icon set has a pre-assigned ASCII-safe fallback
defined in the glyph registry. These fallbacks are not displayed unless the
primary glyph fails the startup detection — they are the invisible insurance
policy that keeps the UI clean on any terminal, any font.

The fallbacks preserve the communicative intent of each icon using the most
expressive ASCII equivalent available — for example, a timing glyph falls back
to a simple bracketed `[t]` label, a success mark falls back to `[+]`, a
warning falls back to `[!]`, and so on — never silently leaving a blank where
information should be.

---

## 7. Per-Glyph Fix Map

This table defines exactly which fix class applies to every glyph category
currently present in Anythink's UI, so the fix can be applied exhaustively
rather than reactively when individual glyphs break:

| Glyph Category | Unicode Block | Default Presentation | Primary Fix | Secondary Fix |
|---|---|---|---|---|
| Timer / clock symbols (e.g., `⏱`) | Misc Technical U+23xx | **Emoji** | VS15 + explicit width | Font fallback |
| Star / sparkle symbols (e.g., `✦`) | Dingbats U+27xx | Text | Font fallback only | ASCII fallback |
| Diamond / geometric (e.g., `◆`) | Geometric Shapes U+25xx | Text | Font fallback only | ASCII fallback |
| Arrow / indicator symbols (e.g., `▸`) | Block Elements U+25xx | Text | Font fallback only | ASCII fallback |
| Circle / spinner frames (e.g., `◐◓◑◒`) | Geometric Shapes U+25xx | Text | Font fallback only | ASCII fallback |
| Check / cross marks (e.g., `✓`, `✕`) | Dingbats U+27xx | Text | Font fallback only | ASCII fallback |
| Branch / diff symbols (e.g., `⎇`) | Misc Technical U+23xx | Text | Font fallback only | ASCII fallback |
| Warning triangle (e.g., `▲`) | Geometric Shapes U+25xx | Text | Font fallback only | ASCII fallback |
| Bookmark star (e.g., `★`) | Misc Symbols U+26xx | **Emoji** (some terminals) | VS15 + explicit width | ASCII fallback |
| Bullet / dot separators (e.g., `·`) | Latin-1 Supplement U+00B7 | Text | None needed | — |
| Spinner active dot (e.g., `●`) | Geometric Shapes U+25xx | Text | Font fallback only | ASCII fallback |

The key takeaway from this table: **VS15 is only required for glyphs with emoji
as their default presentation**. Applying VS15 unnecessarily to already-text
glyphs is harmless but adds noise to string constants; the clean approach is to
apply it only where the table above shows "Emoji" in the Default Presentation
column.

---

## 8. Validation Approach

### 8.1 What Correct Rendering Looks Like

After all fixes are applied, every glyph in Anythink's UI should exhibit
all four of these properties simultaneously:

1. **Single-width** — exactly one terminal cell consumed, no trailing blank cell,
   no layout misalignment of characters following it on the same line.
2. **Monochrome** — no color of its own; it takes on exactly the ANSI color
   Anythink assigns to it via the active theme, no more and no less.
3. **Theme-responsive** — changing the active theme in `/settings` causes the
   glyph to immediately change to the new theme's color, confirming ANSI codes
   are being applied and respected.
4. **Layout-stable** — the glyph participates correctly in borders, padding,
   alignment, and line-length calculations; switching between themes, verbosity
   levels, or bubble styles does not cause any line to become misaligned because
   of a glyph's width.

### 8.2 Cross-Terminal Validation Targets

The fix should be confirmed working on at least the following terminal emulators
before shipping, as they represent the primary environments where Anythink users
are likely running:

| Terminal | Platform | Relevant Risk |
|---|---|---|
| **iTerm2** | macOS | Typically good emoji/text selector support |
| **macOS Terminal.app** | macOS | More conservative; stricter emoji width behavior |
| **Windows Terminal** | Windows | Generally good; VS15 support varies by font |
| **GNOME Terminal** | Linux | Depends on VTE version; newer is better |
| **Alacritty** | Cross-platform | GPU-rendered; good Unicode but strict width tables |
| **Kitty** | Cross-platform | Excellent Unicode; explicit width override well supported |
| **tmux / screen** | All (multiplexer) | Multiplexers add their own width calculation layer |

### 8.3 The Single-Line Alignment Test

The simplest, fastest manual validation: construct a single terminal output
line that places one of each glyph in the icon set side by side, followed by
a pipe character `|`, a fixed-width string, and another pipe `|`. If every pipe
character aligns perfectly in a vertical column when the line is duplicated,
every glyph is exactly one cell wide and the fix is working. If any pipe
character is off by one column, the glyph immediately before the break is still
being calculated as two cells wide somewhere in the rendering pipeline.

---

*Anythink — Think anything. Ask anything.*

*Version described: Glyph Rendering Fix — applies to V2.2.0 and all subsequent builds*
*Document last updated: June 2025*
