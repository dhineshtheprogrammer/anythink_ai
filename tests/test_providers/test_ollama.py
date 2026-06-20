"""Tests for OllamaProvider using pytest-httpx to mock HTTP calls."""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from anythink.exceptions import ModelNotFoundError, ProviderUnavailableError
from anythink.providers.ollama import OllamaProvider
from tests.test_providers.conftest import make_messages


def _ndjson(*payloads: dict) -> bytes:
    return b"\n".join(json.dumps(p).encode() for p in payloads)


class TestOllamaProvider:
    def test_name(self) -> None:
        p = OllamaProvider()
        assert p.name == "ollama"

    def test_does_not_require_api_key(self) -> None:
        p = OllamaProvider()
        assert p.requires_api_key is False

    def test_default_url(self) -> None:
        p = OllamaProvider()
        assert "11434" in p._url

    def test_custom_url(self) -> None:
        p = OllamaProvider(base_url="http://localhost:12345")
        assert "12345" in p._url

    @pytest.mark.asyncio
    async def test_stream_chat_yields_text(self, httpx_mock: HTTPXMock) -> None:
        chunks = [
            {"message": {"role": "assistant", "content": "Hello"}, "done": False},
            {"message": {"role": "assistant", "content": " world"}, "done": False},
            {
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "prompt_eval_count": 5,
                "eval_count": 10,
            },
        ]
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:11434/api/chat",
            content=_ndjson(*chunks),
        )

        p = OllamaProvider()
        all_chunks = [c async for c in p.stream_chat(make_messages("Hi"), "llama3")]

        text = "".join(c.text for c in all_chunks)
        assert "Hello world" in text

        final = next((c for c in all_chunks if c.finish_reason == "stop"), None)
        assert final is not None
        assert final.usage is not None
        assert final.usage.prompt_tokens == 5
        assert final.usage.completion_tokens == 10

    @pytest.mark.asyncio
    async def test_stream_chat_model_not_found(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:11434/api/chat",
            status_code=404,
        )
        p = OllamaProvider()
        with pytest.raises(ModelNotFoundError):
            async for _ in p.stream_chat(make_messages("Hi"), "nonexistent"):
                pass

    @pytest.mark.asyncio
    async def test_list_models(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="http://localhost:11434/api/tags",
            json={
                "models": [
                    {"name": "llama3:latest", "details": {"context_length": 8192}},
                    {"name": "mistral:latest", "details": {}},
                ]
            },
        )
        p = OllamaProvider()
        models = await p.list_models()
        assert len(models) == 2
        assert models[0].id == "llama3:latest"
        assert models[0].context_window == 8192

    @pytest.mark.asyncio
    async def test_list_models_connect_error(self, httpx_mock: HTTPXMock) -> None:
        import httpx

        httpx_mock.add_exception(httpx.ConnectError("refused"))
        p = OllamaProvider()
        with pytest.raises(ProviderUnavailableError, match="Cannot connect"):
            await p.list_models()

    @pytest.mark.asyncio
    async def test_test_connection_true(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="http://localhost:11434/api/tags",
            json={"models": []},
        )
        p = OllamaProvider()
        assert await p.test_connection() is True

    @pytest.mark.asyncio
    async def test_test_connection_false_on_error(self, httpx_mock: HTTPXMock) -> None:
        import httpx

        httpx_mock.add_exception(httpx.ConnectError("refused"))
        p = OllamaProvider()
        assert await p.test_connection() is False

    def test_supports_vision_is_false(self) -> None:
        assert OllamaProvider().supports_vision is False

    @pytest.mark.asyncio
    async def test_stream_chat_with_max_tokens(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:11434/api/chat",
            content=_ndjson({"message": {"content": "Hi"}, "done": True}),
        )
        p = OllamaProvider()
        chunks = [c async for c in p.stream_chat(make_messages("Hello"), "llama3", max_tokens=100)]
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_stream_chat_skips_empty_and_invalid_lines(self, httpx_mock: HTTPXMock) -> None:
        content = (
            b'{"message": {"content": "Hi"}, "done": false}\n'
            b"\n"
            b"not-valid-json\n"
            b'{"message": {"content": "!"}, "done": true}\n'
        )
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:11434/api/chat",
            content=content,
        )
        p = OllamaProvider()
        chunks = [c async for c in p.stream_chat(make_messages("Hello"), "llama3")]
        text = "".join(c.text for c in chunks)
        assert "Hi" in text

    @pytest.mark.asyncio
    async def test_stream_chat_connect_error(self, httpx_mock: HTTPXMock) -> None:
        import httpx

        httpx_mock.add_exception(httpx.ConnectError("refused"))
        p = OllamaProvider()
        with pytest.raises(ProviderUnavailableError, match="Cannot connect"):
            async for _ in p.stream_chat(make_messages("Hi"), "llama3"):
                pass

    @pytest.mark.asyncio
    async def test_stream_chat_http_status_error(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:11434/api/chat",
            status_code=500,
        )
        p = OllamaProvider()
        with pytest.raises(ProviderUnavailableError):
            async for _ in p.stream_chat(make_messages("Hi"), "llama3"):
                pass
