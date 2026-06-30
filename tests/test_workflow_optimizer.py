"""Tests for workflow/optimizer.py — StageOutputOptimizer."""

from __future__ import annotations

import pytest

from anythink.workflow.models import (
    AccumulationStrategy,
    LoopDefinition,
    Stage,
    StageResult,
    StageType,
    WorkflowPlan,
    WorkflowState,
)
from anythink.workflow.optimizer import StageOutputOptimizer


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_result(
    stage_id: str = "stage_1",
    stage_type: StageType = StageType.MCP_CALL,
    output: dict | None = None,
    raw_content: str = "",
) -> StageResult:
    return StageResult(
        stage_id=stage_id,
        stage_type=stage_type,
        output=output or {},
        raw_content=raw_content,
    )


def _make_stage(
    stage_id: str = "stage_2",
    stage_type: StageType = StageType.LLM_SPECIALIST,
    **kwargs: object,
) -> Stage:
    return Stage(id=stage_id, type=stage_type, **kwargs)  # type: ignore[arg-type]


def _make_state(stages: list[Stage] | None = None) -> WorkflowState:
    plan = WorkflowPlan(name="test", trigger="do it", stages=stages or [])
    return WorkflowState(plan=plan)


# ---------------------------------------------------------------------------
# LLM_SPECIALIST transformation
# ---------------------------------------------------------------------------


