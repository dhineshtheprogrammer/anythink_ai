"""MMAE core data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SubQuestion:
    """One routed sub-question in a routing plan."""

    sub_question: str
    category: str
    model_alias: str
    context_included: bool = True


@dataclass
class RoutingPlan:
    """Full output of the router — complexity flag, sub-questions, reasoning."""

    complexity: str  # "single" | "multi"
    categories_detected: list[str]
    routing_plan: list[SubQuestion]
    reasoning_summary: str


@dataclass
class SpecialistResponse:
    """One specialist model's output for a sub-question."""

    slot: int
    category: str
    model_alias: str
    sub_question: str
    response: str
    quality_score: int  # 0–100
    retry_count: int
    duration_s: float
    low_confidence: bool = False


@dataclass
class TemporaryStore:
    """In-memory per-turn store of all specialist responses."""

    entries: list[SpecialistResponse] = field(default_factory=list)


@dataclass
class SmartResult:
    """Final output of the MMAE pipeline for one turn."""

    combined_text: str
    formatter_applied: str | None  # None if formatter stage did not run
    total_duration_s: float
    routing_plan: RoutingPlan
    store: TemporaryStore
    combiner_model: str
    combiner_mode: str
