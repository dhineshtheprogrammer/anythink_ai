"""Tests for session export formats."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anythink.exceptions import ExportError
from anythink.export.formats import export_json, export_markdown, export_pdf
from anythink.providers.base import ChatMessage


def _make_session(tmp_path: Path) -> MagicMock:
    from anythink.session.models import Session

    messages = [
        ChatMessage(role="user", content="Hello AI"),
        ChatMessage(role="assistant", content="Hello! How can I help?"),
    ]
    return Session(
        id="test-session-id",
        provider="openai",
        model_id="gpt-4o",
        name="Test Session",
        messages=messages,
    )


class TestExportMarkdown:
    def test_creates_file(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        out = tmp_path / "export.md"
        export_markdown(session, out)
        assert out.exists()

    def test_contains_model(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        out = tmp_path / "export.md"
        export_markdown(session, out)
        content = out.read_text()
        assert "gpt-4o" in content

    def test_contains_messages(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        out = tmp_path / "export.md"
        export_markdown(session, out)
        content = out.read_text()
        assert "Hello AI" in content
        assert "Hello! How can I help?" in content

    def test_message_range(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        out = tmp_path / "export.md"
        export_markdown(session, out, message_range=(0, 1))
        content = out.read_text()
        assert "Hello AI" in content
        # Second message should not be present
        assert "How can I help?" not in content


class TestExportJson:
    def test_creates_valid_json(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        out = tmp_path / "export.json"
        export_json(session, out)
        data = json.loads(out.read_text())
        assert data["id"] == "test-session-id"
        assert data["model_id"] == "gpt-4o"
        assert len(data["messages"]) == 2

    def test_json_message_range(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        out = tmp_path / "export.json"
        export_json(session, out, message_range=(0, 1))
        data = json.loads(out.read_text())
        assert len(data["messages"]) == 1


class TestExportPdf:
    def test_raises_when_fpdf2_missing(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        out = tmp_path / "export.pdf"
        with pytest.raises(ExportError, match="fpdf2"), pytest.MonkeyPatch.context() as mp:
            mp.setitem(sys.modules, "fpdf", None)  # type: ignore[arg-type]
            export_pdf(session, out)

    def test_creates_pdf_when_fpdf2_available(self, tmp_path: Path) -> None:
        # Only run if fpdf2 is installed
        pytest.importorskip("fpdf")
        session = _make_session(tmp_path)
        out = tmp_path / "export.pdf"
        export_pdf(session, out)
        assert out.exists()
        assert out.stat().st_size > 0


# ── V4 MMOS export tests ───────────────────────────────────────────────────────


def _make_session_with_mmos(tmp_path: Path) -> MagicMock:
    """Session with an AI message that carries MMOS metadata."""
    from anythink.session.models import Session

    mmos_meta = {
        "strategy": "ensemble",
        "model_ids": ["groq/llama3-70b", "ollama/mistral"],
        "total_tokens": 2500,
        "elapsed_s": 3.2,
        "intent": None,
        "routing_decision": None,
        "plan_session_id": None,
        "phase_outputs": [],
    }
    messages = [
        ChatMessage(role="user", content="Tell me about Python", metadata={}),
        ChatMessage(
            role="assistant",
            content="Python is a great language!",
            metadata={"mmos": mmos_meta},
        ),
    ]
    return Session(
        id="mmos-session",
        provider="groq",
        model_id="llama3-70b",
        name="MMOS Session",
        messages=messages,
    )


class TestExportJsonWithMMOS:
    def test_mmos_metadata_included_in_assistant_message(self, tmp_path: Path) -> None:
        session = _make_session_with_mmos(tmp_path)
        out = tmp_path / "export_mmos.json"
        export_json(session, out)
        data = json.loads(out.read_text())
        ai_msg = next(m for m in data["messages"] if m["role"] == "assistant")
        assert "mmos" in ai_msg
        assert ai_msg["mmos"]["strategy"] == "ensemble"
        assert ai_msg["mmos"]["total_tokens"] == 2500

    def test_user_message_has_no_mmos_key(self, tmp_path: Path) -> None:
        session = _make_session_with_mmos(tmp_path)
        out = tmp_path / "export_mmos.json"
        export_json(session, out)
        data = json.loads(out.read_text())
        user_msg = next(m for m in data["messages"] if m["role"] == "user")
        assert "mmos" not in user_msg

    def test_message_without_mmos_has_no_mmos_key(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)  # uses the plain session without MMOS
        out = tmp_path / "export_no_mmos.json"
        export_json(session, out)
        data = json.loads(out.read_text())
        for msg in data["messages"]:
            assert "mmos" not in msg

    def test_model_ids_preserved(self, tmp_path: Path) -> None:
        session = _make_session_with_mmos(tmp_path)
        out = tmp_path / "export_mmos.json"
        export_json(session, out)
        data = json.loads(out.read_text())
        ai_msg = next(m for m in data["messages"] if m["role"] == "assistant")
        assert ai_msg["mmos"]["model_ids"] == ["groq/llama3-70b", "ollama/mistral"]


class TestExportMarkdownWithMMOS:
    def test_attribution_header_in_assistant_section(self, tmp_path: Path) -> None:
        session = _make_session_with_mmos(tmp_path)
        out = tmp_path / "export_mmos.md"
        export_markdown(session, out)
        content = out.read_text()
        # Attribution header should appear in markdown for AI turns
        assert "ensemble" in content
        assert "groq/llama3-70b" in content

    def test_message_content_still_present(self, tmp_path: Path) -> None:
        session = _make_session_with_mmos(tmp_path)
        out = tmp_path / "export_mmos.md"
        export_markdown(session, out)
        content = out.read_text()
        assert "Python is a great language!" in content
