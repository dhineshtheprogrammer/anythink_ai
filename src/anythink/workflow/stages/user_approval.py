"""USER_APPROVAL stage executor — pauses execution for user confirmation."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from anythink.workflow.models import StageResult, StageType, UserDecision

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.workflow.models import Stage, WorkflowCallbacks, WorkflowState


async def execute(
    stage: Stage,
    state: WorkflowState,
    ctx: AppContext,
    callbacks: WorkflowCallbacks,
) -> StageResult:
    """Execute a USER_APPROVAL stage by invoking the approval callback."""
    start = time.monotonic()

    message = stage.approval_message or "Proceed with the next step?"
    decision_str = await callbacks.on_approval_needed(message)

    try:
        decision = UserDecision(decision_str)
    except ValueError:
        decision = UserDecision.APPROVED

    return StageResult(
        stage_id=stage.id,
        stage_type=StageType.USER_APPROVAL,
        output={"decision": decision.value},
        raw_content=decision.value,
        duration_s=time.monotonic() - start,
        user_decision=decision,
        skipped=(decision == UserDecision.SKIPPED),
    )
