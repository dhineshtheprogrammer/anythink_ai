"""Tests for smart/formatter.py."""

from pathlib import Path
from unittest.mock import MagicMock

from anythink.providers.base import StreamChunk
from anythink.smart.formatter import FormatterModel, _FORMAT_INSTRUCTIONS
from anythink.smart.registry import SmartRegistry


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


def _make_provider_registry(response: str = "formatted output") -> MagicMock:
    async def _stream(**kwargs):
        chunk = MagicMock(spec=StreamChunk)
        chunk.text = response
        yield chunk

    provider = MagicMock()
    provider.stream_chat = _stream
    preg = MagicMock()
    preg.instantiate.return_value = provider
    return preg


def test_format_instructions_has_all_formats():
    expected = {"markdown", "list", "table", "code_only", "json", "summary", "detailed"}
    assert set(_FORMAT_INSTRUCTIONS.keys()) == expected


async def test_unknown_format_passthrough(tmp_path: Path):
    reg = _make_registry(tmp_path)
    # No model registry call expected for unknown format
    formatter = FormatterModel(reg, MagicMock(), MagicMock(), MagicMock())
    result = await formatter.format("original text", "nonexistent-format")
    assert result == "original text"


async def test_format_markdown_calls_provider(tmp_path: Path):
    reg = _make_registry(tmp_path)
    mreg = _make_model_registry()
    preg = _make_provider_registry("## Formatted")

    formatter = FormatterModel(reg, preg, mreg, MagicMock())
    result = await formatter.format("raw text", "markdown")
    assert result == "## Formatted"


async def test_format_summary_calls_provider(tmp_path: Path):
    reg = _make_registry(tmp_path)
    mreg = _make_model_registry()
    preg = _make_provider_registry("Summary: X is Y.")

    formatter = FormatterModel(reg, preg, mreg, MagicMock())
    result = await formatter.format("Long text...", "summary")
    assert result == "Summary: X is Y."


def test_build_formatter_prompt_contains_text_and_instruction(tmp_path: Path):
    reg = _make_registry(tmp_path)
    formatter = FormatterModel(reg, MagicMock(), MagicMock(), MagicMock())
    prompt = formatter._build_formatter_prompt("my content", "Reformat this.")
    assert "my content" in prompt
    assert "Reformat this." in prompt


async def test_formatter_falls_back_to_combiner_alias(tmp_path: Path):
    reg = _make_registry(tmp_path)
    reg.set_combiner("combiner-alias")  # formatter not set, combiner is

    alias_obj = MagicMock()
    alias_obj.alias = "combiner-alias"
    alias_obj.model_id = "test"
    alias_obj.provider = "ollama"

    mreg = MagicMock()
    mreg.get.side_effect = lambda name: alias_obj if name == "combiner-alias" else None
    mreg.list_all.return_value = [alias_obj]

    preg = _make_provider_registry("formatted via combiner")

    formatter = FormatterModel(reg, preg, mreg, MagicMock())
    result = await formatter.format("text", "list")
    assert result == "formatted via combiner"


async def test_formatter_falls_back_to_first_model(tmp_path: Path):
    reg = _make_registry(tmp_path)
    # Neither formatter nor combiner set

    alias_obj = MagicMock()
    alias_obj.alias = "first"
    alias_obj.model_id = "test"
    alias_obj.provider = "ollama"

    mreg = MagicMock()
    mreg.get.return_value = None
    mreg.list_all.return_value = [alias_obj]

    preg = _make_provider_registry("fallback formatted")

    formatter = FormatterModel(reg, preg, mreg, MagicMock())
    result = await formatter.format("text", "json")
    assert result == "fallback formatted"
