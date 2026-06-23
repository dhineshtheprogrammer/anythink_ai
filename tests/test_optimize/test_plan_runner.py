"""Tests for optimize/plan_runner.py — PlanRunner."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anythink.config.manager import Paths
from anythink.optimize.models import ModelCapability, OptimizeSettings
from anythink.optimize.plan import (
    PHASE_STATUS_DONE,
    PHASE_STATUS_FAILED,
    PHASE_STATUS_SKIPPED,
    PLAN_STATUS_ABORTED,
    PLAN_STATUS_DONE,
    ExecutionPlan,
    PhaseUpdate,
    PlanPhase,
)
from anythink.optimize.plan_runner import PlanRunner
from anythink.optimize.rate_limit import RateLimitManager
from anythink.optimize.registry import ModelCapabilityRegistry
from anythink.providers.base import BaseProvider, StreamChunk


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
        requires_network=False,
    )


def _make_registry(tmp_path: Path, models: list[ModelCapability], xdg_dirs: Paths) -> ModelCapabilityRegistry:
    bundled = tmp_path / "bundled.json"
    bundled.write_text(
        json.dumps({"_registry_version": "4.0.0", "models": [m.to_dict() for m in models]})
    )
    return ModelCapabilityRegistry(bundled_path=bundled, user_path=xdg_dirs.model_capability_registry_user_file)


def _mock_provider(response: str) -> BaseProvider:
    provider = MagicMock(spec=BaseProvider)

    async def _stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield StreamChunk(text=response, finish_reason="stop")

    provider.stream_chat = _stream
    return provider


def _simple_plan(session_id: str = "sess", models: list[str] | None = None) -> ExecutionPlan:
    models = models or ["test/local"]
    phases = [
        PlanPhase(
            phase_num=i + 1,
            title=f"Phase {i + 1}",
            description=f"Do task {i + 1}",
            model_id=models[i % len(models)],
            estimated_tokens=300,
        )
        for i in range(len(models) if len(models) > 1 else 2)
    ]
    return ExecutionPlan.new(
        session_id=session_id,
        original_query="Test query",
        recombination_model=models[0],
    )._replace_phases(phases)  # type: ignore[attr-defined]


def _make_plan_with_phases(phases: list[PlanPhase], session_id: str = "sess") -> ExecutionPlan:
    plan = ExecutionPlan.new(session_id=session_id, original_query="Q", recombination_model="test/local")
    plan.phases = phases
    return plan


class TestPlanRunner:
    def _make_runner(self, registry: ModelCapabilityRegistry, xdg_dirs: Paths) -> PlanRunner:
        rate_mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        return PlanRunner(
            registry=registry,
            rate_limit_manager=rate_mgr,
            plans_dir=xdg_dirs.plans_dir,
        )

    def _simple_resolver(self, provider: BaseProvider, api_id: str = "model-id"):
        def _resolve(model_id: str):
            return provider, api_id
        return _resolve

    async def test_single_phase_completes(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/local")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        runner = self._make_runner(registry, xdg_dirs)

        provider = _mock_provider("Phase 1 result")
        phases = [PlanPhase(1, "Task", "Do it", "test/local", 300)]
        plan = _make_plan_with_phases(phases)

        result = await runner.execute(plan, self._simple_resolver(provider))
        assert result.status == PLAN_STATUS_DONE
        assert result.phases[0].status == PHASE_STATUS_DONE
        assert result.phases[0].output == "Phase 1 result"
        assert result.phases[0].actual_model == "test/local"

    async def test_final_output_comes_from_recombination(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/local")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        runner = self._make_runner(registry, xdg_dirs)

        call_count = 0
        responses = ["phase output", "synthesised final answer"]

        async def _stream(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            yield StreamChunk(text=responses[min(call_count, len(responses) - 1)], finish_reason="stop")
            call_count += 1

        provider = MagicMock(spec=BaseProvider)
        provider.stream_chat = _stream

        phases = [PlanPhase(1, "Task", "Do it", "test/local", 300)]
        plan = _make_plan_with_phases(phases)

        result = await runner.execute(plan, self._simple_resolver(provider))
        assert result.final_output != ""

    async def test_abort_signal_stops_execution(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/local")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        runner = self._make_runner(registry, xdg_dirs)

        abort = asyncio.Event()
        abort.set()  # Pre-set: abort immediately

        provider = _mock_provider("should not appear")
        phases = [
            PlanPhase(1, "First", "Do first", "test/local", 300),
            PlanPhase(2, "Second", "Do second", "test/local", 300),
        ]
        plan = _make_plan_with_phases(phases)

        result = await runner.execute(plan, self._simple_resolver(provider), abort_signal=abort)
        assert result.status == PLAN_STATUS_ABORTED
        # Both phases should be skipped
        assert all(p.status == PHASE_STATUS_SKIPPED for p in result.phases)

    async def test_skip_phase_marks_as_skipped(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/local")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        runner = self._make_runner(registry, xdg_dirs)

        provider = _mock_provider("done")
        phases = [
            PlanPhase(1, "First", "Do first", "test/local", 300),
            PlanPhase(2, "Skip me", "Skip this", "test/local", 300),
        ]
        plan = _make_plan_with_phases(phases)

        result = await runner.execute(plan, self._simple_resolver(provider), skip_phase=2)
        assert result.phases[0].status == PHASE_STATUS_DONE
        assert result.phases[1].status == PHASE_STATUS_SKIPPED

    async def test_phase_update_callback_fires(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/local")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        runner = self._make_runner(registry, xdg_dirs)

        updates: list[PhaseUpdate] = []

        def _on_update(u: PhaseUpdate) -> None:
            updates.append(u)

        provider = _mock_provider("result")
        phases = [PlanPhase(1, "Task", "Do it", "test/local", 300)]
        plan = _make_plan_with_phases(phases)

        await runner.execute(plan, self._simple_resolver(provider), on_phase_update=_on_update)
        statuses = [u.status for u in updates]
        assert "running" in statuses
        assert PHASE_STATUS_DONE in statuses

    async def test_provider_error_marks_phase_failed(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/local")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        runner = self._make_runner(registry, xdg_dirs)

        bad_provider = MagicMock(spec=BaseProvider)

        async def _error_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("Network failure")
            yield  # noqa: unreachable

        bad_provider.stream_chat = _error_stream

        phases = [PlanPhase(1, "Task", "Do it", "test/local", 300)]
        plan = _make_plan_with_phases(phases)

        result = await runner.execute(plan, self._simple_resolver(bad_provider))
        assert result.phases[0].status == PHASE_STATUS_FAILED

    def test_build_phase_prompt_includes_dependency_output(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/local")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        runner = self._make_runner(registry, xdg_dirs)

        phase = PlanPhase(
            phase_num=2,
            title="Second",
            description="Build on phase 1",
            model_id="test/local",
            estimated_tokens=300,
            depends_on=[1],
        )
        phases = [PlanPhase(1, "First", "Do first", "test/local", 300), phase]
        plan = _make_plan_with_phases(phases)

        prior = {1: "Phase 1 produced this output"}
        prompt = runner._build_phase_prompt(phase, plan, prior)
        assert "Phase 1 produced this output" in prompt
        assert "Phase 2 of 2" in prompt

    def test_build_phase_prompt_no_dependency_excludes_prior(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/local")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        runner = self._make_runner(registry, xdg_dirs)

        phase = PlanPhase(1, "First", "Do first", "test/local", 300)
        plan = _make_plan_with_phases([phase])
        prior = {99: "Unrelated output"}
        prompt = runner._build_phase_prompt(phase, plan, prior)
        assert "Unrelated output" not in prompt

    async def test_plan_saved_to_file(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        models = [_make_cap("test/local")]
        registry = _make_registry(tmp_path, models, xdg_dirs)
        runner = self._make_runner(registry, xdg_dirs)

        provider = _mock_provider("output")
        phases = [PlanPhase(1, "Task", "Do it", "test/local", 300)]
        plan = _make_plan_with_phases(phases)

        await runner.execute(plan, self._simple_resolver(provider))
        plan_files = list(xdg_dirs.plans_dir.glob("plan_*.txt"))
        assert len(plan_files) == 1


# Need to add _replace_phases workaround for the test helper above
def _patch_execution_plan() -> None:
    """Monkey-patch ExecutionPlan with a helper used only in tests."""
    def _replace_phases(self: ExecutionPlan, phases: list[PlanPhase]) -> ExecutionPlan:
        self.phases = phases
        return self

    ExecutionPlan._replace_phases = _replace_phases  # type: ignore[attr-defined]


_patch_execution_plan()
