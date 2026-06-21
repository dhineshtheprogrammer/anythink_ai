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
