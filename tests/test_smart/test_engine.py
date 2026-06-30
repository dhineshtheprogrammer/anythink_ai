"""Tests for smart/engine.py."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.providers.base import StreamChunk
from anythink.smart.engine import SmartEngine
from anythink.smart.models import RoutingPlan, SmartResult, SubQuestion
from anythink.smart.registry import SmartRegistry
from anythink.smart.store import TemporaryResponseStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(tmp_path: Path) -> SmartRegistry:
    reg = SmartRegistry(tmp_path / "reg.yaml")
    reg.load()
    return reg


def _make_alias(alias: str = "local") -> MagicMock:
    obj = MagicMock()
    obj.alias = alias
    obj.model_id = "model"
    obj.provider = "ollama"
    return obj


def _make_model_registry(alias: str = "local") -> MagicMock:
    obj = _make_alias(alias)
    mreg = MagicMock()
    mreg.get.return_value = obj
    mreg.list_all.return_value = [obj]
    return mreg


def _make_provider_registry(text: str = "Answer") -> MagicMock:
    async def _stream(**kwargs):
        chunk = MagicMock(spec=StreamChunk)
        chunk.text = text
        yield chunk

    provider = MagicMock()
    provider.stream_chat = _stream
    preg = MagicMock()
    preg.instantiate.return_value = provider
    return preg


def _make_debug_manager(active: bool = False) -> MagicMock:
    dm = MagicMock()
    dm.is_active.return_value = active
    dm.level.return_value = 2
    return dm


def _make_engine(
    tmp_path: Path,
    provider_text: str = "Answer",
    debug_active: bool = False,
    quality_threshold: int = 0,
) -> SmartEngine:
    reg = _make_registry(tmp_path)
    mreg = _make_model_registry()
    preg = _make_provider_registry(provider_text)
    dm = _make_debug_manager(debug_active)
    spend = MagicMock()

    return SmartEngine(
        registry=reg,
        provider_registry=preg,
        model_registry=mreg,
        key_manager=MagicMock(),
        debug_manager=dm,
        spend_tracker=spend,
        quality_threshold=quality_threshold,
        max_splits=5,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_engine_run_returns_smart_result(tmp_path: Path):
    engine = _make_engine(tmp_path, provider_text="Good response.")
    # Mock router to avoid real LLM call
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["general"],
        routing_plan=[SubQuestion("What is 2+2?", "general", "local")],
        reasoning_summary="Simple",
    )
    engine._router.route = AsyncMock(return_value=plan)

    result = await engine.run(
        message="What is 2+2?",
        history=[],
        session_id="sess-1",
        combiner_mode="stitch",
        session_format="",
    )
    assert isinstance(result, SmartResult)
    assert result.combiner_mode == "stitch"
    assert result.total_duration_s >= 0


async def test_engine_run_no_formatter_when_no_format(tmp_path: Path):
    engine = _make_engine(tmp_path)
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["general"],
        routing_plan=[SubQuestion("Q", "general", "local")],
        reasoning_summary="",
    )
    engine._router.route = AsyncMock(return_value=plan)

    result = await engine.run("Q", [], "sess", "stitch", "")
    # No format requested → formatter_applied should be None
    assert result.formatter_applied is None


async def test_engine_run_formatter_applied_when_format_detected(tmp_path: Path):
    engine = _make_engine(tmp_path, provider_text="formatted text")
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["general"],
        routing_plan=[SubQuestion("Q", "general", "local")],
        reasoning_summary="",
    )
    engine._router.route = AsyncMock(return_value=plan)

    # "as markdown" should trigger "markdown" format detection
    result = await engine.run("Tell me about X as markdown", [], "sess", "stitch", "")
    assert result.formatter_applied == "markdown"


async def test_engine_run_session_format_used_when_no_keyword(tmp_path: Path):
    engine = _make_engine(tmp_path, provider_text="formatted text")
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["general"],
        routing_plan=[SubQuestion("Q", "general", "local")],
        reasoning_summary="",
    )
    engine._router.route = AsyncMock(return_value=plan)

    result = await engine.run("Just a plain question", [], "sess", "stitch", "summary")
    assert result.formatter_applied == "summary"


async def test_engine_run_clears_store_each_turn(tmp_path: Path):
    engine = _make_engine(tmp_path)
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["general"],
        routing_plan=[SubQuestion("Q", "general", "local")],
        reasoning_summary="",
    )
    engine._router.route = AsyncMock(return_value=plan)

    await engine.run("Q1", [], "sess", "stitch", "")
    first_store_len = len(engine._store)

    await engine.run("Q2", [], "sess", "stitch", "")
    # Store should only contain responses from Q2, not Q1 + Q2
    assert len(engine._store) == first_store_len


async def test_engine_store_snapshot_returns_store(tmp_path: Path):
    engine = _make_engine(tmp_path)
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["general"],
        routing_plan=[SubQuestion("Q", "general", "local")],
        reasoning_summary="",
    )
    engine._router.route = AsyncMock(return_value=plan)
    await engine.run("Q", [], "sess", "stitch", "")

    snapshot = engine.store_snapshot()
    assert isinstance(snapshot, TemporaryResponseStore)


async def test_engine_debug_events_emitted_when_active(tmp_path: Path):
    reg = _make_registry(tmp_path)
    mreg = _make_model_registry()
    preg = _make_provider_registry("Answer.")
    dm = _make_debug_manager(active=True)
    dm._pending_event = MagicMock()  # simulate method existing
    spend = MagicMock()

    engine = SmartEngine(
        registry=reg,
        provider_registry=preg,
        model_registry=mreg,
        key_manager=MagicMock(),
        debug_manager=dm,
        spend_tracker=spend,
        quality_threshold=0,
        max_splits=5,
    )
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["general"],
        routing_plan=[SubQuestion("Q", "general", "local")],
        reasoning_summary="",
    )
    engine._router.route = AsyncMock(return_value=plan)
    await engine.run("Q", [], "sess", "stitch", "")

    # At minimum, the router invocation and completion events should fire
    assert dm._pending_event.call_count >= 2


async def test_engine_debug_inactive_no_events(tmp_path: Path):
    reg = _make_registry(tmp_path)
    mreg = _make_model_registry()
    preg = _make_provider_registry("Answer.")
    dm = _make_debug_manager(active=False)
    dm._pending_event = MagicMock()

    engine = SmartEngine(
        registry=reg,
        provider_registry=preg,
        model_registry=mreg,
        key_manager=MagicMock(),
        debug_manager=dm,
        spend_tracker=MagicMock(),
        quality_threshold=0,
    )
    plan = RoutingPlan(
        complexity="single",
        categories_detected=["general"],
        routing_plan=[SubQuestion("Q", "general", "local")],
        reasoning_summary="",
    )
    engine._router.route = AsyncMock(return_value=plan)
    await engine.run("Q", [], "sess", "stitch", "")

    dm._pending_event.assert_not_called()


async def test_engine_on_progress_callback_called(tmp_path: Path):
    engine = _make_engine(tmp_path)
    plan = RoutingPlan(
        complexity="multi",
        categories_detected=["math", "code"],
        routing_plan=[
            SubQuestion("Math Q", "math", "local"),
            SubQuestion("Code Q", "code", "local"),
        ],
        reasoning_summary="",
    )
    engine._router.route = AsyncMock(return_value=plan)

    progress_msgs: list[str] = []

    def on_progress(msg: str) -> None:
        progress_msgs.append(msg)

    await engine.run("Q", [], "sess", "stitch", "", on_progress=on_progress)
    assert len(progress_msgs) >= 2
