"""Tests for /rag command dispatch, sub-namespaces, and backward-compat aliases."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.config.schema import AppConfig
from anythink.rag.models import IndexInfo


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_ctx(
    *,
    active_rag: str | None = None,
    indexes: list[IndexInfo] | None = None,
) -> MagicMock:
    """Return a minimal AppContext mock sufficient for _rag() calls."""
    ctx = MagicMock()
    ctx.config = AppConfig(active_rag_index=active_rag)
    ctx.config_manager = MagicMock()
    ctx.config_manager.save = MagicMock()

    rm = MagicMock()
    rm.is_active = active_rag is not None
    rm.active_name = active_rag
    rm.list_indexes.return_value = indexes or []
    rm.get_info.return_value = None
    rm._last_results = []
    ctx.rag_manager = rm
    return ctx


def _make_state() -> MagicMock:
    return MagicMock()


def _make_registry() -> MagicMock:
    return MagicMock()


async def _call_rag(args: str, ctx: MagicMock | None = None) -> object:
    from anythink.commands.handlers import _rag

    if ctx is None:
        ctx = _make_ctx()
    return await _rag(ctx, args, _make_state(), _make_registry())


# ── /rag status ───────────────────────────────────────────────────────────────


class TestRagStatus:
    async def test_no_args_shows_status(self) -> None:
        result = await _call_rag("")
        assert result.error is False
        assert "inactive" in result.message.lower() or "rag" in result.message.lower()

    async def test_status_subcommand(self) -> None:
        result = await _call_rag("status")
        assert result.error is False

    async def test_active_index_shown_in_status(self) -> None:
        ctx = _make_ctx(active_rag="my-index")
        info = IndexInfo(
            name="my-index",
            index_type="document",
            source_path="/tmp",
            persistence_mode="rebuild",
        )
        ctx.rag_manager.get_info.return_value = info
        result = await _call_rag("status", ctx)
        assert "my-index" in result.message


# ── /rag on / off ─────────────────────────────────────────────────────────────


class TestRagOnOff:
    async def test_on_no_indexes(self) -> None:
        ctx = _make_ctx(indexes=[])
        result = await _call_rag("on", ctx)
        assert result.error is True

    async def test_on_with_active_index(self) -> None:
        ctx = _make_ctx(active_rag="myidx")
        ctx.rag_manager.use_index.return_value = True
        result = await _call_rag("on", ctx)
        assert result.error is False
        assert "myidx" in result.message

    async def test_off_deactivates(self) -> None:
        ctx = _make_ctx(active_rag="myidx")
        result = await _call_rag("off", ctx)
        assert result.error is False
        ctx.rag_manager.deactivate.assert_called_once()


# ── /rag index ────────────────────────────────────────────────────────────────


class TestRagIndexList:
    async def test_list_empty(self) -> None:
        result = await _call_rag("index list")
        assert result.error is False
        assert "no rag indexes" in result.message.lower() or "name" in result.message.lower()

    async def test_list_with_indexes(self) -> None:
        info = IndexInfo(
            name="docs",
            index_type="document",
            source_path="/data",
            persistence_mode="rebuild",
        )
        ctx = _make_ctx(indexes=[info])
        result = await _call_rag("index list", ctx)
        assert "docs" in result.message

    async def test_bare_index_shows_list(self) -> None:
        result = await _call_rag("index")
        assert result.error is False


class TestRagIndexUse:
    async def test_use_found(self) -> None:
        ctx = _make_ctx()
        ctx.rag_manager.use_index.return_value = True
        result = await _call_rag("index use myidx", ctx)
        assert result.error is False
        assert "myidx" in result.message
        ctx.rag_manager.use_index.assert_called_once_with("myidx")

    async def test_use_not_found(self) -> None:
        ctx = _make_ctx()
        ctx.rag_manager.use_index.return_value = False
        result = await _call_rag("index use missing", ctx)
        assert result.error is True

    async def test_use_no_args(self) -> None:
        result = await _call_rag("index use")
        assert result.error is True


class TestRagIndexDelete:
    async def test_delete_success(self) -> None:
        ctx = _make_ctx()
        result = await _call_rag("index delete oldidx", ctx)
        assert result.error is False
        ctx.rag_manager.delete_index.assert_called_once_with("oldidx")

    async def test_delete_no_args(self) -> None:
        result = await _call_rag("index delete")
        assert result.error is True

    async def test_delete_raises_rag_error(self) -> None:
        from anythink.exceptions import RAGError

        ctx = _make_ctx()
        ctx.rag_manager.delete_index.side_effect = RAGError("not found", user_message="Not found")
        result = await _call_rag("index delete nope", ctx)
        assert result.error is True


class TestRagIndexRebuild:
    async def test_rebuild_active(self) -> None:
        ctx = _make_ctx(active_rag="myidx")
        result = await _call_rag("index rebuild", ctx)
        assert result.error is False
        assert result.action == "rag_rebuild:myidx"

    async def test_rebuild_named(self) -> None:
        result = await _call_rag("index rebuild namedidx")
        assert result.action == "rag_rebuild:namedidx"

    async def test_rebuild_no_name_no_active(self) -> None:
        result = await _call_rag("index rebuild")
        assert result.error is True


class TestRagIndexRename:
    async def test_rename_success(self) -> None:
        ctx = _make_ctx()
        result = await _call_rag("index rename old new", ctx)
        assert result.error is False
        ctx.rag_manager.rename_index.assert_called_once_with("old", "new")

    async def test_rename_missing_new_name(self) -> None:
        result = await _call_rag("index rename justonearg")
        assert result.error is True


class TestRagIndexNew:
    async def test_new_no_args_returns_wizard_action(self) -> None:
        result = await _call_rag("index new")
        assert result.action == "rag_index_wizard"

    async def test_new_full_args_creates_index(self) -> None:
        ctx = _make_ctx()
        result = await _call_rag("index new myidx document /tmp", ctx)
        assert result.error is False
        ctx.rag_manager.create_index.assert_called_once()


# ── /rag ingest ───────────────────────────────────────────────────────────────


class TestRagIngest:
    async def test_ingest_no_active_index(self) -> None:
        result = await _call_rag("ingest")
        assert result.error is True

    async def test_ingest_incremental(self) -> None:
        ctx = _make_ctx(active_rag="myidx")
        result = await _call_rag("ingest", ctx)
        assert result.error is False
        assert "rag_ingest_start:myidx:incremental" in result.action

    async def test_ingest_full(self) -> None:
        ctx = _make_ctx(active_rag="myidx")
        result = await _call_rag("ingest --full", ctx)
        assert result.error is False
        assert "rag_rebuild:myidx" in result.action

    async def test_ingest_status(self) -> None:
        result = await _call_rag("ingest status")
        assert result.error is False

    async def test_ingest_history_no_active(self) -> None:
        result = await _call_rag("ingest history")
        assert result.error is True

    async def test_ingest_history_active(self) -> None:
        ctx = _make_ctx(active_rag="myidx")
        info = IndexInfo(
            name="myidx",
            index_type="document",
            source_path="/data",
            persistence_mode="rebuild",
            ingestion_history=[
                {
                    "timestamp": "2026-01-01T00:00:00",
                    "mode": "full",
                    "files_processed": 10,
                    "duration_s": 2.5,
                }
            ],
        )
        ctx.rag_manager.get_info.return_value = info
        result = await _call_rag("ingest history", ctx)
        assert result.error is False
        assert "full" in result.message

    async def test_ingest_path_no_active(self) -> None:
        result = await _call_rag("ingest --path /some/file.md")
        assert result.error is True

    async def test_ingest_path_with_active(self) -> None:
        ctx = _make_ctx(active_rag="myidx")
        result = await _call_rag("ingest --path /some/file.md", ctx)
        assert result.error is False
        assert "/some/file.md" in result.action


# ── /rag threshold ────────────────────────────────────────────────────────────


class TestRagThreshold:
    async def test_show_current_threshold(self) -> None:
        result = await _call_rag("threshold")
        assert result.error is False
        assert "0.65" in result.message

    async def test_set_threshold(self) -> None:
        ctx = _make_ctx()
        result = await _call_rag("threshold 0.75", ctx)
        assert result.error is False
        assert "0.75" in result.message

    async def test_invalid_threshold_string(self) -> None:
        result = await _call_rag("threshold notanumber")
        assert result.error is True

    async def test_threshold_out_of_range_high(self) -> None:
        result = await _call_rag("threshold 1.5")
        assert result.error is True

    async def test_threshold_out_of_range_low(self) -> None:
        result = await _call_rag("threshold -0.1")
        assert result.error is True

    async def test_threshold_boundary_zero(self) -> None:
        ctx = _make_ctx()
        result = await _call_rag("threshold 0.0", ctx)
        assert result.error is False

    async def test_threshold_boundary_one(self) -> None:
        ctx = _make_ctx()
        result = await _call_rag("threshold 1.0", ctx)
        assert result.error is False


# ── /rag query / chunks / sources / quality ──────────────────────────────────


class TestRagQuery:
    async def test_query_no_active_index(self) -> None:
        result = await _call_rag("query hello")
        assert result.error is True

    async def test_query_no_args(self) -> None:
        ctx = _make_ctx(active_rag="myidx")
        result = await _call_rag("query", ctx)
        assert result.error is True

    async def test_query_active_index(self) -> None:
        from anythink.rag.models import RetrievalResult

        ctx = _make_ctx(active_rag="myidx")
        mock_emb = MagicMock()
        ctx.embedding_registry.get_available.return_value = mock_emb
        ctx.rag_manager.retrieve = AsyncMock(
            return_value=[
                RetrievalResult(
                    source_path="file.py",
                    chunk_text="def hello(): pass",
                    relevance=0.9,
                    start_line=1,
                    end_line=1,
                )
            ]
        )
        result = await _call_rag("query hello world", ctx)
        assert result.error is False
        assert "file.py" in result.message


class TestRagChunks:
    async def test_no_results_yet(self) -> None:
        result = await _call_rag("chunks")
        assert result.error is False
        assert "no chunks" in result.message.lower() or "retrieved" in result.message.lower()

    async def test_shows_last_results(self) -> None:
        from anythink.rag.models import RetrievalResult

        ctx = _make_ctx(active_rag="myidx")
        ctx.rag_manager._last_results = [
            RetrievalResult(
                source_path="readme.md",
                chunk_text="This is a test chunk.",
                relevance=0.85,
            )
        ]
        result = await _call_rag("chunks", ctx)
        assert "readme.md" in result.message


class TestRagSources:
    async def test_no_results(self) -> None:
        result = await _call_rag("sources")
        assert result.error is False

    async def test_shows_sources(self) -> None:
        from anythink.rag.models import RetrievalResult

        ctx = _make_ctx()
        ctx.rag_manager._last_results = [
            RetrievalResult(
                source_path="notes.txt",
                chunk_text="some content",
                relevance=0.7,
            )
        ]
        result = await _call_rag("sources", ctx)
        assert "notes.txt" in result.message


class TestRagQuality:
    async def test_no_results(self) -> None:
        result = await _call_rag("quality")
        assert result.error is False

    async def test_quality_report(self) -> None:
        from anythink.rag.models import RetrievalResult

        ctx = _make_ctx()
        ctx.rag_manager._last_results = [
            RetrievalResult(source_path="a.py", chunk_text="x", relevance=0.90),
            RetrievalResult(source_path="b.py", chunk_text="y", relevance=0.75),
        ]
        result = await _call_rag("quality", ctx)
        assert result.error is False
        assert "confidence" in result.message.lower()
        assert "90%" in result.message or "STRONG" in result.message or "GOOD" in result.message


# ── /rag settings ─────────────────────────────────────────────────────────────


class TestRagSettings:
    async def test_settings_returns_action(self) -> None:
        result = await _call_rag("settings")
        assert result.action == "rag_settings_open"


# ── Backward-compat aliases ───────────────────────────────────────────────────


class TestBackwardCompatAliases:
    async def test_rag_list_alias(self) -> None:
        result = await _call_rag("list")
        assert result.error is False

    async def test_rag_info_no_arg(self) -> None:
        result = await _call_rag("info")
        assert result.error is True

    async def test_rag_use_alias(self) -> None:
        ctx = _make_ctx()
        ctx.rag_manager.use_index.return_value = True
        result = await _call_rag("use someidx", ctx)
        assert result.error is False

    async def test_rag_delete_alias(self) -> None:
        ctx = _make_ctx()
        result = await _call_rag("delete someidx", ctx)
        assert result.error is False
        ctx.rag_manager.delete_index.assert_called_once_with("someidx")

    async def test_rag_rebuild_alias(self) -> None:
        result = await _call_rag("rebuild myidx")
        assert result.action == "rag_rebuild:myidx"

    async def test_rag_new_alias_no_args_wizard(self) -> None:
        result = await _call_rag("new")
        assert result.action == "rag_index_wizard"

    async def test_unknown_subcommand_returns_error(self) -> None:
        result = await _call_rag("frobnicate")
        assert result.error is True
