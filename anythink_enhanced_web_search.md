# Anythink — Enhanced Web Search Build

> A ground-up upgrade of Anythink's web search capability — from a user-invoked
> browsing tool into a fully autonomous, AI-driven research layer that decides
> when to search, rewrites queries for precision, runs multiple searches per
> response, streams live progress to the user, and integrates six search backends
> across general web and dedicated news modes. Every behavior is controllable
> from the `/search` command namespace and the `/settings` menu.
>
> This document describes all changes to the existing `browse/` and `search/`
> modules and all new components introduced in this build.

---

## Table of Contents

1. [What Changes From the Current Implementation](#1-what-changes-from-the-current-implementation)
2. [Per-Session Web Search Toggle](#2-per-session-web-search-toggle)
3. [AI-Initiated Autonomous Search Loop](#3-ai-initiated-autonomous-search-loop)
4. [AI Search Query Rewriting](#4-ai-search-query-rewriting)
5. [Multi-Search Per Response](#5-multi-search-per-response)
6. [Search Backends — Full Roster](#6-search-backends--full-roster)
7. [News Search Mode](#7-news-search-mode)
8. [Result Freshness Filtering](#8-result-freshness-filtering)
9. [Live Step-by-Step Search Progress Display](#9-live-step-by-step-search-progress-display)
10. [Pre-Synthesis Result Preview](#10-pre-synthesis-result-preview)
11. [Collapsible Sources Section](#11-collapsible-sources-section)
12. [Content Extraction Upgrades](#12-content-extraction-upgrades)
13. [Domain Filtering](#13-domain-filtering)
14. [Safe Search Configuration](#14-safe-search-configuration)
15. [Search Result Caching](#15-search-result-caching)
16. [Search + RAG Conflict Handling](#16-search--rag-conflict-handling)
17. [The `/search` Command Namespace](#17-the-search-command-namespace)
18. [AppConfig Changes](#18-appconfig-changes)
19. [Architecture Changes Summary](#19-architecture-changes-summary)

---

## 1. What Changes From the Current Implementation

### 1.1 The Core Shift

The current implementation treats web search as a **tool the user manually
invokes** via `/browse`. The AI is a passive participant — the user decides
when to search, what to search for, and when to stop. The model receives the
raw result as a user-role message and generates a response.

This build changes search into a capability the **AI owns and drives**. When
the per-session toggle is on, the AI monitors every incoming user message,
decides autonomously whether a web search is needed to answer it accurately,
generates its own optimized search queries, runs one or more searches, reads
pages as needed, and synthesizes all of it into a final response — all while
streaming live progress to the user so nothing happens invisibly.

### 1.2 What Stays Unchanged

The following components from the existing implementation are preserved exactly:

- `BrowseFetcher` class structure and dependency injection pattern
- `BrowseTool` inheriting `BaseTool` and its `is_available()` contract
- `BaseSearchBackend` ABC and `SearchResult` dataclass from `base.py`
- `SearchRegistry` registration and entry-point discovery mechanism
- `DuckDuckGoSearch` and `SerpAPISearch` backends (with additions)
- Deferred import pattern for optional dependencies
- `BrowseError` and `SearchError` exception hierarchy
- The `"http"` vs `"headless"` fetch mode controlled by `AppConfig.browse_mode`
- The `"auto"` vs `"ask"` autonomy mode controlled by `AppConfig.browse_autonomy`

### 1.3 What Changes

| Component | Change |
|---|---|
| `_MAX_PAGE_CHARS` | Raised from `8,000` to `15,000` |
| `_strip_html()` | Extended with table structure extraction |
| `BrowseFetcher.fetch_snippets()` | Extended with freshness, domain, and safe search params |
| `BrowseTool.run()` | Extended to support the autonomous multi-search loop |
| `SearchRegistry` | Four new backends added |
| `BaseSearchBackend` | New capability flags: `supports_freshness`, `supports_safe_search`, `supports_news` |
| `AppConfig` | New fields for all new behaviors |
| TUI background worker | Upgraded to stream live progress events per search step |
| New: `SearchOrchestrator` | Manages the full autonomous multi-search loop |
| New: `QueryRewriter` | AI-powered query optimization before backend dispatch |
| New: `SearchCache` | In-session cache with semantic similarity matching |
| New: `NewsMode` routing | Separate backend selection path for news queries |
| New: `/search` namespace | Full command interface for all search behaviors |

---

## 2. Per-Session Web Search Toggle

### 2.1 What It Is

Web search is not always-on. It is a **per-session toggle** the user controls
before or during a conversation. When it is off, the AI answers entirely from
its training knowledge. When it is on, the AI has access to the full web
search capability described in this document and uses it autonomously.

The toggle state is shown in the HUD at all times:

```
🔍 Search: ON   (general)
🔍 Search: ON   (news)
🔍 Search: OFF
```

### 2.2 Enabling and Disabling

```
/search on            Enable general web search for this session
/search off           Disable web search for this session
/search news          Enable news-only search mode
/search toggle        Toggle between on and off
```

### 2.3 Toggle Does Not Persist Across Sessions

The per-session toggle defaults to **OFF** at the start of every new session.
The user explicitly enables it before asking a question that needs web access.
This default-off behavior prevents unintended API usage, unexpected latency,
or unnecessary network calls in sessions where the user only wants to chat with
the model's training knowledge.

A global default can be set in `/settings` → Search → Default web search state,
which controls what the toggle starts as when a new session begins — but the
user can always override it per session. The global default is OFF unless the
user changes it.

### 2.4 Visual State Indicator

When web search is on, the HUD search indicator switches from muted-gray
(`Search: OFF`) to the theme's accent color (`Search: ON`). During active
search operations (while a search is running mid-response), the indicator
shows a live pulse animation to communicate that network activity is in progress.

---

## 3. AI-Initiated Autonomous Search Loop

### 3.1 How the AI Decides to Search

When the per-session toggle is on, the model is given access to web search
as an agent tool — defined in the tool schema passed to the provider's API.
The model sees a tool definition that describes what web search can do and
when it is appropriate to use it. The model then decides, on its own, whether
each incoming user message needs a web lookup to answer accurately.

The decision is made by the model itself — Anythink does not apply any
rule-based heuristics on top of the model's judgment. The model decides based
on its own understanding of when its training knowledge may be stale, incomplete,
or insufficient.

### 3.2 The Autonomous Loop Sequence

When the model decides to search, the following sequence executes automatically,
without any user intervention:

```
User sends message
      │
      ▼
Model receives message + tool schema for web_search
      │
      ▼
Model generates a tool_use request: { "tool": "web_search", "query": "..." }
      │
      ▼
QueryRewriter optimizes the query (Section 4)
      │
      ▼
Cache check — is this query (or a similar one) cached? (Section 15)
      │
  ┌───┴────┐
Cache hit  Cache miss
  │           │
  ▼           ▼
Use cached  Run backend search
result        │
  │           ▼
  └──→  Results returned
      │
      ▼
Quality check — are results useful?
      │
      ▼
Results injected as tool_result back to the model
      │
      ▼
Model may issue another tool_use (Section 5) or begin final response
      │
      ▼
Pre-synthesis preview shown to user (Section 10)
      │
      ▼
Model streams final synthesized response
      │
      ▼
Collapsible sources section appended (Section 11)
```

### 3.3 The Tool Schema Passed to the Model

The web search tool is presented to the model via the provider's function/tool
calling API with a schema that communicates its capabilities and appropriate
use cases. The schema includes the tool's name, a clear description of when to
use it, and its parameters — including query, search mode (general or news),
freshness filter, and domain filters. The model reads this schema and uses it
to construct tool calls with the right parameters for each search it decides
to run.

### 3.4 Autonomy Mode Still Applies

The existing `browse_autonomy` config field (`"auto"` or `"ask"`) still
controls the confirmation behavior:

- **Auto mode**: The AI runs searches immediately when it decides to, with
  no interruption to the user (they see live progress but are not asked)
- **Ask mode**: Before the first search of a response, the user is shown
  a confirmation prompt listing what the AI intends to search for. The user
  approves or declines. If declined, the model answers from training knowledge
  only. Subsequent searches within the same response (multi-search) do not
  re-prompt in ask mode — only the first one does.

---

## 4. AI Search Query Rewriting

### 4.1 What Query Rewriting Does

Before any search query reaches a backend, it passes through the
`QueryRewriter` — a lightweight AI prompt that converts the raw user message
(or the model's internally generated sub-question) into an **optimized search
query** tuned for web search engines.

Raw user messages are often conversational, ambiguous, or contain context that
only makes sense in a chat session. Search engines respond better to concise,
keyword-rich, specific queries. Query rewriting bridges this gap.

### 4.2 Examples

| Raw Input | Rewritten Query |
|---|---|
| "what's the latest llama model?" | `Meta Llama 3 latest release 2025` |
| "how do I fix the CORS error in my Flask app?" | `Flask CORS error fix Python 2025` |
| "compare the two approaches we were just discussing" | `transformer vs RNN sequence modeling comparison` |
| "is it still maintained?" | `[previously discussed library] maintenance status 2025` |

The rewriter handles session-contextual references (like "it" or "the two
approaches") by reading the recent conversation history to resolve what the
user is referring to before constructing the query string.

### 4.3 The QueryRewriter Component

`QueryRewriter` is a new component in `search/rewriter.py`. It takes the raw
input (user message or AI-generated sub-question), the recent conversation
history (last 3–5 turns for context resolution), and the active search mode
(general or news) and produces one or more optimized query strings.

It uses the **same LLM already active in the session** — sending a short
system prompt and the input to the model, requesting only the rewritten query
as output (no explanation, no preamble). The prompt is small and the response
is a single line, so this adds minimal latency. Typically under 200ms for
a local model or fast cloud provider.

### 4.4 Multi-Query Generation

For complex user messages, the rewriter may generate **more than one query
string** — representing different aspects of the question that benefit from
separate searches. For example, a question comparing two technologies might
produce one query per technology rather than one combined query that a search
engine would answer less precisely. The rewriter signals multi-query output
by returning a list of strings rather than a single string. The
`SearchOrchestrator` (Section 5) receives this list and runs each query as a
separate search.

### 4.5 Rewriter Bypass

The user can bypass query rewriting for a specific search using the
`/search raw <query>` command — sending the query to the backend exactly as
typed, without any AI transformation. This is useful when the user already
knows the exact search string they want.

---

## 5. Multi-Search Per Response

### 5.1 How It Works

The AI is not limited to one search per response. When web search is active,
the model can issue multiple sequential `tool_use` calls — each one a new
search request — before it begins generating its final response. This allows
the model to:

- Search for different sub-topics of a complex question independently
- Follow up on an initial result set with a more specific query when the
  first results raise new questions
- Search for both the general concept and a specific implementation separately
- Run a news search and a general web search in the same response when both
  types of information are needed

### 5.2 The SearchOrchestrator

`SearchOrchestrator` is a new component in `search/orchestrator.py` that
manages the full multi-search loop. It receives tool call requests from the
model, dispatches them to the appropriate backend (through the QueryRewriter
and cache layer), collects results, and feeds them back to the model as
tool results — in a loop until the model stops issuing tool calls and begins
its final generation.

The orchestrator enforces a **maximum search count per response** (default 5,
configurable in `/search settings`) to prevent runaway loops on poorly
scoped questions. If the model attempts a 6th search, the orchestrator returns
a synthetic tool result informing the model it has reached its search limit
and should synthesize from what it has.

### 5.3 Sequential, Not Parallel

Searches within a single response run **sequentially**, not in parallel.
Each search result is returned to the model before the next search begins.
This allows the model to use the result of search 1 to inform what to search
for in search 2 — which is the primary value of multi-search. Parallel
execution would prevent this adaptive behavior.

### 5.4 Live Display During Multi-Search

The live progress display (Section 9) streams each search step in real time,
so the user sees the entire multi-search sequence as it happens:

```
 ◐ Generating search queries…
 ✓ Query 1: "Python asyncio event loop 2025"
 ◐ Searching: "Python asyncio event loop 2025"
 ✓ Found 5 results
 ◐ Reading: docs.python.org/3/library/asyncio…
 ✓ Read 1 page (12,400 chars)
 ◐ Searching: "asyncio.run() deprecation Python 3.12"
 ✓ Found 4 results
 ◐ Synthesizing response…
```

---

## 6. Search Backends — Full Roster

### 6.1 Roster Overview

This build adds four new backends to the existing two, bringing the total to
six. All six are registered via the existing entry-point system in
`pyproject.toml` and discoverable by `SearchRegistry.from_entry_points()`.

| Backend | Class | Mode | Key Required | Best For |
|---|---|---|---|---|
| DuckDuckGo | `DuckDuckGoSearch` | General | No | Default free general search |
| SerpAPI | `SerpAPISearch` | General | Yes | Google-quality results |
| Exa | `ExaSearch` | General | Yes | AI-optimized semantic research |
| Google Custom Search | `GoogleCSESearch` | General | Yes | Google results via CSE API |
| Bing Search API | `BingSearch` | General | Yes | Microsoft index, news-capable |
| NewsAPI | `NewsAPISearch` | **News only** | Yes | Dedicated news articles |

### 6.2 BaseSearchBackend — New Capability Flags

Three new class-level boolean attributes are added to `BaseSearchBackend`
in `base.py`. Each concrete backend sets these to reflect its actual
capabilities. The registry and orchestrator read them to route queries
correctly:

| Attribute | Type | Default | Description |
|---|---|---|---|
| `supports_freshness` | `bool` | `False` | Can accept `date_from` / `date_to` filter params |
| `supports_safe_search` | `bool` | `False` | Accepts a safe search level parameter |
| `supports_news` | `bool` | `False` | Can search news articles specifically |

The `search()` abstract method signature is extended with optional parameters:

```
async def search(
    self,
    query: str,
    max_results: int = 5,
    date_from: str | None = None,
    date_to: str | None = None,
    safe_search: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> list[SearchResult]
```

Backends that do not support a given parameter silently ignore it.

### 6.3 SearchResult — Extended Fields

`SearchResult` in `base.py` gains two new optional fields to support
freshness display and news-specific metadata:

| New Field | Type | Description |
|---|---|---|
| `published_date` | `str \| None` | Publication date of the result (ISO format where available) |
| `source_domain` | `str \| None` | Root domain of the result URL (e.g., `"python.org"`) |

These fields are populated where the backend provides them and are shown in
the pre-synthesis preview and the sources section.

---

### 6.4 New Backend: Exa (`exa.py`)

**Class:** `ExaSearch`
**Mode:** General web
**Requires:** `pip install anythink[exa]` (the `exa-py` SDK)
**Key setup:** `anythink keys add exa`

```
name         = "exa"
display_name = "Exa"
supports_freshness  = True
supports_safe_search = False
supports_news       = False
```

Exa (formerly Metaphor) uses a neural search index purpose-built for AI
retrieval use cases. Unlike keyword-based engines, Exa understands the semantic
meaning of a query and returns results that are conceptually relevant rather
than just keyword-matched. This makes it particularly strong for research
questions, technical topics, and queries where the exact phrasing is uncertain.

The `search()` method calls the Exa Python SDK's `search()` endpoint. Results
include full highlights (excerpts from the page) rather than just snippets,
which reduces the need for a separate page-fetch step for many queries. The
`date_from` filter is passed as Exa's `start_published_date` parameter when
freshness filtering is active.

---

### 6.5 New Backend: Google Custom Search (`google_cse.py`)

**Class:** `GoogleCSESearch`
**Mode:** General web
**Requires:** No extra package (`httpx` is a core dep)
**Key setup:** `anythink keys add google_cse` (requires a Google API key and
a Custom Search Engine ID)

```
name         = "google_cse"
display_name = "Google"
supports_freshness  = True
supports_safe_search = True
supports_news       = False
```

Uses the Google Custom Search JSON API to return Google Search results.
The method makes a GET request to `https://www.googleapis.com/customsearch/v1`
with `q`, `key`, `cx` (the CSE ID), `num`, `dateRestrict` (for freshness),
`safe` (for safe search), and `siteSearch`/`siteSearchFilter` parameters for
domain inclusion/exclusion.

`date_from` and `date_to` are translated into Google's `dateRestrict`
parameter format (e.g., `d7` for the last 7 days, `m1` for the last month).
`safe_search` maps to Google's `safe` parameter values (`"active"` or `"off"`).

---

### 6.6 New Backend: Bing Search API (`bing.py`)

**Class:** `BingSearch`
**Mode:** General web and news
**Requires:** No extra package (`httpx` is a core dep)
**Key setup:** `anythink keys add bing`

```
name         = "bing"
display_name = "Bing"
supports_freshness  = True
supports_safe_search = True
supports_news       = True
```

Uses the Microsoft Bing Web Search API v7. The method makes a GET request to
`https://api.bing.microsoft.com/v7.0/search` (general) or
`https://api.bing.microsoft.com/v7.0/news/search` (news mode, triggered when
the orchestrator is in news mode). The `Ocp-Apim-Subscription-Key` header
carries the API key.

Parameters supported: `q`, `count`, `freshness` (for date filtering —
`"Day"`, `"Week"`, `"Month"`, or an explicit date range string), `safeSearch`
(`"Off"`, `"Moderate"`, `"Strict"`), and `site:` operators embedded in the
query string for domain filtering.

Bing is the only backend in this roster that supports both general web and
news mode natively through different endpoint paths, making it a flexible
fallback when a dedicated news backend like NewsAPI is not configured.

---

### 6.7 New Backend: NewsAPI (`newsapi.py`)

**Class:** `NewsAPISearch`
**Mode:** News only
**Requires:** No extra package (`httpx` is a core dep)
**Key setup:** `anythink keys add newsapi`

```
name         = "newsapi"
display_name = "NewsAPI"
supports_freshness  = True
supports_safe_search = False
supports_news       = True
```

Uses the NewsAPI.org `everything` endpoint
(`https://newsapi.org/v2/everything`) for general news searches and the
`top-headlines` endpoint for breaking/trending news. Returns news articles
with titles, descriptions, source names, URLs, and publication dates.

`date_from` and `date_to` map directly to NewsAPI's `from` and `to` parameters
(ISO 8601 date strings). Results include `published_date` in `SearchResult`
from the article's `publishedAt` field and `source_domain` from the article's
`source.name` field.

NewsAPI is the **primary news backend** when news mode is active. If no
NewsAPI key is configured, the orchestrator falls back to Bing's news endpoint.

---

## 7. News Search Mode

### 7.1 What It Is

News mode is a separate search mode — enabled with `/search news` — that routes
all queries to news-capable backends (NewsAPI, Bing news endpoint) rather than
the general web backends. In this mode, results are articles with publication
dates, bylines, and source names rather than general web pages.

The HUD reflects the mode:

```
🔍 Search: ON (news)
```

### 7.2 News Mode vs General Mode Routing

The `SearchOrchestrator` reads the active mode from session state and passes
it to `SearchRegistry.get_available()` as a new `news_mode: bool` parameter.
When `news_mode=True`, the registry filters its backend list to only those
where `backend.supports_news == True`, selecting from: NewsAPI (preferred),
Bing (fallback). If neither is available, a clear error is shown:
`"No news backend configured. Run /keys add newsapi or /keys add bing."`

### 7.3 Auto-Detection for Time-Sensitive Queries

When general search mode is on and the model detects a query that is clearly
about current events ("today's news about...", "latest release of...",
"what happened with..."), the model may request news mode in its tool call
by setting a `news_mode: true` parameter. The orchestrator honors this even
if the user enabled general web search — allowing mixed responses where some
searches are general and others are news-specific.

### 7.4 News Result Display Differences

News results in the pre-synthesis preview and sources section show additional
fields not shown for general web results:

- Publication date (relative time for recent articles: "3h ago", "2 days ago")
- Source domain / news outlet name
- Article byline where available from the backend

---

## 8. Result Freshness Filtering

### 8.1 What It Is

Freshness filtering restricts search results to those published or indexed
within a specified date range. It prevents the AI from incorporating
outdated content when answering time-sensitive questions.

### 8.2 User-Controlled Freshness

The user can set a freshness filter for the current session or for a specific
query:

```
/search fresh 24h       Only results from the last 24 hours
/search fresh 7d        Only results from the last 7 days
/search fresh 30d       Only results from the last 30 days
/search fresh 3m        Only results from the last 3 months
/search fresh off       Remove freshness filter
/search fresh custom 2025-01-01 2025-06-01   Explicit date range
```

The active freshness filter is shown in the search progress display and
pre-synthesis preview so the user knows the filter was applied.

### 8.3 AI-Requested Freshness

The model can also request freshness in its tool call. When the query
contains time-sensitive language ("latest", "current", "recent", "this week",
"today") the model is prompted by its tool schema to include appropriate
`date_from` and `date_to` parameters in the tool call. The orchestrator
passes these to `fetch_snippets()` and the active backend.

### 8.4 Backend Support for Freshness

Not all backends support server-side freshness filtering. The orchestrator
handles this per-backend:

| Backend | Freshness Support | How Applied |
|---|---|---|
| DuckDuckGo | None | Post-filter: filter returned results by `published_date` where available |
| SerpAPI | Via `tbs` parameter | Server-side — most accurate |
| Exa | Via `start_published_date` | Server-side |
| Google CSE | Via `dateRestrict` | Server-side |
| Bing | Via `freshness` parameter | Server-side |
| NewsAPI | Via `from` / `to` parameters | Server-side |

For backends without server-side support, post-filtering is applied: results
are returned from the backend and those with a `published_date` outside the
requested range are removed from the list before it reaches the orchestrator.
Results without a `published_date` are kept (since they cannot be reliably
dated) and flagged with a `⚠ date unknown` label in the preview.

---

## 9. Live Step-by-Step Search Progress Display

### 9.1 What the User Sees

From the moment a search begins to the moment the AI starts generating its
final response, a live, updating progress display runs in the conversation
area — above where the AI response bubble will appear. Each step of the
search process appears as it happens, in chronological order, with a
status indicator per step.

This display replaces the current `SystemBubble("Browsing: …")` single-line
indicator with a multi-step, semantically accurate, real-time feed:

```
╭─ ⚙ Web Search — Request #4 ───────────────────────────────────────╮
│                                                                     │
│  ✓ Query rewritten: "Python asyncio event loop internals 2025"     │
│  ✓ Cache check: miss — running live search                         │
│  ◐ Searching: "Python asyncio event loop internals 2025"           │
│  ✓ Found 6 results (DuckDuckGo)                                    │
│  ◐ Reading: docs.python.org/3/library/asyncio-eventloop.html       │
│  ✓ Read 1 page — 12,800 chars extracted                            │
│  ◐ Searching: "asyncio.run() behavior change Python 3.12"          │
│  ✓ Found 4 results (DuckDuckGo)                                    │
│  ◐ Processing results…                                              │
│  ✓ 2 searches · 1 page read · total 1.8s                          │
│                                                                     │
╰─────────────────────────────────────────────────────────────────────╯
```

### 9.2 Step Status Indicators

Each step uses the existing monochrome icon language:

| Symbol | Meaning |
|---|---|
| `◐` (spinning) | In progress |
| `✓` | Completed successfully |
| `✕` | Failed — error message inline |
| `⚠` | Completed with a warning (e.g., few results, date unknown) |

### 9.3 Step Types Shown

| Step | When It Appears |
|---|---|
| `Query rewritten: "…"` | After QueryRewriter produces the optimized query |
| `Cache check: hit` or `Cache check: miss` | After cache lookup |
| `Searching: "…"` | When a backend search call begins |
| `Found N results (BackendName)` | When a backend search returns |
| `Reading: <url>` | When a full-page fetch begins |
| `Read 1 page — N chars extracted` | When a page fetch completes |
| `Re-searching: "…"` | When the model issues a second or subsequent search |
| `Processing results…` | While results are being assembled for the model |
| `Summary: N searches · M pages · total Xs` | Final summary line before synthesis |

### 9.4 Display Lifecycle

The search progress panel appears when the first search step begins and
collapses to a single summary line after the AI begins streaming its final
response:

```
 ✓ 2 searches completed in 1.8s — [expand to see steps]
```

This summary line persists in the conversation scrollback as a permanent
record of what web activity occurred for that response, collapsible to avoid
cluttering the conversation. The full step-by-step log is always accessible
by expanding it.

---

## 10. Pre-Synthesis Result Preview

### 10.1 What It Shows

Before the AI begins generating its final synthesized response, Anythink
shows the **raw search results** to the user — the titles, snippets, URLs,
and dates of everything found across all searches, formatted like a search
results page. This gives the user full visibility into what the AI found
before it interprets and synthesizes the information.

```
╭─ 🔍 Search Results — 2 queries · 9 results ───────────────────────╮
│                                                                     │
│  Query 1: "Python asyncio event loop internals 2025"               │
│  ────────────────────────────────────────────────────────────────  │
│  1. Python asyncio documentation — Event Loop                      │
│     docs.python.org · 2 days ago                                   │
│     "The event loop is the core of every asyncio application.      │
│     asyncio.run() creates a new event loop, runs the coroutine..." │
│                                                                     │
│  2. Real Python: Async IO in Python — A Complete Walkthrough       │
│     realpython.com · 6 months ago                                  │
│     "asyncio is a library to write concurrent code using the       │
│     async/await syntax, running coroutines on a single thread..."  │
│                                                                     │
│  Query 2: "asyncio.run() behavior change Python 3.12"             │
│  ────────────────────────────────────────────────────────────────  │
│  3. Python 3.12 Release Notes                                      │
│     docs.python.org · 1 year ago                                   │
│     "asyncio.run() now accepts an optional loop_factory parameter" │
│                                                                     │
│  [+ 6 more results]   [Synthesize →]   [Cancel]                    │
│                                                                     │
╰─────────────────────────────────────────────────────────────────────╯
```

### 10.2 User Actions From the Preview

Three actions are available at the bottom of the preview panel:

**`[+ N more results]`** — Expands the preview to show all results (not
just the top few per query). Useful when the user wants to see everything
before deciding whether to continue.

**`[Synthesize →]`** — The user confirms they want the AI to proceed with
synthesis. Synthesis begins immediately. In ask mode this button must be
clicked; in auto mode the synthesis begins automatically after a brief
delay (3 seconds) unless the user intervenes.

**`[Cancel]`** — Cancels the synthesis. The search results remain visible
but no AI response is generated. The user can rephrase their question or
search manually.

### 10.3 Preview in Auto Mode

In auto mode, the preview appears briefly (3 seconds by default) before
synthesis automatically begins. The countdown is visible: `"Synthesizing
in 3… 2… 1…"`. The user can press any key to pause the countdown, then
click `[Synthesize →]` to proceed manually or `[Cancel]` to abort.

This delay is configurable in `/settings` → Search → Preview auto-proceed
delay (0 = no preview in auto mode, proceed immediately).

---

## 11. Collapsible Sources Section

### 11.1 Placement

Every AI response generated using web search results has a **sources section**
appended at the bottom of the AI response bubble — between the response text
and the standard response metadata footer (word count, timestamp).

### 11.2 Collapsed Default State

The sources section is **collapsed by default**, showing only a summary line:

```
│  🔍 3 sources used  [expand]                                       │
│                                  Groq · just now  62 words · ··   │
```

### 11.3 Expanded State

When the user expands the sources section, it shows each source with its
title, domain, date, and relevance to the response:

```
│  🔍 Sources                                    [collapse]          │
│                                                                     │
│  1. Python asyncio documentation — Event Loop                      │
│     docs.python.org  ·  2 days ago  ·  used in synthesis          │
│     https://docs.python.org/3/library/asyncio-eventloop.html       │
│                                                                     │
│  2. Real Python: Async IO in Python                                │
│     realpython.com  ·  6 months ago  ·  used in synthesis         │
│     https://realpython.com/async-io-python/                        │
│                                                                     │
│  3. Python 3.12 Release Notes                                       │
│     docs.python.org  ·  1 year ago  ·  used in synthesis          │
│     https://docs.python.org/3/whatsnew/3.12.html                   │
│                                                                     │
│                                  Groq · just now  62 words · ··   │
```

### 11.4 "Used in Synthesis" vs "Retrieved but Not Used"

Sources found during search but not referenced in the AI's synthesized
response are labeled `retrieved only` rather than `used in synthesis`,
and are shown in a dimmed/muted style so the user can distinguish which
sources actually informed the response from which were retrieved but
ultimately not needed.

---

## 12. Content Extraction Upgrades

### 12.1 Raised Character Cap — 15,000

`_MAX_PAGE_CHARS` in `browse/fetch.py` is raised from `8,000` to `15,000`.

This is approximately 3,750 tokens at typical ratios — still well within
the 40K–80K context windows of the local LLMs targeted in this build, even
when combined with conversation history and RAG context. The higher cap
captures more complete page content, reducing cases where a technical
explanation or reference page is cut off mid-section.

### 12.2 Table Structure Extraction

The existing `_strip_html()` helper is extended with a new pre-processing
step that runs **before** generic tag stripping: HTML `<table>` elements are
detected and converted to Markdown-compatible plain text tables before the
rest of the HTML is stripped.

The table extraction process:

- Identifies `<table>` elements in the raw HTML
- Extracts `<th>` header cells and `<td>` data cells, row by row
- Reconstructs the table as a pipe-delimited Markdown table:

```
| Column A | Column B | Column C |
|---|---|---|
| Value 1 | Value 2 | Value 3 |
| Value 4 | Value 5 | Value 6 |
```

- Replaces the original `<table>...</table>` block in the HTML string with
  this Markdown representation before the rest of `_strip_html()` runs.

This means that when a page is fetched that contains pricing tables, comparison
charts, API parameter tables, or data tables of any kind, the structured
information is preserved in a format the LLM can reason about precisely, rather
than being flattened into an undifferentiated string of cell values.

### 12.3 Table Extraction Limitations

Nested tables (a `<table>` inside another `<table>`) are handled by processing
the innermost tables first. Tables with merged cells (`colspan`/`rowspan`) are
handled gracefully — merged cells are repeated in the output to maintain column
alignment, with a `[merged]` suffix where appropriate. Very wide tables (more
than 10 columns) are rendered with abbreviated column names to avoid line-length
issues in the terminal display.

### 12.4 Expanded Entity Unescaping

The existing entity unescaping in `_strip_html()` covers 5 entities. This
is extended to cover the full set of named HTML entities that commonly appear
in technical and news content, ensuring that characters like `—` (em dash),
`"` (curly quotes), `·` (middle dot), and `©` (copyright) are rendered as
their actual Unicode characters rather than their HTML entity codes in the
extracted text.

---

## 13. Domain Filtering

### 13.1 Two Filter Types

Domain filtering supports two complementary lists:

**Include list (allowlist):** When set, search results are restricted to only
those from the specified domains. The AI only retrieves content from the listed
domains, regardless of what the backend returns.

**Exclude list (blocklist):** When set, search results from the specified
domains are removed from results regardless of their relevance score. The
remaining results proceed normally.

Both lists can be active simultaneously (search only within `include` domains,
but exclude specific paths or subdomains from within that set).

### 13.2 Setting Domain Filters

```
/search include docs.python.org stackoverflow.com
/search include add github.com
/search exclude w3schools.com reddit.com
/search exclude add quora.com
/search filters          Show active include and exclude lists
/search filters clear    Remove all domain filters
```

Domain filters set with `/search include` or `/search exclude` persist for
the current session. They can also be set as session-persistent defaults in
`/settings` → Search → Domain filters.

### 13.3 How Domain Filtering is Applied

Domain filtering is applied at two layers:

**Layer 1 — Backend-level (server-side where supported):** For backends that
support query-level domain filtering (Google CSE via `siteSearch` parameter,
Bing via `site:` operator in the query string, SerpAPI via `as_sitesearch`),
the domain list is passed directly to the backend API. This produces more
accurate results because the backend only returns content from the specified
domains.

**Layer 2 — Result-level (client-side, always applied):** After results are
returned by any backend, the orchestrator filters the list — removing any result
whose URL's root domain is in the exclude list, and (when an include list is
set) keeping only results whose domain appears in the include list. This ensures
domain filtering is always enforced regardless of backend support.

### 13.4 Domain Filter Visibility

Active domain filters are shown in the live search progress display so the user
knows filtering is in effect:

```
│  ◐ Searching: "Python asyncio" [domains: docs.python.org only]    │
```

---

## 14. Safe Search Configuration

### 14.1 Configurable Levels

Safe search is configurable with three levels, accessible via
`/settings` → Search → Safe search:

| Level | Description |
|---|---|
| **Strict** | Maximum filtering — removes all adult content, most graphic content |
| **Moderate** | Balanced filtering — removes explicit content, allows mature topics |
| **Off** | No filtering applied by Anythink or requested from backends |

Default is **Moderate**.

### 14.2 How It Is Applied

The safe search level is passed to the backend's `search()` method via the
`safe_search` parameter. Each backend that supports it maps the level to its
own parameter format:

| Backend | Strict | Moderate | Off |
|---|---|---|---|
| Google CSE | `"active"` | `"active"` | `"off"` |
| Bing | `"Strict"` | `"Moderate"` | `"Off"` |
| SerpAPI | `"active"` | `"active"` | not sent |
| DuckDuckGo | DuckDuckGo applies its own default; no override | — | — |
| Exa, NewsAPI | Not supported; parameter ignored | — | — |

For backends that do not support safe search, the level is silently ignored —
Anythink does not attempt to post-filter results from these backends based on
content, since reliable content classification would require a separate ML
model.

---

## 15. Search Result Caching

### 15.1 What Caching Does

The `SearchCache` component stores the results of completed searches
in memory for the duration of the current session. If a subsequent search —
either from the user or from the AI's autonomous multi-search loop —
is identical or semantically similar to a cached query, the cached results
are returned immediately without making a new backend API call.

This saves latency, preserves API quota on rate-limited backends (Exa,
Google CSE, Bing), and produces consistent results when the same question
is asked multiple times in a session.

### 15.2 Exact Match Caching

The first layer of the cache is an exact key match — the normalized,
lowercased, whitespace-trimmed query string is used as the cache key.
If the incoming query matches a key exactly, the cached result is returned
immediately.

### 15.3 Semantic Similarity Matching

The second layer handles near-duplicate queries that are not exactly identical
but are asking for the same thing (e.g., "Python asyncio docs" vs "asyncio
Python documentation"). The `SearchCache` maintains query embeddings alongside
results — using the same embedding model active for RAG if RAG is configured,
otherwise using a lightweight local embedding model. Incoming queries are
embedded and compared against cached query embeddings. If cosine similarity
exceeds a configurable threshold (default 0.92), the cached result is returned.

### 15.4 Cache Indicators in Live Display

When a cache hit occurs, the live progress display shows it clearly:

```
 ✓ Cache check: hit — reusing result from 4m ago
```

When a cache miss occurs:

```
 ✓ Cache check: miss — running live search
```

### 15.5 Cache Toggle in Settings

Caching can be toggled on or off via `/settings` → Search → Result caching:

```
/search cache on      Enable result caching for this session
/search cache off     Disable result caching for this session
/search cache clear   Clear all cached results for this session
/search cache status  Show how many results are cached and their ages
```

When off, every search always makes a live backend call regardless of whether
the query was already searched. This is useful when real-time freshness is
critical and the user cannot afford to get a result from 10 minutes ago.

### 15.6 Cache TTL

Cached results expire after **30 minutes** by default. After expiry, a
re-search is triggered automatically even if the query is an exact match.
The TTL is configurable in `/settings` → Search → Cache TTL
(options: 10m, 30m, 1h, session — meaning cache never expires within a session).

---

## 16. Search + RAG Conflict Handling

### 16.1 The Conflict

When both a RAG index is active and web search is toggled on, Anythink does
not silently combine the two information sources. Instead, it treats this as
a configuration conflict and handles it explicitly before any response is
generated.

The design decision: when RAG is loaded, the user has invested effort in
building a local knowledge base specifically for Anythink to use. Web search
retrieving different, potentially contradictory information in the same response
would undermine the trustworthiness of the RAG system. RAG always takes
full priority.

### 16.2 Conflict Detection and Prompt

The conflict is detected at the start of each conversation turn — before any
model generation or search begins — by checking session state for both an
active RAG index and web search toggled on simultaneously.

When detected, Anythink pauses before processing the user's message and shows
a one-time, session-persistent conflict prompt:

```
╭─ ⚠ RAG + Web Search Conflict ────────────────────────────────────╮
│                                                                    │
│  You have both a RAG index (my-project) and web search active.    │
│                                                                    │
│  When a RAG index is loaded, Anythink answers only from your      │
│  local index. Web search is not used.                             │
│                                                                    │
│  To use web search for this session:                              │
│   → Run /rag off to deactivate the index first                   │
│                                                                    │
│  [Continue with RAG only]   [Turn off web search]                 │
│                                                                    │
╰────────────────────────────────────────────────────────────────────╯
```

### 16.3 After the Prompt

**If the user chooses "Continue with RAG only":** Web search is silently
suppressed for the remainder of the session. The HUD search indicator changes
to `🔍 Search: OFF (RAG active)` to communicate clearly that web search is
not running. The conflict prompt does not appear again for the rest of the
session — it is shown once, the user has made their choice, and the system
honors it.

**If the user chooses "Turn off web search":** Web search is toggled off
(`/search off`) immediately. The user's original message is then processed
normally using RAG only.

### 16.4 No Hybrid Mode

There is no hybrid RAG + web search mode in this build. The two systems are
explicitly mutually exclusive per session by design. A future build may
introduce a hybrid synthesis mode — but only once the quality and reliability
of both systems individually are well established.

---

## 17. The `/search` Command Namespace

All web search functionality is accessible from a unified `/search` namespace.

### 17.1 Toggle Commands

```
/search on                    Enable general web search
/search off                   Disable web search
/search news                  Enable news-only search mode
/search toggle                Toggle between on and off
/search status                Show full current search configuration
```

### 17.2 Query Commands

```
/search <query>               Run a one-off manual search and show results
/search raw <query>           Run a search with no query rewriting
/search url <url>             Fetch a specific page directly
```

### 17.3 Filter Commands

```
/search include <domains…>    Set domain include list
/search include add <domain>  Add one domain to include list
/search exclude <domains…>    Set domain exclude list
/search exclude add <domain>  Add one domain to exclude list
/search filters               Show active domain filters
/search filters clear         Remove all domain filters
/search fresh <period>        Set freshness filter (24h, 7d, 30d, 3m, off)
/search fresh custom <from> <to>  Set explicit date range
```

### 17.4 Cache Commands

```
/search cache on              Enable result caching
/search cache off             Disable result caching
/search cache clear           Clear all cached results
/search cache status          Show cache contents and ages
```

### 17.5 Backend Commands

```
/search backends              List all registered backends and their status
/search backend use <name>    Set preferred backend for this session
/search backend test <name>   Test a backend with a sample query
```

### 17.6 Settings Command

```
/search settings              Open the interactive search settings panel
```

---

## 18. AppConfig Changes

New fields added to `AppConfig` in `config/schema.py` to support all new
behaviors described in this document:

| Field | Type | Default | Description |
|---|---|---|---|
| `search_enabled` | `bool` | `False` | Per-session web search toggle |
| `search_mode` | `str` | `"general"` | `"general"` or `"news"` |
| `search_max_per_response` | `int` | `5` | Max searches the model may run per response |
| `search_query_rewrite` | `bool` | `True` | Enable AI query rewriting |
| `search_preview` | `bool` | `True` | Show pre-synthesis result preview |
| `search_preview_delay_s` | `float` | `3.0` | Auto-proceed delay in auto mode |
| `search_cache_enabled` | `bool` | `True` | Enable result caching |
| `search_cache_ttl_minutes` | `int` | `30` | Cache TTL in minutes |
| `search_safe_search` | `str` | `"moderate"` | Safe search level |
| `search_freshness` | `str \| None` | `None` | Active freshness filter |
| `search_include_domains` | `list[str]` | `[]` | Domain allowlist |
| `search_exclude_domains` | `list[str]` | `[]` | Domain blocklist |
| `search_max_page_chars` | `int` | `15_000` | Character cap per page fetch |
| `search_default_enabled` | `bool` | `False` | Global default for toggle at session start |

---

## 19. Architecture Changes Summary

### 19.1 New Files

| File | Purpose |
|---|---|
| `search/orchestrator.py` | `SearchOrchestrator` — manages the autonomous multi-search loop, dispatches to backends, enforces max search count |
| `search/rewriter.py` | `QueryRewriter` — AI-powered query optimization using the active session model |
| `search/cache.py` | `SearchCache` — in-session result cache with exact and semantic matching |
| `search/newsapi.py` | `NewsAPISearch` backend |
| `search/exa.py` | `ExaSearch` backend |
| `search/google_cse.py` | `GoogleCSESearch` backend |
| `search/bing.py` | `BingSearch` backend |

### 19.2 Modified Files

| File | What Changes |
|---|---|
| `browse/fetch.py` | `_MAX_PAGE_CHARS` raised to 15,000; `_strip_html()` extended with table extraction and full entity unescaping; `BrowseFetcher.fetch_snippets()` accepts new filter parameters |
| `search/base.py` | `BaseSearchBackend` gains three capability flags and extended `search()` signature; `SearchResult` gains `published_date` and `source_domain` |
| `search/registry.py` | `get_available()` gains `news_mode` parameter; four new backends registered in entry points |
| `search/duckduckgo.py` | Extended to pass new filter params where supported |
| `search/serpapi.py` | Extended to pass freshness, safe search, and domain params |
| `config/schema.py` | All new `AppConfig` fields from Section 18 |
| `app.py` | Background worker upgraded to use `SearchOrchestrator`; live progress events streamed to TUI; conflict detection for RAG + search |

### 19.3 Data Flow — Comparing Old vs New

**Old flow:**
```
/browse command → TUI dispatch → BrowseFetcher → Backend → SystemBubble → AI response
```

**New flow (autonomous, multi-search):**
```
User message
  → Session state check (RAG conflict? search toggle on?)
  → Model receives message + tool schema
  → Model issues tool_use: web_search
  → QueryRewriter optimizes query
  → SearchCache check
  → SearchOrchestrator dispatches to backend
    (+ freshness filter + domain filter + safe search)
  → Results return to model as tool_result
  → Live progress updated in TUI
  → Model may issue another tool_use (loop, max 5)
  → Pre-synthesis preview shown
  → Model streams final response
  → Sources section appended
```

---

*Anythink — Think anything. Ask anything.*

*Version described: Enhanced Web Search — V3 Feature Expansion*
*Document last updated: June 2025*
