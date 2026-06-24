"""Text chunkers for RAG indexing — all 6 strategies.

Strategies:
  fixed     — character-level fixed size with boundary preference   (chunk_text)
  code      — split at function/class definition boundaries          (chunk_code)
  sentence  — split at sentence endings, group to size              (chunk_sentence)
  paragraph — split at double-newlines, merge/split to size         (chunk_paragraph)
  heading   — split at markdown headings, carry heading_path meta   (chunk_heading)
  semantic  — async: rolling-window cosine similarity boundary det.  (achunk_semantic)

dispatch_chunk() is the synchronous routing entry point for all strategies except
semantic (which requires an async embedding backend).  Use achunk_semantic() directly
for semantic chunking, then fall back to dispatch_chunk for the remaining strategies.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anythink.embeddings.base import BaseEmbeddingBackend

_CODE_EXTENSIONS = frozenset(
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
        ".php",
    }
)

_DEFAULT_CHUNK = 512
_DEFAULT_OVERLAP = 100  # chars; minimum enforced by dispatch_chunk is 80
_SEMANTIC_WINDOW = 3  # sentences per rolling window
_SEMANTIC_THRESHOLD = 0.6  # cosine similarity below which a boundary is placed


# ── Internal helpers ──────────────────────────────────────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length float vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _split_sentences(text: str) -> list[str]:
    """Split *text* into a flat list of non-empty sentence strings.

    Sentence boundaries are detected at:
      • [.!?] followed by whitespace
      • double-newlines (paragraph breaks)
    """
    # Split on sentence-ending punctuation followed by whitespace
    parts = re.split(r"(?<=[.!?])\s+", text)
    result: list[str] = []
    for part in parts:
        # Also split on paragraph breaks within each part
        for sub in re.split(r"\n\n+", part):
            s = sub.strip()
            if s:
                result.append(s)
    return result


def _overlap_prefix(chunks: list[str], overlap: int) -> str:
    """Return the last *overlap* characters of the most recent chunk."""
    if not chunks:
        return ""
    tail = chunks[-1]
    return tail[-overlap:] if len(tail) > overlap else tail


# ── Strategy 1: Fixed size (original) ────────────────────────────────────────


def chunk_text(
    text: str,
    *,
    chunk_size: int = _DEFAULT_CHUNK,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[str]:
    """Split *text* into overlapping character-level chunks.

    Prefers to break at paragraph / sentence / word boundaries.
    """
    if not text.strip():
        return []

    chunks: list[str] = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)
        segment = text[start:end]

        if end < n:
            for pat in (r"\n\n", r"\.\s", r"\s"):
                m = list(re.finditer(pat, segment))
                if m:
                    last = m[-1]
                    end = start + last.end()
                    segment = text[start:end]
                    break

        chunk = segment.strip()
        if chunk:
            chunks.append(chunk)

        if end >= n:
            break
        start = max(start + 1, end - overlap)

    return chunks


# ── Strategy 2: Code-aware (original) ────────────────────────────────────────


def chunk_code(
    text: str,
    *,
    chunk_size: int = _DEFAULT_CHUNK,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[str]:
    """Split at top-level function/class definition boundaries."""
    if not text.strip():
        return []

    boundary = re.compile(r"^(def |class |fn |func |function |public |private |async def )", re.M)
    positions = [m.start() for m in boundary.finditer(text)]

    if not positions:
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    blocks: list[str] = []
    positions.append(len(text))
    prev = 0
    for pos in positions[1:]:
        block = text[prev:pos].strip()
        if block:
            blocks.append(block)
        prev = pos
    if text[prev:].strip():
        blocks.append(text[prev:].strip())

    chunks: list[str] = []
    for block in blocks:
        if len(block) <= chunk_size:
            chunks.append(block)
        else:
            chunks.extend(chunk_text(block, chunk_size=chunk_size, overlap=overlap))

    return chunks


# ── Strategy 3: Sentence-based ────────────────────────────────────────────────


def chunk_sentence(
    text: str,
    *,
    chunk_size: int = _DEFAULT_CHUNK,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[str]:
    """Group sentences into chunks up to *chunk_size* characters.

    Splits at sentence boundaries (period/exclamation/question + whitespace and
    paragraph breaks).  Applies character-level overlap by carrying trailing
    sentences from the previous chunk into the start of the next.
    """
    if not text.strip():
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    chunks: list[str] = []
    buf: list[str] = []
    buf_size = 0

    for sent in sentences:
        sent_len = len(sent)
        # Single sentence that exceeds chunk_size — keep it as its own chunk
        if sent_len > chunk_size:
            if buf:
                chunks.append(" ".join(buf))
                buf = []
                buf_size = 0
            chunks.append(sent)
            continue

        if buf and buf_size + sent_len + 1 > chunk_size:
            chunks.append(" ".join(buf))
            # Overlap: carry trailing sentences that fit within *overlap* chars
            new_buf: list[str] = []
            carried = 0
            for s in reversed(buf):
                if carried + len(s) + 1 > overlap:
                    break
                new_buf.insert(0, s)
                carried += len(s) + 1
            buf = new_buf
            buf_size = carried

        buf.append(sent)
        buf_size += sent_len + 1

    if buf:
        chunks.append(" ".join(buf))

    return chunks if chunks else [text.strip()]


# ── Strategy 4: Paragraph-based ───────────────────────────────────────────────


def chunk_paragraph(
    text: str,
    *,
    chunk_size: int = _DEFAULT_CHUNK,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[str]:
    """Group paragraphs into chunks; oversized paragraphs are sentence-split.

    Paragraphs are delimited by two or more consecutive newlines.  Multiple
    short paragraphs are merged up to *chunk_size* characters.  After flushing
    a chunk, trailing paragraphs are carried forward for overlap continuity.
    """
    if not text.strip():
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
    if not paragraphs:
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    chunks: list[str] = []
    buf: list[str] = []
    buf_size = 0

    for para in paragraphs:
        if len(para) > chunk_size:
            # Flush current buffer first
            if buf:
                chunks.append("\n\n".join(buf))
                buf = []
                buf_size = 0
            # Split oversized paragraph at sentence level
            chunks.extend(chunk_sentence(para, chunk_size=chunk_size, overlap=overlap))
            continue

        para_len = len(para)
        if buf and buf_size + para_len + 2 > chunk_size:
            chunks.append("\n\n".join(buf))
            # Overlap: carry trailing paragraphs
            new_buf: list[str] = []
            carried = 0
            for p in reversed(buf):
                if carried + len(p) + 2 > overlap:
                    break
                new_buf.insert(0, p)
                carried += len(p) + 2
            buf = new_buf
            buf_size = carried

        buf.append(para)
        buf_size += para_len + 2

    if buf:
        chunks.append("\n\n".join(buf))

    return chunks if chunks else [text.strip()]


# ── Strategy 5: Heading-based ─────────────────────────────────────────────────


def chunk_heading(
    text: str,
    *,
    chunk_size: int = _DEFAULT_CHUNK,
    overlap: int = _DEFAULT_OVERLAP,
    base_meta: dict[str, Any] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Split at markdown heading markers; carry full heading_path per chunk.

    Unlike the other chunkers, this returns ``(chunk_text, chunk_meta)`` tuples
    directly because each chunk section has its own distinct ``heading_path``.

    If *base_meta* contains a ``heading_path`` from the parser (e.g. the parent
    section already split by parse_markdown), that path is prepended to any
    headings found within *text*.

    Sections that exceed *chunk_size* are further split at paragraph boundaries.
    Falls back to paragraph chunking if no heading markers are found.
    """
    base = dict(base_meta) if base_meta else {}
    parent_path: str = str(base.get("heading_path", ""))

    if not text.strip():
        return []

    _H = re.compile(r"^(#{1,6})\s+(.*)", re.M)
    matches = list(_H.finditer(text))

    if not matches:
        # No headings — paragraph chunk, inherit existing heading_path
        raw = chunk_paragraph(text, chunk_size=chunk_size, overlap=overlap)
        return [(chunk, {**base, "chunk_index": i}) for i, chunk in enumerate(raw)]

    result: list[tuple[str, dict[str, Any]]] = []
    heading_stack: list[tuple[int, str]] = []  # (level, text)
    chunk_idx = 0

    boundaries = [(m.start(), len(m.group(1)), m.group(2).strip()) for m in matches]
    # Sentinel at end
    ends = [b[0] for b in boundaries[1:]] + [len(text)]

    for (pos, level, heading), end in zip(boundaries, ends, strict=False):
        section_text = text[pos:end].strip()
        if not section_text:
            continue

        # Maintain heading stack: pop levels >= current
        heading_stack = [(lvl, h) for lvl, h in heading_stack if lvl < level]
        heading_stack.append((level, heading))

        local_path = " > ".join(h for _, h in heading_stack)
        full_path = f"{parent_path} > {local_path}" if parent_path else local_path

        section_meta = {**base, "heading_path": full_path}

        if len(section_text) <= chunk_size:
            result.append((section_text, {**section_meta, "chunk_index": chunk_idx}))
            chunk_idx += 1
        else:
            sub_chunks = chunk_paragraph(section_text, chunk_size=chunk_size, overlap=overlap)
            for sub in sub_chunks:
                result.append((sub, {**section_meta, "chunk_index": chunk_idx}))
                chunk_idx += 1

    return result if result else [(text.strip(), {**base, "chunk_index": 0})]


