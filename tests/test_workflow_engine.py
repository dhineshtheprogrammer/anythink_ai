"""Tests for workflow/engine.py — WorkflowEngine and workflow/loop.py — LoopExecutor."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.workflow.models import (
    AccumulationStrategy,
    LoopDefinition,
    Stage,
    StageResult,
    StageType,
    UserDecision,
    WorkflowPlan,
    WorkflowState,
    WorkflowStatus,
)

# ---------------------------------------------------------------------------
# Shared factories
# ---------------------------------------------------------------------------


def _make_plan(stages: list[Stage] | None = None, name: str = "test") -> WorkflowPlan:
    return WorkflowPlan(
        name=name,
        trigger="test trigger",
        stages=stages or [],
    )


def _make_state(plan: WorkflowPlan | None = None) -> WorkflowState:
    return WorkflowState(plan=plan or _make_plan())


def _make_stage(
    stage_type: StageType = StageType.LLM_SPECIALIST,
    stage_id: str = "stage_1",
    **kwargs: Any,
) -> Stage:
    return Stage(id=stage_id, type=stage_type, **kwargs)


def _make_result(
    stage_id: str = "stage_1",
    stage_type: StageType = StageType.LLM_SPECIALIST,
    raw_content: str = "output",
    error: str | None = None,
    user_decision: UserDecision | None = None,
    skipped: bool = False,
) -> StageResult:
    return StageResult(
        stage_id=stage_id,
        stage_type=stage_type,
        output={"result": raw_content},
        raw_content=raw_content,
        error=error,
        user_decision=user_decision,
        skipped=skipped,
    )


def _make_logger() -> MagicMock:
    from anythink.workflow.log import WorkflowLogger
    from anythink.workflow.models import WorkflowLog

    logger = MagicMock(spec=WorkflowLogger)
    log_obj = WorkflowLog(workflow_name="test", trigger="test")
    logger.begin.return_value = log_obj
    logger.finalize.return_value = MagicMock()
    logger.record_stage.return_value = None
    return logger


def _make_engine(logger: MagicMock | None = None) -> Any:
    from anythink.workflow.engine import WorkflowEngine
    from anythink.workflow.loop import LoopExecutor
    from anythink.workflow.optimizer import StageOutputOptimizer

    return WorkflowEngine(
        planner=MagicMock(),
        router=MagicMock(),
        optimizer=StageOutputOptimizer(),
        loop_executor=LoopExecutor(),
        logger=logger or _make_logger(),
        storage=MagicMock(),
    )


def _make_callbacks(**overrides: Any) -> MagicMock:
    cb = MagicMock()
    cb.on_stage_start = AsyncMock()
    cb.on_stage_complete = AsyncMock()
    cb.on_approval_needed = AsyncMock(return_value="approved")
    cb.on_loop_progress = AsyncMock()
    cb.on_model_unavailable = AsyncMock(return_value="")
    for k, v in overrides.items():
        setattr(cb, k, v)
    return cb


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.model_registry = MagicMock()
    ctx.model_registry.list_all.return_value = []
    ctx.mcp_manager = MagicMock()
    ctx.spend_tracker = MagicMock()
    ctx.key_manager = MagicMock()
    ctx.provider_registry = MagicMock()
    ctx.workflow_registry = MagicMock()
    ctx.workflow_registry.get_fallback_chain.return_value = []
    return ctx


# ---------------------------------------------------------------------------
# WorkflowEngine — basic execution
# ---------------------------------------------------------------------------


class TestWorkflowEngineRun:
    @pytest.mark.asyncio
    async def test_empty_plan_completes(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        plan = _make_plan(stages=[])
        log = await engine.run(plan, _make_ctx(), _make_callbacks())

        engine._logger.finalize.assert_called_once()
        _, call_args = engine._logger.finalize.call_args[0], engine._logger.finalize.call_args
        status_arg = engine._logger.finalize.call_args.args[1]
        assert status_arg == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_single_stage_dispatched_and_logged(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        stage = _make_stage(StageType.LLM_SPECIALIST, stage_id="s1")
        plan = _make_plan(stages=[stage])
        callbacks = _make_callbacks()

        ok_result = _make_result("s1", raw_content="done")

        with patch(
            "anythink.workflow.engine._dispatch_stage", new=AsyncMock(return_value=ok_result)
        ):
            await engine.run(plan, _make_ctx(), callbacks)

        callbacks.on_stage_start.assert_called_once_with(stage)
        callbacks.on_stage_complete.assert_called_once()
        engine._logger.record_stage.assert_called_once()

    @pytest.mark.asyncio
    async def test_aborted_user_decision_stops_pipeline(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        stage1 = _make_stage(StageType.USER_APPROVAL, "s1")
        stage2 = _make_stage(StageType.LLM_SPECIALIST, "s2")
        plan = _make_plan(stages=[stage1, stage2])

        aborted_result = _make_result("s1", user_decision=UserDecision.ABORTED)
        ok_result = _make_result("s2")

        call_count = 0

        async def _dispatch(stage, state, ctx, callbacks):
            nonlocal call_count
            call_count += 1
            return aborted_result if stage.id == "s1" else ok_result

        with patch("anythink.workflow.engine._dispatch_stage", side_effect=_dispatch):
            await engine.run(plan, _make_ctx(), _make_callbacks())

        # stage2 must NOT have been executed
        assert call_count == 1
        status_arg = engine._logger.finalize.call_args.args[1]
        assert status_arg == WorkflowStatus.ABORTED

    @pytest.mark.asyncio
    async def test_stage_error_does_not_stop_pipeline(self) -> None:
        """A stage error is recorded but execution continues to subsequent stages."""
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        stage1 = _make_stage(StageType.MCP_CALL, "s1")
        stage2 = _make_stage(StageType.LLM_SPECIALIST, "s2")
        plan = _make_plan(stages=[stage1, stage2])

        error_result = _make_result("s1", error="tool not found")
        ok_result = _make_result("s2", raw_content="summary")

        call_ids: list[str] = []

        async def _dispatch(stage, state, ctx, callbacks):
            call_ids.append(stage.id)
            return error_result if stage.id == "s1" else ok_result

        with patch("anythink.workflow.engine._dispatch_stage", side_effect=_dispatch):
            await engine.run(plan, _make_ctx(), _make_callbacks())

        assert call_ids == ["s1", "s2"]
        status_arg = engine._logger.finalize.call_args.args[1]
        assert status_arg == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_failed_status(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        stage = _make_stage(StageType.LLM_SPECIALIST, "s1")
        plan = _make_plan(stages=[stage])

        async def _boom(stage, state, ctx, callbacks):
            raise RuntimeError("unexpected crash")

        with patch("anythink.workflow.engine._dispatch_stage", side_effect=_boom):
            await engine.run(plan, _make_ctx(), _make_callbacks())

        status_arg = engine._logger.finalize.call_args.args[1]
        assert status_arg == WorkflowStatus.FAILED


# ---------------------------------------------------------------------------
# WorkflowEngine — parallel stages
# ---------------------------------------------------------------------------


class TestWorkflowEngineParallel:
    @pytest.mark.asyncio
    async def test_parallel_stages_both_executed(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        s1 = _make_stage(StageType.LLM_SPECIALIST, "s1", is_parallel=True)
        s2 = _make_stage(StageType.LLM_SPECIALIST, "s2", is_parallel=True)
        plan = _make_plan(stages=[s1, s2])

        executed: set[str] = set()

        async def _dispatch(stage, state, ctx, callbacks):
            executed.add(stage.id)
            return _make_result(stage.id)

        with patch("anythink.workflow.engine._dispatch_stage", side_effect=_dispatch):
            await engine.run(plan, _make_ctx(), _make_callbacks())

        assert executed == {"s1", "s2"}

    @pytest.mark.asyncio
    async def test_parallel_abort_stops_pipeline(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        s1 = _make_stage(StageType.USER_APPROVAL, "s1", is_parallel=True)
        s2 = _make_stage(StageType.LLM_SPECIALIST, "s2")  # after parallel group
        plan = _make_plan(stages=[s1, s2])

        call_ids: list[str] = []

        async def _dispatch(stage, state, ctx, callbacks):
            call_ids.append(stage.id)
            if stage.id == "s1":
                return _make_result("s1", user_decision=UserDecision.ABORTED)
            return _make_result("s2")

        with patch("anythink.workflow.engine._dispatch_stage", side_effect=_dispatch):
            await engine.run(plan, _make_ctx(), _make_callbacks())

        assert "s2" not in call_ids


# ---------------------------------------------------------------------------
# WorkflowEngine — CONDITION branching
# ---------------------------------------------------------------------------


class TestWorkflowEngineCondition:
    @pytest.mark.asyncio
    async def test_branch_a_executed_on_true(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        branch_stage_a = _make_stage(StageType.LLM_SPECIALIST, "branch_a_s1")
        branch_stage_b = _make_stage(StageType.LLM_SPECIALIST, "branch_b_s1")
        cond_stage = Stage(
            id="cond",
            type=StageType.CONDITION,
            condition_expr="1 == 1",
            branch_a=[branch_stage_a],
            branch_b=[branch_stage_b],
        )
        plan = _make_plan(stages=[cond_stage])
        executed: list[str] = []

        async def _dispatch(stage, state, ctx, callbacks):
            executed.append(stage.id)
            if stage.id == "cond":
                return _make_result("cond", raw_content="branch_a", error=None)
            return _make_result(stage.id)

        cond_result = StageResult(
            stage_id="cond",
            stage_type=StageType.CONDITION,
            output={"branch": "a", "condition_result": True},
            raw_content="branch_a",
        )

        async def _smart_dispatch(stage, state, ctx, callbacks):
            executed.append(stage.id)
            if stage.id == "cond":
                return cond_result
            return _make_result(stage.id)

        with patch("anythink.workflow.engine._dispatch_stage", side_effect=_smart_dispatch):
            await engine.run(plan, _make_ctx(), _make_callbacks())

        assert "branch_a_s1" in executed
        assert "branch_b_s1" not in executed

    @pytest.mark.asyncio
    async def test_branch_b_executed_on_false(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        branch_stage_a = _make_stage(StageType.LLM_SPECIALIST, "branch_a_s1")
        branch_stage_b = _make_stage(StageType.LLM_SPECIALIST, "branch_b_s1")
        cond_stage = Stage(
            id="cond",
            type=StageType.CONDITION,
            condition_expr="1 == 2",
            branch_a=[branch_stage_a],
            branch_b=[branch_stage_b],
        )
        plan = _make_plan(stages=[cond_stage])
        executed: list[str] = []

        cond_result = StageResult(
            stage_id="cond",
            stage_type=StageType.CONDITION,
            output={"branch": "b", "condition_result": False},
            raw_content="branch_b",
        )

        async def _smart_dispatch(stage, state, ctx, callbacks):
            executed.append(stage.id)
            if stage.id == "cond":
                return cond_result
            return _make_result(stage.id)

        with patch("anythink.workflow.engine._dispatch_stage", side_effect=_smart_dispatch):
            await engine.run(plan, _make_ctx(), _make_callbacks())

        assert "branch_b_s1" in executed
        assert "branch_a_s1" not in executed


# ---------------------------------------------------------------------------
# WorkflowEngine — destructive guard
# ---------------------------------------------------------------------------


class TestWorkflowEngineDestructiveGuard:
    @pytest.mark.asyncio
    async def test_destructive_stage_triggers_approval_guard(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        stage = _make_stage(
            StageType.MCP_CALL,
            "s1",
            is_destructive=True,
            tool_name="fs.delete_file",
        )
        plan = _make_plan(stages=[stage])
        callbacks = _make_callbacks()
        callbacks.on_approval_needed = AsyncMock(return_value="approved")

        ok_result = _make_result("s1")

        with patch(
            "anythink.workflow.engine._dispatch_stage", new=AsyncMock(return_value=ok_result)
        ):
            with patch(
                "anythink.workflow.stages.user_approval.execute",
                new=AsyncMock(
                    return_value=StageResult(
                        stage_id="s1__guard",
                        stage_type=StageType.USER_APPROVAL,
                        user_decision=UserDecision.APPROVED,
                        output={"decision": "approved"},
                        raw_content="approved",
                    )
                ),
            ):
                await engine.run(plan, _make_ctx(), callbacks)

        # The actual tool stage should still have been dispatched
        assert engine._logger.record_stage.call_count >= 1

    @pytest.mark.asyncio
    async def test_destructive_stage_aborted_at_guard(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        stage = _make_stage(StageType.MCP_CALL, "s1", is_destructive=True)
        plan = _make_plan(stages=[stage])

        with patch(
            "anythink.workflow.stages.user_approval.execute",
            new=AsyncMock(
                return_value=StageResult(
                    stage_id="s1__guard",
                    stage_type=StageType.USER_APPROVAL,
                    user_decision=UserDecision.ABORTED,
                    skipped=True,
                    raw_content="aborted",
                )
            ),
        ):
            with patch(
                "anythink.workflow.engine._dispatch_stage", new=AsyncMock()
            ) as mock_dispatch:
                await engine.run(plan, _make_ctx(), _make_callbacks())

        # The actual tool should NOT have been dispatched
        mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# WorkflowEngine — dry_run
# ---------------------------------------------------------------------------


class TestWorkflowEngineDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_returns_plan_summary(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        plan = _make_plan(
            stages=[
                _make_stage(StageType.MCP_CALL, "s1", label="Fetch emails", tool_name="gmail.list"),
                _make_stage(StageType.LLM_SPECIALIST, "s2", label="Summarize", model_alias="llm-a"),
            ]
        )
        text = await engine.dry_run(plan, _make_ctx())

        assert "test" in text  # plan name
        assert "MCP_CALL" in text
        assert "LLM_SPECIALIST" in text
        assert "gmail.list" in text
        assert "llm-a" in text

    @pytest.mark.asyncio
    async def test_dry_run_includes_estimated_duration(self) -> None:
        from anythink.workflow.engine import WorkflowEngine

        engine = _make_engine()
        plan = _make_plan()
        plan.estimated_duration_s = 120
        text = await engine.dry_run(plan, _make_ctx())

        assert "120" in text


# ---------------------------------------------------------------------------
# LoopExecutor
# ---------------------------------------------------------------------------


class TestLoopExecutor:
    @pytest.mark.asyncio
    async def test_iterates_all_items(self) -> None:
        from anythink.workflow.loop import LoopExecutor
        from anythink.workflow.models import AccumulationStrategy, LoopDefinition, Stage

        loop_def = LoopDefinition(
            input_collection_ref="items",
            sub_stages=[_make_stage(StageType.LLM_SPECIALIST, "sub_1")],
            accumulation_strategy=AccumulationStrategy.APPEND,
        )

        state = _make_state()
        state.accumulated_results["items"] = ["a", "b", "c"]

        progress_calls: list[tuple[int, int]] = []

        async def _runner(stage, st, ctx, cb):
            return _make_result(stage.id, raw_content=f"processed")

        async def _on_progress(current, total, last):
            progress_calls.append((current, total))

        callbacks = _make_callbacks()
        callbacks.on_loop_progress = AsyncMock(side_effect=_on_progress)

        executor = LoopExecutor()
        result = await executor.run(
            loop_def=loop_def,
            collection=["a", "b", "c"],
            state=state,
            ctx=_make_ctx(),
            callbacks=callbacks,
            stage_runner=_runner,
        )

        assert result.stage_type == StageType.LOOP
        assert len(progress_calls) == 3
        assert progress_calls[0] == (1, 3)
        assert progress_calls[-1] == (3, 3)

    @pytest.mark.asyncio
    async def test_stop_requested_halts_early(self) -> None:
        from anythink.workflow.loop import LoopExecutor
        from anythink.workflow.models import AccumulationStrategy, LoopDefinition

        loop_def = LoopDefinition(
            input_collection_ref="items",
            sub_stages=[_make_stage(StageType.LLM_SPECIALIST, "sub")],
            accumulation_strategy=AccumulationStrategy.APPEND,
        )
        state = _make_state()

        call_count = 0

        async def _runner(stage, st, ctx, cb):
            nonlocal call_count
            call_count += 1
            # Stop after first item
            st.stop_requested = True
            return _make_result(stage.id)

        executor = LoopExecutor()
        await executor.run(
            loop_def=loop_def,
            collection=["a", "b", "c"],
            state=state,
            ctx=_make_ctx(),
            callbacks=_make_callbacks(),
            stage_runner=_runner,
        )

        # Only one item should have been processed
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_empty_collection_returns_empty_result(self) -> None:
        from anythink.workflow.loop import LoopExecutor
        from anythink.workflow.models import AccumulationStrategy, LoopDefinition

        loop_def = LoopDefinition(
            input_collection_ref="items",
            sub_stages=[],
            accumulation_strategy=AccumulationStrategy.APPEND,
        )
        state = _make_state()

        async def _runner(stage, st, ctx, cb):
            return _make_result(stage.id)

        executor = LoopExecutor()
        result = await executor.run(
            loop_def=loop_def,
            collection=[],
            state=state,
            ctx=_make_ctx(),
            callbacks=_make_callbacks(),
            stage_runner=_runner,
        )

        assert result.raw_content == ""
        assert result.error is None

    @pytest.mark.asyncio
    async def test_iteration_error_recorded_but_continues(self) -> None:
        from anythink.workflow.loop import LoopExecutor
        from anythink.workflow.models import AccumulationStrategy, LoopDefinition

        loop_def = LoopDefinition(
            input_collection_ref="items",
            sub_stages=[_make_stage(StageType.MCP_CALL, "sub")],
            accumulation_strategy=AccumulationStrategy.APPEND,
        )
        state = _make_state()

        call_count = 0

        async def _runner(stage, st, ctx, cb):
            nonlocal call_count
            call_count += 1
            error = "tool failed" if call_count == 1 else None
            return _make_result(stage.id, error=error)

        executor = LoopExecutor()
        result = await executor.run(
            loop_def=loop_def,
            collection=["a", "b"],
            state=state,
            ctx=_make_ctx(),
            callbacks=_make_callbacks(),
            stage_runner=_runner,
        )

        # Both items processed, error recorded in result
        assert call_count == 2
        assert result.error is not None
        assert "item 0" in result.error

    @pytest.mark.asyncio
    async def test_merge_accumulation(self) -> None:
        from anythink.workflow.loop import LoopExecutor
        from anythink.workflow.models import AccumulationStrategy, LoopDefinition

        loop_def = LoopDefinition(
            input_collection_ref="items",
            sub_stages=[_make_stage(StageType.FORMATTER, "sub")],
            accumulation_strategy=AccumulationStrategy.MERGE,
        )
        state = _make_state()
        items = [{"key": "a"}, {"key": "b"}]

        call_idx = 0

        async def _runner(stage, st, ctx, cb):
            nonlocal call_idx
            result = StageResult(
                stage_id=stage.id,
                stage_type=stage.type,
                output=items[call_idx],
                raw_content=str(items[call_idx]),
            )
            call_idx += 1
            return result

        executor = LoopExecutor()
        result = await executor.run(
            loop_def=loop_def,
            collection=items,
            state=state,
            ctx=_make_ctx(),
            callbacks=_make_callbacks(),
            stage_runner=_runner,
        )

        assert result.error is None


# ---------------------------------------------------------------------------
# Accumulation helper unit tests
# ---------------------------------------------------------------------------


class TestAccumulationHelpers:
    def test_append_strategy(self) -> None:
        from anythink.workflow.loop import _accumulate

        acc: list = []
        _accumulate(acc, "x", AccumulationStrategy.APPEND)
        _accumulate(acc, "y", AccumulationStrategy.APPEND)
        assert acc == ["x", "y"]

    def test_merge_strategy_merges_dicts(self) -> None:
        from anythink.workflow.loop import _accumulate

        acc: list = [{"a": 1}]
        _accumulate(acc, {"b": 2}, AccumulationStrategy.MERGE)
        # The first dict is updated in place
        assert acc[0] == {"a": 1, "b": 2}

    def test_merge_strategy_appends_non_dict(self) -> None:
        from anythink.workflow.loop import _accumulate

        acc: list = []
        _accumulate(acc, "string", AccumulationStrategy.MERGE)
        assert acc == ["string"]

    def test_structured_list_parses_json(self) -> None:
        from anythink.workflow.loop import _accumulate

        acc: list = []
        _accumulate(acc, '{"key": "val"}', AccumulationStrategy.STRUCTURED_LIST)
        assert acc == [{"key": "val"}]

    def test_structured_list_keeps_non_json_as_string(self) -> None:
        from anythink.workflow.loop import _accumulate

        acc: list = []
        _accumulate(acc, "not json", AccumulationStrategy.STRUCTURED_LIST)
        assert acc == ["not json"]

    def test_build_final_empty(self) -> None:
        from anythink.workflow.loop import _build_final

        assert _build_final([], AccumulationStrategy.APPEND) == ""

    def test_build_final_append_produces_json(self) -> None:
        import json

        from anythink.workflow.loop import _build_final

        result = _build_final(["a", "b"], AccumulationStrategy.APPEND)
        assert json.loads(result) == ["a", "b"]

    def test_build_final_merge_produces_merged_json(self) -> None:
        import json

        from anythink.workflow.loop import _build_final

        result = _build_final([{"a": 1, "b": 2}], AccumulationStrategy.MERGE)
        assert json.loads(result) == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# _dispatch_stage
# ---------------------------------------------------------------------------


class TestDispatchStage:
    @pytest.mark.asyncio
    async def test_unknown_stage_type_returns_error_result(self) -> None:
        from anythink.workflow.stages import _dispatch_stage

        # Use a valid StageType to construct a stage, then manually check PLANNER
        stage = _make_stage(StageType.PLANNER, "s1")  # no executor registered
        state = _make_state()
        result = await _dispatch_stage(stage, state, _make_ctx(), _make_callbacks())

        assert result.error is not None

    @pytest.mark.asyncio
    async def test_dispatches_mcp_call_to_executor(self) -> None:
        from anythink.mcp.models import MCPCallResult
        from anythink.workflow.stages import _dispatch_stage

        stage = _make_stage(StageType.MCP_CALL, "s1", tool_name="fs.read")
        state = _make_state()
        ctx = _make_ctx()
        ctx.mcp_manager.call_tool = AsyncMock(
            return_value=MCPCallResult(tool_name="fs.read", server_name="fs", content="data")
        )

        result = await _dispatch_stage(stage, state, ctx, _make_callbacks())

        assert result.stage_type == StageType.MCP_CALL
        assert result.error is None
