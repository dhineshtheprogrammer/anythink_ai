"""Tests for smart/executor.py."""

from pathlib import Path
from unittest.mock import MagicMock, call

from anythink.providers.base import ChatMessage, StreamChunk
from anythink.smart.executor import SequentialExecutor, _build_specialist_messages
from anythink.smart.models import RoutingPlan, SubQuestion
from anythink.smart.quality import QualityGate
from anythink.smart.registry import SmartRegistry
from anythink.smart.store import TemporaryResponseStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sq(category: str = "general", alias: str = "local") -> SubQuestion:
    return SubQuestion(sub_question="Explain this.", category=category, model_alias=alias)


def _make_registry(tmp_path: Path, general_alias: str = "") -> SmartRegistry:
    reg = SmartRegistry(tmp_path / "reg.yaml")
    reg.load()
    if general_alias:
        reg.set("general", general_alias)
    return reg


def _make_alias(alias: str = "local", provider: str = "ollama") -> MagicMock:
    obj = MagicMock()
    obj.alias = alias
    obj.model_id = "model"
    obj.provider = provider
    return obj


def _make_model_registry(alias: str = "local") -> MagicMock:
    alias_obj = _make_alias(alias)
    mreg = MagicMock()
    mreg.get.return_value = alias_obj
    mreg.list_all.return_value = [alias_obj]
    return mreg


def _make_provider(response: str = "Good answer. This is a substantial response.") -> MagicMock:
    async def _stream(**kwargs):
        chunk = MagicMock(spec=StreamChunk)
        chunk.text = response
        yield chunk

    provider = MagicMock()
    provider.stream_chat = _stream
    return provider


def _make_provider_registry(
    response: str = "Good answer. This is a substantial response.",
) -> MagicMock:
    preg = MagicMock()
    preg.instantiate.return_value = _make_provider(response)
    return preg


# ---------------------------------------------------------------------------
# _build_specialist_messages tests
# ---------------------------------------------------------------------------


def test_build_specialist_messages_structure():
    sq = _sq("code")
    history = [ChatMessage(role="user", content="Prior question")]
    messages = _build_specialist_messages(
        sq, "What is the original question?", history, "Code / Programming"
    )
    roles = [m.role for m in messages]
    assert roles[0] == "system"
    assert roles[-1] == "user"
    last = messages[-1].content
    assert "[ORIGINAL QUESTION]" in last
    assert "[YOUR TASK]" in last


def test_build_specialist_messages_strips_system_from_history():
    sq = _sq("math")
    history = [
        ChatMessage(role="system", content="You are a helpful assistant."),
        ChatMessage(role="user", content="Previous question"),
    ]
    messages = _build_specialist_messages(sq, "Original", history, "Math")
    system_messages = [m for m in messages[1:] if m.role == "system"]
    assert system_messages == []


def test_build_specialist_messages_tail_at_most_10():
    sq = _sq("general")
    history = [ChatMessage(role="user", content=f"Message {i}") for i in range(20)]
    messages = _build_specialist_messages(sq, "Original", history, "General")
    non_system = [m for m in messages if m.role != "system"]
    # tail is 10 messages + 1 final user task = 11 non-system messages
    assert len(non_system) <= 11


# ---------------------------------------------------------------------------
# SequentialExecutor integration tests
# ---------------------------------------------------------------------------


async def test_execute_single_specialist_adds_to_store(tmp_path: Path):
    reg = _make_registry(tmp_path)
    gate = QualityGate(threshold=0)  # always pass
    mreg = _make_model_registry()
    preg = _make_provider_registry("Helpful answer about everything. It is good.")

    executor = SequentialExecutor(reg, gate, preg, mreg, MagicMock())
    store = TemporaryResponseStore()
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["general"],
        routing_plan=[_sq("general", "local")],
        reasoning_summary="",
    )
    await executor.execute(plan, "Original question", [], store, on_progress=None)
    assert len(store) == 1
    assert store.all()[0].category == "general"


async def test_execute_calls_on_progress(tmp_path: Path):
    reg = _make_registry(tmp_path)
    gate = QualityGate(threshold=0)
    mreg = _make_model_registry()
    preg = _make_provider_registry("Answer.")

    progress_calls: list = []

    def on_progress(msg, current, total):
        progress_calls.append((msg, current, total))

    executor = SequentialExecutor(reg, gate, preg, mreg, MagicMock())
    store = TemporaryResponseStore()
    plan = RoutingPlan(
        complexity="multi",
        categories_detected=["math", "code"],
        routing_plan=[_sq("math"), _sq("code")],
        reasoning_summary="",
    )
    await executor.execute(plan, "Q", [], store, on_progress=on_progress)
    assert len(progress_calls) == 2
    assert progress_calls[0][1] == 1
    assert progress_calls[1][1] == 2


async def test_executor_marks_low_confidence_when_all_fail(tmp_path: Path):
    reg = _make_registry(tmp_path)
    gate = QualityGate(threshold=100)  # impossible to pass
    mreg = _make_model_registry()
    # Short response — will never reach threshold
    preg = _make_provider_registry("no")

    executor = SequentialExecutor(reg, gate, preg, mreg, MagicMock())
    store = TemporaryResponseStore()
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["general"],
        routing_plan=[_sq("general", "local")],
        reasoning_summary="",
    )
    await executor.execute(plan, "Q", [], store)
    resp = store.all()[0]
    assert resp.low_confidence is True


async def test_executor_returns_passing_result_without_low_confidence(tmp_path: Path):
    reg = _make_registry(tmp_path)
    gate = QualityGate(threshold=50)
    mreg = _make_model_registry()
    # A good long response that should pass quality gate
    good_response = (
        "The answer is quite clear. First, consider the context. "
        "Second, apply the relevant principles. Third, verify the result. "
        "The conclusion is that the approach works well."
    )
    preg = _make_provider_registry(good_response)

    executor = SequentialExecutor(reg, gate, preg, mreg, MagicMock())
    store = TemporaryResponseStore()
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["general"],
        routing_plan=[_sq("general", "local")],
        reasoning_summary="",
    )
    await executor.execute(plan, "Explain something", [], store)
    resp = store.all()[0]
    assert resp.low_confidence is False
    assert resp.quality_score >= 50


def test_build_candidates_includes_primary_and_general(tmp_path: Path):
    reg = _make_registry(tmp_path, general_alias="general-model")
    reg.set("code", "code-model")
    mreg = _make_model_registry()

    executor = SequentialExecutor(reg, QualityGate(), MagicMock(), mreg, MagicMock())
    candidates = executor._build_candidates("code", "code-model")
    assert candidates[0] == "code-model"
    assert "general-model" in candidates


def test_build_candidates_falls_back_to_first_model(tmp_path: Path):
    reg = _make_registry(tmp_path)  # no assignments
    alias_obj = _make_alias("only-alias")
    mreg = MagicMock()
    mreg.get.return_value = None
    mreg.list_all.return_value = [alias_obj]

    executor = SequentialExecutor(reg, QualityGate(), MagicMock(), mreg, MagicMock())
    candidates = executor._build_candidates("math", "")
    assert "only-alias" in candidates