# ── Strategy 6: Semantic (async) ──────────────────────────────────────────────


async def achunk_semantic(
    text: str,
    backend: BaseEmbeddingBackend,
    *,
    chunk_size: int = _DEFAULT_CHUNK,
    overlap: int = _DEFAULT_OVERLAP,
    window_size: int = _SEMANTIC_WINDOW,
    similarity_threshold: float = _SEMANTIC_THRESHOLD,
) -> list[str]:
    """Detect topic boundaries via rolling-window cosine similarity, then chunk.

    Algorithm:
      1. Split text into sentences.
      2. Build rolling windows of *window_size* consecutive sentences.
      3. Embed every window with *backend*.
      4. Place a boundary between window i and i+1 when their cosine
         similarity drops below *similarity_threshold*.
      5. Merge sentence spans between boundaries; apply *chunk_size* limits.

    Falls back to paragraph chunking if fewer than 2 × *window_size* sentences
    exist (too few for meaningful similarity comparison).
    """
    if not text.strip():
        return []

    sentences = _split_sentences(text)

    if len(sentences) < 2 * window_size:
        return chunk_paragraph(text, chunk_size=chunk_size, overlap=overlap)

    # Build one text string per window
    windows = [
        " ".join(sentences[i : i + window_size]) for i in range(len(sentences) - window_size + 1)
    ]

    window_vecs = await backend.embed(windows)

    # Identify boundaries: window positions where similarity drops below threshold
    # boundary_sentence_indices marks the sentence index that starts a new segment
    boundary_sentences: list[int] = [0]
    for i in range(1, len(window_vecs)):
        sim = _cosine(window_vecs[i - 1], window_vecs[i])
        if sim < similarity_threshold:
            boundary_sentences.append(i)
    boundary_sentences.append(len(sentences))

    # Build raw sections from sentence spans
    sections: list[str] = []
    for j in range(len(boundary_sentences) - 1):
        start = boundary_sentences[j]
        end = boundary_sentences[j + 1]
        section = " ".join(sentences[start:end]).strip()
        if section:
            sections.append(section)

    if not sections:
        return chunk_paragraph(text, chunk_size=chunk_size, overlap=overlap)

    # Apply size limits across sections
    chunks: list[str] = []
    buf: list[str] = []
    buf_size = 0

    for section in sections:
        sec_len = len(section)
        if sec_len > chunk_size:
            if buf:
                chunks.append(" ".join(buf))
                buf = []
                buf_size = 0
            chunks.extend(chunk_paragraph(section, chunk_size=chunk_size, overlap=overlap))
        elif buf and buf_size + sec_len + 1 > chunk_size:
            chunks.append(" ".join(buf))
            # Overlap
            new_buf: list[str] = []
            carried = 0
            for s in reversed(buf):
                if carried + len(s) + 1 > overlap:
                    break
                new_buf.insert(0, s)
                carried += len(s) + 1
            buf = new_buf + [section]
            buf_size = carried + sec_len + 1
        else:
            buf.append(section)
            buf_size += sec_len + 1

    if buf:
        chunks.append(" ".join(buf))

    return chunks if chunks else chunk_paragraph(text, chunk_size=chunk_size, overlap=overlap)


