"""Six-stage RAG ingestion pipeline with incremental change detection.

# noqa: UP017 — datetime.UTC not available in Python 3.11

Stages:
  1. Source Discovery   — walk source path, classify files as new/changed/unchanged
  2. Document Parsing   — dispatch to type-specific parser
  3. Text Preprocessing — already done in parsers; final cleanup pass here
  4. Chunking           — apply configured strategy via dispatch_chunk()
  5. Embedding          — batch embed (64 texts/batch)
  6. Vector Store Write — write store, update IndexInfo with mtime cache + history
"""

from __future__ import annotations

import datetime as _dt
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from anythink.exceptions import RAGError
from anythink.rag.chunkers import dispatch_chunk
from anythink.rag.parsers import dispatch_parser, is_url, parse_url

if TYPE_CHECKING:
    from anythink.embeddings.base import BaseEmbeddingBackend
    from anythink.rag.manager import RAGManager

_BATCH_SIZE = 64

_PROJECT_EXTS = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".go",
        ".rs",
        ".cpp",
        ".c",
        ".h",
        ".cs",
        ".rb",
        ".swift",
        ".kt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".md",
    }
)
_DOC_EXTS = frozenset({".md", ".txt", ".rst", ".pdf", ".csv", ".docx"})
_ALL_EXTS = _PROJECT_EXTS | _DOC_EXTS


@dataclass
class IngestionProgress:
    """Live progress snapshot passed to the progress_callback after each update."""

    stage: int = 1
    stage_name: str = "Starting"
    files_total: int = 0
    files_new: int = 0
    files_changed: int = 0
    files_unchanged: int = 0
    files_parsed: int = 0
    files_failed: int = 0
    chunks_total: int = 0
    chunks_embedded: int = 0
    chunks_written: int = 0
    elapsed_s: float = 0.0
    eta_s: float | None = None
    current_file: str = ""


@dataclass
class IngestionResult:
    """Summary of a completed ingestion run."""

    name: str
    mode: str
    files_processed: int
    chunks_created: int
    duration_s: float
    errors: list[str] = field(default_factory=list)


