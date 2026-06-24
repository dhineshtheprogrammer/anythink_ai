# `src/anythink/export` — Session Export Module

## Purpose

The `export` package serialises a live Anythink chat session into a portable external file. Three formats are supported — **Markdown**, **JSON**, and **PDF** — selectable at call time. The package is intentionally thin: it contains no state, no registry, no CLI wiring. All orchestration (argument parsing, path resolution, session assembly) lives in the `/export` slash-command handler in `commands/handlers.py:_export()`. This package only does the write.

| File | Role |
|---|---|
| `__init__.py` | Package marker |
| `formats.py` | All three export functions + private helpers |

---

## File: `__init__.py`

**Full path:** `src/anythink/export/__init__.py`

```python
"""Session export functionality for Anythink."""
```

Empty beyond its module docstring. Makes `src/anythink/export/` a valid Python package so `from anythink.export.formats import ...` works. No symbols are re-exported here.

---

## File: `formats.py`

**Full path:** `src/anythink/export/formats.py`

Contains all export logic. Imports are kept minimal: only `json`, `pathlib.Path`, `ExportError`, and `TextPart`. The `Session` type is imported under `TYPE_CHECKING` only, so this module loads with zero runtime overhead from the session layer.

---

### Private helper: `_get_messages(session, message_range)`

```python
def _get_messages(session: Session, message_range: tuple[int, int] | None) -> list[Any]
```

Slices `session.messages` by the optional `message_range` tuple `(start, end)`. Indices follow Python slice semantics (`start` is inclusive, `end` is exclusive). Negative `start` is clamped to 0 via `max(0, start)`. When `message_range` is `None`, all messages are returned unchanged. All three public export functions call this first.

---

### Private helper: `_content_to_text(content)`

```python
def _content_to_text(content: Any) -> str
```

Converts a `ChatMessage.content` value — which can be a plain `str`, a `list[TextPart | ImagePart]`, or something unknown — into a plain string suitable for file output.

| Input type | Output |
|---|---|
| `str` | Returned as-is |
| `list` | Each element joined with a space; `TextPart` items emit `.text`, everything else emits the literal string `"[image]"` |
| Anything else | `str(content)` fallback |

This means image attachments in multimodal turns are represented as the placeholder `[image]` in exported files. No binary data is written.

---

### Private helper: `_mmos_header_text(mmos_raw)`

```python
def _mmos_header_text(mmos_raw: dict[str, Any]) -> str
```

Produces a single attribution line from a raw MMOS (Multi-Model Orchestration System) metadata dictionary that is stored in `ChatMessage.metadata["mmos"]` when V4 multi-model routing was active during a turn.

**Fields read from `mmos_raw`:**

| Key | Default | Usage |
|---|---|---|
| `"strategy"` | `"routing"` | The routing strategy used (e.g. `"ensemble"`, `"decompose"`, `"plan"`) |
| `"model_ids"` | `[]` | List of model IDs that contributed; first three are shown |
| `"total_tokens"` | `0` | Combined token count across all models |
| `"elapsed_s"` | `0.0` | Wall-clock seconds the full MMOS turn took |

**Output format:**

```
── groq/llama3-70b, ollama/mistral  ·  ensemble  ·  2,500 tokens  ·  3.2s ──
```

Called by `export_markdown()` to prepend an attribution line before the message text on AI turns that carry MMOS metadata.

---

### Public function: `export_markdown(session, path, *, message_range=None)`

```python
def export_markdown(
    session: Session,
    path: Path,
    *,
    message_range: tuple[int, int] | None = None,
) -> None
```

Writes the session as a human-readable Markdown file.

**Output structure:**

```markdown
# <session name or id>

**Date:** 2025-06-24 14:30
**Model:** claude-sonnet-4-6
**Provider:** anthropic

---

### **You**

Hello AI

---

### **AI**

*── claude-sonnet-4-6  ·  ensemble  ·  1,234 tokens  ·  1.5s ──*

Hello! How can I help?

---
```

**Role label mapping:**

