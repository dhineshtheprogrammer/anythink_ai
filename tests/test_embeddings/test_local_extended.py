"""Tests for LocalEmbeddingBackend — extended model support (Phase 8)."""

from __future__ import annotations

import pytest

from anythink.embeddings.local import SUPPORTED_MODELS, LocalEmbeddingBackend


class TestSupportedModels:
    def test_all_minilm_l6_dims(self) -> None:
        assert SUPPORTED_MODELS["all-MiniLM-L6-v2"] == 384

    def test_all_minilm_l12_dims(self) -> None:
        assert SUPPORTED_MODELS["all-MiniLM-L12-v2"] == 384

    def test_bge_small_dims(self) -> None:
        assert SUPPORTED_MODELS["bge-small-en-v1.5"] == 384

    def test_bge_base_dims(self) -> None:
        assert SUPPORTED_MODELS["bge-base-en-v1.5"] == 768

    def test_bge_large_dims(self) -> None:
        assert SUPPORTED_MODELS["bge-large-en-v1.5"] == 1024

    def test_bge_m3_dims(self) -> None:
        assert SUPPORTED_MODELS["bge-m3"] == 1024

    def test_e5_base_dims(self) -> None:
        assert SUPPORTED_MODELS["e5-base-v2"] == 768

    def test_e5_large_dims(self) -> None:
        assert SUPPORTED_MODELS["e5-large-v2"] == 1024

    def test_eight_models_registered(self) -> None:
        assert len(SUPPORTED_MODELS) == 8


class TestLocalEmbeddingBackendDimensions:
    def test_default_model_dimensions(self) -> None:
        backend = LocalEmbeddingBackend()
        assert backend.dimensions == 384

    def test_bge_base_dimensions(self) -> None:
        backend = LocalEmbeddingBackend("bge-base-en-v1.5")
        assert backend.dimensions == 768

    def test_bge_large_dimensions(self) -> None:
        backend = LocalEmbeddingBackend("bge-large-en-v1.5")
        assert backend.dimensions == 1024

    def test_unknown_model_defaults_to_384(self) -> None:
        backend = LocalEmbeddingBackend("some-unknown-model")
        assert backend.dimensions == 384

    def test_name_is_local(self) -> None:
        backend = LocalEmbeddingBackend()
        assert backend.name == "local"

    def test_display_name(self) -> None:
        backend = LocalEmbeddingBackend()
        assert "sentence-transformers" in backend.display_name

    def test_is_available_false_without_dep(self) -> None:
        import sys
        from unittest.mock import patch

        with patch.dict(sys.modules, {"sentence_transformers": None}):
            backend = LocalEmbeddingBackend()
            assert backend.is_available() is False

    @pytest.mark.asyncio
    async def test_embed_raises_without_dep(self) -> None:
        import sys
        from unittest.mock import patch

        with patch.dict(sys.modules, {"sentence_transformers": None}):
            backend = LocalEmbeddingBackend()
            with pytest.raises(ImportError, match="anythink\\[rag\\]"):
                await backend.embed(["hello"])


class TestMockEmbeddingBackend:
    def test_dimensions_property(self) -> None:
        from anythink.embeddings.mock import MockEmbeddingBackend

        backend = MockEmbeddingBackend()
        assert isinstance(backend.dimensions, int)
        assert backend.dimensions > 0
