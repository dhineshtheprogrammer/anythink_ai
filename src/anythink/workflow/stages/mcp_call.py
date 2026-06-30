"""MCP_CALL stage executor — delegates to ctx.mcp_manager."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

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
    """Execute a MCP_CALL stage by calling the specified MCP tool."""
    start = time.monotonic()

    resolved_params = _resolve_params(stage.tool_params, state)

    result = await ctx.mcp_manager.call_tool(stage.tool_name, resolved_params)

    duration = time.monotonic() - start

    if result.is_error:
        return StageResult(
            stage_id=stage.id,
            stage_type=StageType.MCP_CALL,
            output={},
            raw_content=result.content,
            duration_s=duration,
            tool_name=stage.tool_name,
            error=result.content,
        )

    raw_content = result.content
    output: dict[str, Any] = (
        {stage.output_field: raw_content} if stage.output_field else {"result": raw_content}
    )

    return StageResult(
        stage_id=stage.id,
        stage_type=StageType.MCP_CALL,
        output=output,
        raw_content=raw_content,
        duration_s=duration,
        tool_name=stage.tool_name,
    )


def _resolve_params(
    tool_params: dict[str, Any],
    state: WorkflowState,
) -> dict[str, Any]:
    """Resolve ``{{ref}}`` placeholders in *tool_params* from accumulated results."""
    resolved: dict[str, Any] = {}
    for key, value in tool_params.items():
        if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
            ref_key = value[2:-2].strip()
            actual = state.resolve_ref(ref_key)
            resolved[key] = actual if actual is not None else value
        else:
            resolved[key] = value
    return resolved
