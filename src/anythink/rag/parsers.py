"""Document parsers for the RAG ingestion pipeline.

Each parser returns a list of (text, metadata) tuples representing the natural
sections of a document before chunking.  Parsers are responsible for extracting
clean structured text and rich metadata; chunking happens in Stage 4 of the
ingestion pipeline.

All parsers include at minimum in metadata:
  source_path, file_type, file_modified_at

Heavy optional dependencies (pypdf, python-docx) are lazy-imported so the
core package runs without them; a RAGError is raised with a clear install hint
if a missing dep is needed for an actual file.
"""

from __future__ import annotations

import ast
import csv
import io
import json
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from anythink.exceptions import RAGError

# ── Helpers ───────────────────────────────────────────────────────────────────


def _base_meta(path: Path) -> dict[str, Any]:
    """Return common metadata fields present for every chunk."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return {
        "source_path": str(path),
        "file_type": path.suffix.lower(),
        "file_modified_at": mtime,
    }


def _preprocess(text: str) -> str:
    """Stage 3 preprocessing: NFC unicode, strip control chars, collapse blanks."""
    text = unicodedata.normalize("NFC", text)
    # Keep newline, tab, carriage return; drop other control chars
    text = "".join(
        ch
        for ch in text
        if ch in ("\n", "\t", "\r") or not unicodedata.category(ch).startswith("C")
    )
    # Collapse 3+ blank lines → 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Normalize horizontal whitespace within lines
    lines = [re.sub(r"[ \t]+", " ", line) for line in text.split("\n")]
    return "\n".join(lines).strip()


# ── Plain text / RST ──────────────────────────────────────────────────────────


def parse_text(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Return the whole file as a single text unit."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RAGError(
            f"Cannot read {path}: {exc}",
            user_message=f"Cannot read file: {path.name}",
        ) from exc
    meta = _base_meta(path)
    meta["start_line"] = 1
    meta["end_line"] = raw.count("\n") + 1
    return [(_preprocess(raw), meta)]


# ── Markdown ─────────────────────────────────────────────────────────────────


def parse_markdown(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Split at heading boundaries; carry full heading_path as metadata."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RAGError(
            f"Cannot read {path}: {exc}",
            user_message=f"Cannot read file: {path.name}",
        ) from exc

    lines = raw.split("\n")
    _H = re.compile(r"^(#{1,6})\s+(.*)")
    sections: list[tuple[str, dict[str, Any]]] = []
    buf: list[str] = []
    buf_start = 1
    headings: list[str] = []

    for lineno, line in enumerate(lines, 1):
        m = _H.match(line)
        if m:
            if buf:
                text = _preprocess("\n".join(buf))
                if text:
                    meta = _base_meta(path)
                    meta["start_line"] = buf_start
                    meta["end_line"] = lineno - 1
                    meta["heading_path"] = " > ".join(headings)
                    sections.append((text, meta))
            level = len(m.group(1))
            headings = headings[: level - 1] + [m.group(2).strip()]
            buf = [line]
            buf_start = lineno
        else:
            buf.append(line)

    if buf:
        text = _preprocess("\n".join(buf))
        if text:
            meta = _base_meta(path)
            meta["start_line"] = buf_start
            meta["end_line"] = len(lines)
            meta["heading_path"] = " > ".join(headings)
            sections.append((text, meta))

    return sections if sections else parse_text(path)


# ── Python ────────────────────────────────────────────────────────────────────


def parse_python(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Extract module preamble plus each top-level function/class as a unit."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RAGError(
            f"Cannot read {path}: {exc}",
            user_message=f"Cannot read file: {path.name}",
        ) from exc

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return parse_text(path)

    lines = source.split("\n")
    top_defs: list[tuple[int, int, str]] = []  # (start, end, name)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            top_defs.append((start, end, node.name))

    if not top_defs:
        return parse_text(path)

    top_defs.sort(key=lambda x: x[0])
    sections: list[tuple[str, dict[str, Any]]] = []

    # Preamble: everything before first def
    first_line = top_defs[0][0]
    preamble = "\n".join(lines[: first_line - 1]).strip()
    if preamble:
        meta = _base_meta(path)
        meta["start_line"] = 1
        meta["end_line"] = first_line - 1
        meta["function_name"] = ""
        sections.append((_preprocess(preamble), meta))

    # Each top-level def/class
    for start, end, name in top_defs:
        unit = "\n".join(lines[start - 1 : end]).strip()
        if unit:
            meta = _base_meta(path)
            meta["start_line"] = start
            meta["end_line"] = end
            meta["function_name"] = name
            sections.append((_preprocess(unit), meta))

    return sections if sections else parse_text(path)


# ── JavaScript / TypeScript ───────────────────────────────────────────────────


def parse_js(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Extract JS/TS function declarations and class definitions as units."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RAGError(
            f"Cannot read {path}: {exc}",
            user_message=f"Cannot read file: {path.name}",
        ) from exc

    lines = source.split("\n")
    # Match function declarations, arrow functions assigned to const, class decls
    _BOUNDARY = re.compile(
        r"^(export\s+)?(default\s+)?"
        r"(async\s+)?"
        r"(function\s+\w+|class\s+\w+|const\s+\w+\s*=\s*(async\s+)?\(|"
        r"const\s+\w+\s*=\s*(async\s+)?function)",
        re.M,
    )

    positions: list[tuple[int, str]] = []  # (line_no, name)
    for m in _BOUNDARY.finditer(source):
        line_no = source[: m.start()].count("\n") + 1
        name_m = re.search(r"(?:function|class|const)\s+(\w+)", m.group())
        name = name_m.group(1) if name_m else "anonymous"
        positions.append((line_no, name))

    if not positions:
        return parse_text(path)

    sections: list[tuple[str, dict[str, Any]]] = []
    boundary_lines = [p[0] for p in positions] + [len(lines) + 1]

    # Preamble
    preamble = "\n".join(lines[: positions[0][0] - 1]).strip()
    if preamble:
        meta = _base_meta(path)
        meta["start_line"] = 1
        meta["end_line"] = positions[0][0] - 1
        meta["function_name"] = ""
        sections.append((_preprocess(preamble), meta))

    for i, (start_line, name) in enumerate(positions):
        end_line = boundary_lines[i + 1] - 1
        unit = "\n".join(lines[start_line - 1 : end_line]).strip()
        if unit:
            meta = _base_meta(path)
            meta["start_line"] = start_line
            meta["end_line"] = end_line
            meta["function_name"] = name
            sections.append((_preprocess(unit), meta))

    return sections if sections else parse_text(path)


# ── Generic code ──────────────────────────────────────────────────────────────


def parse_code_generic(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Generic code parser: split at structural boundary markers with line tracking."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RAGError(
            f"Cannot read {path}: {exc}",
            user_message=f"Cannot read file: {path.name}",
        ) from exc

    lines = source.split("\n")
    _BOUNDARY = re.compile(
        r"^(func |fn |pub fn |pub async fn |async fn |"
        r"def |class |public |private |protected |static |"
        r"impl |trait |interface |struct |enum |type )",
        re.M,
    )

    positions = [(source[: m.start()].count("\n") + 1) for m in _BOUNDARY.finditer(source)]

    if not positions:
        return parse_text(path)

    sections: list[tuple[str, dict[str, Any]]] = []
    boundary_lines = positions + [len(lines) + 1]

    # Preamble
    if positions[0] > 1:
        preamble = "\n".join(lines[: positions[0] - 1]).strip()
        if preamble:
            meta = _base_meta(path)
            meta["start_line"] = 1
            meta["end_line"] = positions[0] - 1
            sections.append((_preprocess(preamble), meta))

    for i, start_line in enumerate(positions):
        end_line = boundary_lines[i + 1] - 1
        unit = "\n".join(lines[start_line - 1 : end_line]).strip()
        if unit:
            meta = _base_meta(path)
            meta["start_line"] = start_line
            meta["end_line"] = end_line
            sections.append((_preprocess(unit), meta))

    return sections if sections else parse_text(path)


# ── PDF ───────────────────────────────────────────────────────────────────────


def parse_pdf(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Extract text page-by-page.  Requires pypdf (pip install anythink[rag])."""
    try:
        import pypdf
    except ImportError as exc:
        raise RAGError(
            "pypdf not installed.",
            user_message="PDF parsing requires: pip install anythink[rag]",
        ) from exc

    sections: list[tuple[str, dict[str, Any]]] = []
    try:
        reader = pypdf.PdfReader(str(path))
        for page_num, page in enumerate(reader.pages, 1):
            raw = page.extract_text() or ""
            text = _preprocess(raw)
            if not text:
                continue
            meta = _base_meta(path)
            meta["page_number"] = page_num
            sections.append((text, meta))
    except Exception as exc:
        raise RAGError(
            f"PDF parsing failed for {path}: {exc}",
            user_message=f"Failed to parse PDF: {path.name}",
        ) from exc

    if not sections:
        return [(_preprocess(f"[Empty or unreadable PDF: {path.name}]"), _base_meta(path))]
    return sections


