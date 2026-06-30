"""Tests for workflow/registry.py — WorkflowCapabilityRegistry."""

from __future__ import annotations

import pytest

from anythink.exceptions import WorkflowError
from anythink.workflow.registry import (
    PREDEFINED_TAGS,
    WorkflowCapabilityRegistry,
    _infer_tags,
)


# ---------------------------------------------------------------------------
# Tag inference
# ---------------------------------------------------------------------------


class TestInferTags:
    def test_mistral(self) -> None:
        assert "summarization" in _infer_tags("mistral:7b")
        assert "extraction" in _infer_tags("mistral:7b")

    def test_deepseek_coder(self) -> None:
        tags = _infer_tags("deepseek-coder:6.7b")
        assert "code" in tags
        assert "code-review" in tags

    def test_llama3(self) -> None:
        tags = _infer_tags("llama3.2:8b")
        assert "planning" in tags
        assert "reasoning" in tags

    def test_gemini(self) -> None:
        tags = _infer_tags("gemini-2.0-flash")
        assert "multimodal" in tags
        assert "long-context" in tags

    def test_gpt4(self) -> None:
        tags = _infer_tags("gpt-4o")
        assert "reasoning" in tags
        assert "code" in tags

    def test_unknown_returns_empty(self) -> None:
        assert _infer_tags("totally-unknown-model-xyz") == []


# ---------------------------------------------------------------------------
# Registry — basic tag CRUD
# ---------------------------------------------------------------------------


class TestWorkflowCapabilityRegistry:
    def test_get_tags_inferred_when_absent(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        tags = reg.get_tags("mistral:7b")
        assert "summarization" in tags

    def test_set_tags_overrides_inference(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_tags("my-model", ["writing", "analysis"])
        assert reg.get_tags("my-model") == ["writing", "analysis"]

    def test_add_tag(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_tags("local1", ["summarization"])
        reg.add_tag("local1", "reasoning")
        assert "reasoning" in reg.get_tags("local1")
        assert "summarization" in reg.get_tags("local1")

    def test_add_tag_no_duplicate(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_tags("local1", ["summarization"])
        reg.add_tag("local1", "summarization")
        assert reg.get_tags("local1").count("summarization") == 1

    def test_remove_tag(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_tags("local1", ["summarization", "extraction"])
        reg.remove_tag("local1", "extraction")
        assert "extraction" not in reg.get_tags("local1")
        assert "summarization" in reg.get_tags("local1")

    def test_remove_nonexistent_tag_is_noop(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_tags("local1", ["summarization"])
        reg.remove_tag("local1", "nonexistent")  # should not raise
        assert reg.get_tags("local1") == ["summarization"]


# ---------------------------------------------------------------------------
# Fallback chains
# ---------------------------------------------------------------------------


class TestFallbackChain:
    def test_simple_fallback(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_fallback("google2", "local-summarizer")
        assert reg.get_fallback_chain("google2") == ["local-summarizer"]

    def test_chained_fallback(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_fallback("a", "b")
        reg.set_fallback("b", "c")
        chain = reg.get_fallback_chain("a")
        assert chain == ["b", "c"]

    def test_cycle_detection(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_fallback("a", "b")
        reg.set_fallback("b", "a")  # cycle
        chain = reg.get_fallback_chain("a")
        assert "a" not in chain  # cycle cut
        assert len(chain) <= 1

    def test_no_fallback_returns_empty(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        assert reg.get_fallback_chain("lone-model") == []


# ---------------------------------------------------------------------------
# Listing and querying
# ---------------------------------------------------------------------------


class TestRegistryListing:
    def test_all_aliases_includes_added(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_tags("alpha", ["code"])
        reg.set_tags("beta", ["reasoning"])
        names = [e["alias"] for e in reg.all_aliases()]
        assert "alpha" in names
        assert "beta" in names

    def test_all_aliases_inferred_flag(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_tags("explicit-model", ["code"])
        entries = {e["alias"]: e for e in reg.all_aliases()}
        assert entries["explicit-model"]["inferred"] is False

    def test_aliases_with_tag(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_tags("m1", ["summarization", "code"])
        reg.set_tags("m2", ["code"])
        reg.set_tags("m3", ["reasoning"])
        coders = reg.aliases_with_tag("code")
        assert "m1" in coders
        assert "m2" in coders
        assert "m3" not in coders

    def test_has_alias(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        assert reg.has_alias("nobody") is False
        reg.set_tags("nobody", ["fast"])
        assert reg.has_alias("nobody") is True

    def test_remove_alias(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "caps.yaml")
        reg.set_tags("temp", ["fast"])
        reg.remove_alias("temp")
        assert reg.has_alias("temp") is False


# ---------------------------------------------------------------------------
# YAML round-trip persistence
# ---------------------------------------------------------------------------


class TestRegistryPersistence:
    def test_yaml_round_trip(self, tmp_path: "pytest.fixture") -> None:
        path = tmp_path / "caps.yaml"
        reg1 = WorkflowCapabilityRegistry(path)
        reg1.set_tags("local-summarizer", ["summarization", "extraction"])
        reg1.set_fallback("local-summarizer", "fallback-model")

        reg2 = WorkflowCapabilityRegistry(path)
        assert reg2.get_tags("local-summarizer") == ["summarization", "extraction"]
        assert reg2.get_fallback_chain("local-summarizer") == ["fallback-model"]

    def test_none_tags_preserved_as_inferred(self, tmp_path: "pytest.fixture") -> None:
        path = tmp_path / "caps.yaml"
        reg1 = WorkflowCapabilityRegistry(path)
        # Set only a fallback — no explicit tags
        reg1.set_fallback("mistral:7b", "backup")

        reg2 = WorkflowCapabilityRegistry(path)
        # Tags should still be inferred from model name, not empty
        tags = reg2.get_tags("mistral:7b")
        assert "summarization" in tags

    def test_corrupt_yaml_raises(self, tmp_path: "pytest.fixture") -> None:
        path = tmp_path / "caps.yaml"
        path.write_text("{{invalid: [yaml", encoding="utf-8")
        reg = WorkflowCapabilityRegistry(path)
        with pytest.raises(WorkflowError):
            reg.get_tags("anything")

    def test_missing_file_returns_empty(self, tmp_path: "pytest.fixture") -> None:
        reg = WorkflowCapabilityRegistry(tmp_path / "nonexistent.yaml")
        assert reg.all_aliases() == []
        assert reg.get_fallback_chain("x") == []


# ---------------------------------------------------------------------------
# Predefined tags constant
# ---------------------------------------------------------------------------


class TestPredefinedTags:
    def test_contains_expected_tags(self) -> None:
        assert "planning" in PREDEFINED_TAGS
        assert "summarization" in PREDEFINED_TAGS
        assert "code" in PREDEFINED_TAGS
        assert "long-context" in PREDEFINED_TAGS
