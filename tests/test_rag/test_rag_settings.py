"""Tests for RAG settings panel value logic (Phase 7).

Tests the read/write helpers and value-cycling logic in RAGSettingsMenu
without spinning up a live Textual TUI.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from anythink.config.schema import AppConfig
from anythink.rag.models import IndexInfo
from anythink.ui.textual.rag_settings import _NAVIGABLE, _RAG_ROWS, RAGSettingsMenu


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_info(**overrides: object) -> IndexInfo:
    defaults: dict = dict(
        name="test-idx",
        index_type="document",
        source_path="/data/docs",
        persistence_mode="persist",
        chunk_strategy="fixed",
        chunk_size=512,
        chunk_overlap=100,
        embedding_backend="local",
        retrieval_strategy="vector",
        reranking_enabled=False,
        reranking_model="bge-reranker-base",
        quality_threshold=0.65,
        top_k=3,
        vector_backend="pure",
    )
    defaults.update(overrides)
    return IndexInfo(**defaults)  # type: ignore[arg-type]


def _make_ctx(info: IndexInfo | None = None) -> MagicMock:
    ctx = MagicMock()
    cfg = AppConfig()
    ctx.config = cfg
    ctx.config_manager = MagicMock()
    ctx.config_manager.save = MagicMock()

    rm = MagicMock()
    rm.active_name = info.name if info else None
    rm.get_info.return_value = info
    rm.list_indexes.return_value = [info] if info else []
    ctx.rag_manager = rm

    registry = MagicMock()
    registry.names.return_value = ["mock", "local"]
    ctx.embedding_registry = registry

    return ctx


def _make_menu(ctx: MagicMock) -> RAGSettingsMenu:
    from anythink.ui.theme import MIDNIGHT

    return RAGSettingsMenu(ctx, MIDNIGHT)


# ── Row definitions ───────────────────────────────────────────────────────────


class TestRowDefinitions:
    def test_navigable_rows_exclude_sections(self) -> None:
        sections = [i for i, (_, src, _, _, _) in enumerate(_RAG_ROWS) if src == "section"]
        for s in sections:
            assert s not in _NAVIGABLE

    def test_navigable_rows_nonempty(self) -> None:
        assert len(_NAVIGABLE) > 0

    def test_all_fields_are_strings(self) -> None:
        for label, source, field, choices, rebuild in _RAG_ROWS:
            assert isinstance(label, str)
            assert isinstance(source, str)
            assert isinstance(field, str)
            assert isinstance(rebuild, bool)

    def test_rebuild_rows_have_index_source(self) -> None:
        for label, source, field, choices, rebuild in _RAG_ROWS:
            if rebuild:
                # Only index-level settings require rebuild
                assert source in ("index", "index_sel")

    def test_chunk_strategy_row_has_6_choices(self) -> None:
        for label, source, field, choices, _ in _RAG_ROWS:
            if field == "chunk_strategy":
                assert choices is not None
                assert len(choices) == 6
                break


# ── RAGSettingsMenu._read_value ───────────────────────────────────────────────


class TestReadValue:
    def test_reads_index_string_field(self) -> None:
        info = _make_info(chunk_strategy="sentence")
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        val = menu._read_value("index", "chunk_strategy")
        assert val == "sentence"

    def test_reads_index_int_field(self) -> None:
        info = _make_info(chunk_size=256)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        val = menu._read_value("index", "chunk_size")
        assert val == "256"

    def test_reads_index_bool_field_as_on_off(self) -> None:
        info = _make_info(reranking_enabled=True)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        val = menu._read_value("index", "reranking_enabled")
        assert val == "on"

    def test_reads_index_float_field(self) -> None:
        info = _make_info(quality_threshold=0.75)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        val = menu._read_value("index", "quality_threshold")
        assert "0.75" in val

    def test_reads_config_bool_as_on_off(self) -> None:
        ctx = _make_ctx()
        menu = _make_menu(ctx)
        val = menu._read_value("config", "rag_quality_indicators")
        assert val in ("on", "off")

    def test_no_active_index_returns_placeholder(self) -> None:
        ctx = _make_ctx(info=None)
        menu = _make_menu(ctx)
        val = menu._read_value("index", "chunk_strategy")
        assert "no active" in val.lower()

    def test_readonly_idx_returns_value(self) -> None:
        info = _make_info(source_path="/my/docs")
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        val = menu._read_value("readonly_idx", "source_path")
        assert "/my/docs" in val


# ── RAGSettingsMenu._nudge_numeric ────────────────────────────────────────────


class TestNudgeNumeric:
    def test_chunk_size_increments_by_64(self) -> None:
        info = _make_info(chunk_size=512)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        new = menu._nudge_numeric("index", "chunk_size", 1, info)
        assert new == 576

    def test_chunk_size_decrements_by_64(self) -> None:
        info = _make_info(chunk_size=512)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        new = menu._nudge_numeric("index", "chunk_size", -1, info)
        assert new == 448

    def test_chunk_size_clamped_at_256(self) -> None:
        info = _make_info(chunk_size=256)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        new = menu._nudge_numeric("index", "chunk_size", -1, info)
        assert new == 256

    def test_chunk_size_clamped_at_2048(self) -> None:
        info = _make_info(chunk_size=2048)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        new = menu._nudge_numeric("index", "chunk_size", 1, info)
        assert new == 2048

    def test_top_k_increments_by_1(self) -> None:
        info = _make_info(top_k=3)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        new = menu._nudge_numeric("index", "top_k", 1, info)
        assert new == 4

    def test_top_k_clamped_at_20(self) -> None:
        info = _make_info(top_k=20)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        new = menu._nudge_numeric("index", "top_k", 1, info)
        assert new == 20

    def test_quality_threshold_increments_by_005(self) -> None:
        info = _make_info(quality_threshold=0.65)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        new = menu._nudge_numeric("index", "quality_threshold", 1, info)
        assert new == pytest.approx(0.70)

    def test_quality_threshold_clamped_at_0(self) -> None:
        info = _make_info(quality_threshold=0.0)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        new = menu._nudge_numeric("index", "quality_threshold", -1, info)
        assert new == pytest.approx(0.0)


# ── RAGSettingsMenu._parse_to_type ────────────────────────────────────────────


class TestParseToType:
    def test_bool_on_to_true(self) -> None:
        info = _make_info(reranking_enabled=False)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        val = menu._parse_to_type("index", "reranking_enabled", "on", info)
        assert val is True

    def test_bool_off_to_false(self) -> None:
        info = _make_info(reranking_enabled=True)
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        val = menu._parse_to_type("index", "reranking_enabled", "off", info)
        assert val is False

    def test_string_field_stays_string(self) -> None:
        info = _make_info(chunk_strategy="fixed")
        ctx = _make_ctx(info)
        menu = _make_menu(ctx)
        val = menu._parse_to_type("index", "chunk_strategy", "sentence", info)
        assert val == "sentence"


# ── RAGSettingsMenu._choices_for ─────────────────────────────────────────────


class TestChoicesFor:
    def test_chunk_strategy_has_6_choices(self) -> None:
        ctx = _make_ctx()
        ctx.embedding_registry.names.return_value = ["mock", "local"]
        menu = _make_menu(ctx)
        menu._embed_choices = ["mock", "local"]
        # Find the chunk_strategy row index
        for row_idx, (label, source, field, choices, _) in enumerate(_RAG_ROWS):
            if field == "chunk_strategy":
                result = menu._choices_for(row_idx)
                assert len(result) == 6
                break

    def test_embedding_uses_registry_names(self) -> None:
        ctx = _make_ctx()
        ctx.embedding_registry.names.return_value = ["mock", "local", "openai"]
        menu = _make_menu(ctx)
        menu._embed_choices = ["mock", "local", "openai"]
        for row_idx, (label, source, field, choices, _) in enumerate(_RAG_ROWS):
            if field == "embedding_backend":
                result = menu._choices_for(row_idx)
                assert "openai" in result
                break


# ── Config field added (rag_no_match_behavior) ────────────────────────────────


class TestNoMatchBehaviorField:
    def test_default_is_graceful(self) -> None:
        cfg = AppConfig()
        assert cfg.rag_no_match_behavior == "graceful"

    def test_valid_values(self) -> None:
        from anythink.config.manager import validate_config

        for val in ("graceful", "passthrough"):
            errors = validate_config({"rag_no_match_behavior": val})
            assert errors == []

    def test_invalid_value_fails(self) -> None:
        from anythink.config.manager import validate_config

        errors = validate_config({"rag_no_match_behavior": "ignore"})
        assert len(errors) == 1
