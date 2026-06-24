"""Tests for CohereEmbeddingBackend (Phase 8)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from anythink.embeddings.cohere_emb import SUPPORTED_MODELS, CohereEmbeddingBackend


class TestCohereBackendMeta:
    def test_default_name(self) -> None:
        assert CohereEmbeddingBackend().name == "cohere-emb"

    def test_non_default_name(self) -> None:
        backend = CohereEmbeddingBackend("embed-multilingual-v3.0")
        assert backend.name == "cohere-emb/embed-multilingual-v3.0"

    def test_display_name(self) -> None:
        assert "Cohere" in CohereEmbeddingBackend().display_name

    def test_default_dimensions(self) -> None:
        assert CohereEmbeddingBackend().dimensions == 1024

    def test_light_model_dimensions(self) -> None:
        assert CohereEmbeddingBackend("embed-english-light-v3.0").dimensions == 384

    def test_unknown_model_default_dims(self) -> None:
        assert CohereEmbeddingBackend("custom-model").dimensions == 1024

    def test_three_supported_models(self) -> None:
        assert len(SUPPORTED_MODELS) == 3


class TestCohereIsAvailable:
    def test_available_when_env_key_set(self) -> None:
        with patch.dict(os.environ, {"COHERE_API_KEY": "co-test"}):
            with patch("keyring.get_password", return_value=None):
                assert CohereEmbeddingBackend().is_available() is True

    def test_available_when_keyring_has_key(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "COHERE_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with patch("keyring.get_password", return_value="co-keyring"):
                assert CohereEmbeddingBackend().is_available() is True

    def test_unavailable_without_key(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "COHERE_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with patch("keyring.get_password", return_value=None):
                assert CohereEmbeddingBackend().is_available() is False


class TestCohereEmbed:
    @pytest.mark.asyncio
    async def test_embed_returns_correct_shape(self, httpx_mock: object) -> None:
        from pytest_httpx import HTTPXMock

        mock: HTTPXMock = httpx_mock  # type: ignore[assignment]
        mock.add_response(
            method="POST",
            url="https://api.cohere.com/v1/embed",
            json={"embeddings": [[0.1] * 1024, [0.2] * 1024]},
        )
        with patch("anythink.embeddings.cohere_emb._get_api_key", return_value="co-test"):
            backend = CohereEmbeddingBackend()
            result = await backend.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 1024

    @pytest.mark.asyncio
    async def test_embed_raises_without_key(self) -> None:
        with patch("anythink.embeddings.cohere_emb._get_api_key", return_value=None):
            backend = CohereEmbeddingBackend()
            with pytest.raises(EnvironmentError, match="cohere"):
                await backend.embed(["hello"])

    @pytest.mark.asyncio
    async def test_embed_single_text(self, httpx_mock: object) -> None:
        from pytest_httpx import HTTPXMock

        mock: HTTPXMock = httpx_mock  # type: ignore[assignment]
        mock.add_response(
            method="POST",
            url="https://api.cohere.com/v1/embed",
            json={"embeddings": [[0.5] * 1024]},
        )
        with patch("anythink.embeddings.cohere_emb._get_api_key", return_value="co-test"):
            backend = CohereEmbeddingBackend()
            result = await backend.embed(["test"])
        assert result == [[0.5] * 1024]
