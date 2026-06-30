"""Tests for smart/router.py."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.exceptions import SmartError
from anythink.providers.base import ChatMessage, StreamChunk
from anythink.smart.registry import SmartRegistry
from anythink.smart.router import RouterModel, _extract_json, _parse_routing_plan


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_valid_routing_json(
    complexity: str = "single", categories: list[str] | None = None
) -> str:
    if categories is None:
        categories = ["general"]
    return json.dumps(
        {
            "complexity": complexity,
            "categories_detected": categories,
            "routing_plan": [
                {
                    "sub_question": "What is 2+2?",
                    "category": categories[0],
                    "model_alias": "local",
                    "context_included": True,
                }
            ],
            "reasoning_summary": "Simple single-category question.",
        }
    )


def _mock_registry(tmp_path: Path) -> SmartRegistry:
    reg = SmartRegistry(tmp_path / "reg.yaml")
    reg.load()
    return reg


def _mock_model_registry(
    alias: str = "local", model_id: str = "test-model", provider: str = "ollama"
):
    alias_obj = MagicMock()
    alias_obj.alias = alias
    alias_obj.model_id = model_id
    alias_obj.provider = provider
    mreg = MagicMock()
    mreg.get.return_value = alias_obj
    mreg.list_all.return_value = [alias_obj]
    return mreg


def _mock_provider_registry(response_text: str):
    async def _fake_stream(**kwargs):
        chunk = MagicMock(spec=StreamChunk)
        chunk.text = response_text
        yield chunk

    provider = MagicMock()
    provider.stream_chat = _fake_stream
    preg = MagicMock()
    preg.instantiate.return_value = provider
    return preg


# ---------------------------------------------------------------------------
# _extract_json unit tests
# ---------------------------------------------------------------------------


def test_extract_json_from_bare_object():
    raw = '{"key": "value"}'
    assert _extract_json(raw) == raw


def test_extract_json_from_markdown_fence():
    raw = '```json\n{"key": "val"}\n```'
    result = _extract_json(raw)
    assert result == '{"key": "val"}'


def test_extract_json_finds_first_brace_pair():
    raw = 'Some text {"a": 1} more text'
    result = _extract_json(raw)
    assert json.loads(result) == {"a": 1}


def test_extract_json_raises_on_no_json():
    with pytest.raises(SmartError):
        _extract_json("No JSON here at all!")


# ---------------------------------------------------------------------------
# _parse_routing_plan unit tests
# ---------------------------------------------------------------------------


def test_parse_valid_single_plan():
    raw = _make_valid_routing_json("single", ["math"])
    plan = _parse_routing_plan(raw, max_splits=5)
    assert plan.complexity == "single"
    assert plan.categories_detected == ["math"]
    assert len(plan.routing_plan) == 1
    assert plan.routing_plan[0].category == "math"


def test_parse_multi_plan():
    data = {
        "complexity": "multi",
        "categories_detected": ["math", "code"],
        "routing_plan": [
            {"sub_question": "Math part", "category": "math", "model_alias": "m1"},
            {"sub_question": "Code part", "category": "code", "model_alias": "m2"},
        ],
        "reasoning_summary": "Two domains.",
    }
    plan = _parse_routing_plan(json.dumps(data), max_splits=5)
    assert plan.complexity == "multi"
    assert len(plan.routing_plan) == 2


def test_parse_enforces_max_splits():
    data = {
        "complexity": "multi",
        "categories_detected": ["math", "code", "writing"],
        "routing_plan": [
            {"sub_question": f"Q{i}", "category": "general", "model_alias": "m"} for i in range(6)
        ],
        "reasoning_summary": "Many splits.",
    }
    plan = _parse_routing_plan(json.dumps(data), max_splits=3)
    assert len(plan.routing_plan) == 3


def test_parse_missing_required_field_raises():
    data = {"complexity": "single", "categories_detected": ["math"]}
    with pytest.raises(SmartError, match="missing required field"):
        _parse_routing_plan(json.dumps(data), max_splits=5)


def test_parse_empty_routing_plan_raises():
    data = {
        "complexity": "single",
        "categories_detected": ["math"],
        "routing_plan": [],
        "reasoning_summary": "Empty",
    }
    with pytest.raises(SmartError, match="non-empty list"):
        _parse_routing_plan(json.dumps(data), max_splits=5)


def test_parse_invalid_json_raises():
    with pytest.raises(SmartError, match="malformed"):
        _parse_routing_plan("{not json}", max_splits=5)


# ---------------------------------------------------------------------------
# RouterModel integration tests (mocked provider)
# ---------------------------------------------------------------------------


async def test_router_model_returns_plan(tmp_path: Path):
    reg = _mock_registry(tmp_path)
    mreg = _mock_model_registry()
    response_text = _make_valid_routing_json("single", ["general"])
    preg = _mock_provider_registry(response_text)

    router = RouterModel(
        registry=reg,
        provider_registry=preg,
        model_registry=mreg,
        key_manager=MagicMock(),
        max_splits=5,
    )
    plan = await router.route("Hello", [], None)
    assert plan.complexity == "single"
    assert len(plan.routing_plan) == 1


async def test_router_model_retries_on_bad_json(tmp_path: Path):
    reg = _mock_registry(tmp_path)
    mreg = _mock_model_registry()

    call_count = 0

    async def _fake_stream(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            chunk = MagicMock(spec=StreamChunk)
            chunk.text = "not json at all"
            yield chunk
        else:
            chunk = MagicMock(spec=StreamChunk)
            chunk.text = _make_valid_routing_json()
            yield chunk

    provider = MagicMock()
    provider.stream_chat = _fake_stream
    preg = MagicMock()
    preg.instantiate.return_value = provider

    router = RouterModel(
        registry=reg,
        provider_registry=preg,
        model_registry=mreg,
        key_manager=MagicMock(),
        max_splits=5,
    )
    plan = await router.route("What is 2+2?", [], None)
    assert plan is not None
    assert call_count == 2  # retried once


async def test_router_model_raises_after_max_retries(tmp_path: Path):
    reg = _mock_registry(tmp_path)
    mreg = _mock_model_registry()

    async def _bad_stream(**kwargs):
        chunk = MagicMock(spec=StreamChunk)
        chunk.text = "completely invalid"
        yield chunk

    provider = MagicMock()
    provider.stream_chat = _bad_stream
    preg = MagicMock()
    preg.instantiate.return_value = provider

    router = RouterModel(
        registry=reg,
        provider_registry=preg,
        model_registry=mreg,
        key_manager=MagicMock(),
        max_splits=5,
    )
    with pytest.raises(SmartError):
        await router.route("Q", [], None)


async def test_router_model_no_aliases_raises(tmp_path: Path):
    reg = _mock_registry(tmp_path)
    mreg = MagicMock()
    mreg.get.return_value = None
    mreg.list_all.return_value = []
    preg = MagicMock()

    router = RouterModel(
        registry=reg,
        provider_registry=preg,
        model_registry=mreg,
        key_manager=MagicMock(),
        max_splits=5,
    )
    with pytest.raises(SmartError, match="No model aliases"):
        await router.route("Q", [], None)


async def test_router_appends_format_hint_to_message(tmp_path: Path):
    reg = _mock_registry(tmp_path)
    mreg = _mock_model_registry()
    captured_messages: list = []

    async def _capture_stream(messages, **kwargs):
        captured_messages.extend(messages)
        chunk = MagicMock(spec=StreamChunk)
        chunk.text = _make_valid_routing_json()
        yield chunk

    provider = MagicMock()
    provider.stream_chat = _capture_stream
    preg = MagicMock()
    preg.instantiate.return_value = provider

    router = RouterModel(
        registry=reg,
        provider_registry=preg,
        model_registry=mreg,
        key_manager=MagicMock(),
        max_splits=5,
    )
    await router.route("Tell me about X", [], format_hint="table")
    last_user_msg = [m for m in captured_messages if m.role == "user"][-1]
    assert "table" in last_user_msg.content