class TestForLLM:
    def test_prepends_task_instruction(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result(raw_content="raw email body")
        stage = _make_stage(
            stage_type=StageType.LLM_SPECIALIST,
            task_instruction="Summarise this email in 2 sentences.",
        )
        state = _make_state()
        ctx = opt.transform(result, stage, state)
        assert "Summarise this email in 2 sentences." in ctx["content"]
        assert "raw email body" in ctx["content"]

    def test_includes_format_hint_when_set(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result(raw_content="data")
        stage = _make_stage(
            stage_type=StageType.LLM_SPECIALIST,
            task_instruction="Analyse this.",
            expected_format="json",
        )
        ctx = opt.transform(result, stage, _make_state())
        assert "json" in ctx["content"].lower()

    def test_uses_refs_when_present(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result(raw_content="ignored")
        stage = _make_stage(
            stage_type=StageType.LLM_SPECIALIST,
            task_instruction="Summarise.",
            input_refs=["stage_1.email_body"],
        )
        state = _make_state()
        state.accumulated_results["stage_1.email_body"] = "Important email content"
        ctx = opt.transform(result, stage, state)
        assert "Important email content" in ctx["content"]


# ---------------------------------------------------------------------------
# MCP_CALL transformation
# ---------------------------------------------------------------------------


class TestForMCP:
    def test_resolves_template_params(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result()
        stage = _make_stage(
            stage_type=StageType.MCP_CALL,
            tool_name="gmail.read_email",
            tool_params={"email_id": "{{stage_1.current_email_id}}"},
        )
        state = _make_state()
        state.accumulated_results["stage_1.current_email_id"] = "abc123"
        ctx = opt.transform(result, stage, state)
        assert ctx["resolved_params"]["email_id"] == "abc123"

    def test_static_params_preserved(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result()
        stage = _make_stage(
            stage_type=StageType.MCP_CALL,
            tool_params={"max_results": 50},
        )
        ctx = opt.transform(result, stage, _make_state())
        assert ctx["resolved_params"]["max_results"] == 50


# ---------------------------------------------------------------------------
# FORMATTER transformation
# ---------------------------------------------------------------------------


class TestForFormatter:
    def test_sets_target_format(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result(raw_content="some text")
        stage = _make_stage(
            stage_type=StageType.FORMATTER,
            expected_format="numbered_list",
        )
        ctx = opt.transform(result, stage, _make_state())
        assert ctx["target_format"] == "numbered_list"

    def test_detects_json_content_type(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result(raw_content='{"key": "value"}')
        stage = _make_stage(stage_type=StageType.FORMATTER)
        ctx = opt.transform(result, stage, _make_state())
        assert ctx["source_content_type"] == "json"

    def test_detects_markdown_content_type(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result(raw_content="# Title\n\n- item one\n- item two")
        stage = _make_stage(stage_type=StageType.FORMATTER)
        ctx = opt.transform(result, stage, _make_state())
        assert ctx["source_content_type"] == "markdown"

    def test_default_format_is_markdown(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result(raw_content="data")
        stage = _make_stage(stage_type=StageType.FORMATTER, expected_format="")
        ctx = opt.transform(result, stage, _make_state())
        assert ctx["target_format"] == "markdown"


# ---------------------------------------------------------------------------
# LOOP transformation
# ---------------------------------------------------------------------------


class TestForLoop:
    def test_resolves_collection_from_state(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result()
        loop_def = LoopDefinition(
            input_collection_ref="stage_1.email_list",
            sub_stages=[],
            accumulation_strategy=AccumulationStrategy.APPEND,
        )
        stage = _make_stage(stage_type=StageType.LOOP, loop_def=loop_def)
        state = _make_state()
        state.accumulated_results["stage_1.email_list"] = ["id1", "id2", "id3"]
        ctx = opt.transform(result, stage, state)
        assert ctx["collection"] == ["id1", "id2", "id3"]

    def test_no_loop_def_returns_empty_collection(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result()
        stage = _make_stage(stage_type=StageType.LOOP, loop_def=None)
        ctx = opt.transform(result, stage, _make_state())
        assert ctx["collection"] == []

    def test_scalar_collection_wrapped_in_list(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result()
        loop_def = LoopDefinition(
            input_collection_ref="stage_1.single_item",
            sub_stages=[],
        )
        stage = _make_stage(stage_type=StageType.LOOP, loop_def=loop_def)
        state = _make_state()
        state.accumulated_results["stage_1.single_item"] = "one_email"
        ctx = opt.transform(result, stage, state)
        assert ctx["collection"] == ["one_email"]


# ---------------------------------------------------------------------------
# USER_APPROVAL transformation
# ---------------------------------------------------------------------------


class TestForApproval:
    def test_includes_approval_message(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result()
        stage = _make_stage(
            stage_type=StageType.USER_APPROVAL,
            approval_message="Proceed to write the file?",
        )
        ctx = opt.transform(result, stage, _make_state())
        assert ctx["content"] == "Proceed to write the file?"

    def test_default_message_when_empty(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result()
        stage = _make_stage(stage_type=StageType.USER_APPROVAL, approval_message="")
        ctx = opt.transform(result, stage, _make_state())
        assert ctx["content"] == "Proceed?"


# ---------------------------------------------------------------------------
# CONDITION transformation
# ---------------------------------------------------------------------------


class TestForCondition:
    def test_includes_condition_expr(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result()
        stage = _make_stage(
            stage_type=StageType.CONDITION,
            condition_expr="output.count > 0",
        )
        state = _make_state()
        state.accumulated_results["stage_1.count"] = 5
        ctx = opt.transform(result, stage, state)
        assert ctx["condition_expr"] == "output.count > 0"
        assert "stage_1.count" in ctx["accumulated_results"]


# ---------------------------------------------------------------------------
# _primary_text helper
# ---------------------------------------------------------------------------


class TestPrimaryText:
    def test_prefers_refs_over_raw_content(self) -> None:
        opt = StageOutputOptimizer()
        # Use transform path to indirectly test _primary_text
        result = _make_result(raw_content="raw fallback")
        stage = _make_stage(
            stage_type=StageType.LLM_SPECIALIST,
            input_refs=["stage_1.body"],
        )
        state = _make_state()
        state.accumulated_results["stage_1.body"] = "ref content"
        ctx = opt.transform(result, stage, state)
        assert "ref content" in ctx["content"]
        # raw fallback should NOT appear when ref resolves
        assert "raw fallback" not in ctx["content"]

    def test_falls_back_to_raw_content(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result(raw_content="fallback content")
        stage = _make_stage(
            stage_type=StageType.LLM_SPECIALIST,
            task_instruction="process",
        )
        ctx = opt.transform(result, stage, _make_state())
        assert "fallback content" in ctx["content"]

    def test_falls_back_to_output_dict(self) -> None:
        opt = StageOutputOptimizer()
        result = _make_result(output={"key": "value"})
        stage = _make_stage(stage_type=StageType.LLM_SPECIALIST, task_instruction="go")
        ctx = opt.transform(result, stage, _make_state())
        assert "key" in ctx["content"]
