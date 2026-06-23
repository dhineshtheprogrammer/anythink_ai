"""Tests for optimize/plan.py — ExecutionPlan and PlanPhase dataclasses."""

from __future__ import annotations

from datetime import datetime

from anythink.optimize.plan import (
    PHASE_STATUS_DONE,
    PHASE_STATUS_WAITING,
    PLAN_STATUS_PENDING,
    ExecutionPlan,
    MixingResult,
    PhaseUpdate,
    PlanPhase,
)
from anythink.optimize.models import QueryIntent, RoutingDecision, TurnMMOSMetadata


def _make_phase(num: int, model: str = "groq/fast", tokens: int = 500) -> PlanPhase:
    return PlanPhase(
        phase_num=num,
        title=f"Phase {num}",
        description=f"Do task {num}",
        model_id=model,
        estimated_tokens=tokens,
    )


def _make_plan(phases: list[PlanPhase] | None = None) -> ExecutionPlan:
    phases = phases or [_make_phase(1), _make_phase(2)]
    return ExecutionPlan(
        plan_id="test-plan-id",
        session_id="sess-abc",
        original_query="Explain React and Node.js architecture",
        phases=phases,
        created_at=datetime(2024, 6, 1, 12, 0, 0),
        recombination_model="ollama/mistral",
    )


class TestPlanPhase:
    def test_roundtrip_dict(self) -> None:
        phase = PlanPhase(
            phase_num=3,
            title="Backend architecture",
            description="Describe the Node.js backend",
            model_id="groq/llama3-70b-8192",
            estimated_tokens=1200,
            depends_on=[1, 2],
            output_type="detail",
            status=PHASE_STATUS_DONE,
            output="Here is the backend...",
            elapsed_s=12.5,
            actual_model="groq/llama3-70b-8192",
        )
        restored = PlanPhase.from_dict(phase.to_dict())
        assert restored.phase_num == 3
        assert restored.title == "Backend architecture"
        assert restored.depends_on == [1, 2]
        assert restored.output_type == "detail"
        assert restored.status == PHASE_STATUS_DONE
        assert restored.elapsed_s == 12.5
        assert restored.output == "Here is the backend..."

    def test_defaults(self) -> None:
        phase = PlanPhase(
            phase_num=1,
            title="First",
            description="desc",
            model_id="test/model",
            estimated_tokens=100,
        )
        assert phase.status == PHASE_STATUS_WAITING
        assert phase.output == ""
        assert phase.depends_on == []
        assert phase.actual_model == ""


class TestExecutionPlan:
    def test_total_estimated_tokens(self) -> None:
        plan = _make_plan([_make_phase(1, tokens=500), _make_phase(2, tokens=800)])
        assert plan.total_estimated_tokens == 1300

    def test_unique_models_deduplicates(self) -> None:
        plan = _make_plan([
            _make_phase(1, model="groq/fast"),
            _make_phase(2, model="groq/fast"),
            _make_phase(3, model="ollama/local"),
        ])
        plan.recombination_model = "ollama/mistral"
        models = plan.unique_models
        assert "groq/fast" in models
        assert "ollama/local" in models
        assert "ollama/mistral" in models
        assert models.count("groq/fast") == 1

    def test_unique_models_includes_recombination(self) -> None:
        plan = _make_plan([_make_phase(1, model="groq/fast")])
        plan.recombination_model = "ollama/mistral"
        assert "ollama/mistral" in plan.unique_models

    def test_estimated_minutes_range(self) -> None:
        # 10_000 tokens at 2s/1k = 20s = 0.33 min (rounds to 0.3); max = 1.0 min
        plan = _make_plan([_make_phase(1, tokens=10_000)])
        min_m, max_m = plan.estimated_minutes
        assert 0 < min_m <= max_m

    def test_roundtrip_dict(self) -> None:
        plan = _make_plan()
        restored = ExecutionPlan.from_dict(plan.to_dict())
        assert restored.plan_id == "test-plan-id"
        assert restored.session_id == "sess-abc"
        assert len(restored.phases) == 2
        assert restored.recombination_model == "ollama/mistral"
        assert restored.status == PLAN_STATUS_PENDING

    def test_roundtrip_text_basic(self) -> None:
        plan = _make_plan()
        text = plan.to_text()
        restored = ExecutionPlan.from_text(text)
        assert restored.plan_id == "test-plan-id"
        assert restored.session_id == "sess-abc"
        assert len(restored.phases) == 2

    def test_roundtrip_text_with_output(self) -> None:
        phases = [
            PlanPhase(
                phase_num=1,
                title="Overview",
                description="Give an overview",
                model_id="groq/llama3-70b-8192",
                estimated_tokens=600,
                status=PHASE_STATUS_DONE,
                output="Here is a comprehensive overview.\nSecond line.",
                elapsed_s=5.3,
                actual_model="groq/llama3-70b-8192",
            )
        ]
        plan = ExecutionPlan(
            plan_id="pid-xyz",
            session_id="sess-999",
            original_query="What is React?",
            phases=phases,
            created_at=datetime(2024, 6, 1, 10, 0, 0),
            recombination_model="ollama/mistral",
            status=PLAN_STATUS_PENDING,
            final_output="Final synthesised answer.",
        )
        text = plan.to_text()
        restored = ExecutionPlan.from_text(text)

        assert restored.plan_id == "pid-xyz"
        assert len(restored.phases) == 1
        assert "overview" in restored.phases[0].output.lower()
        assert "Final synthesised answer" in restored.final_output

    def test_roundtrip_text_multi_phase_dependencies(self) -> None:
        phases = [
            _make_phase(1),
            PlanPhase(
                phase_num=2,
                title="Dependent",
                description="Builds on phase 1",
                model_id="groq/fast",
                estimated_tokens=400,
                depends_on=[1],
            ),
        ]
        plan = _make_plan(phases)
        restored = ExecutionPlan.from_text(plan.to_text())
        assert restored.phases[1].depends_on == [1]

    def test_new_factory(self) -> None:
        plan = ExecutionPlan.new(
            session_id="sess-new",
            original_query="Test query",
            recombination_model="ollama/mistral",
        )
        assert plan.session_id == "sess-new"
        assert plan.phases == []
        assert plan.status == PLAN_STATUS_PENDING
        assert len(plan.plan_id) == 36  # UUID format


class TestPhaseUpdate:
    def test_fields(self) -> None:
        update = PhaseUpdate(
            phase_num=2,
            status="running",
            elapsed_s=1.5,
            queue_wait_s=3.0,
            actual_model="groq/fast",
        )
        assert update.phase_num == 2
        assert update.status == "running"
        assert update.queue_wait_s == 3.0


class TestMixingResult:
    def test_fields(self) -> None:
        meta = TurnMMOSMetadata(
            strategy="routing",
            model_ids=["groq/fast"],
            intent=None,
            routing_decision=None,
            total_tokens=100,
            elapsed_s=0.5,
        )
        result = MixingResult(
            strategy="routing",
            outputs=[("groq/fast", "Hello world", 0.5)],
            final_text="Hello world",
            total_tokens=100,
            metadata=meta,
        )
        assert result.strategy == "routing"
        assert result.final_text == "Hello world"
        assert result.metadata.total_tokens == 100
