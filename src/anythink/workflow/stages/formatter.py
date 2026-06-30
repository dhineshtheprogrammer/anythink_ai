"""FORMATTER stage executor — pure Python format conversion, no LLM or MCP."""

from __future__ import annotations

import csv
import io
import json
import re
import time
from typing import TYPE_CHECKING, Any

from anythink.workflow.models import StageResult, StageType

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.workflow.models import Stage, WorkflowCallbacks, WorkflowState

SUPPORTED_FORMATS = frozenset(["markdown", "plain_text", "json", "csv", "html", "numbered_list"])


async def execute(
    stage: Stage,
    state: WorkflowState,
    ctx: AppContext,
    callbacks: WorkflowCallbacks,
) -> StageResult:
    """Execute a FORMATTER stage by converting content to the target format."""
    start = time.monotonic()

    raw_input = _gather_input(stage, state)
    target_format = stage.expected_format or "plain_text"

    try:
        formatted = _format(raw_input, target_format)
        error: str | None = None
    except Exception as exc:
        formatted = raw_input
        error = f"Formatting to '{target_format}' failed: {exc}"

    output: dict[str, Any] = (
        {stage.output_field: formatted} if stage.output_field else {"formatted": formatted}
    )

    return StageResult(
        stage_id=stage.id,
        stage_type=StageType.FORMATTER,
        output=output,
        raw_content=formatted,
        duration_s=time.monotonic() - start,
        error=error,
    )


def _gather_input(stage: Stage, state: WorkflowState) -> str:
    """Collect text from input_refs, or fall back to the last stage's raw_content."""
    parts: list[str] = []
    for ref in stage.input_refs:
        value = state.resolve_ref(ref)
        if value is not None:
            parts.append(str(value))
    if not parts and state.completed_stages:
        parts.append(state.completed_stages[-1].raw_content)
    return "\n\n".join(parts)


def _format(text: str, target_format: str) -> str:
    """Dispatch to the appropriate converter."""
    converters = {
        "markdown": _to_markdown,
        "plain_text": _to_plain,
        "json": _to_json,
        "csv": _to_csv,
        "html": _to_html,
        "numbered_list": _to_numbered_list,
    }
    fn = converters.get(target_format)
    return fn(text) if fn else text


def _to_markdown(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("#") or "**" in stripped or re.search(r"^- ", stripped, re.M):
        return stripped
    return "\n\n".join(p.strip() for p in stripped.split("\n\n") if p.strip())


def _to_plain(text: str) -> str:
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


def _to_json(text: str) -> str:
    try:
        data = json.loads(text)
        return json.dumps(data, indent=2)
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"content": text})


def _to_csv(text: str) -> str:
    try:
        data = json.loads(text)
        if isinstance(data, list) and data:
            buf = io.StringIO()
            if isinstance(data[0], dict):
                writer = csv.DictWriter(buf, fieldnames=list(data[0].keys()))
                writer.writeheader()
                writer.writerows(data)
            else:
                w = csv.writer(buf)
                for item in data:
                    w.writerow([item])
            return buf.getvalue().strip()
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    buf = io.StringIO()
    w = csv.writer(buf)
    for line in lines:
        w.writerow([line])
    return buf.getvalue().strip()


def _to_html(text: str) -> str:
    lines = text.strip().splitlines()
    html_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            html_lines.append("<br>")
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if m:
            lvl = len(m.group(1))
            html_lines.append(f"<h{lvl}>{m.group(2)}</h{lvl}>")
        elif stripped.startswith(("- ", "* ")):
            html_lines.append(f"<li>{stripped[2:]}</li>")
        else:
            html_lines.append(f"<p>{stripped}</p>")
    return "\n".join(html_lines)


def _to_numbered_list(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    clean: list[str] = []
    for line in lines:
        m = re.match(r"^\d+[\.\)]\s+(.+)$", line)
        if m:
            clean.append(m.group(1))
        elif line.startswith(("- ", "* ")):
            clean.append(line[2:])
        else:
            clean.append(line)
    return "\n".join(f"{i + 1}. {ln}" for i, ln in enumerate(clean))
