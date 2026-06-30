"""LoopExecutor — iterates a sub-stage pipeline over each item in a collection."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from anythink.workflow.models import (
    AccumulationStrategy,
    LoopDefinition,
    StageResult,
    StageType,
)

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.workflow.models import Stage, WorkflowCallbacks, WorkflowState

StageRunnerFn = Callable[
    ["Stage", "WorkflowState", "AppContext", "WorkflowCallbacks"],
    Awaitable[StageResult],
]


class LoopExecutor:
    """Runs a sub-stage pipeline once per item in a collection.

    Accumulation strategy controls how per-iteration outputs are combined:
    - ``append``: each output is appended to a list (default)
    - ``merge``: dict outputs are merged into a single dict
    - ``structured_list``: JSON-parseable outputs are collected as structured objects
    """

    async def run(
        self,
        loop_def: LoopDefinition,
        collection: list[Any],
        state: WorkflowState,
        ctx: AppContext,
        callbacks: WorkflowCallbacks,
        stage_runner: StageRunnerFn,
    ) -> StageResult:
        """Iterate *collection* through *loop_def.sub_stages* and accumulate results."""
        start = time.monotonic()
        total = len(collection)
        accumulated: list[Any] = []
        errors: list[str] = []
        last_result: StageResult | None = None

        for idx, item in enumerate(collection):
            if state.stop_requested:
                break

            # Honour pause: spin until resumed or stopped
            while state.paused and not state.stop_requested:
                await asyncio.sleep(0.1)

            if state.stop_requested:
                break

            # Expose the current loop item to downstream refs
            state.accumulated_results["loop.current_item"] = item
            state.accumulated_results["loop.current_index"] = idx

            iteration_error: str | None = None

            for sub_stage in loop_def.sub_stages:
                result = await stage_runner(sub_stage, state, ctx, callbacks)
                last_result = result
                state.store_result(result)
                if result.error and not result.skipped:
                    iteration_error = result.error
                    break

            if last_result is None:
                last_result = StageResult(
                    stage_id="loop_item",
                    stage_type=StageType.LOOP,
                    output={},
                    error="No sub-stages were executed for this iteration.",
                )

            item_value = _extract_value(last_result, item)
            _accumulate(accumulated, item_value, loop_def.accumulation_strategy)

            if iteration_error:
                errors.append(f"[item {idx}] {iteration_error}")

            await callbacks.on_loop_progress(idx + 1, total, last_result)

        final_output = _build_final(accumulated, loop_def.accumulation_strategy)

        return StageResult(
            stage_id="loop_accumulated",
            stage_type=StageType.LOOP,
            output={"results": accumulated, "final": final_output},
            raw_content=final_output,
            duration_s=time.monotonic() - start,
            error="; ".join(errors) if errors else None,
        )


# ---------------------------------------------------------------------------
# Accumulation helpers
# ---------------------------------------------------------------------------


def _extract_value(result: StageResult, fallback: Any) -> Any:
    """Return the primary output value from a stage result."""
    if result.output:
        vals = list(result.output.values())
        return vals[0] if len(vals) == 1 else result.output
    return result.raw_content if result.raw_content else fallback


def _accumulate(
    accumulated: list[Any],
    value: Any,
    strategy: AccumulationStrategy,
) -> None:
    """Add *value* to *accumulated* according to *strategy*."""
    if strategy == AccumulationStrategy.MERGE:
        if isinstance(value, dict) and accumulated and isinstance(accumulated[0], dict):
            accumulated[0].update(value)
            return
    elif strategy == AccumulationStrategy.STRUCTURED_LIST and isinstance(value, str):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            value = json.loads(value)
    accumulated.append(value)


def _build_final(accumulated: list[Any], strategy: AccumulationStrategy) -> str:
    """Serialise the accumulated list to a human-readable string."""
    if not accumulated:
        return ""

    if strategy == AccumulationStrategy.MERGE and accumulated and isinstance(accumulated[0], dict):
        return json.dumps(accumulated[0], indent=2, default=str)

    try:
        return json.dumps(accumulated, indent=2, default=str)
    except (TypeError, ValueError):
        return "\n".join(str(x) for x in accumulated)
