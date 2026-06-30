"""Stage executor implementations for the MMWE."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.workflow.models import Stage, StageResult, WorkflowCallbacks, WorkflowState


async def _dispatch_stage(
    stage: Stage,
    state: WorkflowState,
    ctx: AppContext,
    callbacks: WorkflowCallbacks,
) -> StageResult:
    """Route *stage* to its executor. All imports are deferred to break cycles."""
    from anythink.workflow.models import StageResult, StageType
    from anythink.workflow.stages import (
        condition,
        formatter,
        llm_specialist,
        loop,
        mcp_call,
        user_approval,
    )

    _executors = {
        StageType.MCP_CALL: mcp_call.execute,
        StageType.LLM_SPECIALIST: llm_specialist.execute,
        StageType.USER_APPROVAL: user_approval.execute,
        StageType.CONDITION: condition.execute,
        StageType.FORMATTER: formatter.execute,
        StageType.LOOP: loop.execute,
    }

    executor = _executors.get(stage.type)
    if executor is not None:
        return await executor(stage, state, ctx, callbacks)

    return StageResult(
        stage_id=stage.id,
        stage_type=stage.type,
        error=f"No executor registered for stage type: {stage.type.value}",
        duration_s=0.0,
    )
