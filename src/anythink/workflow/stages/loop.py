"""LOOP stage wrapper — delegates to LoopExecutor (workflow/loop.py)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from anythink.workflow.models import StageResult, StageType

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.workflow.models import Stage, WorkflowCallbacks, WorkflowState


async def execute(
    stage: Stage,
    state: WorkflowState,
    ctx: AppContext,
    callbacks: WorkflowCallbacks,
) -> StageResult:
    """Execute a LOOP stage — iterates sub-stages over each item in a collection."""
    # All imports are deferred to avoid circular dependencies at module load time.
    from anythink.workflow.loop import LoopExecutor  # noqa: PLC0415
    from anythink.workflow.stages import _dispatch_stage  # noqa: PLC0415

    start = time.monotonic()

    if stage.loop_def is None:
        return StageResult(
            stage_id=stage.id,
            stage_type=StageType.LOOP,
            output={},
            raw_content="",
            duration_s=time.monotonic() - start,
            error="LOOP stage is missing loop_def.",
        )

    collection = state.resolve_ref(stage.loop_def.input_collection_ref)
    if not isinstance(collection, list):
        collection = [collection] if collection is not None else []

    async def _run_sub_stage(
        sub_stage: Stage,
        sub_state: WorkflowState,
        sub_ctx: AppContext,
        sub_callbacks: WorkflowCallbacks,
    ) -> StageResult:
        return await _dispatch_stage(sub_stage, sub_state, sub_ctx, sub_callbacks)

    return await LoopExecutor().run(
        loop_def=stage.loop_def,
        collection=collection,
        state=state,
        ctx=ctx,
        callbacks=callbacks,
        stage_runner=_run_sub_stage,
    )
