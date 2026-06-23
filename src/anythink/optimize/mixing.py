"""MixingOrchestrator — coordinates the four MMOS mixing strategies."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

from anythink.optimize.models import (
    OptimizeSettings,
    QueryIntent,
    RoutingDecision,
    TurnMMOSMetadata,
)
from anythink.optimize.plan import MixingResult
from anythink.optimize.plan_engine import PlanEngine, ProviderResolver, _collect_text
from anythink.optimize.plan_runner import PhaseUpdateCallback, PlanRunner
from anythink.optimize.rate_limit import RateLimitManager
from anythink.optimize.registry import ModelCapabilityRegistry
from anythink.providers.base import ChatMessage

_ENSEMBLE_SEPARATOR = "\n\n{bar}\nResponse from {model} ({speed}):\n{bar}\n"
_BAR = "=" * 60

_CHAIN_SYSTEM: dict[int, str] = {
    0: "You are a subject-matter expert. Provide a thorough initial draft response.",
    1: (
        "You are a critical reviewer. Review the draft response below and identify "
        "gaps, errors, or missing information. Be concise and specific."
    ),
    2: (
        "You are a refinement assistant. Using the original draft and the critique, "
        "produce an improved, polished final response."
    ),
}


class MixingOrchestrator:
    """Coordinates multi-model strategies for a single user query.

    Strategies:
    - routing    : single best-model call
    - ensemble   : parallel calls to multiple models; concatenate with attribution
    - chaining   : sequential draft → critique → refine pipeline
    - decompose  : Plan Mode (delegates to PlanEngine + PlanRunner)
    """

    def __init__(
        self,
        registry: ModelCapabilityRegistry,
        rate_limit_manager: RateLimitManager,
        settings: OptimizeSettings,
        plan_engine: PlanEngine,
        plan_runner: PlanRunner,
    ) -> None:
        self._registry = registry
        self._rate = rate_limit_manager
        self._settings = settings
        self._plan_engine = plan_engine
        self._plan_runner = plan_runner

    # ── Public API ────────────────────────────────────────────────────────

    async def execute(
        self,
        decision: RoutingDecision,
        messages: list[ChatMessage],
        intent: QueryIntent,
        provider_resolver: ProviderResolver,
        session_id: str,
        on_phase_update: PhaseUpdateCallback | None = None,
    ) -> MixingResult:
        """Dispatch to the appropriate strategy and return a MixingResult."""
        strategy = decision.strategy

        if strategy == "ensemble":
            return await self._ensemble_mode(decision, messages, intent, provider_resolver)
        if strategy == "chaining":
            return await self._chaining_mode(decision, messages, intent, provider_resolver)
        if strategy in ("decompose", "plan"):
            return await self._decompose_mode(
                decision, messages, intent, provider_resolver, session_id, on_phase_update
            )
        # Default: routing (single best model)
        return await self._routing_mode(decision, messages, intent, provider_resolver)

    # ── Strategies ────────────────────────────────────────────────────────

    async def _routing_mode(
        self,
        decision: RoutingDecision,
        messages: list[ChatMessage],
        intent: QueryIntent,
        provider_resolver: ProviderResolver,
    ) -> MixingResult:
        """Single-model call — fastest path."""
        model_id = decision.primary_model
        resolved = provider_resolver(model_id)
        if resolved is None:
            return _empty_result("routing", model_id, intent, decision)

        provider, api_model_id = resolved
        t0 = time.monotonic()
        try:
            text = await _collect_text(provider, messages, api_model_id)
        except Exception as exc:
            text = f"[Error from {model_id}: {exc}]"
        elapsed = time.monotonic() - t0

        tokens = len(text) // 4
        self._rate.record_request(model_id, tokens)

        meta = TurnMMOSMetadata(
            strategy="routing",
            model_ids=[model_id],
            intent=intent,
            routing_decision=decision,
            total_tokens=tokens,
            elapsed_s=elapsed,
        )
        return MixingResult(
            strategy="routing",
            outputs=[(model_id, text, elapsed)],
            final_text=text,
            total_tokens=tokens,
            metadata=meta,
        )

    async def _ensemble_mode(
        self,
        decision: RoutingDecision,
        messages: list[ChatMessage],
        intent: QueryIntent,
        provider_resolver: ProviderResolver,
    ) -> MixingResult:
        """Call multiple models concurrently; concatenate results with attribution."""
        model_ids = decision.phase_models or [decision.primary_model]
        if not model_ids:
            return _empty_result("ensemble", decision.primary_model, intent, decision)

        async def _call(mid: str) -> tuple[str, str, float]:
            resolved = provider_resolver(mid)
            if resolved is None:
                return mid, f"[{mid} not available]", 0.0
            provider, api_id = resolved
            t0 = time.monotonic()
            try:
                text = await _collect_text(provider, messages, api_id)
            except Exception as exc:
                text = f"[Error: {exc}]"
            return mid, text, time.monotonic() - t0

        results = await asyncio.gather(*[_call(mid) for mid in model_ids])

        # Build attributed concatenated text
        parts: list[str] = []
        total = len(results)
        used_model_ids: list[str] = []
        total_tokens = 0

        for idx, (mid, text, _elapsed) in enumerate(results, start=1):
            cap = self._registry.get(mid)
            speed = cap.speed_class if cap else "?"
            header = f"\n{_BAR}\nResponse {idx} of {total}  ·  {mid}  ·  [{speed}]\n{_BAR}\n"
            parts.append(header + text)
            used_model_ids.append(mid)
            tokens = len(text) // 4
            total_tokens += tokens
            self._rate.record_request(mid, tokens)

        final_text = "\n".join(parts)

        meta = TurnMMOSMetadata(
            strategy="ensemble",
            model_ids=used_model_ids,
            intent=intent,
            routing_decision=decision,
            total_tokens=total_tokens,
            elapsed_s=max((r[2] for r in results), default=0.0),
        )
        return MixingResult(
            strategy="ensemble",
            outputs=list(results),
            final_text=final_text,
            total_tokens=total_tokens,
            metadata=meta,
        )

    async def _chaining_mode(
        self,
        decision: RoutingDecision,
        messages: list[ChatMessage],
        intent: QueryIntent,
        provider_resolver: ProviderResolver,
    ) -> MixingResult:
        """Sequential draft → critique → refine pipeline."""
        chain = decision.phase_models or [decision.primary_model]
        if not chain:
            return _empty_result("chaining", decision.primary_model, intent, decision)

        outputs: list[tuple[str, str, float]] = []
        total_tokens = 0
        current_messages = list(messages)

        for step_idx, model_id in enumerate(chain):
            system_msg = _CHAIN_SYSTEM.get(step_idx, _CHAIN_SYSTEM[0])

            # Build step-specific context
            step_messages: list[ChatMessage] = [
                ChatMessage(
                    role="system", content=system_msg, timestamp=datetime.utcnow(), metadata={}
                )
            ]

            if step_idx > 0 and outputs:
                # Inject the previous step's output
                prev_text = outputs[-1][1]
                step_messages.append(
                    ChatMessage(
                        role="user",
                        content=f"Draft response to review/refine:\n\n{prev_text}",
                        timestamp=datetime.utcnow(),
                        metadata={},
                    )
                )
            else:
                step_messages.extend(current_messages)

            resolved = provider_resolver(model_id)
            if resolved is None:
                outputs.append((model_id, "[not available]", 0.0))
                continue

            provider, api_id = resolved
            t0 = time.monotonic()
            try:
                text = await _collect_text(provider, step_messages, api_id)
            except Exception as exc:
                text = f"[Error: {exc}]"
            elapsed = time.monotonic() - t0

            tokens = len(text) // 4
            total_tokens += tokens
            self._rate.record_request(model_id, tokens)
            outputs.append((model_id, text, elapsed))

        final_text = outputs[-1][1] if outputs else ""
        used_model_ids = [o[0] for o in outputs]

        meta = TurnMMOSMetadata(
            strategy="chaining",
            model_ids=used_model_ids,
            intent=intent,
            routing_decision=decision,
            total_tokens=total_tokens,
            elapsed_s=sum(o[2] for o in outputs),
        )
        return MixingResult(
            strategy="chaining",
            outputs=outputs,
            final_text=final_text,
            total_tokens=total_tokens,
            metadata=meta,
        )

    async def _decompose_mode(
        self,
        decision: RoutingDecision,
        messages: list[ChatMessage],
        intent: QueryIntent,
        provider_resolver: ProviderResolver,
        session_id: str,
        on_phase_update: PhaseUpdateCallback | None,
    ) -> MixingResult:
        """Generate a plan, execute it, return the recombined output."""
        # Extract the user query from the last user message
        query = ""
        for msg in reversed(messages):
            if msg.role == "user":
                query = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        plan = await self._plan_engine.generate_plan(
            query=query,
            intent=intent,
            routing_decision=decision,
            provider_resolver=provider_resolver,
            session_id=session_id,
            mode=self._settings.mode,
        )

        t0 = time.monotonic()
        plan = await self._plan_runner.execute(
            plan=plan,
            provider_resolver=provider_resolver,
            on_phase_update=on_phase_update,
        )
        elapsed = time.monotonic() - t0

        outputs = [(p.actual_model or p.model_id, p.output, p.elapsed_s) for p in plan.phases]
        total_tokens = sum(len(p.output) // 4 for p in plan.phases)
        used_model_ids = list({p.actual_model or p.model_id for p in plan.phases})

        phase_dicts = [
            {
                "phase_num": p.phase_num,
                "title": p.title,
                "model": p.actual_model or p.model_id,
                "output": p.output,
                "elapsed_s": p.elapsed_s,
            }
            for p in plan.phases
        ]

        meta = TurnMMOSMetadata(
            strategy="decompose",
            model_ids=used_model_ids,
            intent=intent,
            routing_decision=decision,
            total_tokens=total_tokens,
            elapsed_s=elapsed,
            plan_session_id=plan.plan_id,
            phase_outputs=phase_dicts,
        )
        return MixingResult(
            strategy="decompose",
            outputs=outputs,
            final_text=plan.final_output,
            total_tokens=total_tokens,
            metadata=meta,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _empty_result(
    strategy: str,
    model_id: str,
    intent: QueryIntent,
    decision: RoutingDecision,
) -> MixingResult:
    meta = TurnMMOSMetadata(
        strategy=strategy,
        model_ids=[model_id],
        intent=intent,
        routing_decision=decision,
        total_tokens=0,
        elapsed_s=0.0,
    )
    return MixingResult(
        strategy=strategy,
        outputs=[],
        final_text="[No provider available]",
        total_tokens=0,
        metadata=meta,
    )
