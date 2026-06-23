"""Tests for optimize/mixing.py — MixingOrchestrator."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anythink.config.manager import Paths
from anythink.optimize.models import (
    ModelCapability,
    OptimizeSettings,
    QueryIntent,
    RoutingDecision,
)
from anythink.optimize.mixing import MixingOrchestrator
from anythink.optimize.plan_engine import PlanEngine
from anythink.optimize.plan_runner import PlanRunner
from anythink.optimize.rate_limit import RateLimitManager
from anythink.optimize.registry import ModelCapabilityRegistry
from anythink.providers.base import BaseProvider, ChatMessage, StreamChunk


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_cap(model_id: str, tier: str = "local") -> ModelCapability:
    return ModelCapability(
        id=model_id,
        provider=model_id.split("/")[0],
        display_name=model_id,
        tier=tier,
        context_window=8192,
        max_output_tokens=4096,
        rpm_limit=None,
        tpm_limit=None,
        rpd_limit=None,
        strength_categories=["coding"],
        speed_class="fast",
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


def _provider_for(response: str) -> BaseProvider:
    p = MagicMock(spec=BaseProvider)

    async def _stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield StreamChunk(text=response, finish_reason="stop")

    p.stream_chat = _stream
    return p


def _make_orchestrator(
    registry: ModelCapabilityRegistry, xdg_dirs: Paths, settings: OptimizeSettings | None = None
) -> MixingOrchestrator:
    rate_mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
    settings = settings or OptimizeSettings()
    plan_engine = PlanEngine(registry=registry, rate_limit_manager=rate_mgr, settings=settings)
    plan_runner = PlanRunner(registry=registry, rate_limit_manager=rate_mgr, plans_dir=xdg_dirs.plans_dir)
    return MixingOrchestrator(
        registry=registry,
        rate_limit_manager=rate_mgr,
        settings=settings,
        plan_engine=plan_engine,
        plan_runner=plan_runner,
    )


def _user_messages(text: str) -> list[ChatMessage]:
    return [ChatMessage(role="user", content=text, timestamp=datetime.utcnow(), metadata={})]


def _coding_intent() -> QueryIntent:
    return QueryIntent(category="Coding", format_preference="detailed", priority_override=None)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestMixingOrchestratorRouting:
    async def test_routing_calls_single_model(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        registry = _make_registry(tmp_path, [_make_cap("test/local")], xdg_dirs)
        orch = _make_orchestrator(registry, xdg_dirs)

        provider = _provider_for("routing response")
        resolver_calls: list[str] = []

        def _resolver(mid: str):
            resolver_calls.append(mid)
            return provider, mid

        decision = RoutingDecision(strategy="routing", primary_model="test/local")
        result = await orch.execute(
            decision=decision,
            messages=_user_messages("Hello"),
            intent=_coding_intent(),
            provider_resolver=_resolver,
            session_id="sess",
        )

        assert result.strategy == "routing"
        assert result.final_text == "routing response"
        # Should only call the primary model
        assert resolver_calls == ["test/local"]

    async def test_routing_unavailable_provider_returns_empty(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        registry = _make_registry(tmp_path, [_make_cap("test/local")], xdg_dirs)
        orch = _make_orchestrator(registry, xdg_dirs)

        decision = RoutingDecision(strategy="routing", primary_model="test/local")
        result = await orch.execute(
            decision=decision,
            messages=_user_messages("Q"),
            intent=_coding_intent(),
            provider_resolver=lambda _: None,
            session_id="sess",
        )
        assert "no provider available" in result.final_text.lower()


class TestMixingOrchestratorEnsemble:
    async def test_ensemble_calls_all_phase_models(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [
            _make_cap("test/model-a"),
            _make_cap("test/model-b"),
            _make_cap("test/model-c"),
        ]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        orch = _make_orchestrator(registry, xdg_dirs)

        responses = {"test/model-a": "A says hello", "test/model-b": "B says world", "test/model-c": "C says!"}
        called: list[str] = []

        def _resolver(mid: str):
            called.append(mid)
            return _provider_for(responses.get(mid, "generic")), mid

        decision = RoutingDecision(
            strategy="ensemble",
            primary_model="test/model-a",
            phase_models=["test/model-a", "test/model-b", "test/model-c"],
        )
        result = await orch.execute(
            decision=decision,
            messages=_user_messages("Compare approaches"),
            intent=_coding_intent(),
            provider_resolver=_resolver,
            session_id="sess",
        )

        assert result.strategy == "ensemble"
        assert len(result.outputs) == 3
        assert set(called) == {"test/model-a", "test/model-b", "test/model-c"}
        # All responses present in final text
        for mid, text, _ in result.outputs:
            assert text in result.final_text

    async def test_ensemble_output_includes_attribution_headers(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/m1"), _make_cap("test/m2")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        orch = _make_orchestrator(registry, xdg_dirs)

        def _resolver(mid: str):
            return _provider_for(f"response from {mid}"), mid

        decision = RoutingDecision(
            strategy="ensemble",
            primary_model="test/m1",
            phase_models=["test/m1", "test/m2"],
        )
        result = await orch.execute(
            decision=decision,
            messages=_user_messages("Q"),
            intent=_coding_intent(),
            provider_resolver=_resolver,
            session_id="sess",
        )

        # Attribution headers should be present
        assert "test/m1" in result.final_text
        assert "test/m2" in result.final_text
        assert "Response 1 of 2" in result.final_text

    async def test_ensemble_total_tokens_sums_all(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/m1"), _make_cap("test/m2")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        orch = _make_orchestrator(registry, xdg_dirs)

        def _resolver(mid: str):
            return _provider_for("x" * 400), mid  # 400 chars ≈ 100 tokens

        decision = RoutingDecision(
            strategy="ensemble",
            primary_model="test/m1",
            phase_models=["test/m1", "test/m2"],
        )
        result = await orch.execute(
            decision=decision,
            messages=_user_messages("Q"),
            intent=_coding_intent(),
            provider_resolver=_resolver,
            session_id="sess",
        )
        assert result.total_tokens > 0


class TestMixingOrchestratorChaining:
    async def test_chaining_passes_output_to_next_step(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/draft"), _make_cap("test/critique"), _make_cap("test/refine")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        orch = _make_orchestrator(registry, xdg_dirs)

        messages_received: dict[str, list[ChatMessage]] = {}

        def _resolver(mid: str):
            p = MagicMock(spec=BaseProvider)

            async def _stream(msgs, *args, **kwargs):  # type: ignore[no-untyped-def]
                messages_received[mid] = msgs
                yield StreamChunk(text=f"{mid} output", finish_reason="stop")

            p.stream_chat = _stream
            return p, mid

        decision = RoutingDecision(
            strategy="chaining",
            primary_model="test/draft",
            phase_models=["test/draft", "test/critique", "test/refine"],
        )
        result = await orch.execute(
            decision=decision,
            messages=_user_messages("Write a function"),
            intent=_coding_intent(),
            provider_resolver=_resolver,
            session_id="sess",
        )

        assert result.strategy == "chaining"
        assert len(result.outputs) == 3
        # The critique step should receive the draft output in its messages
        critique_content = " ".join(
            m.content if isinstance(m.content, str) else str(m.content)
            for m in messages_received.get("test/critique", [])
        )
        assert "test/draft output" in critique_content

    async def test_chaining_final_text_is_last_output(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/a"), _make_cap("test/b")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        orch = _make_orchestrator(registry, xdg_dirs)

        def _resolver(mid: str):
            response = "final refined answer" if mid == "test/b" else "draft output"
            return _provider_for(response), mid

        decision = RoutingDecision(
            strategy="chaining",
            primary_model="test/a",
            phase_models=["test/a", "test/b"],
        )
        result = await orch.execute(
            decision=decision,
            messages=_user_messages("Write something"),
            intent=_coding_intent(),
            provider_resolver=_resolver,
            session_id="sess",
        )
        assert result.final_text == "final refined answer"


class TestMixingOrchestratorMetadata:
    async def test_metadata_strategy_matches(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        registry = _make_registry(tmp_path, [_make_cap("test/local")], xdg_dirs)
        orch = _make_orchestrator(registry, xdg_dirs)

        for strategy in ("routing", "ensemble", "chaining"):
            decision = RoutingDecision(
                strategy=strategy,
                primary_model="test/local",
                phase_models=["test/local"],
            )

            def _resolver(mid: str):
                return _provider_for("ok"), mid

            result = await orch.execute(
                decision=decision,
                messages=_user_messages("Q"),
                intent=_coding_intent(),
                provider_resolver=_resolver,
                session_id="sess",
            )
            assert result.metadata.strategy == strategy
            assert result.metadata.intent is not None
