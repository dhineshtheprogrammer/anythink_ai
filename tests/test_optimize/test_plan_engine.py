"""Tests for optimize/plan_engine.py — PlanEngine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from anythink.config.manager import Paths
from anythink.optimize.models import (
    ModelCapability,
    OptimizeSettings,
    QueryIntent,
    RoutingDecision,
)
from anythink.optimize.plan import PLAN_STATUS_PENDING, ExecutionPlan
from anythink.optimize.plan_engine import PlanEngine
from anythink.optimize.rate_limit import RateLimitManager
from anythink.optimize.registry import ModelCapabilityRegistry
from anythink.providers.base import BaseProvider, StreamChunk


def _make_cap(model_id: str, tier: str = "free-api", speed: str = "fast") -> ModelCapability:
    return ModelCapability(
        id=model_id,
        provider=model_id.split("/")[0],
        display_name=model_id,
        tier=tier,
        context_window=8192,
        max_output_tokens=4096,
        rpm_limit=30 if tier == "free-api" else None,
        tpm_limit=None,
        rpd_limit=None,
        strength_categories=["coding"],
        speed_class=speed,
        quality_class="medium",
        supports_system_prompt=True,
        supports_streaming=True,
        requires_network=tier != "local",
    )


def _make_registry(tmp_path: Path, models: list[ModelCapability], xdg_dirs: Paths) -> ModelCapabilityRegistry:
    bundled = tmp_path / "bundled.json"
    bundled.write_text(
        json.dumps({"_registry_version": "4.0.0", "models": [m.to_dict() for m in models]})
    )
    return ModelCapabilityRegistry(bundled_path=bundled, user_path=xdg_dirs.model_capability_registry_user_file)


def _mock_provider(response_text: str) -> BaseProvider:
    """Create a mock provider that streams *response_text* as a single chunk."""
    provider = MagicMock(spec=BaseProvider)

    async def _stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield StreamChunk(text=response_text, finish_reason="stop")

    provider.stream_chat = _stream
    return provider


def _resolver_for(provider: BaseProvider, api_model_id: str = "model-id"):
    """Return a ProviderResolver that always returns the given provider."""
    def _resolve(model_id: str):
        return provider, api_model_id
    return _resolve


class TestPlanEngine:
    def _make_engine(self, registry: ModelCapabilityRegistry, xdg_dirs: Paths) -> PlanEngine:
        rate_mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        return PlanEngine(
            registry=registry,
            rate_limit_manager=rate_mgr,
            settings=OptimizeSettings(),
        )

    def _coding_intent(self) -> QueryIntent:
        return QueryIntent(category="Coding", format_preference="detailed", priority_override=None)

    def _routing_decision(self, primary: str = "groq/fast") -> RoutingDecision:
        return RoutingDecision(strategy="decompose", primary_model=primary, plan_mode=True)

    async def test_generates_plan_from_valid_response(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("groq/fast"), _make_cap("ollama/local", tier="local")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        engine = self._make_engine(registry, xdg_dirs)

        plan_text = (
            "PHASE 1: Project structure\n"
            "  DESCRIPTION: Set up folder layout\n"
            "  MODEL: groq/fast\n"
            "  EST_TOKENS: 800\n"
            "  DEPENDS_ON: none\n"
            "  OUTPUT_TYPE: explanation\n"
            "\n"
            "PHASE 2: Frontend setup\n"
            "  DESCRIPTION: Configure React\n"
            "  MODEL: groq/fast\n"
            "  EST_TOKENS: 1000\n"
            "  DEPENDS_ON: 1\n"
            "  OUTPUT_TYPE: detail\n"
        )
        provider = _mock_provider(plan_text)

        plan = await engine.generate_plan(
            query="Build a React + Node.js app",
            intent=self._coding_intent(),
            routing_decision=self._routing_decision("groq/fast"),
            provider_resolver=_resolver_for(provider),
            session_id="sess-test",
            mode="auto",
        )

        assert isinstance(plan, ExecutionPlan)
        assert len(plan.phases) == 2
        assert plan.phases[0].title == "Project structure"
        assert plan.phases[1].depends_on == [1]
        assert plan.status == PLAN_STATUS_PENDING

    async def test_fallback_plan_on_empty_response(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("groq/fast")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        engine = self._make_engine(registry, xdg_dirs)

        provider = _mock_provider("")  # Empty response → parse fails → fallback
        plan = await engine.generate_plan(
            query="Explain quantum physics",
            intent=self._coding_intent(),
            routing_decision=self._routing_decision("groq/fast"),
            provider_resolver=_resolver_for(provider),
            session_id="sess-fallback",
            mode="auto",
        )

        assert len(plan.phases) == 1
        assert plan.phases[0].title == "Answer query"

    async def test_fallback_plan_when_no_provider(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("groq/fast")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        engine = self._make_engine(registry, xdg_dirs)

        def _no_resolver(model_id: str):
            return None

        plan = await engine.generate_plan(
            query="Test query",
            intent=self._coding_intent(),
            routing_decision=self._routing_decision("groq/fast"),
            provider_resolver=_no_resolver,
            session_id="sess-noprov",
            mode="auto",
        )
        assert plan is not None
        assert len(plan.phases) >= 1

    def test_select_planning_model_prefers_fast_local_in_offline(
        self, tmp_path: Path, xdg_dirs: Paths
    ) -> None:
        models = [
            _make_cap("ollama/fast-local", tier="local", speed="fast"),
            _make_cap("groq/online", tier="free-api", speed="fast"),
        ]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        engine = self._make_engine(registry, xdg_dirs)
        model = engine._select_planning_model(mode="offline")
        assert model == "ollama/fast-local"

    def test_select_planning_model_online_returns_api_model(
        self, tmp_path: Path, xdg_dirs: Paths
    ) -> None:
        models = [
            _make_cap("ollama/local", tier="local", speed="fast"),
            _make_cap("groq/online", tier="free-api", speed="fast"),
        ]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        engine = self._make_engine(registry, xdg_dirs)
        model = engine._select_planning_model(mode="online")
        assert model == "groq/online"

    def test_select_planning_model_returns_none_when_empty(
        self, tmp_path: Path, xdg_dirs: Paths
    ) -> None:
        registry = _make_registry(tmp_path, [], xdg_dirs)
        engine = self._make_engine(registry, xdg_dirs)
        assert engine._select_planning_model("auto") is None

    async def test_provider_exception_returns_fallback(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("groq/fast")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        engine = self._make_engine(registry, xdg_dirs)

        bad_provider = MagicMock(spec=BaseProvider)

        async def _error_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("API error")
            yield  # make it a generator  # noqa: unreachable

        bad_provider.stream_chat = _error_stream

        plan = await engine.generate_plan(
            query="Something",
            intent=self._coding_intent(),
            routing_decision=self._routing_decision("groq/fast"),
            provider_resolver=_resolver_for(bad_provider),
            session_id="sess-err",
            mode="auto",
        )
        # Should return a fallback plan rather than raising
        assert isinstance(plan, ExecutionPlan)
        assert len(plan.phases) >= 1

    async def test_regenerate_plan_returns_new_plan(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("groq/fast")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        engine = self._make_engine(registry, xdg_dirs)

        plan_text = (
            "PHASE 1: Revised approach\n"
            "  DESCRIPTION: New description\n"
            "  MODEL: groq/fast\n"
            "  EST_TOKENS: 600\n"
            "  DEPENDS_ON: none\n"
            "  OUTPUT_TYPE: explanation\n"
        )
        provider = _mock_provider(plan_text)
        original = ExecutionPlan.new("sess-orig", "original query")

        revised = await engine.regenerate_plan(
            original=original,
            feedback="Too many phases",
            provider_resolver=_resolver_for(provider),
            mode="auto",
        )
        assert isinstance(revised, ExecutionPlan)
