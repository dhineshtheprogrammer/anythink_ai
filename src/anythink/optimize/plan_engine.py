"""PlanEngine — generates an ExecutionPlan from a query using a fast model."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import datetime

from anythink.optimize.models import OptimizeSettings, QueryIntent, RoutingDecision
from anythink.optimize.plan import (
    PLAN_STATUS_PENDING,
    ExecutionPlan,
    PlanPhase,
)
from anythink.optimize.rate_limit import RateLimitManager
from anythink.optimize.registry import ModelCapabilityRegistry
from anythink.providers.base import BaseProvider, ChatMessage

# Type alias: takes a capability model_id → (provider, api_model_id) or None
ProviderResolver = Callable[[str], tuple[BaseProvider, str] | None]

_PLANNING_SYSTEM_PROMPT = """\
You are a planning assistant. Your job is to decompose a complex user query into
a numbered list of focused sub-tasks. Each sub-task will be executed independently
by an AI model. Output ONLY the plan in the exact format below — no preamble,
no markdown, no explanation outside the format.

Format:
PHASE 1: <short title>
  DESCRIPTION: <one or two sentences describing this sub-task>
  MODEL: <model_id from the provided list>
  EST_TOKENS: <integer estimate of tokens needed for this sub-task>
  DEPENDS_ON: <comma-separated phase numbers, or "none">
  OUTPUT_TYPE: <explanation|code|table|detail>

PHASE 2: ...

Rules:
- Decompose into 2–6 phases. Never more than 6.
- Each phase must be independently answerable.
- Assign the most appropriate model for each phase's category.
- EST_TOKENS should be between 200 and 2000.
- DEPENDS_ON: phases whose output this phase needs (typically "none" or a single prior phase).
- OUTPUT_TYPE: "code" for code-heavy, "table" for comparisons, "explanation" or "detail" otherwise.
"""

_PLANNING_USER_TEMPLATE = """\
User query: {query}

Available models:
{model_list}

