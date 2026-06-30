"""Tests for smart/models.py."""

from anythink.smart.models import (
    RoutingPlan,
    SmartResult,
    SpecialistResponse,
    SubQuestion,
    TemporaryStore,
)


def test_sub_question_defaults():
    sq = SubQuestion(sub_question="What is 2+2?", category="math", model_alias="local")
    assert sq.context_included is True


def test_sub_question_fields():
    sq = SubQuestion("Q", "code", "alias", context_included=False)
    assert sq.sub_question == "Q"
    assert sq.category == "code"
    assert sq.model_alias == "alias"
    assert sq.context_included is False


def test_routing_plan_fields():
    sq = SubQuestion("What is pi?", "math", "m1")
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["math"],
        routing_plan=[sq],
        reasoning_summary="Only math needed.",
    )
    assert plan.complexity == "single"
    assert plan.categories_detected == ["math"]
    assert len(plan.routing_plan) == 1
    assert plan.reasoning_summary == "Only math needed."


def test_specialist_response_defaults():
    resp = SpecialistResponse(
        slot=1,
        category="math",
        model_alias="local",
        sub_question="Calc pi",
        response="3.14",
        quality_score=80,
        retry_count=0,
        duration_s=0.5,
    )
    assert resp.low_confidence is False


def test_specialist_response_with_low_confidence():
    resp = SpecialistResponse(
        slot=2,
        category="code",
        model_alias="local",
        sub_question="Write a sort",
        response="I can't",
        quality_score=10,
        retry_count=2,
        duration_s=1.0,
        low_confidence=True,
    )
    assert resp.low_confidence is True
    assert resp.retry_count == 2


def test_temporary_store_default_empty():
    ts = TemporaryStore()
    assert ts.entries == []


def test_smart_result_fields():
    sq = SubQuestion("Q", "research", "m1")
    plan = RoutingPlan("single", ["research"], [sq], "summary")
    ts = TemporaryStore()
    result = SmartResult(
        combined_text="Answer",
        formatter_applied=None,
        total_duration_s=1.2,
        routing_plan=plan,
        store=ts,
        combiner_model="local",
        combiner_mode="stitch",
    )
    assert result.combined_text == "Answer"
    assert result.formatter_applied is None
    assert result.combiner_mode == "stitch"
