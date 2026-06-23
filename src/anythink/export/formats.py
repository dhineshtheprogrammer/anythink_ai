"""Session export in Markdown, JSON, and PDF formats."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from anythink.exceptions import ExportError
from anythink.providers.base import TextPart

if TYPE_CHECKING:
    from anythink.session.models import Session


def _get_messages(session: Session, message_range: tuple[int, int] | None) -> list[Any]:
    msgs = session.messages
    if message_range is not None:
        start, end = message_range
        msgs = msgs[max(0, start) : end]
    return msgs


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.text if isinstance(p, TextPart) else "[image]" for p in content)
    return str(content)


def _mmos_header_text(mmos_raw: dict[str, Any]) -> str:
    """Produce a plain-text attribution line from a raw MMOS metadata dict."""
    strategy = mmos_raw.get("strategy", "routing")
    model_ids = mmos_raw.get("model_ids", [])
    total_tokens = mmos_raw.get("total_tokens", 0)
    elapsed_s = mmos_raw.get("elapsed_s", 0.0)
    models_str = ", ".join(model_ids[:3]) if model_ids else "?"
    return f"── {models_str}  ·  {strategy}  ·  {total_tokens:,} tokens  ·  {elapsed_s:.1f}s ──"


def export_markdown(
    session: Session,
    path: Path,
    *,
    message_range: tuple[int, int] | None = None,
) -> None:
    """Export session as a Markdown file."""
    lines: list[str] = [
        f"# {session.name or session.id}",
        "",
        f"**Date:** {session.created_at.strftime('%Y-%m-%d %H:%M')}",
        f"**Model:** {session.model_id}",
        f"**Provider:** {session.provider}",
        "",
        "---",
        "",
    ]

    for msg in _get_messages(session, message_range):
        role_label = {"user": "**You**", "assistant": "**AI**", "system": "_System_"}.get(
            msg.role, f"**{msg.role}**"
        )
        text = _content_to_text(msg.content)
        lines.append(f"### {role_label}")
        lines.append("")
        # V4: prepend MMOS attribution header for AI turns that have metadata
        mmos_raw = msg.metadata.get("mmos") if hasattr(msg, "metadata") else None
        if mmos_raw and msg.role == "assistant":
            lines.append(f"*{_mmos_header_text(mmos_raw)}*")
            lines.append("")
        lines.append(text)
        lines.append("")
        lines.append("---")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def export_json(
    session: Session,
    path: Path,
    *,
    message_range: tuple[int, int] | None = None,
) -> None:
    """Export session as a structured JSON file."""
    messages = _get_messages(session, message_range)
    def _msg_dict(msg: Any) -> dict[str, Any]:
        d: dict[str, Any] = {
            "role": msg.role,
            "content": _content_to_text(msg.content),
            "timestamp": msg.timestamp.isoformat(),
        }
        # V4: include MMOS metadata when present
        mmos_raw = msg.metadata.get("mmos") if hasattr(msg, "metadata") else None
        if mmos_raw:
            d["mmos"] = mmos_raw
        return d

    data: dict[str, Any] = {
        "id": session.id,
        "name": session.name,
        "provider": session.provider,
        "model_id": session.model_id,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "messages": [_msg_dict(msg) for msg in messages],
        "message_count": len(messages),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def export_pdf(
    session: Session,
    path: Path,
    *,
    message_range: tuple[int, int] | None = None,
) -> None:
    """Export session as a PDF file. Requires the ``pdf`` optional extra."""
    try:
        from fpdf import FPDF
    except ImportError as e:
        raise ExportError(
            "fpdf2 is not installed",
            user_message="Install PDF support with: pip install anythink[pdf]",
        ) from e

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, session.name or session.id, ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Model: {session.model_id}  |  Provider: {session.provider}", ln=True)
    pdf.cell(0, 6, f"Date: {session.created_at.strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.ln(4)

    for msg in _get_messages(session, message_range):
        role_label = {"user": "You", "assistant": "AI", "system": "System"}.get(msg.role, msg.role)
        text = _content_to_text(msg.content)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, role_label, ln=True)
        pdf.set_font("Helvetica", "", 10)
        # multi_cell handles word wrap
        safe_text = text.encode("latin-1", errors="replace").decode("latin-1")
        pdf.multi_cell(0, 5, safe_text)
        pdf.ln(3)

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