| `msg.role` | Rendered label |
|---|---|
| `"user"` | `**You**` |
| `"assistant"` | `**AI**` |
| `"system"` | `_System_` |
| anything else | `**<role>**` |

**MMOS attribution (V4):** If a message has role `"assistant"` and `msg.metadata["mmos"]` is present, `_mmos_header_text()` is called and the result is inserted as an italic line (`*...*`) directly before the message text.

**File creation:** `path.parent.mkdir(parents=True, exist_ok=True)` is called before writing, so the destination directory is created automatically if it does not exist. The file is written as UTF-8.

---

### Public function: `export_json(session, path, *, message_range=None)`

```python
def export_json(
    session: Session,
    path: Path,
    *,
    message_range: tuple[int, int] | None = None,
) -> None
```

Writes the session as a structured, machine-readable JSON file.

**Top-level JSON schema:**

```json
{
  "id": "string — session UUID",
  "name": "string | null — human-assigned session name",
  "provider": "string — provider key (e.g. 'anthropic')",
  "model_id": "string — model alias or full model ID",
  "created_at": "ISO 8601 datetime",
  "updated_at": "ISO 8601 datetime",
  "message_count": "integer — number of messages included (after any range slice)",
  "messages": [ ... ]
}
```

**Per-message schema:**

```json
{
  "role": "user | assistant | system",
  "content": "plain text (images become '[image]')",
  "timestamp": "ISO 8601 datetime",
  "mmos": { ... }  // optional — only present for assistant turns with MMOS metadata
}
```

**MMOS metadata (V4):** When `msg.metadata["mmos"]` exists on an assistant message, the full raw dictionary is included under the `"mmos"` key. User and system messages never carry this key. The dict shape mirrors what `_mmos_header_text()` reads, plus additional V4 fields (`intent`, `routing_decision`, `plan_session_id`, `phase_outputs`).

**File creation:** Same `path.parent.mkdir(parents=True, exist_ok=True)` guard as `export_markdown()`. Output is indented with 2 spaces and written as UTF-8 with `ensure_ascii=False` so non-ASCII characters (e.g. CJK, emoji) are preserved verbatim.

---

### Public function: `export_pdf(session, path, *, message_range=None)`

```python
def export_pdf(
    session: Session,
    path: Path,
    *,
    message_range: tuple[int, int] | None = None,
) -> None
```

Writes the session as a typeset PDF file.

**Optional dependency:** Requires `fpdf2`. The import is deferred inside the function body:

```python
try:
    from fpdf import FPDF
except ImportError as e:
    raise ExportError(
        "fpdf2 is not installed",
        user_message="Install PDF support with: pip install anythink[pdf]",
    ) from e
```

If `fpdf2` is absent, `ExportError` is raised immediately with a user-friendly install hint. The caller (the `/export` command handler) surfaces this as an error message in the TUI without crashing.

**PDF layout:**

| Section | Font | Size | Notes |
|---|---|---|---|
| Title (session name/id) | Helvetica Bold | 16pt | First line |
| Metadata line | Helvetica | 10pt | `Model: X  \|  Provider: Y` |
| Date line | Helvetica | 10pt | `Date: YYYY-MM-DD HH:MM` |
| Role label per turn | Helvetica Bold | 10pt | "You", "AI", or "System" |
| Message body | Helvetica | 10pt | `multi_cell` for word-wrap |

**Character encoding:** `fpdf2`'s default Latin-1 page encoding cannot represent all Unicode characters. The text is re-encoded with `encode("latin-1", errors="replace").decode("latin-1")` so unrepresentable characters are silently replaced rather than crashing. This is a known limitation of basic PDF export — for full Unicode support, a TTF font would need to be embedded.

**Note:** MMOS attribution is not rendered in the PDF format (only in Markdown). This is an intentional omission; the PDF layout is kept simple.

**File creation:** Same `path.parent.mkdir(parents=True, exist_ok=True)` guard. `pdf.output(str(path))` writes the binary PDF.

---

## How the module is called

The only production call site is `commands/handlers.py:_export()`, which is wired to the `/export` slash command.

**Slash command usage:**

