"""PlanRunner — executes an approved ExecutionPlan phase by phase."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from anythink.optimize.plan import (
    PHASE_STATUS_DONE,
    PHASE_STATUS_FAILED,
    PHASE_STATUS_RUNNING,
    PHASE_STATUS_SKIPPED,
    PLAN_STATUS_ABORTED,
    PLAN_STATUS_DONE,
    PLAN_STATUS_RUNNING,
    ExecutionPlan,
    PhaseUpdate,
    PlanPhase,
)
from anythink.optimize.plan_engine import ProviderResolver, _collect_text
from anythink.optimize.rate_limit import RateLimitManager
from anythink.optimize.registry import ModelCapabilityRegistry
from anythink.providers.base import BaseProvider, ChatMessage

PhaseUpdateCallback = Callable[[PhaseUpdate], None]

_RATE_POLL_INTERVAL = 1.0  # seconds between rate-limit polls
_RECOMBINATION_SYSTEM = (
    "You are a synthesis assistant. You will receive a user's original question "
    "and answers from multiple focused sub-tasks. Combine them into a single, "
    "coherent, well-structured response that fully answers the user's question. "
    "Do not repeat identical information. Maintain a logical flow."
)


class PlanRunner:
    """Executes an approved ExecutionPlan phase by phase.

    Handles:
    - Rate-limit-aware pacing (polls until a slot is available)
    - Automatic model fallback when the assigned model is rate-limited
    - Pause/skip/abort via asyncio.Event signals
    - Progress callbacks that fire on every state transition
    - Saving the plan to a text file after completion
    """

    def __init__(
        self,
        registry: ModelCapabilityRegistry,
        rate_limit_manager: RateLimitManager,
        plans_dir: Path,
    ) -> None:
        self._registry = registry
        self._rate = rate_limit_manager
        self._plans_dir = plans_dir

    # ── Public API ────────────────────────────────────────────────────────

    async def execute(
        self,
        plan: ExecutionPlan,
        provider_resolver: ProviderResolver,
        on_phase_update: PhaseUpdateCallback | None = None,
        *,
        abort_signal: asyncio.Event | None = None,
        skip_phase: int | None = None,
        pause_after_phase: int | None = None,
    ) -> ExecutionPlan:
        """Run all phases; return the plan with outputs filled in."""
        plan.status = PLAN_STATUS_RUNNING
        prior_outputs: dict[int, str] = {}

        for phase in plan.phases:
            if abort_signal is not None and abort_signal.is_set():
                phase.status = PHASE_STATUS_SKIPPED
                _emit(on_phase_update, PhaseUpdate(phase.phase_num, PHASE_STATUS_SKIPPED, 0.0))
                continue

            if skip_phase is not None and phase.phase_num == skip_phase:
                phase.status = PHASE_STATUS_SKIPPED
                _emit(on_phase_update, PhaseUpdate(phase.phase_num, PHASE_STATUS_SKIPPED, 0.0))
                continue

            # Emit "running" update
            phase.status = PHASE_STATUS_RUNNING
            _emit(on_phase_update, PhaseUpdate(phase.phase_num, PHASE_STATUS_RUNNING, 0.0))

            # Resolve provider (with rate-limit-aware switching)
            model_id, provider, api_model_id, queue_wait = await self._resolve_provider(
                phase.model_id,
                provider_resolver,
                on_phase_update,
                phase.phase_num,
                abort_signal,
            )

            if provider is None:
                phase.status = PHASE_STATUS_FAILED
                phase.output = "No provider available for this phase."
                _emit(
                    on_phase_update,
                    PhaseUpdate(phase.phase_num, PHASE_STATUS_FAILED, 0.0, error=phase.output),
                )
                continue

            # Build phase prompt
            prompt = self._build_phase_prompt(phase, plan, prior_outputs)
            messages = [
                ChatMessage(role="user", content=prompt, timestamp=datetime.utcnow(), metadata={})
            ]

            t_start = time.monotonic()
            try:
                output = await _collect_text(provider, messages, api_model_id)
                self._rate.record_request(model_id, len(output) // 4)
            except Exception as exc:
                phase.status = PHASE_STATUS_FAILED
                phase.elapsed_s = time.monotonic() - t_start
                phase.output = f"[Error: {exc}]"
                _emit(
                    on_phase_update,
                    PhaseUpdate(
                        phase.phase_num, PHASE_STATUS_FAILED, phase.elapsed_s, error=str(exc)
                    ),
                )
                continue

            phase.elapsed_s = time.monotonic() - t_start
            phase.actual_model = model_id
            phase.output = output
            phase.status = PHASE_STATUS_DONE
            prior_outputs[phase.phase_num] = output

            _emit(
                on_phase_update,
                PhaseUpdate(
                    phase.phase_num,
                    PHASE_STATUS_DONE,
                    phase.elapsed_s,
                    queue_wait_s=queue_wait,
                    actual_model=model_id,
                ),
            )

            # Handle pause-after
            if (
                pause_after_phase is not None
                and phase.phase_num == pause_after_phase
                and abort_signal is not None
            ):
                await abort_signal.wait()

            if abort_signal is not None and abort_signal.is_set():
                break

        # Recombination step
        if not self._all_failed(plan) and plan.status != PLAN_STATUS_ABORTED:
            plan.final_output = await self._recombine(plan, prior_outputs, provider_resolver)

        if abort_signal is not None and abort_signal.is_set():
            plan.status = PLAN_STATUS_ABORTED
        else:
            plan.status = PLAN_STATUS_DONE

        self._save_plan(plan)
        return plan

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _resolve_provider(
        self,
        preferred_model_id: str,
        provider_resolver: ProviderResolver,
        on_update: PhaseUpdateCallback | None,
        phase_num: int,
        abort_signal: asyncio.Event | None,
    ) -> tuple[str, BaseProvider | None, str, float]:
        """Return (model_id, provider, api_model_id, queue_wait_secs).

        Waits for rate limit window if the model is currently at its limit,
        or falls back to the next available model in the registry.
        """
        queue_wait = 0.0
        candidates = [preferred_model_id] + [
            cap.id
            for cap in self._registry.all()
            if cap.id != preferred_model_id
        ]

        for candidate in candidates:
            # Wait for the rate window if needed
            if self._rate.is_at_rpm_limit(candidate):
                wait = self._rate.seconds_until_available(candidate)
                if wait > 0:
                    queue_wait += wait
                    _emit(
                        on_update,
                        PhaseUpdate(phase_num, "queued", 0.0, queue_wait_s=wait),
                    )
                    # Poll until available or abort
                    waited = 0.0
                    while waited < wait:
                        if abort_signal is not None and abort_signal.is_set():
                            return candidate, None, "", queue_wait
                        await asyncio.sleep(_RATE_POLL_INTERVAL)
                        waited += _RATE_POLL_INTERVAL
                        if not self._rate.is_at_rpm_limit(candidate):
                            break

            window = self._rate._get_window(candidate)
            if window.unavailable:
                continue
            if self._rate.is_at_rpd_limit(candidate):
                continue

            resolved = provider_resolver(candidate)
            if resolved is not None:
                provider, api_model_id = resolved
                return candidate, provider, api_model_id, queue_wait

        return preferred_model_id, None, "", queue_wait

    def _build_phase_prompt(
        self,
        phase: PlanPhase,
        plan: ExecutionPlan,
        prior_outputs: dict[int, str],
    ) -> str:
        """Construct the prompt for a single phase."""
        parts: list[str] = [
            f"Original question: {plan.original_query}",
            "",
            f"Your task (Phase {phase.phase_num} of {len(plan.phases)}): {phase.description}",
        ]

        # Include prior phase outputs this phase depends on
        for dep_num in phase.depends_on:
            dep_output = prior_outputs.get(dep_num, "")
            if dep_output:
                parts += [
                    "",
                    f"--- Output from Phase {dep_num} (you can build on this) ---",
                    dep_output,
                    "--- End of Phase output ---",
                ]

        if phase.output_type == "code":
            parts += ["", "Provide your answer as working code with brief inline comments."]
        elif phase.output_type == "table":
            parts += ["", "Provide your answer as a structured comparison table."]
        elif phase.output_type == "detail":
            parts += ["", "Provide a thorough, detailed explanation."]

        return "\n".join(parts)

    async def _recombine(
        self,
        plan: ExecutionPlan,
        prior_outputs: dict[int, str],
        provider_resolver: ProviderResolver,
    ) -> str:
        """Send all phase outputs to the recombination model for synthesis."""
        if not prior_outputs:
            return ""

        resolved = provider_resolver(plan.recombination_model) if plan.recombination_model else None
        # If recombination model not available, try any available model
        if resolved is None:
            for cap in self._registry.all():
                resolved = provider_resolver(cap.id)
                if resolved is not None:
                    break

        if resolved is None:
            # Last resort: concatenate all outputs
            return "\n\n---\n\n".join(
                f"**Phase {n}:**\n{out}" for n, out in sorted(prior_outputs.items())
            )

        provider, api_model_id = resolved

        lines: list[str] = [
            f"Original question: {plan.original_query}",
            "",
            "The following sub-answers have been gathered:",
            "",
        ]
        for phase in plan.phases:
            output = prior_outputs.get(phase.phase_num, "")
            if output:
                lines += [
                    f"--- Phase {phase.phase_num}: {phase.title} ---",
                    output,
                    "",
                ]
        lines += ["Now synthesise these into a single coherent final answer."]

        now = datetime.utcnow()
        messages = [
            ChatMessage(role="system", content=_RECOMBINATION_SYSTEM, timestamp=now, metadata={}),
            ChatMessage(role="user", content="\n".join(lines), timestamp=now, metadata={}),
        ]

        try:
            result = await _collect_text(provider, messages, api_model_id)
            self._rate.record_request(plan.recombination_model or api_model_id, len(result) // 4)
            return result
        except Exception:
            return "\n\n---\n\n".join(
                f"**Phase {n}:**\n{out}" for n, out in sorted(prior_outputs.items())
            )

    def _save_plan(self, plan: ExecutionPlan) -> Path:
        """Write the plan to a text file; return the file path."""
        self._plans_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"plan_{plan.session_id[:8]}_{ts}.txt"
        path = self._plans_dir / filename
        path.write_text(plan.to_text(), encoding="utf-8")
        return path

    @staticmethod
    def _all_failed(plan: ExecutionPlan) -> bool:
        done = {PHASE_STATUS_DONE, PHASE_STATUS_SKIPPED}
        return not any(p.status in done for p in plan.phases)


def _emit(callback: PhaseUpdateCallback | None, update: PhaseUpdate) -> None:
    """Call *callback* safely, ignoring None."""
    if callback is not None:
        with contextlib.suppress(Exception):
            callback(update)