# ── dispatch_chunk — synchronous routing entry point ─────────────────────────


def dispatch_chunk(
    text: str,
    *,
    strategy: str = "fixed",
    size: int = _DEFAULT_CHUNK,
    overlap: int = _DEFAULT_OVERLAP,
    meta: dict[str, Any] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Route *text* to the configured chunking strategy.

    Returns a list of ``(chunk_text, chunk_metadata)`` pairs where each
    ``chunk_metadata`` is a shallow copy of *meta* extended with
    ``chunk_index`` (and ``heading_path`` for the heading strategy).

    Minimum overlap is enforced at 80 characters.

    Strategies:
      fixed     — character-level, prefer paragraph/sentence boundaries
      code      — split at function/class definition lines
      sentence  — group sentences up to size
      paragraph — group paragraphs up to size; oversized → sentence-split
      heading   — split at markdown headings; carry heading_path metadata
      semantic  — NOT handled here (requires async backend).
                  Falls back to paragraph chunking with a note.
                  Call achunk_semantic() directly from async contexts.
    """
    overlap = max(80, overlap)
    base_meta: dict[str, Any] = dict(meta) if meta else {}

    match strategy:
        case "code":
            raw = chunk_code(text, chunk_size=size, overlap=overlap)
            return [(chunk, {**base_meta, "chunk_index": i}) for i, chunk in enumerate(raw)]
        case "sentence":
            raw = chunk_sentence(text, chunk_size=size, overlap=overlap)
            return [(chunk, {**base_meta, "chunk_index": i}) for i, chunk in enumerate(raw)]
        case "paragraph":
            raw = chunk_paragraph(text, chunk_size=size, overlap=overlap)
            return [(chunk, {**base_meta, "chunk_index": i}) for i, chunk in enumerate(raw)]
        case "heading":
            # chunk_heading returns (text, meta) tuples with heading_path already set
            return chunk_heading(text, chunk_size=size, overlap=overlap, base_meta=base_meta)
        case "semantic":
            # Semantic chunking requires async embedding; the ingestion pipeline
            # calls achunk_semantic() directly before dispatching here.
            # This path only runs when dispatch_chunk is called outside the pipeline.
            raw = chunk_paragraph(text, chunk_size=size, overlap=overlap)
            return [(chunk, {**base_meta, "chunk_index": i}) for i, chunk in enumerate(raw)]
        case _:
            # "fixed" and any unrecognised strategy
            raw = chunk_text(text, chunk_size=size, overlap=overlap)
            return [(chunk, {**base_meta, "chunk_index": i}) for i, chunk in enumerate(raw)]


# ── Legacy chunk_file (used by build_index + tests) ───────────────────────────


def chunk_file(
    path: Path,
    *,
    chunk_size: int = _DEFAULT_CHUNK,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[tuple[str, dict[str, object]]]:
    """Read *path* and return ``(chunk_text, metadata)`` pairs.

    Uses code-aware chunking for code files; fixed-size for everything else.
    Kept for backward compatibility with build_index() and existing tests.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    suffix = path.suffix.lower()
    if suffix in _CODE_EXTENSIONS:
        raw_chunks = chunk_code(text, chunk_size=chunk_size, overlap=overlap)
    else:
        raw_chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    result: list[tuple[str, dict[str, object]]] = []
    line_no = 1
    for chunk in raw_chunks:
        chunk_lines = chunk.count("\n") + 1
        chunk_meta: dict[str, object] = {
            "source_path": str(path),
            "start_line": line_no,
            "end_line": line_no + chunk_lines - 1,
        }
        result.append((chunk, chunk_meta))
        line_no += chunk_lines

    return result
