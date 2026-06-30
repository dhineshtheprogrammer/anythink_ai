"""Tests for workflow/manifest.py — CapabilityManifest."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anythink.workflow.manifest import (
    CapabilityManifest,
    _is_destructive,
)
from anythink.workflow.models import StageType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_alias(alias: str, provider: str = "ollama", ctx_window: int = 32000, model_id: str = "mistral:7b") -> MagicMock:
    a = MagicMock()
    a.alias = alias
    a.provider = provider
    a.model_id = model_id
    a.context_window = ctx_window
    return a


def _make_tool(name: str, server: str, description: str = "A tool") -> MagicMock:
    t = MagicMock()
    t.name = name
    t.server_name = server
    t.description = description
    t.input_schema = {
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
    return t


def _make_registries_and_storage(
    aliases: list,
    tools: list,
    workflow_names: list[str],
) -> tuple:
    model_reg = MagicMock()
    model_reg.list_all.return_value = aliases

    mcp = MagicMock()
    mcp.list_tools.return_value = tools

    wf_reg = MagicMock()
    wf_reg.get_tags.return_value = ["summarization"]
    wf_reg.get_fallback_chain.return_value = []

    storage = MagicMock()
    storage.list_summaries.return_value = [
        {"name": n, "trigger": f"Run {n}", "stage_count": 3} for n in workflow_names
    ]

    return model_reg, mcp, wf_reg, storage


# ---------------------------------------------------------------------------
# _is_destructive
# ---------------------------------------------------------------------------


class TestIsDestructive:
    def test_write_file_is_destructive(self) -> None:
        assert _is_destructive("write_file") is True

    def test_delete_file_is_destructive(self) -> None:
        assert _is_destructive("delete_file") is True

    def test_send_email_is_destructive(self) -> None:
        assert _is_destructive("send_email") is True

    def test_list_dir_not_destructive(self) -> None:
        assert _is_destructive("list_dir") is False

    def test_read_file_not_destructive(self) -> None:
        assert _is_destructive("read_file") is False


# ---------------------------------------------------------------------------
# CapabilityManifest.build
# ---------------------------------------------------------------------------


class TestCapabilityManifestBuild:
    def test_contains_local_models_section(self, tmp_path: Path) -> None:
        manifest = CapabilityManifest(tmp_path / "manifest.txt")
        model_reg, mcp, wf_reg, storage = _make_registries_and_storage(
            [_make_alias("local-sum", provider="ollama")], [], []
        )
        text = manifest.build(model_reg, mcp, wf_reg, storage)
        assert "[LOCAL MODELS]" in text
        assert "local-sum" in text

    def test_cloud_model_in_cloud_section(self, tmp_path: Path) -> None:
        manifest = CapabilityManifest(tmp_path / "manifest.txt")
        model_reg, mcp, wf_reg, storage = _make_registries_and_storage(
            [_make_alias("gpt4o", provider="openai")], [], []
        )
        text = manifest.build(model_reg, mcp, wf_reg, storage)
        assert "[CLOUD MODELS]" in text
        assert "gpt4o" in text

    def test_mcp_tools_section(self, tmp_path: Path) -> None:
        manifest = CapabilityManifest(tmp_path / "manifest.txt")
        model_reg, mcp, wf_reg, storage = _make_registries_and_storage(
            [], [_make_tool("read_file", "filesystem")], []
        )
        text = manifest.build(model_reg, mcp, wf_reg, storage)
        assert "[MCP TOOLS]" in text
        assert "read_file" in text
        assert "filesystem" in text

    def test_destructive_tool_flagged(self, tmp_path: Path) -> None:
        manifest = CapabilityManifest(tmp_path / "manifest.txt")
        model_reg, mcp, wf_reg, storage = _make_registries_and_storage(
            [], [_make_tool("write_file", "filesystem")], []
        )
        text = manifest.build(model_reg, mcp, wf_reg, storage)
        assert "DESTRUCTIVE" in text

    def test_stage_types_section(self, tmp_path: Path) -> None:
        manifest = CapabilityManifest(tmp_path / "manifest.txt")
        model_reg, mcp, wf_reg, storage = _make_registries_and_storage([], [], [])
        text = manifest.build(model_reg, mcp, wf_reg, storage)
        assert "[STAGE TYPES]" in text
        for stype in StageType:
            assert stype.value in text

    def test_saved_workflows_section(self, tmp_path: Path) -> None:
        manifest = CapabilityManifest(tmp_path / "manifest.txt")
        model_reg, mcp, wf_reg, storage = _make_registries_and_storage(
            [], [], ["email-summary", "code-review"]
        )
        text = manifest.build(model_reg, mcp, wf_reg, storage)
        assert "[SAVED WORKFLOWS]" in text
        assert "email-summary" in text
        assert "code-review" in text

    def test_anythink_capabilities_section(self, tmp_path: Path) -> None:
        manifest = CapabilityManifest(tmp_path / "manifest.txt")
        model_reg, mcp, wf_reg, storage = _make_registries_and_storage([], [], [])
        text = manifest.build(model_reg, mcp, wf_reg, storage)
        assert "[ANYTHINK CAPABILITIES]" in text
        assert "rag_search" in text
        assert "web_search" in text

    def test_empty_mcp_tools_shows_none(self, tmp_path: Path) -> None:
        manifest = CapabilityManifest(tmp_path / "manifest.txt")
        model_reg, mcp, wf_reg, storage = _make_registries_and_storage([], [], [])
        text = manifest.build(model_reg, mcp, wf_reg, storage)
        assert "(none)" in text


# ---------------------------------------------------------------------------
# CapabilityManifest.refresh and load
# ---------------------------------------------------------------------------


class TestCapabilityManifestIO:
    def test_refresh_writes_file(self, tmp_path: Path) -> None:
        path = tmp_path / "manifest.txt"
        manifest = CapabilityManifest(path)
        model_reg, mcp, wf_reg, storage = _make_registries_and_storage([], [], [])
        manifest.refresh(model_reg, mcp, wf_reg, storage)
        assert path.exists()

    def test_load_returns_written_text(self, tmp_path: Path) -> None:
        path = tmp_path / "manifest.txt"
        manifest = CapabilityManifest(path)
        model_reg, mcp, wf_reg, storage = _make_registries_and_storage([], [], [])
        manifest.refresh(model_reg, mcp, wf_reg, storage)
        loaded = manifest.load()
        assert "[STAGE TYPES]" in loaded

    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        manifest = CapabilityManifest(tmp_path / "no-manifest.txt")
        assert manifest.load() == ""

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "dir" / "manifest.txt"
        manifest = CapabilityManifest(path)
        model_reg, mcp, wf_reg, storage = _make_registries_and_storage([], [], [])
        manifest.refresh(model_reg, mcp, wf_reg, storage)
        assert path.exists()
