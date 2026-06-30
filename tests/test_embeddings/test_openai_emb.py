"""Tests for OpenAIEmbeddingBackend (Phase 8)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from anythink.embeddings.openai_emb import SUPPORTED_MODELS, OpenAIEmbeddingBackend


class TestOpenAIBackendMeta:
    def test_default_name(self) -> None:
        assert OpenAIEmbeddingBackend().name == "openai-emb"

    def test_non_default_name(self) -> None:
        backend = OpenAIEmbeddingBackend("text-embedding-3-large")
        assert backend.name == "openai-emb/text-embedding-3-large"

    def test_display_name(self) -> None:
        assert "OpenAI" in OpenAIEmbeddingBackend().display_name

    def test_default_dimensions(self) -> None:
        assert OpenAIEmbeddingBackend().dimensions == 1536

    def test_large_model_dimensions(self) -> None:
        assert OpenAIEmbeddingBackend("text-embedding-3-large").dimensions == 3072

    def test_unknown_model_default_dims(self) -> None:
        assert OpenAIEmbeddingBackend("custom-model").dimensions == 1536

    def test_two_supported_models(self) -> None:
        assert len(SUPPORTED_MODELS) == 2


class TestOpenAIIsAvailable:
    def test_available_when_env_key_set(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            with patch("keyring.get_password", return_value=None):
                assert OpenAIEmbeddingBackend().is_available() is True

    def test_available_when_keyring_has_key(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            with patch("keyring.get_password", return_value="sk-keyring"):
                assert OpenAIEmbeddingBackend().is_available() is True

    def test_unavailable_without_key(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with patch("keyring.get_password", return_value=None):
                assert OpenAIEmbeddingBackend().is_available() is False


class TestOpenAIEmbed:
    @pytest.mark.asyncio
    async def test_embed_returns_correct_shape(self, httpx_mock: object) -> None:
        from pytest_httpx import HTTPXMock

        mock: HTTPXMock = httpx_mock  # type: ignore[assignment]
        mock.add_response(
            method="POST",
            url="https://api.openai.com/v1/embeddings",
            json={
                "data": [
                    {"index": 0, "embedding": [0.1] * 1536},
                    {"index": 1, "embedding": [0.2] * 1536},
                ]
            },
        )
        with patch("anythink.embeddings.openai_emb._get_api_key", return_value="sk-test"):
            backend = OpenAIEmbeddingBackend()
            result = await backend.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 1536

    @pytest.mark.asyncio
    async def test_embed_raises_without_key(self) -> None:
        with patch("anythink.embeddings.openai_emb._get_api_key", return_value=None):
            backend = OpenAIEmbeddingBackend()
            with pytest.raises(EnvironmentError, match="openai"):
                await backend.embed(["hello"])

    @pytest.mark.asyncio
    async def test_embed_results_sorted_by_index(self, httpx_mock: object) -> None:
        from pytest_httpx import HTTPXMock

        mock: HTTPXMock = httpx_mock  # type: ignore[assignment]
        mock.add_response(
            method="POST",
            url="https://api.openai.com/v1/embeddings",
            json={
                "data": [
                    {"index": 1, "embedding": [0.2] * 1536},
                    {"index": 0, "embedding": [0.1] * 1536},
                ]
            },
        )
        with patch("anythink.embeddings.openai_emb._get_api_key", return_value="sk-test"):
            backend = OpenAIEmbeddingBackend()
            result = await backend.embed(["hello", "world"])
        assert result[0][0] == pytest.approx(0.1)
        assert result[1][0] == pytest.approx(0.2)


class TestOpenAIKeyringException:
    def test_keyring_exception_falls_back_to_env(self) -> None:
        import os

        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with patch("keyring.get_password", side_effect=Exception("keyring error")):
                assert OpenAIEmbeddingBackend().is_available() is False