# ── Word Document ─────────────────────────────────────────────────────────────


def parse_docx(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Extract paragraphs grouped by heading structure.

    Requires python-docx (pip install anythink[rag]).
    """
    try:
        from docx import Document
    except ImportError as exc:
        raise RAGError(
            "python-docx not installed.",
            user_message="Word document parsing requires: pip install anythink[rag]",
        ) from exc

    try:
        doc = Document(str(path))
    except Exception as exc:
        raise RAGError(
            f"DOCX parsing failed for {path}: {exc}",
            user_message=f"Failed to parse Word document: {path.name}",
        ) from exc

    sections: list[tuple[str, dict[str, Any]]] = []
    current_buf: list[str] = []
    current_headings: list[str] = []

    def _flush() -> None:
        if not current_buf:
            return
        text = _preprocess("\n".join(current_buf))
        if text:
            meta = _base_meta(path)
            meta["heading_path"] = " > ".join(current_headings)
            sections.append((text, meta))

    for para in doc.paragraphs:
        style_name = para.style.name if para.style else ""
        para_text = para.text.strip()

        if style_name.startswith("Heading"):
            _flush()
            current_buf = []
            try:
                level = int(style_name.split()[-1])
            except (ValueError, IndexError):
                level = 1
            current_headings = current_headings[: level - 1] + [para_text]
            if para_text:
                current_buf = [para_text]
        elif para_text:
            current_buf.append(para_text)

    _flush()

    return sections if sections else parse_text(path)


# ── CSV ───────────────────────────────────────────────────────────────────────


def parse_csv(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Return row groups with column headers in each chunk."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RAGError(
            f"Cannot read {path}: {exc}",
            user_message=f"Cannot read file: {path.name}",
        ) from exc

    reader = csv.DictReader(io.StringIO(raw))
    headers = list(reader.fieldnames or [])
    header_str = ", ".join(str(h) for h in headers)

    _BATCH = 20  # rows per unit
    sections: list[tuple[str, dict[str, Any]]] = []
    buf: list[str] = []
    start_row = 2  # 1-indexed, row 1 is headers

    for row_num, row in enumerate(reader, 2):
        buf.append("  ".join(f"{k}: {v}" for k, v in row.items() if v is not None))
        if len(buf) >= _BATCH:
            meta = _base_meta(path)
            meta["column_headers"] = header_str
            meta["row_range"] = f"{start_row}-{row_num}"
            sections.append((_preprocess("\n".join(buf)), meta))
            buf = []
            start_row = row_num + 1

    if buf:
        meta = _base_meta(path)
        meta["column_headers"] = header_str
        sections.append((_preprocess("\n".join(buf)), meta))

    return sections if sections else parse_text(path)


# ── JSON ──────────────────────────────────────────────────────────────────────


def parse_json(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Flatten top-level keys (dict) or index batches (list) as units."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise RAGError(
            f"JSON parsing failed for {path}: {exc}",
            user_message=f"Invalid JSON in {path.name}",
        ) from exc

    sections: list[tuple[str, dict[str, Any]]] = []

    if isinstance(data, dict):
        for key, value in data.items():
            text = json.dumps({key: value}, indent=2, ensure_ascii=False)
            meta = _base_meta(path)
            meta["key_path"] = str(key)
            sections.append((_preprocess(text), meta))
    elif isinstance(data, list):
        _BATCH = 10
        for i in range(0, len(data), _BATCH):
            batch = data[i : i + _BATCH]
            text = json.dumps(batch, indent=2, ensure_ascii=False)
            meta = _base_meta(path)
            meta["key_path"] = f"[{i}:{i + _BATCH}]"
            sections.append((_preprocess(text), meta))
    else:
        text = json.dumps(data, indent=2, ensure_ascii=False)
        sections.append((_preprocess(text), _base_meta(path)))

    return sections if sections else parse_text(path)


# ── YAML ──────────────────────────────────────────────────────────────────────


def parse_yaml_file(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Flatten top-level keys as units (same approach as JSON)."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        data = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError) as exc:
        raise RAGError(
            f"YAML parsing failed for {path}: {exc}",
            user_message=f"Invalid YAML in {path.name}",
        ) from exc

    if data is None:
        return parse_text(path)

    sections: list[tuple[str, dict[str, Any]]] = []

    if isinstance(data, dict):
        for key, value in data.items():
            text = yaml.dump({key: value}, default_flow_style=False, allow_unicode=True)
            meta = _base_meta(path)
            meta["key_path"] = str(key)
            sections.append((_preprocess(text), meta))
    elif isinstance(data, list):
        _BATCH = 10
        for i in range(0, len(data), _BATCH):
            batch = data[i : i + _BATCH]
            text = yaml.dump(batch, default_flow_style=False, allow_unicode=True)
            meta = _base_meta(path)
            meta["key_path"] = f"[{i}:{i + _BATCH}]"
            sections.append((_preprocess(text), meta))
    else:
        text = yaml.dump(data, default_flow_style=False, allow_unicode=True)
        sections.append((_preprocess(text), _base_meta(path)))

    return sections if sections else parse_text(path)


# ── URL (HTTP/HTTPS) ──────────────────────────────────────────────────────────


def parse_url(url: str) -> list[tuple[str, dict[str, Any]]]:
    """Fetch an HTTP/HTTPS URL and return its text content as a single unit.

    Uses httpx (already a core dependency).  HTML is stripped to plain text via
    a lightweight regex approach so heavy deps (BeautifulSoup, lxml) are not needed.
    Raises RAGError if the URL cannot be fetched or returns non-200 status.
    """
    import re as _re

    try:
        import httpx
    except ImportError as exc:
        raise RAGError(
            "httpx not installed.",
            user_message="URL fetching requires httpx (it is a core anythink dependency).",
        ) from exc

    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RAGError(
            f"HTTP {exc.response.status_code} fetching {url}",
            user_message=f"Failed to fetch URL (HTTP {exc.response.status_code}): {url}",
        ) from exc
    except Exception as exc:
        raise RAGError(
            f"Cannot fetch {url}: {exc}",
            user_message=f"Failed to fetch URL: {url}",
        ) from exc

    raw_html = resp.text

    # Extract <title>
    title_m = _re.search(r"<title[^>]*>(.*?)</title>", raw_html, _re.I | _re.S)
    page_title = title_m.group(1).strip() if title_m else url

    # Strip <script> / <style> blocks first
    no_scripts = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=_re.I | _re.S)
    # Strip remaining HTML tags
    plain = _re.sub(r"<[^>]+>", " ", no_scripts)
    # Decode common HTML entities
    for entity, char in (
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " "),
    ):
        plain = plain.replace(entity, char)

    text = _preprocess(plain)

    meta: dict[str, Any] = {
        "source_path": url,
        "file_type": "url",
        "file_modified_at": 0.0,
        "source_url": url,
        "page_title": page_title,
    }
    return [(text, meta)] if text else []


# ── Dispatch table ────────────────────────────────────────────────────────────

_GENERIC_CODE_EXTS = frozenset(
    {".go", ".rs", ".java", ".cpp", ".c", ".h", ".cs", ".rb", ".swift", ".kt", ".php"}
)

_PARSER_MAP: dict[str, Callable[[Path], list[tuple[str, dict[str, Any]]]]] = {
    ".txt": parse_text,
    ".rst": parse_text,
    ".toml": parse_text,
    ".md": parse_markdown,
    ".mdx": parse_markdown,
    ".py": parse_python,
    ".js": parse_js,
    ".jsx": parse_js,
    ".ts": parse_js,
    ".tsx": parse_js,
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".csv": parse_csv,
    ".json": parse_json,
    ".yaml": parse_yaml_file,
    ".yml": parse_yaml_file,
}
# Add generic code parsers
for _ext in _GENERIC_CODE_EXTS:
    _PARSER_MAP[_ext] = parse_code_generic


def dispatch_parser(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Select and run the appropriate parser for *path* based on its extension."""
    parser = _PARSER_MAP.get(path.suffix.lower(), parse_text)
    return parser(path)


def is_url(s: str) -> bool:
    """Return True if *s* looks like an HTTP/HTTPS URL."""
    return s.startswith(("http://", "https://"))
