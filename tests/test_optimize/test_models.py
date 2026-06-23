"""Tests for optimize/models.py — dataclass round-trips."""

from __future__ import annotations

from anythink.optimize.models import (
    ModelCapability,
    OptimizeSettings,
    QueryIntent,
    RoutingDecision,
    TurnMMOSMetadata,
)


class TestModelCapability:
    def _make(self) -> ModelCapability:
        return ModelCapability(
            id="groq/llama3-70b",
            provider="groq",
            display_name="Llama 3 70B",
            tier="free-api",
            context_window=8192,
            max_output_tokens=4096,
            rpm_limit=30,
            tpm_limit=6000,
            rpd_limit=14400,
            strength_categories=["coding", "reasoning"],
            speed_class="fast",
            quality_class="high",
            supports_system_prompt=True,
            supports_streaming=True,
            requires_network=True,
            notes="Test model",
        )

    def test_to_dict_contains_all_fields(self) -> None:
        cap = self._make()
        d = cap.to_dict()
        assert d["id"] == "groq/llama3-70b"
        assert d["provider"] == "groq"
        assert d["rpm_limit"] == 30
        assert d["strength_categories"] == ["coding", "reasoning"]
        assert d["tier"] == "free-api"

    def test_roundtrip(self) -> None:
        cap = self._make()
        restored = ModelCapability.from_dict(cap.to_dict())
        assert restored.id == cap.id
        assert restored.rpm_limit == cap.rpm_limit
        assert restored.strength_categories == cap.strength_categories
        assert restored.notes == cap.notes

    def test_null_rate_limits(self) -> None:
        cap = ModelCapability(
            id="ollama/mistral",
            provider="ollama",
            display_name="Mistral Local",
            tier="local",
            context_window=32768,
            max_output_tokens=4096,
            rpm_limit=None,
            tpm_limit=None,
            rpd_limit=None,
            strength_categories=["coding"],
            speed_class="medium",
            quality_class="medium",
            supports_system_prompt=True,
            supports_streaming=True,
            requires_network=False,
        )
        restored = ModelCapability.from_dict(cap.to_dict())
        assert restored.rpm_limit is None
        assert restored.tpm_limit is None
        assert restored.rpd_limit is None
        assert restored.requires_network is False


class TestOptimizeSettings:
    def test_defaults(self) -> None:
        s = OptimizeSettings()
        assert s.enabled is True
        assert s.mode == "auto"
        assert s.priority == "quality"
        assert s.fallback_order == []

    def test_roundtrip(self) -> None:
        s = OptimizeSettings(
            enabled=False,
            mode="offline",
            microprompt_enabled=False,
            priority="reliability",
            history_max_tokens=4096,
            ensemble_count=3,
            fallback_order=["groq/llama3-70b", "ollama/mistral"],
        )
        restored = OptimizeSettings.from_dict(s.to_dict())
        assert restored.enabled is False
        assert restored.mode == "offline"
        assert restored.priority == "reliability"
        assert restored.history_max_tokens == 4096
        assert restored.fallback_order == ["groq/llama3-70b", "ollama/mistral"]

    def test_from_dict_missing_keys_use_defaults(self) -> None:
        s = OptimizeSettings.from_dict({})
        assert s.enabled is True
        assert s.mode == "auto"


class TestRoutingDecision:
    def test_roundtrip(self) -> None:
        rd = RoutingDecision(
            strategy="ensemble",
            primary_model="groq/llama3-70b",
            phase_models=["ollama/mistral", "groq/mixtral"],
            recombination_model="ollama/mistral",
            plan_mode=True,
            confidence=0.85,
            reason="Multi-domain query",
        )
        restored = RoutingDecision.from_dict(rd.to_dict())
        assert restored.strategy == "ensemble"
        assert restored.phase_models == ["ollama/mistral", "groq/mixtral"]
        assert restored.plan_mode is True
        assert restored.confidence == 0.85

    def test_defaults(self) -> None:
        rd = RoutingDecision(strategy="routing", primary_model="groq/llama3-70b")
        assert rd.phase_models == []
        assert rd.recombination_model is None
        assert rd.plan_mode is False


class TestQueryIntent:
    def test_roundtrip(self) -> None:
        qi = QueryIntent(
            category="Coding",
            format_preference="code_only",
            priority_override="speed",
            from_user=True,
        )
        restored = QueryIntent.from_dict(qi.to_dict())
        assert restored.category == "Coding"
        assert restored.format_preference == "code_only"
        assert restored.priority_override == "speed"
        assert restored.from_user is True

    def test_null_priority(self) -> None:
        qi = QueryIntent(
            category="Factual",
            format_preference="concise",
            priority_override=None,
        )
        restored = QueryIntent.from_dict(qi.to_dict())
        assert restored.priority_override is None


class TestTurnMMOSMetadata:
    def test_roundtrip_full(self) -> None:
        intent = QueryIntent(
            category="Research", format_preference="detailed", priority_override=None
        )
        decision = RoutingDecision(
            strategy="decompose", primary_model="groq/llama3-70b", plan_mode=True
        )
        meta = TurnMMOSMetadata(
            strategy="decompose",
            model_ids=["groq/llama3-70b", "ollama/mistral"],
            intent=intent,
            routing_decision=decision,
            total_tokens=3500,
            elapsed_s=12.4,
            plan_session_id="sess-abc123",
            phase_outputs=[{"phase": 1, "output": "hello"}],
        )
        restored = TurnMMOSMetadata.from_dict(meta.to_dict())
        assert restored.strategy == "decompose"
        assert restored.model_ids == ["groq/llama3-70b", "ollama/mistral"]
        assert restored.intent is not None
        assert restored.intent.category == "Research"
        assert restored.routing_decision is not None
        assert restored.routing_decision.plan_mode is True
        assert restored.total_tokens == 3500
        assert restored.plan_session_id == "sess-abc123"
        assert len(restored.phase_outputs) == 1

    def test_roundtrip_minimal(self) -> None:
        meta = TurnMMOSMetadata(
            strategy="routing",
            model_ids=["groq/llama3-70b"],
            intent=None,
            routing_decision=None,
            total_tokens=100,
            elapsed_s=0.5,
        )
        restored = TurnMMOSMetadata.from_dict(meta.to_dict())
        assert restored.intent is None
        assert restored.routing_decision is None
        assert restored.plan_session_id is None
        assert restored.phase_outputs == []
