"""V4 MMOS dataclasses — shared across all optimize submodules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelCapability:
    """Constraint and capability metadata for a single model in the registry."""

    id: str
    provider: str
    display_name: str
    tier: str  # "local" | "free-api"
    context_window: int
    max_output_tokens: int
    rpm_limit: int | None
    tpm_limit: int | None
    rpd_limit: int | None
    strength_categories: list[str]  # e.g. ["coding","reasoning","creative","factual","math"]
    speed_class: str  # "fast" | "medium" | "slow"
    quality_class: str  # "high" | "medium" | "low"
    supports_system_prompt: bool
    supports_streaming: bool
    requires_network: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "display_name": self.display_name,
            "tier": self.tier,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "rpm_limit": self.rpm_limit,
            "tpm_limit": self.tpm_limit,
            "rpd_limit": self.rpd_limit,
            "strength_categories": list(self.strength_categories),
            "speed_class": self.speed_class,
            "quality_class": self.quality_class,
            "supports_system_prompt": self.supports_system_prompt,
            "supports_streaming": self.supports_streaming,
            "requires_network": self.requires_network,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelCapability:
        return cls(
            id=str(data["id"]),
            provider=str(data["provider"]),
            display_name=str(data.get("display_name", data["id"])),
            tier=str(data.get("tier", "free-api")),
            context_window=int(data.get("context_window", 4096)),
            max_output_tokens=int(data.get("max_output_tokens", 4096)),
            rpm_limit=int(data["rpm_limit"]) if data.get("rpm_limit") is not None else None,
            tpm_limit=int(data["tpm_limit"]) if data.get("tpm_limit") is not None else None,
            rpd_limit=int(data["rpd_limit"]) if data.get("rpd_limit") is not None else None,
            strength_categories=list(data.get("strength_categories", [])),
            speed_class=str(data.get("speed_class", "medium")),
            quality_class=str(data.get("quality_class", "medium")),
            supports_system_prompt=bool(data.get("supports_system_prompt", True)),
            supports_streaming=bool(data.get("supports_streaming", True)),
            requires_network=bool(data.get("requires_network", True)),
            notes=str(data.get("notes", "")),
        )


@dataclass
class OptimizeSettings:
    """Persisted optimization settings — mirrors the /optimize panel state."""

    enabled: bool = True
    mode: str = "auto"  # "online" | "offline" | "auto"
    microprompt_enabled: bool = True
    orchestration_mode: str = "auto"  # "deterministic" | "meta_llm" | "auto"
    routing_strategy: str = "combined"  # "category" | "token_length" | "combined"
    priority: str = "quality"  # "quality" | "reliability" | "hybrid"
    override_allowed: bool = True
    history_mode: str = "semantic"  # "semantic" | "recency" | "model_decides"
    history_max_tokens: int = 2048
    summarisation_model: str = ""
    mixing_mode: str = "routing"  # "routing" | "ensemble" | "chaining" | "decompose"
    ensemble_count: int = 2
    plan_mode_enabled: bool = True
    plan_approval_required: bool = True
    queue_mode: str = "auto"  # "auto" | "manual"
    fallback_order: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "microprompt_enabled": self.microprompt_enabled,
            "orchestration_mode": self.orchestration_mode,
            "routing_strategy": self.routing_strategy,
            "priority": self.priority,
            "override_allowed": self.override_allowed,
            "history_mode": self.history_mode,
            "history_max_tokens": self.history_max_tokens,
            "summarisation_model": self.summarisation_model,
            "mixing_mode": self.mixing_mode,
            "ensemble_count": self.ensemble_count,
            "plan_mode_enabled": self.plan_mode_enabled,
            "plan_approval_required": self.plan_approval_required,
            "queue_mode": self.queue_mode,
            "fallback_order": list(self.fallback_order),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OptimizeSettings:
        return cls(
            enabled=bool(data.get("enabled", True)),
            mode=str(data.get("mode", "auto")),
            microprompt_enabled=bool(data.get("microprompt_enabled", True)),
            orchestration_mode=str(data.get("orchestration_mode", "auto")),
            routing_strategy=str(data.get("routing_strategy", "combined")),
            priority=str(data.get("priority", "quality")),
            override_allowed=bool(data.get("override_allowed", True)),
            history_mode=str(data.get("history_mode", "semantic")),
            history_max_tokens=int(data.get("history_max_tokens", 2048)),
            summarisation_model=str(data.get("summarisation_model", "")),
            mixing_mode=str(data.get("mixing_mode", "routing")),
            ensemble_count=int(data.get("ensemble_count", 2)),
            plan_mode_enabled=bool(data.get("plan_mode_enabled", True)),
            plan_approval_required=bool(data.get("plan_approval_required", True)),
            queue_mode=str(data.get("queue_mode", "auto")),
            fallback_order=list(data.get("fallback_order", [])),
        )


@dataclass
class RoutingDecision:
    """Output from the routing engine for a single query."""

    strategy: str  # "routing" | "ensemble" | "chaining" | "decompose"
    primary_model: str
    phase_models: list[str] = field(default_factory=list)
    recombination_model: str | None = None
    plan_mode: bool = False
    confidence: float = 1.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "primary_model": self.primary_model,
            "phase_models": list(self.phase_models),
            "recombination_model": self.recombination_model,
            "plan_mode": self.plan_mode,
            "confidence": self.confidence,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutingDecision:
        return cls(
            strategy=str(data.get("strategy", "routing")),
            primary_model=str(data.get("primary_model", "")),
            phase_models=list(data.get("phase_models", [])),
            recombination_model=data.get("recombination_model"),
            plan_mode=bool(data.get("plan_mode", False)),
            confidence=float(data.get("confidence", 1.0)),
            reason=str(data.get("reason", "")),
        )


@dataclass
class QueryIntent:
    """Classification of the current query — from micro-prompt or deterministic inference."""

    category: str  # "Coding"|"Reasoning"|"Creative"|"Factual"|"Research"|"Other"
    format_preference: str  # "detailed"|"concise"|"step_by_step"|"bullet"|"code_only"
    priority_override: str | None  # "quality"|"speed"|None
    from_user: bool = True  # False when system inferred, not from micro-prompt

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "format_preference": self.format_preference,
            "priority_override": self.priority_override,
            "from_user": self.from_user,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryIntent:
        return cls(
            category=str(data.get("category", "Other")),
            format_preference=str(data.get("format_preference", "detailed")),
            priority_override=data.get("priority_override"),
            from_user=bool(data.get("from_user", True)),
        )


@dataclass
class TurnMMOSMetadata:
    """MMOS metadata stored per conversation turn in ChatMessage.metadata['mmos']."""

    strategy: str
    model_ids: list[str]
    intent: QueryIntent | None
    routing_decision: RoutingDecision | None
    total_tokens: int
    elapsed_s: float
    plan_session_id: str | None = None
    phase_outputs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "model_ids": list(self.model_ids),
            "intent": self.intent.to_dict() if self.intent else None,
            "routing_decision": self.routing_decision.to_dict() if self.routing_decision else None,
            "total_tokens": self.total_tokens,
            "elapsed_s": self.elapsed_s,
            "plan_session_id": self.plan_session_id,
            "phase_outputs": list(self.phase_outputs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TurnMMOSMetadata:
        intent_raw = data.get("intent")
        routing_raw = data.get("routing_decision")
        return cls(
            strategy=str(data.get("strategy", "routing")),
            model_ids=list(data.get("model_ids", [])),
            intent=QueryIntent.from_dict(intent_raw) if intent_raw else None,
            routing_decision=RoutingDecision.from_dict(routing_raw) if routing_raw else None,
            total_tokens=int(data.get("total_tokens", 0)),
            elapsed_s=float(data.get("elapsed_s", 0.0)),
            plan_session_id=data.get("plan_session_id"),
            phase_outputs=list(data.get("phase_outputs", [])),
        )
