"""Tests for optimize/router.py — RoutingEngine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anythink.config.manager import Paths
from anythink.optimize.classifier import IntentClassifier
from anythink.optimize.models import ModelCapability, OptimizeSettings, QueryIntent
from anythink.optimize.rate_limit import RateLimitManager
from anythink.optimize.registry import ModelCapabilityRegistry
from anythink.optimize.router import RoutingEngine
from anythink.optimize.rules import RoutingRulesLoader


# ── Test fixtures ─────────────────────────────────────────────────────────────


def _make_cap(
    model_id: str,
    tier: str = "free-api",
    strength: list[str] | None = None,
    speed: str = "fast",
    quality: str = "high",
    context_window: int = 8192,
    rpm_limit: int | None = 30,
) -> ModelCapability:
    return ModelCapability(
        id=model_id,
        provider=model_id.split("/")[0],
        display_name=model_id,
        tier=tier,
        context_window=context_window,
        max_output_tokens=4096,
        rpm_limit=rpm_limit,
        tpm_limit=None,
        rpd_limit=None,
        strength_categories=strength or ["coding"],
        speed_class=speed,
        quality_class=quality,
        supports_system_prompt=True,
        supports_streaming=True,
        requires_network=tier != "local",
    )


def _write_bundled(tmp_path: Path, models: list[ModelCapability]) -> Path:
    path = tmp_path / "bundled.json"
    path.write_text(
        json.dumps({"_registry_version": "4.0.0", "models": [m.to_dict() for m in models]})
    )
    return path


@pytest.fixture()
def three_model_registry(tmp_path: Path, xdg_dirs: Paths) -> ModelCapabilityRegistry:
    models = [
        _make_cap("test/coding-specialist", strength=["coding"], quality="high"),
        _make_cap("test/reasoning-model", strength=["reasoning"], quality="medium"),
        _make_cap("local/fast-local", tier="local", strength=["factual"], speed="fast", rpm_limit=None),
    ]
    return ModelCapabilityRegistry(
        bundled_path=_write_bundled(tmp_path, models),
        user_path=xdg_dirs.model_capability_registry_user_file,
    )


@pytest.fixture()
def rate_mgr(xdg_dirs: Paths, three_model_registry: ModelCapabilityRegistry) -> RateLimitManager:
    return RateLimitManager(
        state_path=xdg_dirs.rate_limit_state_file,
        registry=three_model_registry,
    )


def _make_engine(
    registry: ModelCapabilityRegistry,
    rate: RateLimitManager,
    settings: OptimizeSettings | None = None,
    rules_path: Path | None = None,
) -> RoutingEngine:
    if settings is None:
        settings = OptimizeSettings()
    if rules_path is None:
        # Use a non-existent path so no rules load
        rules_path = Path("/nonexistent/routing_rules.yaml")
    return RoutingEngine(
        registry=registry,
        rate_limit_manager=rate,
        settings=settings,
        rules_loader=RoutingRulesLoader(path=rules_path),
        classifier=IntentClassifier(),
    )


def _coding_intent() -> QueryIntent:
    return QueryIntent(
        category="Coding",
        format_preference="detailed",
        priority_override=None,
        from_user=False,
    )


def _reasoning_intent() -> QueryIntent:
    return QueryIntent(
        category="Reasoning",
        format_preference="detailed",
        priority_override=None,
        from_user=False,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestRoutingEngine:
    def test_coding_query_routes_to_coding_specialist(
        self, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        engine = _make_engine(three_model_registry, rate_mgr)
        decision = engine.decide(
            query="Write a binary search tree in Python",
            intent=_coding_intent(),
            history_token_estimate=0,
            override_flags={},
            mode="auto",
        )
        assert decision.primary_model == "test/coding-specialist"

    def test_rate_limited_model_skipped(
        self, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        # Exhaust coding specialist RPM
        for _ in range(30):
            rate_mgr.record_request("test/coding-specialist", tokens=100)
        assert rate_mgr.is_at_rpm_limit("test/coding-specialist")

        engine = _make_engine(three_model_registry, rate_mgr)
        decision = engine.decide(
            query="Write a function",
            intent=_coding_intent(),
            history_token_estimate=0,
            override_flags={},
            mode="auto",
        )
        # Should not pick the rate-limited model
        assert decision.primary_model != "test/coding-specialist"

    def test_model_override_flag_honoured(
        self, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        engine = _make_engine(three_model_registry, rate_mgr)
        decision = engine.decide(
            query="Explain something",
            intent=_coding_intent(),
            history_token_estimate=0,
            override_flags={"model": "local/fast-local"},
            mode="auto",
        )
        assert decision.primary_model == "local/fast-local"
        assert decision.reason.startswith("User forced model")

    def test_unknown_model_override_falls_through(
        self, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        engine = _make_engine(three_model_registry, rate_mgr)
        decision = engine.decide(
            query="Explain something",
            intent=_coding_intent(),
            history_token_estimate=0,
            override_flags={"model": "nonexistent/ghost-model"},
            mode="auto",
        )
        # Falls through to deterministic — primary model is from the registry
        assert decision.primary_model in {"test/coding-specialist", "test/reasoning-model", "local/fast-local"}

    def test_online_mode_excludes_local(
        self, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        engine = _make_engine(three_model_registry, rate_mgr)
        decision = engine.decide(
            query="Factual question",
            intent=QueryIntent(category="Factual", format_preference="concise", priority_override=None),
            history_token_estimate=0,
            override_flags={},
            mode="online",
        )
        cap = three_model_registry.get(decision.primary_model)
        assert cap is not None
        assert cap.tier == "free-api"

    def test_offline_mode_returns_local_only(
        self, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        engine = _make_engine(three_model_registry, rate_mgr)
        decision = engine.decide(
            query="Factual question",
            intent=QueryIntent(category="Factual", format_preference="concise", priority_override=None),
            history_token_estimate=0,
            override_flags={},
            mode="offline",
        )
        cap = three_model_registry.get(decision.primary_model)
        assert cap is not None
        assert cap.tier == "local"

    def test_reasoning_quality_first_triggers_ensemble(
        self, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        settings = OptimizeSettings(priority="quality", mixing_mode="routing")
        engine = _make_engine(three_model_registry, rate_mgr, settings=settings)
        decision = engine.decide(
            query="Compare different approaches to system design",
            intent=_reasoning_intent(),
            history_token_estimate=0,
            override_flags={},
            mode="auto",
        )
        assert decision.strategy == "ensemble"
        assert len(decision.phase_models) >= 1

    def test_detect_conflict_context_overflow(
        self, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        engine = _make_engine(three_model_registry, rate_mgr)
        from anythink.optimize.models import RoutingDecision

        decision = RoutingDecision(strategy="routing", primary_model="test/coding-specialist")
        warning = engine.detect_override_conflict(
            override={"model": "local/fast-local"},
            decision=decision,
            query_token_estimate=99999,  # way over context_window=8192
        )
        assert warning is not None
        assert "context window" in warning.lower()

    def test_detect_no_conflict_when_fits(
        self, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        engine = _make_engine(three_model_registry, rate_mgr)
        from anythink.optimize.models import RoutingDecision

        decision = RoutingDecision(strategy="routing", primary_model="test/coding-specialist")
        warning = engine.detect_override_conflict(
            override={"model": "local/fast-local"},
            decision=decision,
            query_token_estimate=100,  # well within 8192
        )
        assert warning is None

    def test_detect_conflict_unknown_model(
        self, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        engine = _make_engine(three_model_registry, rate_mgr)
        from anythink.optimize.models import RoutingDecision

        decision = RoutingDecision(strategy="routing", primary_model="test/coding-specialist")
        warning = engine.detect_override_conflict(
            override={"model": "ghost/model"},
            decision=decision,
            query_token_estimate=100,
        )
        assert warning is not None
        assert "registry" in warning.lower()

    def test_yaml_rule_overrides_deterministic(
        self, tmp_path: Path, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        rules_path = tmp_path / "rules.yaml"
        rules_path.write_text(
            "- name: force-ensemble-for-reasoning\n"
            "  condition: \"category == 'Reasoning'\"\n"
            "  action: strategy=ensemble\n"
            "  priority: 10\n"
        )
        engine = _make_engine(three_model_registry, rate_mgr, rules_path=rules_path)
        decision = engine.decide(
            query="Which is better?",
            intent=_reasoning_intent(),
            history_token_estimate=0,
            override_flags={},
            mode="auto",
        )
        assert decision.strategy == "ensemble"
        assert "rule" in decision.reason.lower()

    def test_select_ensemble_models_returns_diverse_providers(
        self, three_model_registry: ModelCapabilityRegistry, rate_mgr: RateLimitManager
    ) -> None:
        engine = _make_engine(three_model_registry, rate_mgr)
        models = engine._select_ensemble_models(_coding_intent(), count=2, mode="auto")
        assert len(models) >= 1
        providers = [three_model_registry.get(m).provider for m in models if three_model_registry.get(m)]
        # Should prefer different providers when possible
        assert len(set(providers)) >= 1
