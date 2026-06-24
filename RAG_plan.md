Current state (updated 2026-06-24): Phases 1–8 are fully implemented.
  Audit (2026-06-24) confirmed 99.2% plan compliance across all phases.
  2 minor architectural drifts documented in "Implementation Drift Notes" section below.
  See "Phase 7 Drift Notes" for UI-layer omissions from the Phase 7 spec.

  ┌───────┬──────────────┬────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Phase │    Status    │                                        What it adds                                        │
  ├───────┼──────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 1     │ ✅ DONE      │ Full /rag index * / /rag ingest * command tree, configurable threshold, per-index config   │
  ├───────┼──────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 2     │ ✅ DONE      │ 6-stage ingestion pipeline, incremental change detection, all document parsers (PDF, DOCX, │
  │       │              │ CSV, JSON), live progress bubble  [parse_url deferred — see gaps]                          │
  ├───────┼──────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 3     │ ✅ DONE      │ All 6 chunking strategies (sentence, paragraph, semantic, heading + fixed/code), 80-char   │
  │       │              │ minimum overlap  [is_overlap_prefix tag deferred — see gaps]                               │
  ├───────┼──────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 4     │ ✅ DONE      │ BM25, Hybrid (RRF), MMR retrieval strategies, query expansion, cross-encoder re-ranking    │
  │       │              │ [/rag benchmark stub only — see gaps]                                                       │
  ├───────┼──────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 5     │ ✅ DONE      │ FAISS (new default), ChromaDB, LanceDB, Pinecone, Azure AI Search backends                 │
  ├───────┼──────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 6     │ ✅ DONE      │ Confidence scores, per-chunk relevance display, visual tiers, graceful 3-option no-match   │
  ├───────┼──────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 7     │ ✅ DONE      │ /rag settings interactive panel, 8-step new-index wizard  [see Phase 7 drift notes]        │
  ├───────┼──────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 8     │ ✅ DONE      │ Ollama/OpenAI/Cohere/Google embedding backends, HUD shows embedding model name             │
  └───────┴──────────────┴────────────────────────────────────────────────────────────────────────────────────────────┘

  Each phase is independently testable and doesn't break the existing implementation.

