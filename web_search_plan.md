    ---
     Key Architectural Decisions

     1. No changes to BaseProvider — The AI tool-call loop is driven by SearchOrchestrator, which
     calls provider.stream_chat() with a small system-prompt tool-schema injection. No per-provider
     changes are needed.
     2. SearchFilter dataclass — Single object carries freshness, domain lists, safe-search, news mode,
     and max-results so the signature stays clean across all layers.
     3. Pure-Python semantic cache — SearchCache uses TF-IDF cosine similarity (no ML deps) at
     threshold 0.85 for near-duplicate query detection.
     4. Pre-synthesis preview pauses via asyncio.Event — _stream_response awaits user action
     (or auto-proceeds after search_preview_delay_s).
     5. RAG conflict = two-option prompt (spec §16) — "Continue with RAG only" silently suppresses
     search for the rest of the session; "Turn off web search" calls /search off immediately. No
     hybrid mode in this build.

     ---
     Phase 1 — Foundation: Extended Data Model + Four New Backends

     Goal: All six backends register via entry points; SearchResult and AppConfig carry the new
     fields. Every backend is independently testable with no TUI dependency.

     Files to Create

     - src/anythink/search/newsapi.py — NewsAPISearch (NewsAPI.org everything + top-headlines)
     - src/anythink/search/exa.py — ExaSearch (Exa Python SDK, semantic search)
     - src/anythink/search/google_cse.py — GoogleCSESearch (Google Custom Search JSON API)
     - src/anythink/search/bing.py — BingSearch (Bing Web Search API v7, supports news mode)

     Files to Modify

     - src/anythink/search/base.py
       - SearchResult: add published_date: str | None = None, source_domain: str | None = None
       - BaseSearchBackend: add class flags supports_freshness = False, supports_safe_search = False,
     supports_news = False; extend search() signature with optional date_from, date_to,
     safe_search, include_domains, exclude_domains params (backends silently ignore unsupported ones)
     - src/anythink/search/duckduckgo.py — forward new params where supported (DuckDuckGo has timelimit)
     - src/anythink/search/serpapi.py — forward tbs (freshness), as_sitesearch, safe params
     - src/anythink/config/schema.py — add 14 new AppConfig fields (see table below); keep
     web_search_enabled for backward compat but add search_default_enabled as the canonical field
     - src/anythink/config/manager.py
       - Add search_mode, search_safe_search to _ENUM_FIELDS
       - Add range validators for search_max_per_response (1–20), search_cache_ttl_minutes (1–1440),
     search_preview_delay_s (0.0–30.0)
       - Update load() / save() for all 13 persisted fields (all except search_enabled, which is
     session-only and lives only in ChatState)
     - pyproject.toml
       - 4 new entry points under anythink.search_backends
       - 4 new optional extras: [exa], [newsapi], [google-cse], [bing] (all just need httpx)

     New AppConfig Fields

     ┌───────────────────────────────┬────────────────────┬────────────┬───────────┐
     │             Field             │        Type        │  Default   │ Persisted │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_default_enabled        │ bool               │ False      │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_mode                   │ str                │ "general"  │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_max_per_response       │ int                │ 5          │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_query_rewrite          │ bool               │ True       │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_preview                │ bool               │ True       │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_preview_delay_s        │ float              │ 3.0        │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_cache_enabled          │ bool               │ True       │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_cache_ttl_minutes      │ int                │ 30         │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_safe_search            │ str                │ "moderate" │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_freshness              │ str | None         │ None       │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_include_domains        │ list[str]          │ []         │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_exclude_domains        │ list[str]          │ []         │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_max_page_chars         │ int                │ 15_000     │ Yes       │
     ├───────────────────────────────┼────────────────────┼────────────┼───────────┤
     │ search_enabled (session only) │ lives in ChatState │ False      │ No        │
     └───────────────────────────────┴────────────────────┴────────────┴───────────┘

     Verification

     from anythink.search.registry import SearchRegistry
     reg = SearchRegistry.from_entry_points(api_keys={"newsapi": "test", "bing": "test"})
     assert set(reg.names()) >= {"duckduckgo", "serpapi", "newsapi", "bing", "exa", "google_cse"}
     results = await reg.get("duckduckgo").search("python 3.13", max_results=3, date_from="2025-01-01")
     assert all(hasattr(r, "published_date") for r in results)

     ---
     Phase 2 — QueryRewriter and SearchCache

     Goal: Two pure-Python utility classes, fully testable without TUI or network access.

     Files to Create

     - src/anythink/search/rewriter.py — QueryRewriter
     - src/anythink/search/cache.py — SearchCache

     QueryRewriter (search/rewriter.py)

     class QueryRewriter:
         def __init__(self, provider: BaseProvider, model_id: str) -> None: ...
         async def rewrite(self, raw: str, history_context: str = "") -> str:
             # Sends 1-shot prompt to active LLM: "Output ONE concise search query only."
             # Wrapped in asyncio.wait_for(timeout=5.0) — returns raw on any failure.
             ...
         async def rewrite_multi(self, raw: str, history_context: str = "") -> list[str]:
             # For complex questions; returns 1–3 query strings.
             ...
     Uses provider.stream_chat() with a minimal system prompt. Collects the full response (no streaming
     display). Falls back to the original string on timeout or any exception.

     SearchCache (search/cache.py)

     @dataclass
     class _CacheEntry:
         results: list[SearchResult]
         query: str
         backend: str
         created_at: datetime

     class SearchCache:
         def __init__(self, ttl_minutes: int = 30, max_entries: int = 100) -> None: ...
         def get(self, query: str, backend: str) -> list[SearchResult] | None: ...
         def put(self, query: str, backend: str, results: list[SearchResult]) -> None: ...
         def evict_expired(self) -> int: ...
         def clear(self) -> None: ...
         def status(self) -> dict: ...      # {"entries": N, "oldest_age_s": X}
         def _semantic_match(self, query: str) -> _CacheEntry | None:
             # TF-IDF cosine at threshold 0.85 — pure Python, no ML deps
             ...

     Files to Modify

     - src/anythink/app/chat.py — add search_enabled: bool = False, search_mode: str = "general",
     _search_rag_conflict_acked: bool = False to ChatState; initialize search_enabled from
     config.search_default_enabled in _resolve_state()
     - src/anythink/app/context.py — add search_cache: SearchCache field; construct in
     AppContext.create() using config.search_cache_ttl_minutes

     Verification

     cache = SearchCache(ttl_minutes=30)
     fake = [SearchResult(title="T", url="u", snippet="s")]
     cache.put("python async", "duckduckgo", fake)
     assert cache.get("python async", "duckduckgo") is not None       # exact hit
     assert cache.get("python asyncio", "duckduckgo") is not None     # semantic hit
     assert cache.get("quantum physics", "duckduckgo") is None        # miss

     ---
     Phase 3 — SearchOrchestrator and News Mode Routing

     Goal: Single entry-point for all search logic; enforces max-search cap, routes news queries,
     deduplicates results, and streams progress via callback.

     Files to Create

     - src/anythink/search/orchestrator.py — SearchOrchestrator, OrchestratorResult

     Design

     @dataclass
     class OrchestratorResult:
         queries: list[str]
         results: list[SearchResult]
         from_cache: list[bool]
         backend_used: str
         elapsed_s: float

     class SearchOrchestrator:
         def __init__(
             self,
             registry: SearchRegistry,
             cache: SearchCache,
             *,
             preferred_backend: str = "duckduckgo",
             max_searches: int = 5,
         ) -> None: ...

         async def run(
             self,
             queries: list[str],
             *,
             date_from: str | None = None,
             date_to: str | None = None,
             safe_search: str = "moderate",
             include_domains: list[str] | None = None,
             exclude_domains: list[str] | None = None,
             news_mode: bool = False,
             progress_cb: Callable[[str], None] | None = None,
         ) -> OrchestratorResult: ...

         def _pick_backend(self, news_mode: bool) -> BaseSearchBackend | None:
             # news_mode=True: prefer newsapi → bing (news endpoint) → graceful error
             # news_mode=False: use preferred_backend → first available
             ...

         def _post_filter(self, results, include_domains, exclude_domains) -> list[SearchResult]: ...
         def _deduplicate(self, results: list[SearchResult]) -> list[SearchResult]: ...

     News backend selection: iterate ("newsapi", "bing") in order, return first available. If none,
     return a clear OrchestratorResult with 0 results and a descriptive error string in the first
     query slot (e.g. "ERROR: No news backend configured").

     Files to Modify

     - src/anythink/app/context.py — add search_orchestrator: SearchOrchestrator field; construct
     in AppContext.create() from search_registry, search_cache, and config

     Verification

     # Mock registry returning known results
     orchestrator = SearchOrchestrator(mock_registry, cache, max_searches=3)
     result = await orchestrator.run(["python 3.13", "asyncio changes"])
     assert len(result.queries) <= 3
     assert len({r.url for r in result.results}) == len(result.results)   # deduped

     ---
     Phase 4 — /search Command Namespace + HUD Mode Indicator

     Goal: Full /search command namespace; HUD shows ON, ON (news), or OFF; settings menu
     updated with new search settings rows.

     Files to Modify

     src/anythink/commands/handlers.py — Expand _search() to handle:
     - on / off / news / toggle / status — update ChatState; return action="search_hud_update"
     - <query> — run one-off search via orchestrator; format results as text
     - raw <query> — skip query rewriting (pass skip_rewrite=True flag in extra)
     - fresh 24h|7d|30d|3m|off / fresh custom <from> <to> — mutate config via replace()
     - include <domains…> / exclude <domains…> / filters / filters clear — domain lists
     - cache on|off|clear|status — toggle/clear search_cache
     - backends / backend use <name> / backend test <name> — registry introspection
     - settings — return action="open_search_settings" (TUI opens settings overlay)

     Also register /search news, /search fresh, /search include, /search exclude, /search cache,
     /search backends as sub-dispatched routes within the single _search handler.

     src/anythink/ui/hud.py — HUDWidget:
     - Add search_mode: reactive[str] = reactive("general")
     - Update update_from_state() to sync self.search_mode = state.search_mode
     - Update _line2() search block to show ON (news) when search_mode == "news"

     src/anythink/ui/textual/app.py — _dispatch_command():
     - Handle "search_hud_update" → self.query_one(HUDWidget).update_from_state(ctx, state)

     src/anythink/ui/textual/settings_menu.py — Add new rows to _SETTINGS:
     ("Search (default)", "search_default_enabled", ["on", "off"]),
     ("Search safe search", "search_safe_search", ["strict", "moderate", "off"]),
     ("Search cache enabled", "search_cache_enabled", ["on", "off"]),
     ("Search preview", "search_preview", ["on", "off"]),
     ("Search max/response", "search_max_per_response", None),   # numeric, ←→ nudges int

     Verification

     - /search on → HUD: 🔍 Search: ON
     - /search news → HUD: 🔍 Search: ON (news), state.search_mode == "news"
     - /search toggle twice → returns to original state
     - /search fresh 7d → ctx.config.search_freshness == "7d"
     - /settings shows new rows

     ---
     Phase 5 — Content Extraction Upgrades (browse/fetch.py)

     Goal: Raise the page-char cap to 15,000; add HTML table extraction; expand entity unescaping.
     This phase has no TUI dependency and is independently testable.

     Files to Modify

     src/anythink/browse/fetch.py:
     - _MAX_PAGE_CHARS: 8_000 → 15_000 (also honor config.search_max_page_chars when passed)
     - _strip_html(): add pre-processing step that converts <table>…</table> blocks to Markdown
     pipe tables before generic tag stripping. Process innermost tables first (handle nesting).
     Merged cells (colspan/rowspan) are repeated with [merged] suffix. Tables > 10 columns
     get abbreviated headers.
     - _strip_html(): expand named entity unescaping from 5 to full common set (em-dash, curly
     quotes, middle-dot, copyright, etc.)
     - BrowseFetcher.fetch_snippets(): accept new kwargs date_from, date_to, safe_search,
     include_domains, exclude_domains; forward them to registry.get_available() search call

     Verification

     html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
     result = _strip_html(html)
     assert "| A | B |" in result
     assert "| 1 | 2 |" in result

     # Entity test
     assert _strip_html("&mdash; &ldquo;hi&rdquo;") == "— \"hi\""

     ---
     Phase 6 — AI-Driven Search Loop (TUI _stream_response Wiring)

     Goal: Replace the simple backend.search(query) block in _stream_response with the full
     autonomous pipeline: rewrite → orchestrator → live progress → inject into history.

     Files to Modify

     src/anythink/ui/textual/app.py — Replace the # ── Web search ── block in _stream_response:

     if state.search_enabled and self._ctx.config.search_cache_enabled:
         ctx.search_cache.evict_expired()

     if state.search_enabled:
         progress_bubble = SystemBubble("Preparing search…", t, kind="search", config=ctx.config)
         conv.add_bubble(progress_bubble)

         # 1. Rewrite query
         raw_queries = [query]
         if ctx.config.search_query_rewrite:
             rewriter = QueryRewriter(state.provider_obj, state.model_id)
             raw_queries = await rewriter.rewrite_multi(query, _history_context(state))
             progress_bubble.set_message(f"Query rewritten: {raw_queries[0]!r}")

         # 2. Run orchestrator
         orch_result = await ctx.search_orchestrator.run(
             raw_queries,
             date_from=_freshness_to_date(ctx.config.search_freshness),
             safe_search=ctx.config.search_safe_search,
             include_domains=list(ctx.config.search_include_domains),
             exclude_domains=list(ctx.config.search_exclude_domains),
             news_mode=(state.search_mode == "news"),
             progress_cb=lambda msg: progress_bubble.set_message(msg),
         )

         # 3. Inject into history
         if orch_result.results:
             _inject_search_context(state, orch_result.results, query)
             progress_bubble.set_message(
                 f"Found {len(orch_result.results)} results · "
                 f"{orch_result.elapsed_s:.1f}s"
             )
         else:
             progress_bubble.set_message("No search results found.")

         # Pass results along for sources footer (Phase 7)
         _pending_search_results = orch_result.results

     Add private helper _inject_search_context(state, results, original_query) in app.py that
     formats results as a TextPart prefix and mutates state.history[-1].

     Also update app/chat.py ChatApp.run() (console path) to use the orchestrator instead of the
     direct backend.search() call.

     Verification

     - Enable search, send "What happened in AI today?" → see in-place progress bubble updates,
     then AI response referencing web content
     - With DuckDuckGo unavailable: graceful warning, no crash
     - With search_query_rewrite=False: orchestrator skips rewriter, uses original query

     ---
     Phase 7 — Sources Footer, Pre-Synthesis Preview, and RAG Conflict

     Goal: Deliver the three remaining visible UX features from the spec.

     Sub-phase 7A: Sources Footer in AIBubble

     src/anythink/ui/bubbles.py — AIBubble:
     - Add _search_results: list[SearchResult] = field(default_factory=list) and
     _sources_expanded: bool = False
     - Add attach_sources(results: list[SearchResult]) method (called from _stream_response)
     - Modify _redraw() to append sources footer when _search_results is non-empty:
       - Collapsed: 🔍 3 sources  [Tab to expand]
       - Expanded: full list with title, domain, date, URL per source
     - Add Tab key binding scoped to AIBubble that toggles _sources_expanded

     Sub-phase 7B: Pre-Synthesis Preview Panel

     New file: src/anythink/ui/textual/panels/search_preview_panel.py:
     class SearchPreviewPanel(Widget):
         class Decision(Message):
             synthesize: bool

         def show_results(self, results, queries, delay_s=3.0) -> None: ...
         def action_synthesize(self) -> None: ...
         def action_cancel(self) -> None: ...

     src/anythink/ui/textual/app.py:
     - Mount SearchPreviewPanel in compose() (hidden by default)
     - In _stream_response(), after orchestrator returns results and before history injection:
     if ctx.config.search_preview and orch_result.results:
         self._search_preview_event = asyncio.Event()
         self._search_preview_synthesize = True
         panel.show_results(orch_result.results, orch_result.queries, ctx.config.search_preview_delay_s)
         try:
             await asyncio.wait_for(self._search_preview_event.wait(), timeout=ctx.config.search_preview_delay_s + 1)
         except asyncio.TimeoutError:
             pass   # auto-proceed
         if not self._search_preview_synthesize:
             return   # user cancelled
     - Handle SearchPreviewPanel.Decision message to set/clear the event

     Sub-phase 7C: RAG + Web Search Conflict Detection

     src/anythink/ui/textual/app.py — At the top of _stream_response():
     if state.search_enabled and ctx.rag_manager.is_active and not state._search_rag_conflict_acked:
         self._pending_search_rag_conflict = True
         conv.add_bubble(SystemBubble(
             "RAG index is active. Web search is not used while a RAG index is loaded.\n"
             "  [Continue with RAG only]  — type 'rag'\n"
             "  [Turn off web search]    — type 'off'",
             t, kind="warning"
         ))
         state._search_rag_conflict_acked = True
         return

     Add _pending_search_rag_conflict: bool = False to __init__. Handle user response in
     on_input_area_submitted (add to the interactive-mode state flag chain). "rag" → set HUD
     to show Search: OFF (RAG active), suppress for session. "off" → call state.search_enabled = False.

     Verification

     - After a search turn: AI bubble has 🔍 3 sources [Tab to expand] at bottom
     - Tab toggles full source list
     - With search_preview=True: preview panel briefly appears before response; Cancel stops generation
     - With /rag on + /search on + first message → conflict prompt; both resolution paths work

     ---
     Phase 8 — Hardening, Keys, Diagnostics, and Tests

     Goal: Production-ready: keys wired for all 6 backends, full config validation, anythink doctor
     reports search status, test coverage to 80%+.

     Files to Modify

     - src/anythink/app/context.py — pass all 6 backend keys to SearchRegistry.from_entry_points():
     serpapi, exa, newsapi, bing, google_cse (DuckDuckGo needs no key)
     - src/anythink/config/manager.py — finalize all enum and range validators
     - src/anythink/diagnostics.py — add search backend status section to run_diagnostics():
     lists each backend with its availability status and missing-key hint

     New Test Files to Create

     - tests/search/test_base.py — SearchResult, BaseSearchBackend contract
     - tests/search/test_cache.py — TTL expiry, exact match, semantic match, eviction, status()
     - tests/search/test_rewriter.py — rewrite with mock provider, timeout fallback
     - tests/search/test_orchestrator.py — multi-query dedup, news routing, max-search cap, cache hit
     - tests/search/test_newsapi.py — pytest-httpx mocked HTTP responses
     - tests/search/test_exa.py — same
     - tests/search/test_bing.py — same
     - tests/search/test_google_cse.py — same
     - tests/test_config_search.py — config field round-trips, enum validation rejections

     Verification

     anythink doctor        # shows all 6 backends with status
     anythink keys add exa  # stores key
     pytest tests/search/ -v --cov=anythink.search --cov-fail-under=80
     ruff check src/
     mypy src/anythink

     ---
     Phase Summary

     ┌───────┬──────────────────────────────────┬──────────────────────────────────────────────────────────┬───────────────┐
     │ Phase │               Name               │                     Key Deliverable                      │  Dependency   │
     ├───────┼──────────────────────────────────┼──────────────────────────────────────────────────────────┼───────────────┤
     │ 1     │ Foundation                       │ 4 new backends + extended model + AppConfig fields       │ —             │
     ├───────┼──────────────────────────────────┼──────────────────────────────────────────────────────────┼───────────────┤
     │ 2     │ Cache + Rewriter                 │ SearchCache, QueryRewriter, ChatState search fields      │ Phase 1       │
     ├───────┼──────────────────────────────────┼──────────────────────────────────────────────────────────┼───────────────┤
     │ 3     │ Orchestrator                     │ SearchOrchestrator, news routing, dedup                  │ Phase 1, 2    │
     ├───────┼──────────────────────────────────┼──────────────────────────────────────────────────────────┼───────────────┤
     │ 4     │ /search command + HUD            │ Full command namespace, mode indicator, settings rows    │ Phase 2, 3    │
     ├───────┼──────────────────────────────────┼──────────────────────────────────────────────────────────┼───────────────┤
     │ 5     │ Content extraction               │ _strip_html tables, entity unescaping, 15K cap           │ Phase 1       │
     ├───────┼──────────────────────────────────┼──────────────────────────────────────────────────────────┼───────────────┤
     │ 6     │ TUI pipeline wiring              │ _stream_response uses orchestrator; live progress bubble │ Phase 3, 4, 5 │
     ├───────┼──────────────────────────────────┼──────────────────────────────────────────────────────────┼───────────────┤
     │ 7     │ UX: sources + preview + conflict │ Sources footer, preview panel, RAG conflict detection    │ Phase 6       │
     ├───────┼──────────────────────────────────┼──────────────────────────────────────────────────────────┼───────────────┤
     │ 8     │ Hardening                        │ Keys, diagnostics, full test coverage                    │ All           │
     └───────┴──────────────────────────────────┴──────────────────────────────────────────────────────────┴───────────────┘

     Phases 4 and 5 can be worked in parallel (neither depends on the other).

     ---
     Critical Files

     ┌────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────┐
     │                          File                          │                            Role                            │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/search/base.py                            │ Extended SearchResult + BaseSearchBackend capability flags │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/search/orchestrator.py                    │ New — core search loop                                     │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/search/rewriter.py                        │ New — LLM query rewriting                                  │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/search/cache.py                           │ New — TTL + semantic cache                                 │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/search/newsapi.py                         │ New backend                                                │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/search/exa.py                             │ New backend                                                │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/search/google_cse.py                      │ New backend                                                │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/search/bing.py                            │ New backend                                                │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/config/schema.py                          │ 14 new AppConfig fields                                    │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/config/manager.py                         │ Validation + load/save for new fields                      │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/app/chat.py                               │ ChatState search fields                                    │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/app/context.py                            │ search_cache, search_orchestrator in AppContext            │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/commands/handlers.py                      │ Full /search namespace                                     │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/ui/textual/app.py                         │ _stream_response wiring, conflict detection, preview panel │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/ui/hud.py                                 │ search_mode reactive + ON (news) display                   │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/ui/bubbles.py                             │ AIBubble sources footer                                    │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/ui/textual/settings_menu.py               │ New search settings rows                                   │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/ui/textual/panels/search_preview_panel.py │ New — pre-synthesis preview                                │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ src/anythink/browse/fetch.py                           │ 15K cap, table extraction, entity unescaping               │
     ├────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
     │ pyproject.toml                                         │ 4 new entry points + 4 new extras                          │
     └────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────┘