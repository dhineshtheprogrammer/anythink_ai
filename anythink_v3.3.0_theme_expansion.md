# Anythink — V3.3.0 Theme Expansion Build

> V3.3.0 adds four new complete visual identities to Anythink's theme system —
> Charcoal, Linen, Rose, and Dracula — bringing the total theme count to eight.
> Each new theme is fully specified: background fill, surface treatment, all text
> and border color roles, semantic colors, syntax highlighting, logo color, and
> every special behavior required for the two themes (Linen and Rose) that
> introduce design considerations not present in the existing four.

---

## Table of Contents

1. [Theme System Overview](#1-theme-system-overview)
2. [Theme Color Role Reference](#2-theme-color-role-reference)
3. [Charcoal — Basic Dark](#3-charcoal--basic-dark)
4. [Linen — Basic Light](#4-linen--basic-light)
5. [Rose](#5-rose)
6. [Dracula](#6-dracula)
7. [Light Mode Special Behaviors](#7-light-mode-special-behaviors)
8. [Logo Color Per Theme](#8-logo-color-per-theme)
9. [Syntax Highlighting Color Sets](#9-syntax-highlighting-color-sets)
10. [All Eight Themes in `/settings`](#10-all-eight-themes-in-settings)
11. [Cross-Theme Consistency Requirements](#11-cross-theme-consistency-requirements)

---

## 1. Theme System Overview

### 1.1 The Full Theme Roster After This Build

| # | Theme Name | Background Family | Personality |
|---|---|---|---|
| 1 | **Midnight** | Dark — deep indigo-violet | Existing |
| 2 | **Aurora** | Dark — faint forest-green | Existing |
| 3 | **Ember** | Dark — warm charcoal-rust | Existing |
| 4 | **Arctic** | Dark — cool steel-blue | Existing |
| 5 | **Charcoal** | Dark — neutral charcoal | New — basic dark |
| 6 | **Linen** | Light — warm off-white | New — basic light |
| 7 | **Rose** | Dark — deep rose-black | New — elegant pink |
| 8 | **Dracula** | Dark — gray-blue-purple | New — developer classic |

### 1.2 Naming Convention

All eight theme names follow the single evocative word convention. No theme
has a subtitle, variant suffix, or qualifier. The name alone communicates the
theme's personality completely.

### 1.3 What Each Theme Fully Defines

Every theme in Anythink defines values for every color role listed in
Section 2 — no role inherits from another theme, no role is left undefined.
A theme is a complete, self-contained visual identity. Switching themes applies
all of the following simultaneously, instantly, and retroactively to the entire
visible screen as described in V2.2 Section 4:

- Full-canvas background fill
- Surface fill for all message bubbles and overlay panels
- All eight text and border color roles
- All four semantic color roles (Success, Warning, Error, Info)
- The logo color for the ASCII startup wordmark
- The complete syntax highlighting color set for code blocks
- Any theme-specific structural behavior (such as the dark HUD bar on Linen)

---

## 2. Theme Color Role Reference

Every theme defines the following named color roles. These role names are used
throughout the rest of this document when describing each new theme:

| Role | What It Colors |
|---|---|
| **Background** | The full terminal canvas behind all content |
| **Surface** | The fill inside message bubbles and overlay panels |
| **Text Primary** | All main conversation text |
| **Text Muted** | Timestamps, metadata, hints, separator labels |
| **Primary** | User bubble borders, HUD session name, key labels |
| **Accent** | AI bubble borders, HUD model name, active indicators |
| **Highlight** | Maximum emphasis — important values, brand mark `✦` |
| **Muted Border** | Inactive borders, the HUD divider line, scrollbar track |
| **Success** | Confirmation glyphs `✓`, healthy provider dot `●` |
| **Warning** | Context window alert bar shift, warning glyph `▲` |
| **Error** | Error bubble borders, error glyph `✕`, critical alerts |
| **Info** | Informational system bubbles, info glyph |
| **Logo** | The ASCII wordmark color on startup |

---

## 3. Charcoal — Basic Dark

### 3.1 Personality

Charcoal is the theme for users who want a clean, professional dark environment
without the strong hue personality of the existing four themes. Where Midnight
has an indigo undertone and Aurora has a green undertone, Charcoal is
intentionally **neutral** — a dark workspace that gets out of the way and lets
the content itself be the focus. The tinted hue present in Charcoal is a very
subtle cool-gray-blue — enough to prevent the theme from feeling flat or
unfinished, but never strong enough to read as a color-family theme.

### 3.2 Color Values

| Role | Color Description | Hex |
|---|---|---|
| **Background** | Deep charcoal — dark gray, very slight cool tint | `#1E1E1E` |
| **Surface** | Lifted charcoal — fractionally lighter than background | `#252525` |
| **Text Primary** | Warm near-white — slightly softer than pure white | `#E8E8E8` |
| **Text Muted** | Medium charcoal gray | `#6E6E6E` |
| **Primary** | Cool gray-blue — the subtle tinted hue of this theme | `#9EAAB5` |
| **Accent** | Soft steel blue | `#5C9CF5` |
| **Highlight** | Pure white | `#FFFFFF` |
| **Muted Border** | Dark gray — barely above background | `#3A3A3A` |
| **Success** | Desaturated sage green | `#6ABF69` |
| **Warning** | Muted amber | `#D4A847` |
| **Error** | Soft rose-red | `#E06C75` |
| **Info** | Light steel blue | `#7DB3E8` |
| **Logo** | Steel blue — the Accent color | `#5C9CF5` |

### 3.3 Visual Character

The Charcoal background at `#1E1E1E` is the canonical "dark mode" gray — the
same tone used by VS Code, JetBrains IDEs, and most professional dark-mode
development environments. Users who spend their day in those tools will
immediately recognize this background as familiar and restful. The surface at
`#252525` is close enough to the background that bubble borders remain the
primary visual boundary of message areas — the surface fill is present but
subtle, creating depth without drama.

The Primary and Accent colors are both in the blue-gray family — distinguished
enough to clearly differentiate user bubbles from AI bubbles, but both muted
enough that neither competes with the text content inside them. This is the
most text-forward of all eight themes.

---

## 4. Linen — Basic Light

### 4.1 Personality

Linen is the only light-background theme in Anythink's collection. Its
background is inspired by natural linen fabric — an off-white with a warm,
faintly creamy-yellow undertone that is significantly more comfortable for long
reading sessions than pure white, which creates excessive contrast and eye
strain. The overall feel is calm, editorial, and document-like — closer to
reading a well-typeset paper than staring at a computer screen.

Everything in Linen that is dark elsewhere becomes light, and everything that
is light elsewhere becomes dark. The inversion is thorough and deliberate,
including a structurally different HUD treatment described in Section 7.

### 4.2 Color Values

| Role | Color Description | Hex |
|---|---|---|
| **Background** | Warm off-white linen | `#F4F1EB` |
| **Surface** | Slightly darker warm white — visible bubble fill | `#EBE8E0` |
| **Text Primary** | Warm near-black — softer than pure black | `#2C2C2C` |
| **Text Muted** | Warm medium gray | `#8A8680` |
| **Primary** | Deep navy — dark, high contrast on light background | `#1E3A5F` |
| **Accent** | Deep teal | `#0F6B6B` |
| **Highlight** | Near-black for maximum emphasis | `#1A1A1A` |
| **Muted Border** | Warm gray — visible but quiet on linen background | `#C5BFB5` |
| **Success** | Deep forest green — dark enough for light bg | `#166534` |
| **Warning** | Deep amber-brown | `#92400E` |
| **Error** | Deep crimson — dark enough for light bg | `#991B1B` |
| **Info** | Deep ocean blue | `#1E40AF` |
| **Logo** | Deep navy — the Primary color | `#1E3A5F` |

### 4.3 HUD Color Overrides

Linen is the only theme where the HUD does **not** share the theme's background
color. Instead, as specified in the V2.2 design decisions, the Linen HUD is a
**dark bar** — a strong, fully opaque dark background spanning the full terminal
width, with light text on top of it.

| HUD Element | Value |
|---|---|
| **HUD background** | Deep warm charcoal | `#2C2C2C` |
| **HUD text — primary** | Warm off-white (the Linen background color) | `#F4F1EB` |
| **HUD text — muted** | Medium warm gray | `#A09890` |
| **HUD accent elements** | Soft teal — lighter version of Linen's Accent | `#4AADAD` |
| **HUD divider line** | Medium charcoal | `#484848` |
| **HUD context bar fill** | Teal gradient — same color family as accent | `#4AADAD` |

This dark HUD treatment means the top of the terminal reads like a macOS
menubar or a VS Code title bar — a dark anchor that gives the otherwise light
interface a clear top boundary, preventing the terminal from looking like it has
no defined edge at the top. The contrast between the dark HUD and the light
conversation area below it is immediate and clear.

### 4.4 Bubble Borders on Linen

On a light background, bubble borders must be **darker than the surface** — the
inverse of how they work on dark themes, where borders are lighter than the
background. On Linen:

- User bubble borders use the **Primary** deep navy color
- AI bubble borders use the **Accent** deep teal color
- System message bubble borders use the **Muted Border** warm gray

In Minimal bubble style, the left-edge accent bars follow the same color rules.

---

## 5. Rose

### 5.1 Personality

Rose is an elegant, feminine dark theme built around a deep rose-black
background — so dark it reads as near-black at a glance, but with an
unmistakable warm pink-magenta undertone that gives the entire interface a
distinctly soft, intimate quality. The accent colors are delicate blush pinks
and soft magentas rather than saturated hot pinks, keeping the theme in the
"elegant and soft" register rather than the "loud and vibrant" one.

Rose is a dark-background theme. It shares the dark-canvas foundation of the
existing four dark themes but occupies a completely different color family
from all of them — none of the existing themes touch the rose/pink/magenta
hue range.

### 5.2 Color Values

| Role | Color Description | Hex |
|---|---|---|
| **Background** | Very dark rose-black — near-black with warm pink tint | `#1A0E12` |
| **Surface** | Deep rose-black — fractionally lifted from background | `#231318` |
| **Text Primary** | Soft rose-white — warm, creamy near-white | `#F5E6EC` |
| **Text Muted** | Dusty rose-gray | `#8A6070` |
| **Primary** | Soft blush pink | `#E8A0B4` |
| **Accent** | Warm rose-pink | `#FF79A8` |
| **Highlight** | Pale pink-white — near white with rose warmth | `#FFD0E0` |
| **Muted Border** | Dark dusty rose | `#4A2A35` |
| **Success** | Soft mint-teal — complementary contrast to rose | `#7DC4A8` |
| **Warning** | Warm gold | `#F4C77A` |
| **Error** | Bright rose-red | `#FF4D6D` |
| **Info** | Soft lilac-purple — close family to rose | `#C084FC` |
| **Logo** | Soft blush pink — the Primary color | `#E8A0B4` |

### 5.3 Visual Character

The Rose background at `#1A0E12` is distinctly warmer than any of the other
dark themes — where Midnight leans violet-cool, Aurora leans green-cool, Ember
leans rust-warm, and Charcoal leans neutral, Rose leans warm-pink. At full
terminal brightness the pink undertone in the background is visible and
intentional. The surface at `#231318` stays within the same hue family,
creating bubble areas that feel integrated with the background rather than
being a contrasting box placed on top of it.

The Success color in Rose deliberately breaks from the rose color family —
using a soft mint-teal instead of a pinkish green. This is intentional: on a
rose-heavy background, a pink-green success color would be too similar to the
primary accents to be immediately readable as "success." The mint-teal is
visually distinct from every other Rose color, making it unambiguously
meaningful.

---

## 6. Dracula

### 6.1 Personality

Dracula is an implementation of the iconic Dracula color theme — one of the
most widely used developer color themes in the world, recognized by hundreds
of thousands of developers across editors, terminals, and applications. Its
palette is precisely defined by the Dracula project's official specification,
and Anythink's implementation maps the Dracula palette to Anythink's color
role system with full fidelity — no colors are approximated or substituted.

The Dracula background is a distinctive dark gray with a subtle blue-purple
undertone — darker than most purple themes but lighter than pure black,
creating a background that developers who use Dracula in their editor will
recognize immediately as "their" environment.

### 6.2 Color Values

The following values are sourced from the official Dracula color specification:

| Role | Color Description | Hex |
|---|---|---|
| **Background** | Dracula Background — dark blue-gray | `#282A36` |
| **Surface** | Dracula Current Line — elevated surface | `#44475A` |
| **Text Primary** | Dracula Foreground — cream near-white | `#F8F8F2` |
| **Text Muted** | Dracula Comment — muted purple-gray | `#6272A4` |
| **Primary** | Dracula Purple — the signature hue | `#BD93F9` |
| **Accent** | Dracula Pink | `#FF79C6` |
| **Highlight** | Dracula Foreground (full brightness) | `#F8F8F2` |
| **Muted Border** | Dracula Selection — panel borders and dividers | `#44475A` |
| **Success** | Dracula Green | `#50FA7B` |
| **Warning** | Dracula Yellow | `#F1FA8C` |
| **Error** | Dracula Red | `#FF5555` |
| **Info** | Dracula Cyan | `#8BE9FD` |
| **Logo** | Dracula Purple — the Primary color | `#BD93F9` |

### 6.3 Visual Character

The Dracula palette is defined by the contrast between its muted, gray-blue
background and its vivid, saturated accent colors — particularly the
electric purple, pink, green, and cyan that the theme uses as its
distinguishing visual language. Unlike the other Anythink themes where
accents are muted or desaturated relative to their hue, Dracula's accents
are intentionally vivid — this is a defining characteristic of the Dracula
theme and is preserved exactly in this implementation.

The surface color at `#44475A` (Dracula's "Current Line" color) creates a
notably stronger bubble-to-background contrast than most of the other dark
themes — bubbles are clearly and visibly lifted from the background without
any subtlety. This higher surface contrast is also characteristic of the
Dracula theme and is preserved.

### 6.4 Semantic Color Note

Dracula's semantic colors (Success green, Warning yellow, Error red, Info cyan)
are all from the official Dracula palette. They are intentionally more
saturated and vivid than the semantic colors in other Anythink themes. This
means error states, warnings, and success confirmations will appear more
emphatically in Dracula than in other themes — appropriate for a theme used
primarily in development contexts where clear signal distinction is valuable.

---

## 7. Light Mode Special Behaviors

### 7.1 Scope

Only the Linen theme is a light-background theme in this build. Every special
behavior described in this section applies **only when Linen is the active theme**.
All other seven themes are dark-background themes and do not trigger any of
these behaviors.

### 7.2 The Dark HUD Bar

Fully specified in Section 4.3. Summary: when Linen is active, the HUD renders
with a dark charcoal background (`#2C2C2C`) and light text — visually distinct
from the light conversation area below it. The HUD divider line between the
HUD and the conversation area is also dark, and slightly thicker in visual
weight than in dark themes (where the divider is a subtle separator). On Linen,
the divider serves as the visible edge between the dark HUD world and the light
conversation world, and it is drawn with enough contrast to be an unambiguous
boundary.

### 7.3 Scrollbar Inversion

On dark themes, the scrollbar thumb is lighter than the background. On Linen,
the scrollbar thumb is **darker than the background** — a warm gray that sits
visibly on the off-white canvas. The scrollbar track is at background color
(`#F4F1EB`), nearly invisible. The thumb uses the Muted Border color
(`#C5BFB5`) at rest and deepens toward the Text Muted color (`#8A8680`) when
active — the same inversion principle applied to every other element.

### 7.4 System Bubble and Overlay Panels on Linen

All system message bubbles (error, warning, success, info), the `/settings`
overlay, the `/debug` panel, the drop-up slash command menu, and all other
overlay UI surfaces use the **Surface color** (`#EBE8E0`) as their background —
slightly darker than the canvas, so they read as panels sitting above the
background without needing a strong border to define their edges. Their
borders use the Muted Border color (`#C5BFB5`).

---

## 8. Logo Color Per Theme

The ASCII startup wordmark changes color with the active theme. Each theme's
logo color is its **Primary role color** — the same color used for user bubble
borders and key HUD labels — so the logo is visually connected to the rest of
the theme's identity from the very first thing the user sees on startup.

| Theme | Logo Color | Hex |
|---|---|---|
| Midnight | Deep Indigo | `#6C63FF` |
| Aurora | Forest Green | `#3D9970` |
| Ember | Rust Orange | `#E07B39` |
| Arctic | Steel Blue | `#4A9ECA` |
| Charcoal | Steel Blue (cool-gray) | `#5C9CF5` |
| Linen | Deep Navy | `#1E3A5F` |
| Rose | Soft Blush Pink | `#E8A0B4` |
| Dracula | Dracula Purple | `#BD93F9` |

The tagline "Think anything. Ask anything." beneath the logo uses the
**Accent color** of the active theme — giving the startup screen a two-tone
branded appearance where the wordmark and tagline are visually related
but not identical:

| Theme | Tagline Color | Hex |
|---|---|---|
| Midnight | Electric Cyan | `#00D4FF` |
| Aurora | Amber Yellow | `#FFBF00` |
| Ember | Soft Gold | `#F5C842` |
| Arctic | Teal | `#2EC4B6` |
| Charcoal | Soft Steel Blue | `#5C9CF5` |
| Linen | Deep Teal | `#0F6B6B` |
| Rose | Warm Rose-Pink | `#FF79A8` |
| Dracula | Dracula Pink | `#FF79C6` |

---

## 9. Syntax Highlighting Color Sets

### 9.1 Two Highlighting Families

Anythink now maintains two complete, separately tuned syntax highlighting
color sets — one optimized for dark backgrounds (used by all seven dark
themes), and one optimized specifically for Linen's light background.

Each theme in the dark family uses the same base syntax highlighting set,
with minor per-theme accent color blending. Linen uses its own entirely
independent set where every color is chosen for readability on a warm
off-white background at normal screen brightness.

### 9.2 Dark Family Syntax Colors

Used by Midnight, Aurora, Ember, Arctic, Charcoal, Rose, and Dracula.
Each dark theme applies a slight hue shift to these base values to bring
them into alignment with the theme's overall color personality, but the
base values represent the neutral dark-mode baseline:

| Syntax Element | Color Description | Hex |
|---|---|---|
| **Keywords** | Soft purple | `#C678DD` |
| **Strings** | Muted green | `#98C379` |
| **Comments** | Gray-green — clearly de-emphasized | `#5C6370` |
| **Numbers** | Warm orange | `#D19A66` |
| **Functions** | Soft blue | `#61AFEF` |
| **Types / Classes** | Warm yellow | `#E5C07B` |
| **Operators** | Light gray | `#ABB2BF` |
| **Variables** | Soft red-pink | `#E06C75` |
| **Booleans** | Warm orange (same as Numbers) | `#D19A66` |
| **Code block background** | Slightly lifted from surface | Per-theme surface + 4% lighter |
| **Code block border** | Muted border color | Per-theme Muted Border |
| **Language label** | Text Muted color | Per-theme Text Muted |

**Dracula exception:** Because Dracula's official palette defines its own syntax
colors that are widely recognized by its users, the Dracula theme uses the
official Dracula syntax colors instead of the dark family baseline above:

| Syntax Element | Dracula Color | Hex |
|---|---|---|
| **Keywords** | Dracula Pink | `#FF79C6` |
| **Strings** | Dracula Yellow | `#F1FA8C` |
| **Comments** | Dracula Comment | `#6272A4` |
| **Numbers** | Dracula Purple | `#BD93F9` |
| **Functions** | Dracula Green | `#50FA7B` |
| **Types / Classes** | Dracula Cyan | `#8BE9FD` |
| **Operators** | Dracula Foreground | `#F8F8F2` |
| **Variables** | Dracula Orange | `#FFB86C` |
| **Code block background** | Dracula Current Line | `#44475A` |
| **Code block border** | Dracula Selection | `#44475A` |
| **Language label** | Dracula Comment | `#6272A4` |

### 9.3 Linen (Light Mode) Syntax Colors

Every color in this set is chosen for two properties simultaneously: sufficient
contrast against the warm off-white Linen background (`#F4F1EB`) for
readability, and enough hue differentiation from neighboring syntax elements
for clear visual parsing. Lighter, desaturated colors from the dark set would
be invisible on a light background — this set uses deep, saturated, dark
variants of each hue family:

| Syntax Element | Color Description | Hex |
|---|---|---|
| **Keywords** | Deep purple | `#7C3AED` |
| **Strings** | Deep forest green | `#166534` |
| **Comments** | Warm medium gray — italicized where terminal supports | `#6B7280` |
| **Numbers** | Deep burnt orange | `#C2410C` |
| **Functions** | Deep royal blue | `#1E40AF` |
| **Types / Classes** | Deep teal | `#0F766E` |
| **Operators** | Dark warm gray | `#374151` |
| **Variables** | Deep warm brown | `#92400E` |
| **Booleans** | Deep burnt orange (same as Numbers) | `#C2410C` |
| **Code block background** | Slightly cooler than Linen surface | `#E8E4DB` |
| **Code block border** | Warm gray border | `#C5BFB5` |
| **Language label** | Warm medium gray | `#8A8680` |

### 9.4 Per-Theme Hue Blending for Dark Themes

While all seven dark themes share the dark family baseline syntax colors, each
theme applies a subtle hue alignment to the keyword and function colors —
the two most visually prominent syntax elements — so that those colors feel
native to the theme rather than imported:

| Theme | Keyword Color Shift | Function Color Shift |
|---|---|---|
| **Midnight** | Slightly more violet | Slightly more cyan |
| **Aurora** | Slightly more green | Slightly more blue-green |
| **Ember** | Slightly more orange | Slightly more gold |
| **Arctic** | Slightly more blue | Slightly more sky-blue |
| **Charcoal** | No shift — uses baseline | No shift — uses baseline |
| **Rose** | Slightly more pink-purple | Slightly more rose |
| **Dracula** | Overridden by Dracula spec (Section 9.2) | Overridden by Dracula spec |

The baseline values in Section 9.2 serve as the neutral reference point.
Charcoal uses the baseline without any shift, which is appropriate for a
neutral, hue-agnostic theme.

---

## 10. All Eight Themes in `/settings`

### 10.1 Theme Selection Menu Layout

The Theme option in `/settings` expands to an inline horizontal selector
showing all eight themes, each with a one-line personality description to help
new users choose:

```
╭─ ⚙ Theme ──────────────────────────────────────────────────────────╮
│                                                                     │
│  ◀  Midnight   Aurora   Ember   Arctic   Charcoal   Linen   Rose   Dracula  ▶
│                                                                     │
│  ▸ Charcoal — Neutral dark charcoal, clean and focused             │
│                                                                     │
│  ← → Navigate   Enter Select   Esc Cancel                          │
╰─────────────────────────────────────────────────────────────────────╯
```

### 10.2 Live Preview on Navigation

As the user navigates Left/Right through the theme options, the **entire
terminal recolors live** to the highlighted theme — including the open
`/settings` panel itself — so the user sees a real, full-application preview
of each theme before confirming. This is an instant visual preview rather than
a commit, and pressing Escape at any point reverts to the previously active
theme.

### 10.3 Theme Grouping

Themes are ordered in the selector from darkest personality to lightest, with
Linen last in the dark-to-light direction:

```
Midnight → Aurora → Ember → Arctic → Charcoal → Rose → Dracula → Linen
```

This ordering makes the Linen theme findable by users who know they want the
light option — it is always at the rightmost end of the selector.

---

## 11. Cross-Theme Consistency Requirements

### 11.1 Non-Negotiable Rules for All Eight Themes

These rules apply identically to all eight themes, old and new, ensuring that
switching between any two themes never produces an unusable or broken result:

**Minimum contrast:** Every combination of a text color and its background
(or surface) color in any theme must meet a minimum readability standard.
Text that is too close in brightness to its background — even if the hue
difference seems large — is a usability failure. All Primary Text / Background
pairs and all Secondary Text / Surface pairs must be verified legible in normal
terminal lighting conditions before shipping.

**Semantic color recognizability:** In every theme, the Success color must
read as "good" (green-family or clearly positive), the Warning color must
read as "caution" (amber/yellow family), and the Error color must read as
"bad" (red-family) — regardless of how these are tuned per-theme. A user
should be able to identify error state from success state in any theme without
relying on the label text.

**ANSI colorability of all glyphs:** As established in the V2.2 glyph rendering
fix, every icon and glyph in the UI must respond to ANSI color codes and
therefore must visually change color when the theme changes. Any glyph that
appears identical across multiple themes is either still using emoji presentation
(requires VS15 fix) or is incorrectly hardcoded to a fixed color.

**The HUD is always fully readable:** In every theme, both lines of the HUD
must have sufficient contrast to be read without strain. On the dark themes,
this means bright enough text against dark backgrounds. On Linen, this means
the dark HUD bar provides sufficient contrast for the light text on top of it.

**Logo color changes on every theme switch:** As specified in Section 8, every
theme switch must produce a visibly different logo color. Two adjacent themes
in the `/settings` selector must not produce logos that look identical — if
two themes happen to use similar Primary colors, one of them must be adjusted
until the logo color difference is visible.

---

*Anythink — Think anything. Ask anything.*

*Version described: 3.3.0 (V3.3 — Theme Expansion Build)*
*Document last updated: June 2025*
