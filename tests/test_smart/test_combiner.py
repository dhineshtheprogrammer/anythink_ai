"""Tests for smart/combiner.py."""

from pathlib import Path
from unittest.mock import MagicMock

from anythink.providers.base import StreamChunk
from anythink.smart.combiner import CombinerModel, _format_store_entry
from anythink.smart.models import SpecialistResponse
from anythink.smart.registry import SmartRegistry
from anythink.smart.store import TemporaryResponseStore


def _make_resp(slot: int, category: str, response: str, score: int = 80) -> SpecialistResponse:
    return SpecialistResponse(
        slot=slot,
        category=category,
        model_alias="local",
        sub_question="Q",
        response=response,
        quality_score=score,
        retry_count=0,
        duration_s=0.1,
    )


def _make_registry(tmp_path: Path) -> SmartRegistry:
    reg = SmartRegistry(tmp_path / "reg.yaml")
    reg.load()
    return reg


def _make_model_registry(alias: str = "local") -> MagicMock:
    alias_obj = MagicMock()
    alias_obj.alias = alias
    alias_obj.model_id = "test"
    alias_obj.provider = "ollama"
    mreg = MagicMock()
    mreg.get.return_value = alias_obj
    mreg.list_all.return_value = [alias_obj]
    return mreg


def _make_provider_registry(response: str = "combined answer") -> MagicMock:
    async def _stream(**kwargs):
        chunk = MagicMock(spec=StreamChunk)
        chunk.text = response
        yield chunk

    provider = MagicMock()
    provider.stream_chat = _stream
    preg = MagicMock()
    preg.instantiate.return_value = provider
    return preg


def test_format_store_entry_normal():
    resp = _make_resp(1, "math", "The answer is 42.")
    text = _format_store_entry(1, resp)
    assert "Specialist 1" in text
    assert "math" in text
    assert "The answer is 42." in text
    assert "low confidence" not in text


def test_format_store_entry_low_confidence():
    resp = _make_resp(1, "code", "I'm not sure.")
    resp.low_confidence = True
    text = _format_store_entry(1, resp)
    assert "low confidence" in text


async def test_combine_single_entry_passthrough(tmp_path: Path):
    reg = _make_registry(tmp_path)
    mreg = _make_model_registry()
    preg = _make_provider_registry()

    combiner = CombinerModel(reg, preg, mreg, MagicMock())
    store = TemporaryResponseStore()
    store.add(_make_resp(1, "general", "Direct answer."))

    result = await combiner.combine(store, "stitch")
    # Single entry → passthrough, no LLM call
    assert result == "Direct answer."
    preg.instantiate.assert_not_called()


async def test_combine_empty_store_returns_empty(tmp_path: Path):
    reg = _make_registry(tmp_path)
    mreg = _make_model_registry()
    preg = _make_provider_registry()

    combiner = CombinerModel(reg, preg, mreg, MagicMock())
    store = TemporaryResponseStore()

    result = await combiner.combine(store, "stitch")
    assert result == ""


async def test_combine_stitch_calls_provider(tmp_path: Path):
    reg = _make_registry(tmp_path)
    mreg = _make_model_registry()
    preg = _make_provider_registry("Stitched response")

    combiner = CombinerModel(reg, preg, mreg, MagicMock())
    store = TemporaryResponseStore()
    store.add(_make_resp(1, "math", "Math answer."))
    store.add(_make_resp(2, "code", "Code answer."))

    result = await combiner.combine(store, "stitch")
    assert result == "Stitched response"
    preg.instantiate.assert_called_once()


async def test_combine_merge_calls_provider(tmp_path: Path):
    reg = _make_registry(tmp_path)
    mreg = _make_model_registry()
    preg = _make_provider_registry("Merged response")

    combiner = CombinerModel(reg, preg, mreg, MagicMock())
    store = TemporaryResponseStore()
    store.add(_make_resp(1, "research", "Research."))
    store.add(_make_resp(2, "reasoning", "Reasoning."))

    result = await combiner.combine(store, "merge")
    assert result == "Merged response"


def test_build_combiner_prompt_stitch_contains_instruction(tmp_path: Path):
    reg = _make_registry(tmp_path)
    combiner = CombinerModel(reg, MagicMock(), MagicMock(), MagicMock())
    store = TemporaryResponseStore()
    store.add(_make_resp(1, "math", "Answer 1."))
    store.add(_make_resp(2, "code", "Answer 2."))

    prompt = combiner._build_combiner_prompt(store, "stitch")
    assert "transitional" in prompt.lower() or "Combine" in prompt
    assert "Specialist 1" in prompt
    assert "Specialist 2" in prompt


def test_combiner_alias_name_fallback_to_first(tmp_path: Path):
    reg = _make_registry(tmp_path)
    mreg = _make_model_registry("my-alias")
    combiner = CombinerModel(reg, MagicMock(), mreg, MagicMock())
    name = combiner.combiner_alias_name()
    assert name == "my-alias"
