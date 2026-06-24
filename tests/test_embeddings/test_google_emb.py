"""Tests for GoogleEmbeddingBackend (Phase 8)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from anythink.embeddings.google_emb import SUPPORTED_MODELS, GoogleEmbeddingBackend


class TestGoogleBackendMeta:
    def test_default_name(self) -> None:
        assert GoogleEmbeddingBackend().name == "google-emb"

    def test_non_default_name(self) -> None:
        backend = GoogleEmbeddingBackend("embedding-001")
        assert backend.name == "google-emb/embedding-001"

    def test_display_name(self) -> None:
        assert "Google" in GoogleEmbeddingBackend().display_name

    def test_default_dimensions(self) -> None:
        assert GoogleEmbeddingBackend().dimensions == 768

    def test_embedding_001_dimensions(self) -> None:
        assert GoogleEmbeddingBackend("embedding-001").dimensions == 768

    def test_unknown_model_default_dims(self) -> None:
        assert GoogleEmbeddingBackend("custom-model").dimensions == 768

    def test_two_supported_models(self) -> None:
        assert len(SUPPORTED_MODELS) == 2


class TestGoogleIsAvailable:
    def test_available_when_env_key_set(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIza-test"}):
            with patch("keyring.get_password", return_value=None):
                assert GoogleEmbeddingBackend().is_available() is True

    def test_available_when_keyring_has_key(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "GOOGLE_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with patch("keyring.get_password", return_value="AIza-keyring"):
                assert GoogleEmbeddingBackend().is_available() is True

    def test_unavailable_without_key(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "GOOGLE_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with patch("keyring.get_password", return_value=None):
                assert GoogleEmbeddingBackend().is_available() is False


_TEST_KEY = "AIza-test"
_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class TestGoogleEmbed:
    @pytest.mark.asyncio
    async def test_embed_returns_correct_shape(self, httpx_mock: object) -> None:
        from pytest_httpx import HTTPXMock

        mock: HTTPXMock = httpx_mock  # type: ignore[assignment]
        url = f"{_BASE}/text-embedding-004:embedContent?key={_TEST_KEY}"
        mock.add_response(method="POST", url=url, json={"embedding": {"values": [0.1] * 768}})
        mock.add_response(method="POST", url=url, json={"embedding": {"values": [0.2] * 768}})
        with patch("anythink.embeddings.google_emb._get_api_key", return_value=_TEST_KEY):
            backend = GoogleEmbeddingBackend()
            result = await backend.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 768

    @pytest.mark.asyncio
    async def test_embed_raises_without_key(self) -> None:
        with patch("anythink.embeddings.google_emb._get_api_key", return_value=None):
            backend = GoogleEmbeddingBackend()
            with pytest.raises(EnvironmentError, match="gemini"):
                await backend.embed(["hello"])

    @pytest.mark.asyncio
    async def test_embed_uses_correct_model_in_url(self, httpx_mock: object) -> None:
        from pytest_httpx import HTTPXMock

        mock: HTTPXMock = httpx_mock  # type: ignore[assignment]
        url = f"{_BASE}/embedding-001:embedContent?key={_TEST_KEY}"
        mock.add_response(method="POST", url=url, json={"embedding": {"values": [0.3] * 768}})
        with patch("anythink.embeddings.google_emb._get_api_key", return_value=_TEST_KEY):
            backend = GoogleEmbeddingBackend("embedding-001")
            result = await backend.embed(["test"])
        assert result == [[0.3] * 768]
