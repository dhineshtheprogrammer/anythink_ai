"""Tests for the RAG new-index wizard state machine (Phase 7)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anythink.ui.textual.rag_wizard import (
    RAGIndexWizard,
    _CHUNK_STRATEGIES,
    _OVERLAP_PRESETS,
    _validate_name,
    _validate_source_path,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_ctx(tmp_path: Path, existing_names: list[str] | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.config = MagicMock()
    ctx.config.embedding_backend = "local"

    rm = MagicMock()
    infos = []
    for name in (existing_names or []):
        info = MagicMock()
        info.name = name
        infos.append(info)
    rm.list_indexes.return_value = infos
    ctx.rag_manager = rm

    registry = MagicMock()
    registry.names.return_value = ["mock", "local"]
    ctx.embedding_registry = registry

    return ctx


def _run_wizard_to_completion(
    wizard: RAGIndexWizard,
    tmp_path: Path,
    name: str = "test-idx",
    source: str = "",
    chunk_strategy_idx: int = 1,
    chunk_size: str = "",
    overlap_idx: str = "2",
    embedding_idx: str = "1",
    backend_idx: str = "1",
    ingest: str = "n",
) -> object:
    source = source or str(tmp_path)
    step = wizard.start()
    step = wizard.handle_input(name)
    step = wizard.handle_input(source)
    step = wizard.handle_input(str(chunk_strategy_idx))
    step = wizard.handle_input(chunk_size)
    step = wizard.handle_input(overlap_idx)
    step = wizard.handle_input(embedding_idx)
    step = wizard.handle_input(backend_idx)
    step = wizard.handle_input(ingest)
    return step


# ── _validate_name ────────────────────────────────────────────────────────────


class TestValidateName:
    def test_valid_simple(self) -> None:
        assert _validate_name("my-docs", []) is None

    def test_valid_with_underscores(self) -> None:
        assert _validate_name("my_docs_v2", []) is None

    def test_valid_alphanumeric(self) -> None:
        assert _validate_name("docs123", []) is None

    def test_empty_name_fails(self) -> None:
        err = _validate_name("", [])
        assert err is not None

    def test_existing_name_fails(self) -> None:
        err = _validate_name("existing", ["existing", "other"])
        assert err is not None
        assert "existing" in err

    def test_starts_with_dash_fails(self) -> None:
        err = _validate_name("-bad", [])
        assert err is not None

    def test_spaces_fail(self) -> None:
        err = _validate_name("my docs", [])
        assert err is not None

    def test_unique_name_passes(self) -> None:
        assert _validate_name("new-index", ["old-index"]) is None


# ── _validate_source_path ────────────────────────────────────────────────────


class TestValidateSourcePath:
    def test_existing_directory(self, tmp_path: Path) -> None:
        assert _validate_source_path(str(tmp_path)) is None

    def test_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("hi")
        assert _validate_source_path(str(f)) is None

    def test_nonexistent_path_fails(self, tmp_path: Path) -> None:
        err = _validate_source_path(str(tmp_path / "does_not_exist"))
        assert err is not None


# ── RAGIndexWizard — lifecycle ────────────────────────────────────────────────


class TestWizardLifecycle:
    def test_not_active_before_start(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        assert not wizard.is_active

    def test_active_after_start(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        wizard.start()
        assert wizard.is_active

    def test_not_active_after_cancel(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        wizard.start()
        step = wizard.cancel()
        assert not wizard.is_active
        assert step.cancelled is True
        assert step.done is True

    def test_not_active_after_completion(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = _run_wizard_to_completion(wizard, tmp_path)
        assert not wizard.is_active
        assert step.done is True

    def test_cancel_via_input(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        wizard.start()
        step = wizard.handle_input("cancel")
        assert step.cancelled is True
        assert not wizard.is_active


# ── RAGIndexWizard — step prompts ─────────────────────────────────────────────


class TestWizardPrompts:
    def test_step1_prompt_mentions_name(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = wizard.start()
        assert "Step 1" in step.prompt
        assert "Name" in step.prompt

    def test_step2_prompt_mentions_path(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        wizard.start()
        step = wizard.handle_input("my-idx")
        assert "Step 2" in step.prompt
        assert "path" in step.prompt.lower()

    def test_step3_shows_strategy_options(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        wizard.start()
        wizard.handle_input("my-idx")
        step = wizard.handle_input(str(tmp_path))
        assert "Step 3" in step.prompt
        assert "fixed" in step.prompt

    def test_step8_shows_summary(self, tmp_path: Path) -> None:
        # 7 inputs advance through steps 1–7; the return of step 7's input IS the step 8 prompt
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        wizard.start()
        step = None
        for inp in ["summ-idx", str(tmp_path), "1", "", "2", "1", "1"]:
            step = wizard.handle_input(inp)
        assert step is not None
        assert "Step 8" in step.prompt
        assert "summ-idx" in step.prompt

    def test_prefill_name_shown_in_step1(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = wizard.start(prefill_name="my-prefill")
        assert "my-prefill" in step.prompt


# ── RAGIndexWizard — validation ───────────────────────────────────────────────


class TestWizardValidation:
    def test_duplicate_name_shows_error(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, existing_names=["existing"])
        wizard = RAGIndexWizard(ctx)
        wizard.start()
        step = wizard.handle_input("existing")
        assert "⚠" in step.prompt
        assert wizard.is_active  # still on step 1

    def test_bad_source_path_shows_error(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        wizard.start()
        wizard.handle_input("good-name")
        step = wizard.handle_input("/no/such/path/xyz")
        assert "⚠" in step.prompt
        assert wizard.is_active  # still on step 2

    def test_invalid_strategy_number(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        wizard.start()
        wizard.handle_input("idx")
        wizard.handle_input(str(tmp_path))
        step = wizard.handle_input("99")  # out of range
        assert "⚠" in step.prompt

    def test_chunk_size_too_small_shows_error(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        wizard.start()
        wizard.handle_input("idx")
        wizard.handle_input(str(tmp_path))
        wizard.handle_input("1")
        step = wizard.handle_input("10")  # < 256
        assert "⚠" in step.prompt

    def test_ingest_invalid_input_shows_error(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        wizard.start()
        for inp in ["idx2", str(tmp_path), "1", "", "2", "1", "1"]:
            wizard.handle_input(inp)
        step = wizard.handle_input("maybe")  # not y/n
        assert "⚠" in step.prompt


# ── RAGIndexWizard — completion ───────────────────────────────────────────────


class TestWizardCompletion:
    def test_result_has_correct_name(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = _run_wizard_to_completion(wizard, tmp_path, name="final-idx")
        assert step.result is not None
        assert step.result.name == "final-idx"

    def test_result_has_correct_source_path(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = _run_wizard_to_completion(wizard, tmp_path)
        assert step.result is not None
        assert step.result.source_path == str(tmp_path)

    def test_result_chunk_strategy_applied(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = _run_wizard_to_completion(wizard, tmp_path, chunk_strategy_idx=2)
        assert step.result is not None
        assert step.result.chunk_strategy == _CHUNK_STRATEGIES[1]  # "sentence"

    def test_ingest_now_true_when_y(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = _run_wizard_to_completion(wizard, tmp_path, ingest="y")
        assert step.ingest_now is True

    def test_ingest_now_false_when_n(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = _run_wizard_to_completion(wizard, tmp_path, ingest="n")
        assert step.ingest_now is False

    def test_empty_chunk_size_uses_default(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = _run_wizard_to_completion(wizard, tmp_path, chunk_size="")
        assert step.result is not None
        assert step.result.chunk_size == 512  # default

    def test_overlap_preset_applied(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = _run_wizard_to_completion(wizard, tmp_path, overlap_idx="3")
        assert step.result is not None
        assert step.result.chunk_overlap == _OVERLAP_PRESETS[2]  # 150

    def test_not_cancelled(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = _run_wizard_to_completion(wizard, tmp_path)
        assert step.cancelled is False

    def test_persistence_mode_is_persist(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        wizard = RAGIndexWizard(ctx)
        step = _run_wizard_to_completion(wizard, tmp_path)
        assert step.result is not None
        assert step.result.persistence_mode == "persist"
