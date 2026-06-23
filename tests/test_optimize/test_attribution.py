"""Tests for optimize/attribution.py — AttributionFormatter."""

from __future__ import annotations

from anythink.optimize.attribution import AttributionFormatter, _format_elapsed
from anythink.optimize.models import QueryIntent, RoutingDecision, TurnMMOSMetadata
from anythink.optimize.plan import PlanPhase


def _make_mmos(
    strategy: str = "routing",
    model_ids: list[str] | None = None,
    total_tokens: int = 1000,
    elapsed_s: float = 1.5,
    phase_outputs: list[dict] | None = None,
) -> TurnMMOSMetadata:
    return TurnMMOSMetadata(
        strategy=strategy,
        model_ids=model_ids or ["groq/llama3-70b"],
        intent=None,
        routing_decision=None,
        total_tokens=total_tokens,
        elapsed_s=elapsed_s,
        phase_outputs=phase_outputs or [],
    )


class TestSingleModelHeader:
    def test_contains_model_id(self) -> None:
        line = AttributionFormatter.single_model_header(
            "groq/llama3-70b", "routing", 1243, 0.8
        )
        assert "groq/llama3-70b" in line.plain

    def test_contains_strategy(self) -> None:
        line = AttributionFormatter.single_model_header(
            "groq/llama3-70b", "ensemble", 500, 2.1
        )
        assert "ensemble" in line.plain

    def test_contains_token_count(self) -> None:
        line = AttributionFormatter.single_model_header(
            "groq/llama3-70b", "routing", 1500, 1.0
        )
        assert "1,500" in line.plain

    def test_contains_elapsed(self) -> None:
        line = AttributionFormatter.single_model_header(
            "model/x", "routing", 100, 3.5
        )
        assert "3.5s" in line.plain

    def test_width_respected(self) -> None:
        for width in (60, 80, 120):
            line = AttributionFormatter.single_model_header(
                "m/id", "routing", 0, 0.0, width=width
            )
            # Rich Text plain length may differ due to bar chars, but should not be massive
            assert len(line.plain) <= width + 20

    def test_returns_rich_text(self) -> None:
        from rich.text import Text

        line = AttributionFormatter.single_model_header("m/id", "routing", 0, 0.0)
        assert isinstance(line, Text)


class TestPlanModeHeader:
    def test_contains_plan_mode(self) -> None:
        mmos = _make_mmos(strategy="decompose")
        line = AttributionFormatter.plan_mode_header(mmos, phase_count=3)
        assert "Plan Mode" in line.plain

    def test_contains_phase_count(self) -> None:
        mmos = _make_mmos(strategy="decompose")
        line = AttributionFormatter.plan_mode_header(mmos, phase_count=5)
        assert "5 phases" in line.plain

    def test_contains_provider_names(self) -> None:
        mmos = _make_mmos(
            strategy="decompose",
            model_ids=["groq/llama3-70b", "together/mixtral", "ollama/mistral"],
        )
        line = AttributionFormatter.plan_mode_header(mmos)
        text = line.plain
        assert "groq" in text

    def test_contains_total_tokens(self) -> None:
        mmos = _make_mmos(total_tokens=4821)
        line = AttributionFormatter.plan_mode_header(mmos)
        assert "4,821" in line.plain

    def test_elapsed_formatted(self) -> None:
        mmos = _make_mmos(elapsed_s=134.0)  # 2 minutes 14 seconds
        line = AttributionFormatter.plan_mode_header(mmos)
        assert "2m" in line.plain

    def test_deduplicates_providers(self) -> None:
        mmos = _make_mmos(
            model_ids=["groq/llama3-8b", "groq/llama3-70b", "ollama/mistral"]
        )
        line = AttributionFormatter.plan_mode_header(mmos)
        # "groq" should appear only once
        assert line.plain.count("groq") == 1


class TestEnsembleSectionHeader:
    def test_contains_response_counter(self) -> None:
        line = AttributionFormatter.ensemble_section_header(
            "groq/llama3-70b", index=1, total=3, speed_class="fast"
        )
        assert "1 of 3" in line.plain

    def test_contains_model_id(self) -> None:
        line = AttributionFormatter.ensemble_section_header(
            "together/mixtral", index=2, total=3, speed_class="medium"
        )
        assert "together/mixtral" in line.plain

    def test_contains_speed_class(self) -> None:
        line = AttributionFormatter.ensemble_section_header(
            "local/fast-model", index=1, total=2, speed_class="fast"
        )
        assert "fast" in line.plain


class TestPhaseOutputBlock:
    def test_contains_phase_num_and_title(self) -> None:
        phase = PlanPhase(
            phase_num=2,
            title="Frontend architecture",
            description="desc",
            model_id="groq/fast",
            estimated_tokens=800,
            elapsed_s=5.3,
            actual_model="groq/llama3-70b",
        )
        line = AttributionFormatter.phase_output_block(phase)
        assert "Phase 2" in line.plain
        assert "Frontend architecture" in line.plain

    def test_uses_actual_model_when_set(self) -> None:
        phase = PlanPhase(
            phase_num=1,
            title="Title",
            description="d",
            model_id="fallback/model",
            estimated_tokens=100,
            actual_model="groq/actual-model",
        )
        line = AttributionFormatter.phase_output_block(phase)
        assert "groq/actual-model" in line.plain

    def test_falls_back_to_model_id(self) -> None:
        phase = PlanPhase(
            phase_num=1,
            title="Title",
            description="d",
            model_id="groq/assigned-model",
            estimated_tokens=100,
        )
        line = AttributionFormatter.phase_output_block(phase)
        assert "groq/assigned-model" in line.plain


class TestFromMMOSMetadata:
    def test_routing_strategy_returns_single_header(self) -> None:
        mmos = _make_mmos(strategy="routing")
        line = AttributionFormatter.from_mmos_metadata(mmos)
        assert "routing" in line.plain

    def test_decompose_with_phases_returns_plan_header(self) -> None:
        mmos = _make_mmos(
            strategy="decompose",
            phase_outputs=[{"phase": 1}],
        )
        line = AttributionFormatter.from_mmos_metadata(mmos)
        assert "Plan Mode" in line.plain

    def test_decompose_without_phases_returns_single_header(self) -> None:
        mmos = _make_mmos(strategy="decompose", phase_outputs=[])
        line = AttributionFormatter.from_mmos_metadata(mmos)
        # No phase_outputs → falls back to single_model_header
        assert "decompose" in line.plain


class TestFormatElapsed:
    def test_seconds_only(self) -> None:
        assert "s" in _format_elapsed(5.3)
        assert "5.3s" == _format_elapsed(5.3)

    def test_minutes_and_seconds(self) -> None:
        result = _format_elapsed(134.0)
        assert "2m" in result
        assert "14s" in result

    def test_exactly_one_minute(self) -> None:
        result = _format_elapsed(60.0)
        assert "1m" in result
