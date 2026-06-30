"""Tests for workflow/models.py — core MMWE dataclasses."""

from __future__ import annotations

import pytest

from anythink.workflow.models import (
    AccumulationStrategy,
    ClarificationRequest,
    LoopDefinition,
    LoopIterationRecord,
    Stage,
    StageResult,
    StageType,
    UserDecision,
    WorkflowLog,
    WorkflowPlan,
    WorkflowState,
    WorkflowStatus,
)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_stage(
    stage_id: str = "stage_1",
    stage_type: StageType = StageType.MCP_CALL,
    **kwargs: object,
) -> Stage:
    return Stage(id=stage_id, type=stage_type, **kwargs)  # type: ignore[arg-type]


def make_plan(name: str = "test-plan", **kwargs: object) -> WorkflowPlan:
    return WorkflowPlan(name=name, trigger="Do something useful", **kwargs)  # type: ignore[arg-type]


def make_result(
    stage_id: str = "stage_1",
    stage_type: StageType = StageType.MCP_CALL,
    **kwargs: object,
) -> StageResult:
    return StageResult(stage_id=stage_id, stage_type=stage_type, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


class TestStage:
    def test_minimal_construction(self) -> None:
        s = make_stage()
        assert s.id == "stage_1"
        assert s.type == StageType.MCP_CALL
        assert s.is_destructive is False
        assert s.is_parallel is False
        assert s.branch_a == []
        assert s.branch_b == []

    def test_round_trip_dict(self) -> None:
        s = Stage(
            id="stage_2",
            type=StageType.LLM_SPECIALIST,
            label="Summarise email",
            model_alias="local-summarizer",
            task_instruction="Summarise this email in 2 sentences.",
            output_field="summary",
            input_refs=["stage_1.email_content"],
        )
        restored = Stage.from_dict(s.to_dict())
        assert restored.id == s.id
        assert restored.type == s.type
        assert restored.model_alias == s.model_alias
        assert restored.task_instruction == s.task_instruction
        assert restored.input_refs == s.input_refs

    def test_nested_stages_round_trip(self) -> None:
        inner = make_stage("stage_3a", StageType.MCP_CALL, tool_name="gmail.read_email")
        outer = Stage(
            id="stage_3",
            type=StageType.CONDITION,
            condition_expr="output.count > 0",
            branch_a=[inner],
            branch_b=[],
        )
        restored = Stage.from_dict(outer.to_dict())
        assert len(restored.branch_a) == 1
        assert restored.branch_a[0].tool_name == "gmail.read_email"

    def test_loop_def_round_trip(self) -> None:
        loop_def = LoopDefinition(
            input_collection_ref="stage_1.email_list",
            sub_stages=[make_stage("stage_2a", StageType.MCP_CALL)],
            accumulation_strategy=AccumulationStrategy.STRUCTURED_LIST,
        )
        s = Stage(id="stage_2", type=StageType.LOOP, loop_def=loop_def)
        restored = Stage.from_dict(s.to_dict())
        assert restored.loop_def is not None
        assert restored.loop_def.input_collection_ref == "stage_1.email_list"
        assert restored.loop_def.accumulation_strategy == AccumulationStrategy.STRUCTURED_LIST
        assert len(restored.loop_def.sub_stages) == 1


# ---------------------------------------------------------------------------
# WorkflowPlan
# ---------------------------------------------------------------------------


class TestWorkflowPlan:
    def test_construction_defaults(self) -> None:
        plan = make_plan()
        assert plan.stages == []
        assert plan.models_used == []
        assert plan.estimated_duration_s is None

    def test_round_trip_dict(self) -> None:
        plan = WorkflowPlan(
            name="email-summary",
            trigger="Read and summarize all inbox emails",
            stages=[make_stage("stage_1"), make_stage("stage_2", StageType.LLM_SPECIALIST)],
            models_used=["local-summarizer"],
            mcp_servers_used=["gmail"],
            estimated_duration_s=600,
            estimated_loop_iterations=50,
        )
        restored = WorkflowPlan.from_dict(plan.to_dict())
        assert restored.name == plan.name
        assert restored.trigger == plan.trigger
        assert len(restored.stages) == 2
        assert restored.estimated_loop_iterations == 50


# ---------------------------------------------------------------------------
# StageResult
# ---------------------------------------------------------------------------


class TestStageResult:
    def test_defaults(self) -> None:
        r = make_result()
        assert r.output == {}
        assert r.error is None
        assert r.skipped is False
        assert r.user_decision is None
        assert r.fallback_used is False

    def test_round_trip_with_decision(self) -> None:
        r = StageResult(
            stage_id="stage_2",
            stage_type=StageType.USER_APPROVAL,
            user_decision=UserDecision.SKIPPED,
            duration_s=1.5,
        )
        restored = StageResult.from_dict(r.to_dict())
        assert restored.user_decision == UserDecision.SKIPPED
        assert restored.duration_s == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# WorkflowState
# ---------------------------------------------------------------------------


class TestWorkflowState:
    def test_store_and_resolve(self) -> None:
        plan = make_plan(stages=[make_stage("s1", output_field="emails")])
        state = WorkflowState(plan=plan)
        result = make_result("s1", output={"email_list": ["id1", "id2"]})
        # Patch the stage output_field so store_result can find it
        plan.stages[0].output_field = "emails"
        state.store_result(result)
        assert state.resolve_ref("s1.email_list") == ["id1", "id2"]
        assert state.accumulated_results["emails"] == {"email_list": ["id1", "id2"]}

    def test_stop_and_pause_flags(self) -> None:
        state = WorkflowState(plan=make_plan())
        assert state.paused is False
        assert state.stop_requested is False
        state.paused = True
        state.stop_requested = True
        assert state.paused is True
        assert state.stop_requested is True


# ---------------------------------------------------------------------------
# WorkflowLog
# ---------------------------------------------------------------------------


class TestWorkflowLog:
    def test_to_dict_has_all_keys(self) -> None:
        log = WorkflowLog(workflow_name="test", trigger="do it")
        d = log.to_dict()
        assert "workflow_name" in d
        assert "trigger" in d
        assert "start_time" in d
        assert "stage_records" in d
        assert "final_output" in d
        assert d["status"] == WorkflowStatus.RUNNING.value

    def test_loop_iterations_serialised(self) -> None:
        log = WorkflowLog(workflow_name="loop-test", trigger="loop")
        log.loop_iterations.append(
            LoopIterationRecord(
                item_id="email_1",
                iteration_index=0,
                duration_s=1.2,
                result_summary="Done",
            )
        )
        d = log.to_dict()
        assert len(d["loop_iterations"]) == 1
        assert d["loop_iterations"][0]["item_id"] == "email_1"


# ---------------------------------------------------------------------------
# ClarificationRequest
# ---------------------------------------------------------------------------


class TestClarificationRequest:
    def test_fields(self) -> None:
        cr = ClarificationRequest(questions=["How many emails?", "What format?"])
        assert len(cr.questions) == 2
        assert cr.round == 1

    def test_round_2(self) -> None:
        cr = ClarificationRequest(questions=["Still ambiguous?"], round=2)
        assert cr.round == 2


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TestWorkflowExceptions:
    def test_workflow_error(self) -> None:
        from anythink.exceptions import WorkflowError

        err = WorkflowError("something broke", "User-friendly message")
        assert str(err) == "something broke"
        assert err.user_message == "User-friendly message"

    def test_workflow_stage_error(self) -> None:
        from anythink.exceptions import WorkflowStageError

        err = WorkflowStageError("stage failed", stage_id="stage_3")
        assert err.stage_id == "stage_3"