Produce a plan now.
"""

_PHASE_PATTERN = re.compile(
    r"PHASE\s+(\d+)\s*:\s*(.+?)\n"
    r"(?:.*?DESCRIPTION\s*:\s*(.+?)\n)?"
    r"(?:.*?MODEL\s*:\s*(\S+)\n)?"
    r"(?:.*?EST_TOKENS\s*:\s*(\d+)\n)?"
    r"(?:.*?DEPENDS_ON\s*:\s*(.+?)\n)?"
    r"(?:.*?OUTPUT_TYPE\s*:\s*(\S+)\n)?",
    re.DOTALL,
)


async def _collect_text(
    provider: BaseProvider,
    messages: list[ChatMessage],
    model_id: str,
) -> str:
    """Stream all chunks from a provider and return the concatenated text."""
    parts: list[str] = []
    async for chunk in provider.stream_chat(messages, model_id):
        if chunk.text:
            parts.append(chunk.text)
    return "".join(parts)


class PlanEngine:
    """Generates an ExecutionPlan from a user query.

    Uses a fast available model to produce a structured plan document, then
    parses the response into PlanPhase objects. Falls back to a single-phase
    plan if the model output cannot be parsed.
    """

    def __init__(
        self,
        registry: ModelCapabilityRegistry,
        rate_limit_manager: RateLimitManager,
        settings: OptimizeSettings,
    ) -> None:
        self._registry = registry
        self._rate = rate_limit_manager
        self._settings = settings

    # ── Public API ────────────────────────────────────────────────────────

    async def generate_plan(
        self,
        query: str,
        intent: QueryIntent,
        routing_decision: RoutingDecision,
        provider_resolver: ProviderResolver,
        session_id: str,
        mode: str,
    ) -> ExecutionPlan:
        """Generate a plan for *query*; return a pending ExecutionPlan."""
        planning_model_id = self._select_planning_model(mode)
        resolved = provider_resolver(planning_model_id) if planning_model_id else None

        if resolved is None:
            # No planning model available — create a minimal single-phase plan
            return self._fallback_plan(query, routing_decision, session_id)

        provider, api_model_id = resolved
        model_list = self._format_model_list(mode)
        prompt = _PLANNING_USER_TEMPLATE.format(query=query, model_list=model_list)

        now = datetime.utcnow()
        messages = [
            ChatMessage(role="system", content=_PLANNING_SYSTEM_PROMPT, timestamp=now, metadata={}),
            ChatMessage(role="user", content=prompt, timestamp=now, metadata={}),
        ]

        try:
            raw = await _collect_text(provider, messages, api_model_id)
        except Exception:
            return self._fallback_plan(query, routing_decision, session_id)

        plan = self._parse_plan_response(raw, query, session_id, routing_decision)
        return plan

    async def regenerate_plan(
        self,
        original: ExecutionPlan,
        feedback: str,
        provider_resolver: ProviderResolver,
        mode: str,
    ) -> ExecutionPlan:
        """Re-generate a plan, incorporating *feedback* about why the previous was rejected."""
        planning_model_id = self._select_planning_model(mode)
        resolved = provider_resolver(planning_model_id) if planning_model_id else None

        if resolved is None:
            return original

        provider, api_model_id = resolved
        model_list = self._format_model_list(mode)
        prompt = (
            f"The previous plan for this query was rejected. Reason: {feedback}\n\n"
            f"User query: {original.original_query}\n\n"
            f"Available models:\n{model_list}\n\n"
            "Produce a revised plan now."
        )
        now2 = datetime.utcnow()
        messages = [
            ChatMessage(
                role="system", content=_PLANNING_SYSTEM_PROMPT, timestamp=now2, metadata={}
            ),
            ChatMessage(role="user", content=prompt, timestamp=now2, metadata={}),
        ]

        try:
            raw = await _collect_text(provider, messages, api_model_id)
        except Exception:
            return original

        from anythink.optimize.models import RoutingDecision as _RD

        dummy_decision = _RD(strategy="decompose", primary_model="")
        return self._parse_plan_response(
            raw, original.original_query, original.session_id, dummy_decision
        )

    # ── Internal helpers ──────────────────────────────────────────────────

    def _select_planning_model(self, mode: str) -> str | None:
        """Pick the fastest available low-cost model for plan generation."""
        candidates = (
            self._registry.available_offline()
            if mode == "offline"
            else (
                self._registry.available_online()
                if mode == "online"
                else self._registry.all()
            )
        )
        if not candidates:
            return None

        # Prefer fast models; local models preferred in offline/auto
        fast = [c for c in candidates if c.speed_class == "fast"]
        if fast:
            # Prefer local fast if available and not strictly online
            if mode != "online":
                local_fast = [c for c in fast if c.tier == "local"]
                if local_fast:
                    return local_fast[0].id
            return fast[0].id

        return candidates[0].id

    def _format_model_list(self, mode: str) -> str:
        """Format available models as a bulleted list for the planning prompt."""
        if mode == "offline":
            caps = self._registry.available_offline()
        elif mode == "online":
            caps = self._registry.available_online()
        else:
            caps = self._registry.all()

        lines = []
        for cap in caps:
            strengths = ", ".join(cap.strength_categories) if cap.strength_categories else "general"
            line = f"- {cap.id} ({cap.speed_class}, {cap.quality_class} quality, {strengths})"
            lines.append(line)
        return "\n".join(lines) if lines else "- (no models available)"

    def _parse_plan_response(
        self,
        raw: str,
        query: str,
        session_id: str,
        routing_decision: RoutingDecision,
    ) -> ExecutionPlan:
        """Parse the planning model's text output into an ExecutionPlan."""
        phases: list[PlanPhase] = []
        recombination_model = routing_decision.recombination_model or ""

        # Try structured regex parse first
        for m in _PHASE_PATTERN.finditer(raw):
            phase_num = int(m.group(1))
            title = (m.group(2) or "").strip()
            description = (m.group(3) or "").strip()
            model_id = (m.group(4) or routing_decision.primary_model or "").strip()
            est_tokens_raw = m.group(5)
            est_tokens = int(est_tokens_raw) if est_tokens_raw and est_tokens_raw.isdigit() else 500
            depends_raw = (m.group(6) or "none").strip().lower()
            depends = (
                []
                if depends_raw in ("none", "")
                else [int(x.strip()) for x in depends_raw.split(",") if x.strip().isdigit()]
            )
            output_type = (m.group(7) or "explanation").strip()

            # Validate model_id is in registry; fall back to primary_model
            if not self._registry.get(model_id):
                model_id = routing_decision.primary_model or model_id

            phases.append(
                PlanPhase(
                    phase_num=phase_num,
                    title=title,
                    description=description,
                    model_id=model_id,
                    estimated_tokens=min(max(est_tokens, 100), 4096),
                    depends_on=depends,
                    output_type=output_type,
                )
            )

        if not phases:
            return self._fallback_plan(query, routing_decision, session_id)

        # Sort by phase_num
        phases.sort(key=lambda p: p.phase_num)

        # Renumber sequentially in case parsing gaps occurred
        for idx, phase in enumerate(phases, start=1):
            phase.phase_num = idx

        if not recombination_model and routing_decision.recombination_model:
            recombination_model = routing_decision.recombination_model
        elif not recombination_model and phases:
            recombination_model = phases[-1].model_id

        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            session_id=session_id,
            original_query=query,
            phases=phases,
            created_at=datetime.utcnow(),
            recombination_model=recombination_model,
            status=PLAN_STATUS_PENDING,
        )

    def _fallback_plan(
        self,
        query: str,
        routing_decision: RoutingDecision,
        session_id: str,
    ) -> ExecutionPlan:
        """Return a minimal single-phase plan when parsing or model call fails."""
        primary = routing_decision.primary_model or ""
        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            session_id=session_id,
            original_query=query,
            phases=[
                PlanPhase(
                    phase_num=1,
                    title="Answer query",
                    description=query,
                    model_id=primary,
                    estimated_tokens=800,
                    output_type="explanation",
                )
            ],
            created_at=datetime.utcnow(),
            recombination_model=primary,
            status=PLAN_STATUS_PENDING,
        )
