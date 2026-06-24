"""Tests for /rag threshold command — config persistence."""

from __future__ import annotations

import pytest

from anythink.config.schema import AppConfig


class TestThresholdDefault:
    def test_default_threshold(self) -> None:
        cfg = AppConfig()
        assert cfg.rag_threshold == 0.65

    def test_default_top_k(self) -> None:
        cfg = AppConfig()
        assert cfg.rag_top_k == 3

    def test_default_retrieval_strategy(self) -> None:
        cfg = AppConfig()
        assert cfg.rag_retrieval_strategy == "vector"

    def test_default_chunk_strategy(self) -> None:
        cfg = AppConfig()
        assert cfg.rag_chunk_strategy == "fixed"

    def test_default_chunk_size(self) -> None:
        cfg = AppConfig()
        assert cfg.rag_chunk_size == 512

    def test_default_chunk_overlap(self) -> None:
        cfg = AppConfig()
        assert cfg.rag_chunk_overlap == 100


class TestThresholdPersistence:
    def test_save_and_reload_threshold(self, xdg_dirs: object, config_manager: object) -> None:
        from dataclasses import replace

        from anythink.config.manager import ConfigManager

        cm: ConfigManager = config_manager  # type: ignore[assignment]
        original = cm.load()
        updated = replace(original, rag_threshold=0.80)
        cm.save(updated)
        reloaded = cm.load()
        assert reloaded.rag_threshold == pytest.approx(0.80)

    def test_save_and_reload_top_k(self, xdg_dirs: object, config_manager: object) -> None:
        from dataclasses import replace

        from anythink.config.manager import ConfigManager

        cm: ConfigManager = config_manager  # type: ignore[assignment]
        original = cm.load()
        updated = replace(original, rag_top_k=7)
        cm.save(updated)
        reloaded = cm.load()
        assert reloaded.rag_top_k == 7

    def test_save_and_reload_chunk_strategy(self, xdg_dirs: object, config_manager: object) -> None:
        from dataclasses import replace

        from anythink.config.manager import ConfigManager

        cm: ConfigManager = config_manager  # type: ignore[assignment]
        original = cm.load()
        updated = replace(original, rag_chunk_strategy="sentence")
        cm.save(updated)
        reloaded = cm.load()
        assert reloaded.rag_chunk_strategy == "sentence"

    def test_save_and_reload_retrieval_strategy(
        self, xdg_dirs: object, config_manager: object
    ) -> None:
        from dataclasses import replace

        from anythink.config.manager import ConfigManager

        cm: ConfigManager = config_manager  # type: ignore[assignment]
        original = cm.load()
        updated = replace(original, rag_retrieval_strategy="hybrid")
        cm.save(updated)
        reloaded = cm.load()
        assert reloaded.rag_retrieval_strategy == "hybrid"


class TestThresholdValidation:
    def test_valid_chunk_strategies(self) -> None:
        from anythink.config.manager import validate_config

        for strategy in ("fixed", "sentence", "paragraph", "semantic", "code", "heading"):
            errors = validate_config({"rag_chunk_strategy": strategy})
            assert errors == [], f"Expected no errors for strategy '{strategy}'"

    def test_invalid_chunk_strategy(self) -> None:
        from anythink.config.manager import validate_config

        errors = validate_config({"rag_chunk_strategy": "unknown"})
        assert len(errors) == 1
        assert "rag_chunk_strategy" in str(errors[0])

    def test_valid_retrieval_strategies(self) -> None:
        from anythink.config.manager import validate_config

        for strategy in ("vector", "bm25", "hybrid", "mmr"):
            errors = validate_config({"rag_retrieval_strategy": strategy})
            assert errors == [], f"Expected no errors for strategy '{strategy}'"

    def test_invalid_retrieval_strategy(self) -> None:
        from anythink.config.manager import validate_config

        errors = validate_config({"rag_retrieval_strategy": "cosine"})
        assert len(errors) == 1
        assert "rag_retrieval_strategy" in str(errors[0])
