"""Text chunkers for RAG indexing: code-aware and document-aware."""

from __future__ import annotations

import re
from pathlib import Path

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
_DEFAULT_OVERLAP = 64


def chunk_text(
    text: str,
    *,
    chunk_size: int = _DEFAULT_CHUNK,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[str]:
    """Split *text* into overlapping character-level chunks.

    Tries to break at paragraph / sentence boundaries where possible.
    """
    if not text.strip():
        return []

    # Prefer paragraph breaks, then sentence breaks, then word breaks
    chunks: list[str] = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)
        segment = text[start:end]

        # Walk backward to find a cleaner break (only if not at the last segment)
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
            break  # processed the entire text
        start = max(start + 1, end - overlap)

    return chunks


def chunk_code(
    text: str,
    *,
    chunk_size: int = _DEFAULT_CHUNK,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[str]:
    """Code-aware chunker: split at top-level function/class definitions first."""
    if not text.strip():
        return []

    # Split at lines starting a function/class definition
    boundary = re.compile(r"^(def |class |fn |func |function |public |private |async def )", re.M)
    positions = [m.start() for m in boundary.finditer(text)]

    if not positions:
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    # Build natural blocks by grouping lines between definition starts
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

    # Chunk blocks that are too large
    chunks: list[str] = []
    for block in blocks:
        if len(block) <= chunk_size:
            chunks.append(block)
        else:
            chunks.extend(chunk_text(block, chunk_size=chunk_size, overlap=overlap))

    return chunks


def chunk_file(
    path: Path,
    *,
    chunk_size: int = _DEFAULT_CHUNK,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[tuple[str, dict[str, object]]]:
    """Read *path* and return ``(chunk_text, metadata)`` pairs.

    *metadata* contains at minimum ``source_path`` and estimated line ranges.
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
        meta: dict[str, object] = {
            "source_path": str(path),
            "start_line": line_no,
            "end_line": line_no + chunk_lines - 1,
        }
        result.append((chunk, meta))
        line_no += chunk_lines

    return result
