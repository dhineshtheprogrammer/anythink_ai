"""Tests for OllamaEmbeddingBackend (Phase 8)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from anythink.embeddings.ollama import SUPPORTED_MODELS, OllamaEmbeddingBackend


class TestOllamaBackendMeta:
    def test_default_name(self) -> None:
        backend = OllamaEmbeddingBackend()
        assert backend.name == "ollama"

    def test_non_default_name_includes_model(self) -> None:
        backend = OllamaEmbeddingBackend("mxbai-embed-large")
        assert backend.name == "ollama/mxbai-embed-large"

    def test_display_name(self) -> None:
        assert OllamaEmbeddingBackend().display_name == "Ollama"

    def test_default_dimensions(self) -> None:
        assert OllamaEmbeddingBackend().dimensions == 768

    def test_mxbai_dimensions(self) -> None:
        assert OllamaEmbeddingBackend("mxbai-embed-large").dimensions == 1024

    def test_all_minilm_dimensions(self) -> None:
        assert OllamaEmbeddingBackend("all-minilm").dimensions == 384

    def test_unknown_model_default_dims(self) -> None:
        assert OllamaEmbeddingBackend("custom-model").dimensions == 768

    def test_supported_models_count(self) -> None:
        assert len(SUPPORTED_MODELS) == 4


class TestOllamaIsAvailable:
    def test_available_when_server_returns_200(self) -> None:
        backend = OllamaEmbeddingBackend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        with patch("httpx.Client", return_value=mock_client):
            assert backend.is_available() is True

    def test_unavailable_when_server_returns_non_200(self) -> None:
        backend = OllamaEmbeddingBackend()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        with patch("httpx.Client", return_value=mock_client):
            assert backend.is_available() is False

    def test_unavailable_on_connection_error(self) -> None:
        backend = OllamaEmbeddingBackend()
        with patch("httpx.Client") as mock_cls:
            mock_cls.side_effect = Exception("connection refused")
            assert backend.is_available() is False


class TestOllamaEmbed:
    @pytest.mark.asyncio
    async def test_embed_returns_correct_shape(self, httpx_mock: object) -> None:
        from pytest_httpx import HTTPXMock

        mock: HTTPXMock = httpx_mock  # type: ignore[assignment]
        mock.add_response(
            method="POST",
            url="http://localhost:11434/api/embeddings",
            json={"embedding": [0.1] * 768},
        )
        mock.add_response(
            method="POST",
            url="http://localhost:11434/api/embeddings",
            json={"embedding": [0.2] * 768},
        )
        backend = OllamaEmbeddingBackend()
        result = await backend.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 768
        assert len(result[1]) == 768

    @pytest.mark.asyncio
    async def test_embed_single_text(self, httpx_mock: object) -> None:
        from pytest_httpx import HTTPXMock

        mock: HTTPXMock = httpx_mock  # type: ignore[assignment]
        mock.add_response(
            method="POST",
            url="http://localhost:11434/api/embeddings",
            json={"embedding": [0.5] * 768},
        )
        backend = OllamaEmbeddingBackend()
        result = await backend.embed(["test"])
        assert result == [[0.5] * 768]

    @pytest.mark.asyncio
    async def test_embed_uses_custom_base_url(self, httpx_mock: object) -> None:
        from pytest_httpx import HTTPXMock

        mock: HTTPXMock = httpx_mock  # type: ignore[assignment]
        mock.add_response(
            method="POST",
            url="http://myhost:9999/api/embeddings",
            json={"embedding": [0.1] * 768},
        )
        backend = OllamaEmbeddingBackend(base_url="http://myhost:9999")
        result = await backend.embed(["hello"])
        assert len(result) == 1