async def run_ingestion(
    name: str,
    manager: RAGManager,
    backend: BaseEmbeddingBackend,
    *,
    mode: Literal["incremental", "full"] = "incremental",
    extra_path: Path | str | None = None,
    progress_callback: Callable[[IngestionProgress], None] | None = None,
) -> IngestionResult:
    """Execute the full 6-stage ingestion pipeline.

    Args:
        name:               Index name (must already exist in manager).
        manager:            RAGManager instance.
        backend:            Embedding backend to use.
        mode:               'incremental' skips unchanged files; 'full' re-processes all.
        extra_path:         Additional file or directory to ingest into this index.
        progress_callback:  Called synchronously after each significant update.

    Returns:
        IngestionResult with counts and any per-file errors encountered.
    """
    t_start = time.monotonic()
    errors: list[str] = []
    prog = IngestionProgress()

    def _update(
        stage: int,
        stage_name: str,
        *,
        current_file: str = "",
        eta: float | None = None,
    ) -> None:
        prog.stage = stage
        prog.stage_name = stage_name
        prog.current_file = current_file
        prog.elapsed_s = time.monotonic() - t_start
        prog.eta_s = eta
        if progress_callback is not None:
            progress_callback(prog)

    # ── Stage 1: Source Discovery ─────────────────────────────────────────────
    _update(1, "Source Discovery")

    info = manager.get_info(name)
    if info is None:
        raise RAGError(f"Index '{name}' not found.", user_message=f"Unknown index '{name}'.")

    source = Path(info.source_path)
    if not source.exists():
        raise RAGError(
            f"Source path '{source}' does not exist.",
            user_message=f"Source path for index '{name}' no longer exists.",
        )

    exts = _PROJECT_EXTS if info.index_type == "project" else _ALL_EXTS
    mtime_cache = dict(info.file_mtime_cache)

    # Detect whether extra_path is a URL (skip filesystem walk for it)
    extra_url: str | None = None
    extra_file_path: Path | None = None
    if extra_path is not None:
        extra_path_str = str(extra_path)
        if is_url(extra_path_str):
            extra_url = extra_path_str
        else:
            _ep = extra_path if isinstance(extra_path, Path) else Path(extra_path_str)
            if _ep.exists():
                extra_file_path = _ep

    # Collect candidate files from source (and optional file extra_path)
    roots: list[Path] = [source]
    if extra_file_path is not None:
        roots.append(extra_file_path)

    candidate_files: list[Path] = []
    for root in roots:
        if root.is_file():
            if root.suffix.lower() in exts:
                candidate_files.append(root)
        else:
            candidate_files.extend(
                p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts
            )

    # Classify
    to_process: list[Path] = []
    new_count = changed_count = unchanged_count = 0

    for fpath in candidate_files:
        key = str(fpath)
        try:
            mtime = fpath.stat().st_mtime
        except OSError:
            continue
        if key not in mtime_cache:
            new_count += 1
            to_process.append(fpath)
        elif mode == "full" or mtime > mtime_cache[key]:
            changed_count += 1
            to_process.append(fpath)
        else:
            unchanged_count += 1

    # URL extra_path counts as 1 new file
    if extra_url is not None:
        new_count += 1

    prog.files_total = len(candidate_files) + (1 if extra_url else 0)
    prog.files_new = new_count
    prog.files_changed = changed_count
    prog.files_unchanged = unchanged_count
    _update(1, "Source Discovery")

    # ── Stage 2: Document Parsing ─────────────────────────────────────────────
    parsed_units: list[tuple[str, dict[str, Any]]] = []
    parsed_count = 0
    now_iso = _dt.datetime.now(_dt.UTC).isoformat()

    # Parse URL extra_path first (if present)
    if extra_url is not None:
        _update(2, "Document Parsing", current_file=extra_url[:60])
        try:
            url_units = parse_url(extra_url)
            for text, meta in url_units:
                meta.setdefault("ingested_at", now_iso)
                parsed_units.append((text, meta))
            parsed_count += 1
        except RAGError as exc:
            errors.append(f"{extra_url}: {exc.user_message}")
        except Exception as exc:
            errors.append(f"{extra_url}: {exc}")

    for fpath in to_process:
        _update(2, "Document Parsing", current_file=fpath.name)
        try:
            units = dispatch_parser(fpath)
        except RAGError as exc:
            errors.append(f"{fpath.name}: {exc.user_message}")
            continue
        except Exception as exc:
            errors.append(f"{fpath.name}: {exc}")
            continue

        try:
            file_mtime = fpath.stat().st_mtime
        except OSError:
            file_mtime = 0.0

        for text, meta in units:
            meta.setdefault("ingested_at", now_iso)
            meta.setdefault("file_modified_at", file_mtime)
            parsed_units.append((text, meta))

        mtime_cache[str(fpath)] = file_mtime
        parsed_count += 1

    prog.files_parsed = parsed_count
    prog.files_failed = len(to_process) - parsed_count
    _update(2, "Document Parsing")

    # ── Stage 3: Text Preprocessing ───────────────────────────────────────────
    _update(3, "Preprocessing")
    # Parsers already call _preprocess(); final cleanup strips leftover whitespace.
    clean_units = [(text.strip(), meta) for text, meta in parsed_units if text.strip()]

    # ── Stage 4: Chunking ─────────────────────────────────────────────────────
    _update(4, "Chunking")

    all_texts: list[str] = []
    all_metas: list[dict[str, Any]] = []

    strategy = info.chunk_strategy
    chunk_size = info.chunk_size
    chunk_overlap = max(80, info.chunk_overlap)

    if strategy == "semantic":
        # Semantic chunking embeds sentence windows to detect topic shifts.
        # It must run async here (Stage 4) rather than in Stage 5 because
        # the embedding is used to determine where to place chunk boundaries.
        from anythink.rag.chunkers import achunk_semantic

        for text, meta in clean_units:
            try:
                raw_chunks = await achunk_semantic(
                    text, backend, chunk_size=chunk_size, overlap=chunk_overlap
                )
                for i, chunk_val in enumerate(raw_chunks):
                    if chunk_val.strip():
                        all_texts.append(chunk_val)
                        all_metas.append({**meta, "chunk_index": i})
            except Exception:
                # Fallback: treat whole unit as one chunk
                if text.strip():
                    all_texts.append(text)
                    all_metas.append({**meta, "chunk_index": 0})
    else:
        for text, meta in clean_units:
            try:
                chunks = dispatch_chunk(
                    text, strategy=strategy, size=chunk_size, overlap=chunk_overlap, meta=meta
                )
            except Exception:
                chunks = [(text, {**meta, "chunk_index": 0})]
            for chunk_text_val, chunk_meta in chunks:
                if chunk_text_val.strip():
                    all_texts.append(chunk_text_val)
                    all_metas.append(chunk_meta)

    prog.chunks_total = len(all_texts)
    _update(4, "Chunking")

    # ── Stage 5: Embedding ────────────────────────────────────────────────────
    all_vectors: list[list[float]] = []

    if all_texts:
        for i in range(0, len(all_texts), _BATCH_SIZE):
            batch = all_texts[i : i + _BATCH_SIZE]
            vecs = await backend.embed(batch)
            all_vectors.extend(vecs)

            prog.chunks_embedded = len(all_vectors)
            elapsed = time.monotonic() - t_start
            if elapsed > 0 and all_vectors:
                rate = len(all_vectors) / elapsed
                remaining = len(all_texts) - len(all_vectors)
                eta = remaining / rate if rate > 0 else None
            else:
                eta = None
            _update(5, "Embedding", eta=eta)

    # ── Stage 6: Vector Store Write ───────────────────────────────────────────
    _update(6, "Writing to store")

    from anythink.rag.backends.registry import get_backend

    store = get_backend(info.vector_backend)
    if all_texts:
        store.add(all_texts, all_metas, all_vectors)

    # Build BM25 index from the same corpus (always in-memory; persisted if configured)
    from anythink.rag.bm25 import BM25Index

    bm25 = BM25Index()
    if all_texts:
        bm25.build(all_texts)

    # Persist vector store + BM25 if configured
    if info.persistence_mode == "persist":
        manager._cache_dir.mkdir(parents=True, exist_ok=True)  # noqa: SLF001
        store.persist(manager._store_base_path(name))  # noqa: SLF001
        if bm25.is_built:
            bm25.persist(manager._bm25_path(name))  # noqa: SLF001

    # Update active in-memory store and BM25 immediately
    if manager.active_name == name:
        manager._active_store = store  # noqa: SLF001
        manager._active_bm25 = bm25 if bm25.is_built else None  # noqa: SLF001

    # Build updated IndexInfo
    duration = time.monotonic() - t_start
    history_entry: dict[str, Any] = {
        "timestamp": _dt.datetime.now(_dt.UTC).isoformat(),
        "mode": mode,
        "files_processed": parsed_count,
        "files_new": new_count,
        "files_changed": changed_count,
        "chunks_created": store.count(),
        "duration_s": round(duration, 2),
    }
    if errors:
        history_entry["errors"] = len(errors)

    from dataclasses import replace

    updated_info = replace(
        info,
        last_indexed=_dt.datetime.now(_dt.UTC),
        file_count=parsed_count,
        chunk_count=store.count(),
        embedding_backend=backend.name,
        file_mtime_cache=mtime_cache,
        ingestion_history=list(info.ingestion_history) + [history_entry],
    )
    manager.create_index(updated_info)

    # Keep active_info in sync
    if manager._active_info and manager._active_info.name == name:  # noqa: SLF001
        manager._active_info = updated_info  # noqa: SLF001

    prog.chunks_written = store.count()
    _update(6, "Complete")

    return IngestionResult(
        name=name,
        mode=mode,
        files_processed=parsed_count,
        chunks_created=store.count(),
        duration_s=duration,
        errors=errors,
    )