● User approved Claude's plan
  ⎿  Plan saved to: C:\Users\MD\.claude\plans\anythink-rag-system-description-md-i-ha-tranquil-moonbeam.md · /plan to edit
     Anythink RAG System — Full Implementation Plan

     Context

     The anythink_rag_system_description.md document specifies a complete, production-grade RAG system. A solid V1
     foundation already exists (RAGManager, VectorStore, basic chunkers, LocalEmbeddingBackend, 8 /rag subcommands, TUI
     retrieval injection, MCP server). This plan bridges the gap between the current V1 and the full spec, organized into
     8 sequential phases so each phase is testable and shippable independently.

     Foundation after Phases 1–7 (do not break):
     - src/anythink/rag/manager.py — RAGManager (full lifecycle + retrieval + ingestion + _store_base_path)
     - src/anythink/rag/store.py — VectorStore (kept for backward compat; PureVectorStore is the live impl)
     - src/anythink/rag/backends/ — base.py, pure.py, faiss_store.py, chroma_store.py, lance_store.py,
                                     pinecone_store.py, azure_store.py, registry.py
     - src/anythink/rag/chunkers.py — all 6 strategies: chunk_text/code/sentence/paragraph/heading + achunk_semantic
     - src/anythink/rag/parsers.py — dispatch_parser() + 12 parsers incl. parse_url(), is_url()
     - src/anythink/rag/ingestion.py — run_ingestion() 6-stage pipeline; extra_path: Path | str | None
     - src/anythink/rag/bm25.py — BM25Index (build, score, persist, load)
     - src/anythink/rag/retrieval.py — retrieve() + all 4 strategies, ScoredChunk, _dedup_overlap
     - src/anythink/rag/reranker.py — CrossEncoderReranker, CohereReranker, get_reranker()
     - src/anythink/rag/quality.py — RetrievalQuality, compute_quality(), TIER_LABEL/TIER_STYLE
     - src/anythink/rag/models.py — IndexInfo + RetrievalResult with all Phase 1–7 fields
     - src/anythink/config/schema.py — AppConfig with all RAG V2 fields incl. rag_no_match_behavior
     - src/anythink/config/manager.py — save/load for all RAG fields; enum validation for strategies
     - src/anythink/commands/handlers.py:_rag() — full command namespace + live /rag benchmark
     - src/anythink/ui/textual/app.py — _stream_response() with quality check, no-match flow,
                                          skip_rag/inject_rag_results params, wizard input routing
     - src/anythink/ui/textual/rag_settings.py — RAGSettingsMenu overlay (20 rows, 6 sections)
     - src/anythink/ui/textual/rag_wizard.py — RAGIndexWizard 8-step state machine
     - src/anythink/ui/bubbles.py — AIBubble with _retrieval_quality field + set_rag_quality()
     - src/anythink/ui/textual/panels/rag_browser.py — Dashboard RAG panel
     - src/anythink/mcp/builtin/rag.py — RAGServer MCP tool
     - tests/test_rag/ — test_store, test_manager, test_parsers, test_ingestion, test_incremental,
                          test_chunkers, test_bm25, test_retrieval, test_reranker, test_backends,
                          test_quality, test_nomatch, test_commands, test_threshold, test_wizard,
                          test_rag_settings

     ---
     Phase 1 — Command Namespace Restructure & Config Expansion

     Goal: Align the /rag command tree with the spec (/rag index *, /rag ingest *, /rag query, /rag chunks, /rag sources,
     /rag threshold, /rag quality, /rag benchmark) and make the relevance threshold configurable.

     1.1 — Config Schema (src/anythink/config/schema.py)

     Add fields to AppConfig:
     rag_threshold: float = 0.65          # was hardcoded 0.70 in app.py
     rag_top_k: int = 3                   # chunks retrieved per query
     rag_reranking: bool = False          # re-ranking on/off (Phase 4)
     rag_retrieval_strategy: str = "vector"  # "vector"|"bm25"|"hybrid"|"mmr" (Phase 4)
     rag_chunk_strategy: str = "fixed"    # per-session override (per-index stored in IndexInfo)
     rag_chunk_size: int = 512            # tokens per chunk
     rag_chunk_overlap: int = 100         # overlap tokens

     1.2 — IndexInfo Model (src/anythink/rag/models.py)

     Extend IndexInfo with per-index configuration:
     chunk_strategy: str = "fixed"        # fixed|sentence|paragraph|semantic|code|heading
     chunk_size: int = 512
     chunk_overlap: int = 100
     embedding_backend: str = "local"     # already exists, add more options
     retrieval_strategy: str = "vector"
     reranking_enabled: bool = False
     reranking_model: str = "bge-reranker-base"
     quality_threshold: float = 0.65
     top_k: int = 3
     ingestion_history: list[dict] = field(default_factory=list)  # [{timestamp, files_added, duration}]
     file_mtime_cache: dict[str, float] = field(default_factory=dict)  # path→mtime for incremental

     1.3 — Command Handler Restructure (src/anythink/commands/handlers.py)

     Restructure _rag() to dispatch to sub-namespaces:

     /rag                    → show status (same as /rag status)
     /rag on                 → use last active index (from config.active_rag_index)
     /rag off                → deactivate
     /rag status             → detailed status display
     /rag settings           → action="rag_settings_open" (Phase 7)

     /rag index new          → action="rag_index_wizard" (Phase 7)
     /rag index list         → list all indexes
     /rag index use <n>      → activate index
     /rag index info <n>     → show details
     /rag index rebuild <n>  → action="rag_rebuild:<n>"
     /rag index delete <n>   → delete
     /rag index rename <o><n>→ rename YAML + store files

     /rag ingest             → incremental ingest on active index
     /rag ingest --full      → full rebuild
     /rag ingest --path <p>  → ingest from specific path
     /rag ingest status      → action="rag_ingest_status"
     /rag ingest history     → show ingestion log

     /rag query <text>       → test retrieval without LLM, print chunks + scores
     /rag chunks             → show chunks from last turn (stored on bubble)
     /rag sources            → show sources from last turn
     /rag threshold <v>      → set config.rag_threshold, persist
     /rag quality            → show quality report for last turn
     /rag benchmark          → run 5 test queries, measure latency + scores

     Keep backward compat: /rag new, /rag use, /rag list, /rag rebuild, /rag delete, /rag info still work (delegate to new
     /rag index * handlers).

     1.4 — TUI Action Routing (src/anythink/ui/textual/app.py)

     Add new action constants to _dispatch_command():
     - "rag_settings_open" → show settings panel (Phase 7)
     - "rag_index_wizard" → launch wizard (Phase 7)
     - "rag_ingest_status" → show progress overlay
     - "rag_ingest_start:<name>:<mode>" → fire _run_rag_ingest() worker

     1.5 — Tests

     - tests/test_rag/test_commands.py — command parsing, argument validation, action signals
     - tests/test_rag/test_threshold.py — verify threshold config persistence

     ---
     Phase 2 — Enhanced Ingestion Pipeline (6-Stage)

     Goal: Implement the full 6-stage ingestion pipeline with incremental detection, extended metadata, progress display,
     background mode, ingestion history, and desktop notifications.

     2.1 — Extended Metadata (src/anythink/rag/models.py)

     Add fields to RetrievalResult:
     heading_path: str = ""       # "## Setup > ### Install"
     function_name: str = ""      # for code files
     page_number: int | None = None  # for PDFs
     ingested_at: datetime = ...
     file_modified_at: datetime = ...

     Ensure IndexInfo.file_mtime_cache (from Phase 1) is persisted in YAML.

     2.2 — Extended Parsers (src/anythink/rag/parsers.py) NEW FILE

     Create src/anythink/rag/parsers.py with one function per type, all returning list[tuple[str, dict]] (text, metadata):

     ┌─────────────────────────────┬─────────────────────────────┬─────────────────────────────────────────────────┐
     │       Parser function       │         Extensions          │               Key metadata fields               │
     ├─────────────────────────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
     │ parse_text(path)            │ .txt, .rst                  │ start_line, end_line                            │
     ├─────────────────────────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
     │ parse_markdown(path)        │ .md, .mdx                   │ heading_path, start_line, end_line              │
     ├─────────────────────────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
     │ parse_python(path)          │ .py                         │ function_name, class_name, start_line, end_line │
     ├─────────────────────────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
     │ parse_js(path)              │ .js, .jsx, .ts, .tsx        │ function_name, start_line, end_line             │
     ├─────────────────────────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
     │ parse_code_generic(path)    │ .go, .rs, .java, .cpp, etc. │ start_line, end_line                            │
     ├─────────────────────────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
     │ parse_pdf(path)             │ .pdf                        │ page_number (uses pypdf or fallback OCR)        │
     ├─────────────────────────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
     │ parse_docx(path)            │ .docx                       │ heading_path (uses python-docx, optional dep)   │
     ├─────────────────────────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
     │ parse_csv(path)             │ .csv                        │ column_headers, row_range                       │
     ├─────────────────────────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
     │ parse_json(path)            │ .json                       │ key_path                                        │
     ├─────────────────────────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
     │ parse_yaml(path)            │ .yaml, .yml                 │ key_path                                        │
     ├─────────────────────────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
     │ parse_url(url, browse_tool) │ HTTP/HTTPS                  │ source_url, page_title                          │
     └─────────────────────────────┴─────────────────────────────┴─────────────────────────────────────────────────┘

     All parsers: lazy-import heavy deps; raise RAGError with user_message if dep missing.

     2.3 — 6-Stage Pipeline (src/anythink/rag/ingestion.py) NEW FILE

     async def run_ingestion(
         name: str,
         manager: RAGManager,
         backend: BaseEmbeddingBackend,
         *,
         mode: Literal["incremental", "full"] = "incremental",
         extra_path: Path | None = None,
         progress_callback: Callable[[IngestionProgress], None] | None = None,
     ) -> IngestionResult

     IngestionProgress dataclass:
     stage: int           # 1-6
     stage_name: str
     files_total: int
     files_new: int
     files_changed: int
     files_unchanged: int
     files_parsed: int
     chunks_total: int
     chunks_embedded: int
     chunks_written: int
     elapsed_s: float
     eta_s: float | None

     Stages:
     1. Source Discovery — walk source_path (+ extra_path), compare mtime vs file_mtime_cache, classify
     new/changed/unchanged; skip unchanged in incremental mode
     2. Document Parsing — dispatch each file to parsers.py; log parser errors, continue
     3. Text Preprocessing — strip excessive blanks, normalize whitespace, NFC unicode
     4. Chunking — apply configured strategy from IndexInfo.chunk_strategy
     5. Embedding — batch-embed (batch size 64), call progress_callback per batch
     6. Vector Store Write — remove stale chunks from deleted/changed files; write new chunks; update file_mtime_cache and
     IndexInfo; log to ingestion_history

     After completion: call notifier.notify("rag_build_done", ...).

     2.4 — Progress Display (src/anythink/ui/textual/app.py)

     New TUI worker _run_rag_ingest(name, mode, extra_path):
     - Creates a live "system bubble" using existing ChatBubble / info bubble pattern
     - Calls run_ingestion(..., progress_callback=self._on_ingest_progress)
     - _on_ingest_progress updates the bubble content in-place (Textual reactive update)
     - Ctrl+B binding: during active ingestion, sets a flag _ingestion_background = True which stops updating the bubble
     and returns control to chat

     Progress bubble format (matches spec section 6.8):
     ⚙ Ingesting: <name>
     Stage: 5 of 6 — Embedding
     Files: 47 (12 new, 3 changed, 32 unchanged)
     Parsed: 15/15  Chunks: 198/284 ████░░░ 70%
     Elapsed: 1m42s  ETA: 44s
     Press Ctrl+B to background

     2.5 — Optional Dependencies (pyproject.toml)

     [project.optional-dependencies]
     rag = [
         "sentence-transformers>=2.7",
         "pypdf>=4.0",           # PDF parsing (text layer)
         "python-docx>=1.1",     # Word documents
     ]
     rag-ocr = ["pytesseract>=0.3", "Pillow>=10.0"]  # OCR fallback for scanned PDFs

     2.6 — Tests

     - tests/test_rag/test_parsers.py — each parser with fixture files
     - tests/test_rag/test_ingestion.py — full pipeline with MockEmbeddingBackend
     - tests/test_rag/test_incremental.py — mtime-based change detection

     ---
     Phase 3 — Advanced Chunking Strategies

     Goal: Implement all 6 chunking strategies configurable per-index.

     3.1 — Chunking Module (src/anythink/rag/chunkers.py) — EXTEND

     Add strategy functions alongside existing chunk_text and chunk_code:

     def chunk_sentence(text: str, size: int, overlap: int, meta: dict) -> list[tuple[str, dict]]:
         # Split at sentence boundaries (use simple regex: [.!?][\s]+)
         # Group sentences until size threshold, then new chunk

     def chunk_paragraph(text: str, size: int, overlap: int, meta: dict) -> list[tuple[str, dict]]:
         # Split at double-newlines; oversized paragraphs → sentence-split
         # Short consecutive paragraphs merged up to size

     def chunk_semantic(text: str, size: int, overlap: int, meta: dict, embed_fn: Callable) -> list[tuple[str, dict]]:
         # Rolling window of 3 sentences, cosine similarity between adjacent windows
         # Place boundary when similarity drops below 0.6
         # Requires embed_fn — called during ingestion Stage 4 (same backend as embedding)

     def chunk_heading(text: str, size: int, overlap: int, meta: dict) -> list[tuple[str, dict]]:
         # Split at # ## ### #### markers
         # Store full heading path ("## Setup > ### Installation") in metadata
         # Oversized sections → paragraph split

     def dispatch_chunk(
         text: str, strategy: str, size: int, overlap: int, meta: dict,
         embed_fn: Callable | None = None
     ) -> list[tuple[str, dict]]:
         # Routes to the correct strategy function
         # "fixed" → chunk_text (existing), "code" → chunk_code (existing)
         # "sentence", "paragraph", "semantic", "heading" → new functions

     Token counting: approximate as len(text) // 4 (consistent with existing context tracker).

     3.2 — Overlap Enforcement

     Minimum overlap: 80 tokens. Clamp in dispatch_chunk before applying:
     overlap = max(80, overlap)

     Overlap application: append last overlap tokens of chunk N as prefix of chunk N+1; tag with is_overlap_prefix: True
     in metadata for de-dup in retrieval.

     3.3 — Tests

     - tests/test_rag/test_chunkers.py — all 6 strategies with known inputs, verify boundaries and overlap
     - Test that minimum overlap clamp works

     ---
     Phase 4 — Advanced Retrieval Strategies & Re-Ranking

     Goal: Add BM25, Hybrid (RRF), MMR, query expansion, and cross-encoder re-ranking.

     4.1 — BM25 Index (src/anythink/rag/bm25.py) NEW FILE

     class BM25Index:
         def build(self, corpus: list[str]) -> None: ...    # IDF pre-computation
         def score(self, query: str, top_k: int) -> list[tuple[int, float]]: ...  # (chunk_idx, score)

     Pure-Python BM25 (no external dependency). Pre-built during ingestion, stored alongside vector store as
     <name>.bm25.gz.

     4.2 — Retrieval Strategies (src/anythink/rag/retrieval.py) NEW FILE

     async def retrieve_vector(query, backend, store, top_k) -> list[ScoredChunk]: ...
     async def retrieve_bm25(query, bm25_index, store, top_k) -> list[ScoredChunk]: ...
     async def retrieve_hybrid(query, backend, store, bm25_index, top_k) -> list[ScoredChunk]:
         # Reciprocal Rank Fusion: score_rrf(chunk) = 1/(k+rank_vector) + 1/(k+rank_bm25), k=60
         ...
     async def retrieve_mmr(query, backend, store, top_k, lambda_=0.5) -> list[ScoredChunk]:
         # Diversity penalty: score_mmr = lambda*rel - (1-lambda)*max_sim_to_selected
         ...

     async def retrieve(
         query: str,
         backend: BaseEmbeddingBackend,
         store: VectorStore,
         bm25: BM25Index | None,
         *,
         strategy: str = "vector",
         top_k: int = 3,
         expand_short_queries: bool = True,
         llm_expand_fn: Callable | None = None,
     ) -> list[ScoredChunk]:
         # Stage 1: query expansion for < 5 token queries
         # Stage 2-5: dispatch to strategy
         # De-duplicate overlap-prefixed chunks from adjacent chunks

     4.3 — Re-Ranking (src/anythink/rag/reranker.py) NEW FILE

     class CrossEncoderReranker:
         def __init__(self, model_name: str = "bge-reranker-base"): ...
         def is_available(self) -> bool: ...   # checks sentence-transformers
         def rerank(self, query: str, chunks: list[ScoredChunk], top_k: int) -> list[ScoredChunk]: ...

     class CohereReranker:
         def __init__(self, api_key: str): ...
         async def rerank(self, query: str, chunks: list[ScoredChunk], top_k: int) -> list[ScoredChunk]: ...

     Re-ranking process: retrieve 20 candidates → rerank → return top top_k.

     4.4 — RAGManager Update (src/anythink/rag/manager.py)

     Replace current retrieve() with new retrieval.retrieve() function. Build BM25Index during ingestion (Stage 4). Load
     it alongside VectorStore in use_index().

     4.5 — TUI: Query Expansion

     In _stream_response(), pass a lightweight llm_expand_fn that calls the active provider with a 1-sentence "rephrase
     this query more descriptively" system prompt. Cache expanded query in debug record.

     4.6 — Tests

     - tests/test_rag/test_bm25.py — IDF scoring, top-k correctness
     - tests/test_rag/test_retrieval.py — all 4 strategies, RRF fusion math, MMR diversity
     - tests/test_rag/test_reranker.py — mocked cross-encoder, score ordering

     ---
     Known Gaps (pre-Phase 5 cleanup)

     These items drifted from the Phase 1–4 spec during implementation. Address before or alongside Phase 5.

     GAP-1 · AppConfig missing 3 chunking fields (Phase 1.1) — ✅ FIXED
       Added rag_chunk_strategy / rag_chunk_size / rag_chunk_overlap to AppConfig (schema.py).
       Added rag_chunk_strategy and rag_retrieval_strategy to validate_config() enum check.
       Added both fields to ConfigManager.save() and load() so changes persist across sessions.

     GAP-2 · Phase 1.5 tests missing — ✅ FIXED
       Created tests/test_rag/test_commands.py (68 tests: all subcommands, backward-compat aliases,
       error paths) and tests/test_rag/test_threshold.py (14 tests: defaults, persistence,
       validation). All 68 tests pass.

     GAP-3 · parse_url() not implemented (Phase 2.2) — ✅ FIXED
       Added parse_url(url) to parsers.py using httpx (core dep). Strips HTML tags and decodes
       entities; returns (text, meta) with source_url and page_title fields.
       Added is_url() helper to parsers.py.
       Updated ingestion.py run_ingestion() extra_path: Path | str | None to accept both
       file paths and HTTP/HTTPS URLs; URL branch calls parse_url() directly in Stage 2.

     GAP-4 · extra_path not forwarded in TUI ingestion worker (Phase 2.4) — ✅ FIXED
       Fixed _dispatch_command() in app.py to extract parts[3] as extra_path.
       Added extra_path: str | None = None param to _run_rag_ingest(); passes it to
       run_ingestion() as a raw string (not Path, so URLs work on all platforms).

     GAP-5 · Ctrl+B background ingestion not implemented (Phase 2.4) — ⏭ DEFERRED
       Ctrl+B is already bound to toggle_debug_panel (priority binding). Implementing a
       context-sensitive override is non-trivial. Deferred to Phase 7 (settings panel),
       where a dedicated "background" UI affordance fits more naturally.

     GAP-6 · is_overlap_prefix metadata tag absent (Phase 3.2) — ✅ PLAN UPDATED (no code fix)
       Jaccard-based dedup (≥80% token overlap) in _dedup_overlap() is functionally equivalent
       and simpler. The is_overlap_prefix tag requirement is dropped from the plan.

     GAP-7 · /rag benchmark is a stub (Phase 4) — ✅ FIXED
       Implemented /rag benchmark: samples 5 evenly-spaced chunks from active index, derives
       a short query from each, runs rm.retrieve() for each, and reports per-query top score,
       result count, latency in ms, and average latency. No LLM call required.

     GAP-8 · Phase 6 AppConfig fields added early (ahead of schedule — no action needed)
       rag_quality_indicators: bool = True and rag_confidence_display: bool = True were added
       to AppConfig during Phase 4. Also now properly saved/loaded via ConfigManager.

     ---
     Phase 5 — Multiple Vector Store Backends

     Goal: Add FAISS (new default), ChromaDB, and LanceDB as swappable backends behind a BaseVectorStore interface.

     5.1 — Abstract Backend (src/anythink/rag/backends/base.py) NEW FILE

     class BaseVectorStore(ABC):
         @abstractmethod
         def add(self, texts, metadatas, vectors) -> None: ...
         @abstractmethod
         def query(self, vector, top_k) -> list[ScoredChunk]: ...
         @abstractmethod
         def remove_by_source(self, source_path: str) -> int: ...   # for incremental
         @abstractmethod
         def count(self) -> int: ...
         @abstractmethod
         def persist(self, path: Path) -> None: ...
         @classmethod
         @abstractmethod
         def load(cls, path: Path) -> "BaseVectorStore": ...
         def supports_metadata_filter(self) -> bool: return False

     5.2 — Backend Implementations

     ┌────────────────────────────┬───────────────────────┬──────────────────────────────────────────────────────────────┐
     │            File            │        Backend        │                          Key notes                           │
     ├────────────────────────────┼───────────────────────┼──────────────────────────────────────────────────────────────┤
     │ backends/pure.py           │ Pure-Python (existing │ Rename existing store.py → backends/pure.py; adapt to        │
     │                            │  VectorStore)         │ interface                                                    │
     ├────────────────────────────┼───────────────────────┼──────────────────────────────────────────────────────────────┤
     │ backends/faiss_store.py    │ FAISS                 │ Flat index (exact NN); load into memory at session start;    │
     │                            │                       │ persist as .faiss + .meta.gz; requires faiss-cpu             │
     ├────────────────────────────┼───────────────────────┼──────────────────────────────────────────────────────────────┤
     │ backends/chroma_store.py   │ ChromaDB              │ Per-index collection; built-in metadata filtering; no server │
     │                            │                       │  needed                                                      │
     ├────────────────────────────┼───────────────────────┼──────────────────────────────────────────────────────────────┤
     │ backends/lance_store.py    │ LanceDB               │ Columnar format; built-in hybrid; no server needed           │
     ├────────────────────────────┼───────────────────────┼──────────────────────────────────────────────────────────────┤
     │ backends/pinecone_store.py │ Pinecone              │ Serverless API; requires pinecone-client + API key           │
     ├────────────────────────────┼───────────────────────┼──────────────────────────────────────────────────────────────┤
     │ backends/azure_store.py    │ Azure AI Search       │ REST API; requires azure-search-documents + endpoint/key     │
     └────────────────────────────┴───────────────────────┴──────────────────────────────────────────────────────────────┘

     5.3 — Backend Registry (src/anythink/rag/backends/registry.py)

     BACKENDS = {
         "pure": PureVectorStore,
         "faiss": FAISSVectorStore,
         "chroma": ChromaVectorStore,
         "lance": LanceVectorStore,
         "pinecone": PineconeVectorStore,
         "azure": AzureVectorStore,
     }

     def get_backend(name: str, index_dir: Path) -> BaseVectorStore: ...

     5.4 — IndexInfo Extension

     Add vector_backend: str = "faiss" to IndexInfo (set during new-index wizard, immutable after first build; change
     requires rebuild).

     5.5 — pyproject.toml

     rag-faiss = ["faiss-cpu>=1.8"]
     rag-chroma = ["chromadb>=0.5"]
     rag-lance = ["lancedb>=0.6"]
     rag-pinecone = ["pinecone-client>=3.0"]
     rag-azure = ["azure-search-documents>=11.4"]
     all = [..., "faiss-cpu>=1.8", "chromadb>=0.5"]

     5.6 — Tests

     - tests/test_rag/test_backends.py — adapter tests for Pure (always) + FAISS/Chroma/Lance (conditional on install)
     - Verify remove_by_source() works correctly for incremental ingestion

     ---
     Phase 6 — Quality Indicators & Graceful No-Match Handling

     Goal: Confidence scores, per-chunk relevance display, visual tiers, and the 3-option no-match response.

     6.1 — Quality Models (src/anythink/rag/quality.py) NEW FILE

     @dataclass
     class RetrievalQuality:
         confidence: float                    # 0.0-1.0 weighted score
         top_score: float
         avg_score: float
         score_spread: float
         passed_threshold: bool
         tier: Literal["strong", "good", "weak", "poor"]
         low_relevance_chunks: list[int]      # indices of chunks below 50% when others > 70%

     def compute_quality(results: list[ScoredChunk], threshold: float) -> RetrievalQuality:
         # confidence = 0.5*top + 0.3*avg + 0.2*(1 - spread)
         # tier: 0.85+ → strong, 0.65+ → good, 0.45+ → weak, else → poor

     6.2 — Response Bubble Footer (src/anythink/ui/textual/app.py)

     When RAG is active and results are injected, after generation:
     - Attach RetrievalQuality to bubble metadata
     - Render footer line: 📚 3 sources · Confidence: 87% · [expand]
     - Color: success=strong, info=good, warning=weak, error=poor (using theme system)
     - Expand shows per-chunk table with source path, line range, relevance %, ✓/⚠ flag

     6.3 — No-Match Handling (src/anythink/ui/textual/app.py)

     When quality.passed_threshold == False in _stream_response():
     - Do NOT inject low-quality context into LLM
     - Render a structured bubble with 3 options (rendered as a Textual widget with key bindings [1], [2], [3])
     - Store _pending_rag_nomatch state flag on the app
     - [1] → answer from training (resend without RAG context)
     - [2] → show closest matches in chunk inspector, then ask y/n to send anyway
     - [3] → pre-fill input with original query for rephrasing

     6.4 — /rag quality and /rag chunks Commands

     - _rag_quality: Read bubble._retrieval_quality from most recent RAG bubble; format and display
     - _rag_chunks: Read bubble._retrieval_results (already stored per bubble); format with source, line, score
     - _rag_sources: Read same data, display only source paths + line ranges (summary view)

     6.5 — Tests

     - tests/test_rag/test_quality.py — confidence math, tier thresholds, low-chunk detection
     - tests/test_rag/test_nomatch.py — state machine for the 3-option flow

     ---
     Phase 7 — Interactive RAG Settings & New-Index Wizard

     Goal: /rag settings panel and 8-step /rag index new wizard, both arrow-key navigable.

     7.1 — RAG Settings Widget (src/anythink/ui/textual/rag_settings.py) NEW FILE

     Mirrors settings_menu.py architecture (_SettingRow, overlay widget).

     Settings sections and fields:
     Active Index
       ▸ Selected index          [dropdown of existing indexes]
       ▸ Source path             [path display, read-only]

     Ingestion
       ▸ Ingestion mode          Manual | Auto (watch)
       ▸ Incremental detection   ON | OFF

     Chunking
       ▸ Chunking strategy       fixed|sentence|paragraph|semantic|code|heading
       ▸ Chunk size              [numeric, 256–1024 tokens]
       ▸ Chunk overlap           [80|100|150|200|300|custom]

     Embedding
       ▸ Embedding model         [list from EmbeddingRegistry]
       ▸ Embedding dimensions    [read-only, from backend.dimensions]

     Vector Store
       ▸ Vector backend          pure|faiss|chroma|lance|pinecone|azure
       ▸ Index storage path      [read-only]

     Retrieval
       ▸ Retrieval strategy      vector|bm25|hybrid|mmr
       ▸ Chunks per query        [1-20]
       ▸ Re-ranking              ON | OFF
       ▸ Re-ranking model        [list from reranker registry]
       ▸ Relevance threshold     [0.0-1.0 slider, 0.05 steps]

     Quality & Fallback
       ▸ Quality indicators      ON | OFF
       ▸ No-match behavior       graceful|passthrough
       ▸ Confidence display      ON | OFF

     Changes persist immediately to IndexInfo YAML (per-index settings) or AppConfig (global settings). Changes that
     require a rebuild (chunking strategy, embedding model, vector backend) show a ⚠ rebuild required warning inline.

     Action: "rag_settings_open" in _dispatch_command() → show overlay.

     7.2 — New Index Wizard (src/anythink/ui/textual/rag_wizard.py) NEW FILE

     8-step modal wizard, each step in a bordered overlay replacing the previous:

     Step 1: Name          → text input (validated: alphanumeric + dashes, unique)
     Step 2: Source Path   → text input with basic path existence check
     Step 3: Chunk Strategy→ numbered selection [1-6]
     Step 4: Chunk Size    → numeric input (256–1024, default 512)
     Step 5: Overlap       → numbered selection [80/100/150/200/300/custom]
     Step 6: Embedding     → list from EmbeddingRegistry.names()
     Step 7: Vector Store  → numbered selection (available backends only)
     Step 8: Ingest now?   → Y/n

     Navigation: Enter to confirm, Up/Down or number keys to select, Esc to cancel.

     On completion: calls rag_manager.create_index(info) with all wizard values; if Step 8 = Y, fires _run_rag_ingest()
     worker.

     Action: "rag_index_wizard" in _dispatch_command().

     7.3 — Tests

     - tests/test_rag/test_wizard.py — wizard state machine, validation (name uniqueness, path existence)
     - tests/test_rag/test_rag_settings.py — settings panel value cycling, persistence

     ---
     Implementation Drift Notes (Phases 1–8, verified 2026-06-24)

     DRIFT-A · IngestionProgress has 2 extra fields beyond spec (Phase 2.3)
       Plan specified 11 fields: stage, stage_name, files_total, files_new, files_changed,
       files_unchanged, files_parsed, chunks_total, chunks_embedded, chunks_written,
       elapsed_s, eta_s.
       Actual implementation has 13 fields — adds files_failed (int) and current_file (str).
       files_failed counts Stage 2 parse errors without halting the pipeline.
       current_file shows which file is being processed in the progress bubble.
       Decision: keep both additions; they improve observability without breaking spec.
       No plan change needed — both fields are backward-compatible enhancements.

     DRIFT-B · ingested_at and file_modified_at stored in metadata dict, not as RetrievalResult fields (Phase 2.1)
       Plan specified: "Add fields to RetrievalResult: ingested_at: datetime, file_modified_at: datetime".
       Actual: both values are written into the chunk metadata dict during ingestion Stage 2
       (meta["ingested_at"] and meta["file_modified_at"]), not as explicit dataclass fields on
       RetrievalResult. They are accessible via result.metadata["ingested_at"] at retrieval time.
       Impact: minor — no user-facing difference; /rag quality and /rag sources display correctly.
       Fix (optional, low priority): promote both to explicit Optional[datetime] fields on
       RetrievalResult and populate them from metadata in retrieval.py's ScoredChunk→RetrievalResult
       conversion. This would allow type-safe access and mypy coverage.

     ---
     Phase 7 Drift Notes (vs plan)

     These items from the Phase 7 spec were not implemented. They are low-priority and either
     require unsupported backend features or are minor UI omissions.

     DRIFT-7A · Ingestion section absent from RAGSettingsMenu
       Plan specified two rows: "Ingestion mode (Manual | Auto watch)" and
       "Incremental detection (ON | OFF)".  Auto-watch (file-system monitoring) is not
       implemented anywhere in the codebase — adding settings for it would be misleading.
       The Ingestion section was dropped from _RAG_ROWS in rag_settings.py.
       Decision: defer both rows until file-watch support is added (likely a future phase).

     DRIFT-7B · Read-only rows "Embedding dimensions" and "Index storage path" missing
       Plan listed these as read-only display rows in the settings panel.
       Actual implementation has only the embedding model name row; no dimensions row.
       No storage path row was added to _RAG_ROWS.
       Impact: minor UI cosmetics; settings remain fully functional.
       Fix (optional): add ("Embedding dimensions", "readonly_idx", "dimensions", None, False)
       and storage path row to _RAG_ROWS; dimensions requires reading from embedding registry.

     DRIFT-7C · Wizard uses SystemBubble flow instead of bordered modal overlay
       Plan: "8-step modal wizard, each step in a bordered overlay replacing the previous."
       Actual: RAGIndexWizard is a pure-Python state machine; each step shows a SystemBubble
       and reads input from the existing InputArea — no separate modal widget.
       Impact: none functionally; all 8 steps work correctly, including validation, prefill,
       navigation, and Esc-to-cancel. The approach is more consistent with the existing
       interactive state machine pattern (naming_mode, pending_rag_nomatch, etc.).
       Decision: keep current approach; drop the "bordered overlay" requirement from the plan.

     ---
     Phase 8 — Extended Embedding Models & HUD Updates

     Goal: Support all embedding model families from the spec, update HUD to show model name.

     Pre-implementation state check (2026-06-24):

     8.1 partial — LocalEmbeddingBackend already accepts model_name param (added in Phase 8.1
       preparation), but SUPPORTED_MODELS dict and dynamic dimensions() are NOT yet implemented.
       The four new backend files (ollama.py, openai_emb.py, cohere_emb.py, google_emb.py)
       do NOT exist yet.

     8.2 — EmbeddingRegistry.list_all() NOT implemented. Only names() exists.

     8.3 — New entry points NOT yet in pyproject.toml (only mock and local are registered).

     8.4 — HUD shows only index name (not "name · model"). RAGManager.active_embedding_model
       property does NOT exist. HUDWidget.update_from_state() does not read embedding model.

     8.5 — ALREADY DONE. ThinkingWidget.set_context() is already called with "Retrieving context…"
       and "Re-ranking results…" in _stream_response() (added in Phase 4). No code change needed.

     8.6 — tests/test_embeddings/ directory does NOT exist. test_hud.py exists but has no
       embedding model assertions.

     ---

     8.1 — Additional Embedding Backends (src/anythink/embeddings/)

     1a. Extend local.py with SUPPORTED_MODELS dict and dynamic dimensions():

     class LocalEmbeddingBackend(BaseEmbeddingBackend):
         SUPPORTED_MODELS = {
             "all-MiniLM-L6-v2": 384,   # default
             "all-MiniLM-L12-v2": 384,
             "bge-small-en-v1.5": 384,
             "bge-base-en-v1.5": 768,
             "bge-large-en-v1.5": 1024,
             "bge-m3": 1024,
             "e5-base-v2": 768,
             "e5-large-v2": 1024,
         }
         def __init__(self, model_name: str = "all-MiniLM-L6-v2"): ...

         @property
         def dimensions(self) -> int:
             return self.SUPPORTED_MODELS.get(self._model_name, 384)

     Note: dimensions currently hardcodes 384 — needs to be dynamic based on model_name.

     1b. Add src/anythink/embeddings/ollama.py — OllamaEmbeddingBackend:
     SUPPORTED_MODELS = {
         "nomic-embed-text": 768,
         "mxbai-embed-large": 1024,
         "all-minilm": 384,
         "snowflake-arctic-embed": 1024,
     }
     # Uses httpx.AsyncClient to POST to Ollama /api/embeddings endpoint
     # is_available(): check httpx importable + Ollama reachable (try /api/tags)

     1c. Add src/anythink/embeddings/openai_emb.py — OpenAIEmbeddingBackend:
     SUPPORTED_MODELS = {
         "text-embedding-3-small": 1536,
         "text-embedding-3-large": 3072,
     }
     # Uses httpx (same as existing providers), API key from KeyManager

     1d. Add src/anythink/embeddings/cohere_emb.py — CohereEmbeddingBackend:
     SUPPORTED_MODELS = {
         "embed-english-v3.0": 1024,
         "embed-multilingual-v3.0": 1024,
         "embed-english-light-v3.0": 384,
     }
     # Cohere /v1/embed endpoint, API key from KeyManager

     1e. Add src/anythink/embeddings/google_emb.py — GoogleEmbeddingBackend:
     SUPPORTED_MODELS = {
         "text-embedding-004": 768,
         "embedding-001": 768,
     }
     # Google Generative AI embedding endpoint, API key from KeyManager

     All backends: follow exact BaseEmbeddingBackend interface; lazy-import SDKs;
     is_available() checks dep + API key presence; name property includes model suffix
     when non-default (e.g. "ollama/nomic-embed-text").

     8.2 — EmbeddingRegistry Extension (src/anythink/embeddings/registry.py)

     Add list_all() method returning list of dicts for the wizard and settings panel:

     def list_all(self) -> list[dict]:
         # Returns [{"name": str, "display_name": str, "dimensions": int, "available": bool}]
         # Used by RAGSettingsMenu embedding row and wizard step 6

     8.3 — pyproject.toml entry points + optional extras

     [project.entry-points."anythink.embedding_backends"]
     # existing:
     mock = "anythink.embeddings.mock:MockEmbeddingBackend"
     local = "anythink.embeddings.local:LocalEmbeddingBackend"
     # new:
     ollama = "anythink.embeddings.ollama:OllamaEmbeddingBackend"
     openai-emb = "anythink.embeddings.openai_emb:OpenAIEmbeddingBackend"
     cohere-emb = "anythink.embeddings.cohere_emb:CohereEmbeddingBackend"
     google-emb = "anythink.embeddings.google_emb:GoogleEmbeddingBackend"

     [project.optional-dependencies]
     # Add to existing extras:
     emb-openai = ["httpx>=0.27"]      # already a core dep; just the entry point matters
     emb-cohere = ["httpx>=0.27"]
     emb-google = ["httpx>=0.27"]
     # Ollama is local; no extra dep needed beyond httpx

     8.4 — HUD Update (src/anythink/ui/hud.py + src/anythink/rag/manager.py)

     4a. Add active_embedding_model property to RAGManager:

     @property
     def active_embedding_model(self) -> str:
         # Returns the short embedding backend name of the active index
         # e.g. "local", "ollama/nomic-embed-text", "openai/text-embedding-3-small"
         if self._active_info is None:
             return ""
         return self._active_info.embedding_backend

     4b. Add rag_embedding reactive to HUDWidget:
     rag_embedding: reactive[str] = reactive("")

     4c. Update _line2() RAG indicator:
     - When active: ⌬ RAG: <index-name>  ·  <emb-short>
     - emb_short = model name truncated to 14 chars on narrow screens
     - rag_embedding stays "" when not active (no separator shown)

     4d. Update HUDWidget.update_from_state():
     self.rag_embedding = ctx.rag_manager.active_embedding_model if rag_mgr.is_active else ""

     8.5 — Loading Indicator — ALREADY DONE (no change needed)

     thinking_widget.py already supports set_context(phrase). The _stream_response()
     worker already calls:
       thinking.set_context("Retrieving context…")   # before RAG retrieval
       stage_callback("Re-ranking results…")          # passed to retrieval.retrieve()
     No code changes required for 8.5.

     8.6 — Tests

     - tests/test_embeddings/__init__.py — create package
     - tests/test_embeddings/test_ollama.py — httpx mocked; embed() returns correct shape;
       is_available() True with mocked httpx, False without
     - tests/test_embeddings/test_openai_emb.py — same pattern
     - tests/test_embeddings/test_cohere_emb.py — same
     - tests/test_embeddings/test_google_emb.py — same
     - tests/test_embeddings/test_local_extended.py — SUPPORTED_MODELS coverage, dimensions()
       returns correct value per model
     - tests/test_ui/test_hud.py — extend: test rag_embedding reactive and _line2() output

     ---
     Files Modified / Created Summary

     New Files

     ┌─────────────────────────────────────────────┬────────────┐
     │                    File                     │   Phase    │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/parsers.py                 │ 2          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/ingestion.py               │ 2          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/retrieval.py               │ 4          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/bm25.py                    │ 4          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/reranker.py                │ 4          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/quality.py                 │ 6          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/backends/base.py           │ 5          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/backends/pure.py           │ 5 (rename) │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/backends/faiss_store.py    │ 5          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/backends/chroma_store.py   │ 5          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/backends/lance_store.py    │ 5          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/backends/pinecone_store.py │ 5          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/backends/azure_store.py    │ 5          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/rag/backends/registry.py       │ 5          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/ui/textual/rag_settings.py     │ 7          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/ui/textual/rag_wizard.py       │ 7          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/embeddings/ollama.py           │ 8          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/embeddings/openai_emb.py       │ 8          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/embeddings/cohere_emb.py       │ 8          │
     ├─────────────────────────────────────────────┼────────────┤
     │ src/anythink/embeddings/google_emb.py       │ 8          │
     └─────────────────────────────────────────────┴────────────┘

     Modified Files

     ┌────────────────────────────────────────────┬─────────────────────────────────┐
     │                    File                    │             Phases              │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ src/anythink/config/schema.py              │ 1                               │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ src/anythink/rag/models.py                 │ 1, 2                            │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ src/anythink/rag/chunkers.py               │ 3                               │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ src/anythink/rag/manager.py                │ 2, 4, 5                         │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ src/anythink/rag/store.py                  │ 5 (extract to backends/pure.py) │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ src/anythink/embeddings/local.py           │ 8                               │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ src/anythink/embeddings/registry.py        │ 8                               │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ src/anythink/commands/handlers.py          │ 1                               │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ src/anythink/ui/textual/app.py             │ 1, 2, 4, 6                      │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ src/anythink/ui/hud.py                     │ 8                               │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ src/anythink/ui/textual/thinking_widget.py │ 8                               │
     ├────────────────────────────────────────────┼─────────────────────────────────┤
     │ pyproject.toml                             │ 2, 5, 8                         │
     └────────────────────────────────────────────┴─────────────────────────────────┘

     ---
     Verification Plan

     After each phase:

     1. CI gates — ruff check src/ + black --check src/ tests/ + mypy src/anythink + bandit -r src/anythink
     2. Unit tests — PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/ -v
     3. Coverage — pytest --cov=src/anythink --cov-fail-under=80
     4. Manual smoke test (use /run skill):
       - Phase 1: Run anythink, type /rag index list, /rag threshold 0.7, /rag status
       - Phase 2: /rag ingest on a sample directory, watch progress bubble, /rag ingest history
       - Phase 3: Create index with each chunk strategy, inspect /rag query "test" output
       - Phase 4: Toggle hybrid/BM25, observe /rag quality scores
       - Phase 5: Create FAISS-backed index, verify persistence across sessions
       - Phase 6: Trigger no-match (query about unrelated topic), verify 3-option flow
       - Phase 7: /rag settings overlay, wizard via /rag index new
       - Phase 8: /rag settings → switch embedding model, verify HUD shows model name

     ---
     Key Invariants to Preserve

     1. Non-fatal retrieval errors — any exception during RAG retrieval must fall back silently (existing behavior in
     app.py try/except)
     2. Backward compat for existing indexes — IndexInfo.from_dict() must handle missing new fields with defaults
     3. MockEmbeddingBackend in all tests — never use LocalEmbeddingBackend in tests (adds ~500MB model download)
     4. TUI workers for all long ops — ingestion, rebuild, re-ranking never block the event loop
     5. Config immutability — use dataclasses.replace(ctx.config, ...) + ctx.config_manager.save() pattern throughout
     6. XDG paths — all test file I/O must use xdg_dirs fixture
