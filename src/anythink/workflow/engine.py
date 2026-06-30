"""WorkflowEngine — top-level orchestrator for multi-stage workflow execution."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from anythink.workflow.models import (
    Stage,
    StageResult,
    StageType,
    UserDecision,
    WorkflowLog,
    WorkflowPlan,
    WorkflowState,
    WorkflowStatus,
)
from anythink.workflow.stages import _dispatch_stage

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.workflow.log import WorkflowLogger
    from anythink.workflow.loop import LoopExecutor
    from anythink.workflow.models import ClarificationRequest, WorkflowCallbacks
    from anythink.workflow.optimizer import StageOutputOptimizer
    from anythink.workflow.planner import WorkflowPlanner
    from anythink.workflow.router import MetaRouter
    from anythink.workflow.storage import WorkflowStorage


class WorkflowEngine:
    """Drives a :class:`WorkflowPlan` stage by stage to completion.

    Responsibilities:
    - Serial and parallel stage dispatch
    - CONDITION branch selection
    - Automatic USER_APPROVAL guard injection for destructive stages
    - Pause / stop support via :class:`WorkflowState` flags
    - Per-stage logging via :class:`WorkflowLogger`
    """

    def __init__(
        self,
        planner: WorkflowPlanner,
        router: MetaRouter,
        optimizer: StageOutputOptimizer,
        loop_executor: LoopExecutor,
        logger: WorkflowLogger,
        storage: WorkflowStorage,
    ) -> None:
        self._planner = planner
        self._router = router
        self._optimizer = optimizer
        self._loop_executor = loop_executor
        self._logger = logger
        self._storage = storage

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        plan: WorkflowPlan,
        ctx: AppContext,
        callbacks: WorkflowCallbacks,
    ) -> WorkflowLog:
        """Execute *plan* end-to-end and return the completed :class:`WorkflowLog`."""
        log = self._logger.begin(plan)
        state = WorkflowState(plan=plan, status=WorkflowStatus.RUNNING)

        try:
            await self._execute_stages(plan.stages, state, ctx, callbacks, log)
        except Exception as exc:  # noqa: BLE001
            final_output = f"Workflow failed with an unexpected error: {exc}"
            self._logger.finalize(log, WorkflowStatus.FAILED, final_output)
            return log

        if state.stop_requested:
            status = WorkflowStatus.ABORTED
            final_output = "Workflow stopped by user request."
        else:
            status = WorkflowStatus.COMPLETED
            final_output = self._build_final_output(state)

        self._logger.finalize(log, status, final_output)
        return log

    async def plan_task(
        self,
        task: str,
        planner_alias: str = "",
    ) -> WorkflowPlan | ClarificationRequest:
        """Delegate to the planner to decompose *task* into a WorkflowPlan."""
        return await self._planner.plan(task, planner_alias)

    async def dry_run(self, plan: WorkflowPlan, ctx: AppContext) -> str:
        """Return a human-readable summary of what *plan* would do, without executing."""
        lines: list[str] = [
            f"Workflow: {plan.name}",
            f"Trigger : {plan.trigger}",
            "",
            f"Stages ({len(plan.stages)}):",
        ]
        lines.extend(self._describe_stages(plan.stages, indent=2))
        lines += [
            "",
            f"Models     : {', '.join(plan.models_used) or '(none)'}",
            f"MCP servers: {', '.join(plan.mcp_servers_used) or '(none)'}",
        ]
        if plan.estimated_duration_s:
            lines.append(f"Est. time  : {plan.estimated_duration_s}s")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal stage dispatch
    # ------------------------------------------------------------------

    async def _execute_stages(
        self,
        stages: list[Stage],
        state: WorkflowState,
        ctx: AppContext,
        callbacks: WorkflowCallbacks,
        log: WorkflowLog,
    ) -> None:
        """Iterate *stages*, handling parallel groups and CONDITION branches."""
        i = 0
        while i < len(stages):
            if state.stop_requested:
                break

            stage = stages[i]

            # ── Parallel group ─────────────────────────────────────────
            if stage.is_parallel:
                group, i = self._collect_parallel_group(stages, i)
                results = await asyncio.gather(
                    *[self._run_one_stage(s, state, ctx, callbacks) for s in group]
                )
                aborted = False
                for s, result in zip(group, results, strict=False):
                    await self._post_stage(s, result, state, log, callbacks)
                    if result.user_decision == UserDecision.ABORTED:
                        state.stop_requested = True
                        aborted = True
                if aborted:
                    break
                continue

            # ── Serial stage ───────────────────────────────────────────
            result = await self._run_one_stage(stage, state, ctx, callbacks)
            await self._post_stage(stage, result, state, log, callbacks)

            if result.user_decision == UserDecision.ABORTED:
                state.stop_requested = True
                break

            # ── CONDITION branching ────────────────────────────────────
            if stage.type == StageType.CONDITION and not result.error:
                branch = result.output.get("branch", "b")
                branch_stages = stage.branch_a if branch == "a" else stage.branch_b
                if branch_stages:
                    await self._execute_stages(branch_stages, state, ctx, callbacks, log)

            i += 1

    async def _run_one_stage(
        self,
        stage: Stage,
        state: WorkflowState,
        ctx: AppContext,
        callbacks: WorkflowCallbacks,
    ) -> StageResult:
        """Execute a single stage, inserting an approval guard for destructive ops."""
        await callbacks.on_stage_start(stage)
        state.current_stage_id = stage.id

        # Auto-inject USER_APPROVAL guard before any destructive non-approval stage
        if stage.is_destructive and stage.type != StageType.USER_APPROVAL:
            guard = Stage(
                id=f"{stage.id}__guard",
                type=StageType.USER_APPROVAL,
                label=f"Approve destructive action: {stage.label or stage.id}",
                approval_message=(
                    f"The next step is destructive: '{stage.label or stage.id}'. Proceed?"
                ),
            )
            from anythink.workflow.stages import user_approval  # noqa: PLC0415

            guard_result = await user_approval.execute(guard, state, ctx, callbacks)
            if guard_result.user_decision in (UserDecision.ABORTED, UserDecision.SKIPPED):
                return StageResult(
                    stage_id=stage.id,
                    stage_type=stage.type,
                    user_decision=guard_result.user_decision,
                    skipped=True,
                    raw_content=f"{guard_result.user_decision.value} at approval gate.",
                )

        return await _dispatch_stage(stage, state, ctx, callbacks)

    async def _post_stage(
        self,
        stage: Stage,
        result: StageResult,
        state: WorkflowState,
        log: WorkflowLog,
        callbacks: WorkflowCallbacks,
    ) -> None:
        """Store result, update log, and fire the completion callback."""
        state.store_result(result)
        self._logger.record_stage(log, result)
        await callbacks.on_stage_complete(stage, result)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_parallel_group(stages: list[Stage], start: int) -> tuple[list[Stage], int]:
        """Return the run of consecutive parallel stages beginning at *start*."""
        group = [stages[start]]
        j = start + 1
        while j < len(stages) and stages[j].is_parallel:
            group.append(stages[j])
            j += 1
        return group, j

    def _build_final_output(self, state: WorkflowState) -> str:
        """Return the last stage's raw content as the workflow's final output."""
        if not state.completed_stages:
            return "(no output)"
        last = state.completed_stages[-1]
        return last.raw_content or str(last.output) or "(no output)"

    def _describe_stages(self, stages: list[Stage], indent: int) -> list[str]:
        """Recursively build a human-readable stage list for dry_run."""
        prefix = " " * indent
        lines: list[str] = []
        for i, stage in enumerate(stages, 1):
            tags: list[str] = []
            if stage.is_parallel:
                tags.append("parallel")
            if stage.is_destructive:
                tags.append("DESTRUCTIVE")
            tag_str = f"  [{', '.join(tags)}]" if tags else ""
            lines.append(f"{prefix}{i}. [{stage.type.value}] {stage.label or stage.id}{tag_str}")
            if stage.type == StageType.LLM_SPECIALIST:
                lines.append(f"{prefix}   model: {stage.model_alias or '(auto)'}")
            elif stage.type == StageType.MCP_CALL:
                lines.append(f"{prefix}   tool: {stage.tool_name}")
            elif stage.type == StageType.LOOP and stage.loop_def:
                ref = stage.loop_def.input_collection_ref
                sub_n = len(stage.loop_def.sub_stages)
                lines.append(f"{prefix}   loop over: {ref}  sub-stages: {sub_n}")
                if stage.loop_def.sub_stages:
                    lines.extend(self._describe_stages(stage.loop_def.sub_stages, indent + 4))
            elif stage.type == StageType.CONDITION:
                if stage.branch_a:
                    lines.append(f"{prefix}   [branch A]")
                    lines.extend(self._describe_stages(stage.branch_a, indent + 4))
                if stage.branch_b:
                    lines.append(f"{prefix}   [branch B]")
                    lines.extend(self._describe_stages(stage.branch_b, indent + 4))
        return lines