```
/export [markdown|md|json|pdf] [output_path] [--range N-M]
```

**Argument parsing in `_export()`:**

| Token | Effect |
|---|---|
| `markdown` or `md` | Selects Markdown format (default) |
| `json` | Selects JSON format |
| `pdf` | Selects PDF format |
| `--range N-M` | Exports only messages N through M (1-based, converted to 0-based slice internally) |
| Any other non-flag token | Treated as the output file path |

**Default output path:** If no path is given, the file is written to `$XDG_DATA_HOME/anythink/exports/<session_id>.<ext>`, where `<ext>` is `md`, `json`, or `pdf`. The `exports_dir` is created if it does not exist.

**Session assembly:** `_build_session(state)` from `app/chat.py` is called immediately before export to serialise the current in-memory chat state (including the active branch) into a `Session` object. This snapshot is what gets exported.

**Error handling:** Any exception from the three export functions is caught and returned as a `CommandResult(error=True, message=...)`, so failures are shown inline in the TUI rather than crashing.

---

## Exception

```python
class ExportError(AnythinkError):
    """Raised when a session export fails."""
```

Defined in `exceptions.py`. Currently only raised by `export_pdf()` when `fpdf2` is not installed. Carries both an internal `message` (for logging) and a `user_message` (shown in the terminal). Inherits from `AnythinkError`.

---

## Storage location

| Export type | Default path |
|---|---|
| Markdown | `$XDG_DATA_HOME/anythink/exports/<session_id>.md` |
| JSON | `$XDG_DATA_HOME/anythink/exports/<session_id>.json` |
| PDF | `$XDG_DATA_HOME/anythink/exports/<session_id>.pdf` |

The `exports/` directory is created lazily on first use.

---

## Tests

**Test file:** `tests/test_export/test_formats.py`

All tests use a temporary directory via pytest's `tmp_path` fixture and a `_make_session()` factory that builds a real `Session` object with two `ChatMessage` instances (one user, one assistant). V4 MMOS tests use a separate `_make_session_with_mmos()` factory that adds `metadata={"mmos": {...}}` to the assistant message.

| Test class | What is covered |
|---|---|
| `TestExportMarkdown` | File is created; model ID and message content appear in output; `message_range` slicing excludes out-of-range messages |
| `TestExportJson` | Output parses as valid JSON; `id` and `model_id` fields are correct; `message_count` reflects slice |
| `TestExportPdf` | `ExportError` raised when `fpdf` module is patched to `None`; PDF file is created and non-empty when `fpdf2` is installed (skipped otherwise) |
| `TestExportJsonWithMMOS` | MMOS dict present on assistant message; absent on user message; absent when session has no MMOS metadata; `model_ids` list preserved verbatim |
| `TestExportMarkdownWithMMOS` | Attribution header (strategy + model IDs) appears in markdown output; message content still present alongside it |

---

## Dependency summary

| Dependency | Type | Used for |
|---|---|---|
| `json` (stdlib) | Core | JSON serialisation in `export_json()` |
| `pathlib.Path` (stdlib) | Core | File path handling, `mkdir`, `write_text` |
| `anythink.exceptions.ExportError` | Internal | Raised on missing `fpdf2` |
| `anythink.providers.base.TextPart` | Internal | Type check in `_content_to_text()` |
| `anythink.session.models.Session` | Internal (TYPE_CHECKING only) | Type annotation — no runtime import |
| `fpdf2` (optional extra `[pdf]`) | Optional | PDF generation in `export_pdf()` |

---

## Adding a new export format

1. Add a new function `export_<format>(session, path, *, message_range=None) -> None` to `formats.py` following the same signature contract.
2. Call `_get_messages(session, message_range)` to apply the range slice.
3. Use `_content_to_text(msg.content)` to extract text from each message.
4. Guard any optional dependency with a `try/except ImportError` that raises `ExportError` with a `user_message` install hint.
5. Call `path.parent.mkdir(parents=True, exist_ok=True)` before writing.
6. Register the new token in `_export()` in `commands/handlers.py` (the `tok in (...)` check and the `ext_map` dict).
