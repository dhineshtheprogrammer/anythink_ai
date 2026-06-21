"""Tests for batch processing mode."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock

from anythink.batch.runner import BatchResult, run_batch
from anythink.batch.writers import write_json, write_markdown
from anythink.providers.base import StreamChunk, TokenUsage


def _make_ctx(alias_name: str = "test-alias") -> MagicMock:
    usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)

    async def _stream(*args, **kwargs) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(text="Hello ")
        yield StreamChunk(text="world", finish_reason="stop", usage=usage)

    mock_provider = MagicMock()
    mock_provider.name = "openai"
    mock_provider.stream_chat = _stream

    mock_alias = MagicMock()
    mock_alias.provider = "openai"
    mock_alias.model_id = "gpt-4o"
    mock_alias.gen_params = None

    ctx = MagicMock()
    ctx.config.default_model_alias = alias_name
    ctx.model_registry.get.return_value = mock_alias
    ctx.key_manager.get_key.return_value = "test-key"
    ctx.provider_registry.get.return_value = lambda api_key, **kwargs: mock_provider
    return ctx


class TestRunBatch:
    async def test_single_prompt(self) -> None:
        ctx = _make_ctx()
        results = await run_batch(ctx, ["What is 2+2?"])
        assert len(results) == 1
        assert results[0].response == "Hello world"
        assert results[0].error is None

    async def test_multiple_prompts_ordered(self) -> None:
        ctx = _make_ctx()
        prompts = ["Q1?", "Q2?", "Q3?"]
        results = await run_batch(ctx, prompts)
        assert len(results) == 3
        for i, r in enumerate(results):
            assert r.index == i

    async def test_no_alias_returns_error(self) -> None:
        ctx = MagicMock()
        ctx.config.default_model_alias = None
        ctx.model_registry.get.return_value = None
        results = await run_batch(ctx, ["test prompt"])
        assert results[0].error is not None

    async def test_parallel_cap_at_20(self) -> None:
        ctx = _make_ctx()
        prompts = ["Q"] * 5
        results = await run_batch(ctx, prompts, parallel=100)
        assert len(results) == 5

    async def test_error_in_one_prompt_doesnt_abort(self) -> None:
        ctx = MagicMock()
        ctx.config.default_model_alias = "alias"

        call_count = 0

        async def _stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("provider error")
            yield StreamChunk(text="ok", finish_reason="stop")

        mock_provider = MagicMock()
        mock_provider.stream_chat = _stream

        mock_alias = MagicMock()
        mock_alias.provider = "openai"
        mock_alias.model_id = "gpt-4o"
        mock_alias.gen_params = None

        ctx.model_registry.get.return_value = mock_alias
        ctx.key_manager.get_key.return_value = "key"
        ctx.provider_registry.get.return_value = lambda **kw: mock_provider

        results = await run_batch(ctx, ["p1", "p2", "p3"])
        assert len(results) == 3
        error_results = [r for r in results if r.error]
        ok_results = [r for r in results if not r.error]
        assert len(error_results) >= 1


class TestBatchWriters:
    def test_write_markdown(self, tmp_path: Path) -> None:
        results = [
            BatchResult(0, "What is 2+2?", "4", None, None, 0.5),
            BatchResult(1, "Capital of France?", "Paris", None, None, 0.3),
        ]
        out = tmp_path / "results.md"
        write_markdown(results, out)
        content = out.read_text()
        assert "What is 2+2?" in content
        assert "Capital of France?" in content

    def test_write_json(self, tmp_path: Path) -> None:
        import json

        results = [
            BatchResult(0, "prompt", "response", None, None, 1.0),
        ]
        out = tmp_path / "results.json"
        write_json(results, out)
        data = json.loads(out.read_text())
        assert len(data) == 1
        assert data[0]["prompt"] == "prompt"
        assert data[0]["response"] == "response"

    def test_write_markdown_with_error(self, tmp_path: Path) -> None:
        results = [
            BatchResult(0, "bad prompt", "", None, "provider error", 0.0),
        ]
        out = tmp_path / "results.md"
        write_markdown(results, out)
        content = out.read_text()
        assert "provider error" in content
