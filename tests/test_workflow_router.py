"""Tests for workflow/router.py — MetaRouter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from anythink.workflow.router import MetaRouter, _LOCAL_PROVIDERS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_alias(
    name: str,
    provider: str = "ollama",
    context_window: int = 32000,
    tags: list[str] | None = None,
) -> MagicMock:
    a = MagicMock()
    a.alias = name
    a.provider = provider
    a.context_window = context_window
    return a


def _make_router(aliases: list, tags_map: dict[str, list[str]] | None = None) -> MetaRouter:
    model_reg = MagicMock()
    model_reg.list_all.return_value = aliases
    model_reg.get.side_effect = lambda name: next(
        (a for a in aliases if a.alias == name), None
    )

    wf_reg = MagicMock()

    def _tags(alias_name: str) -> list[str]:
        if tags_map:
            return tags_map.get(alias_name, [])
        return []

    wf_reg.get_tags.side_effect = _tags
    wf_reg.get_fallback_chain.return_value = []

    return MetaRouter(workflow_registry=wf_reg, model_registry=model_reg)


# ---------------------------------------------------------------------------
# select_model
# ---------------------------------------------------------------------------


class TestSelectModel:
    def test_selects_only_matching_alias(self) -> None:
        aliases = [
            _make_alias("coder", provider="ollama"),
            _make_alias("summarizer", provider="ollama"),
        ]
        router = _make_router(
            aliases,
            tags_map={"coder": ["code"], "summarizer": ["summarization"]},
        )
        assert router.select_model(["code"]) == "coder"
        assert router.select_model(["summarization"]) == "summarizer"

    def test_no_matching_tag_returns_none(self) -> None:
        aliases = [_make_alias("m", provider="ollama")]
        router = _make_router(aliases, tags_map={"m": ["code"]})
        assert router.select_model(["translation"]) is None

    def test_empty_required_tags_returns_first(self) -> None:
        aliases = [_make_alias("m", provider="ollama")]
        router = _make_router(aliases, tags_map={"m": []})
        # With no required tags, all aliases qualify; router picks by score
        result = router.select_model([])
        assert result == "m"

    def test_context_window_filter(self) -> None:
        aliases = [
            _make_alias("small", context_window=4096),
            _make_alias("large", context_window=128000),
        ]
        router = _make_router(aliases, tags_map={"small": ["code"], "large": ["code"]})
        result = router.select_model(["code"], estimated_input_tokens=50000)
        assert result == "large"

    def test_prefers_local_over_cloud(self) -> None:
        aliases = [
            _make_alias("cloud-sum", provider="openai"),
            _make_alias("local-sum", provider="ollama"),
        ]
        router = _make_router(
            aliases,
            tags_map={"cloud-sum": ["summarization"], "local-sum": ["summarization"]},
        )
        result = router.select_model(["summarization"])
        assert result == "local-sum"

    def test_larger_context_window_wins_tie(self) -> None:
        aliases = [
            _make_alias("m-small", context_window=8000),
            _make_alias("m-large", context_window=128000),
        ]
        # Both are cloud, both have the same tag — larger ctx wins
        router = _make_router(
            aliases,
            tags_map={"m-small": ["reasoning"], "m-large": ["reasoning"]},
        )
        # Override provider to cloud for both
        for a in aliases:
            a.provider = "openai"
        result = router.select_model(["reasoning"])
        assert result == "m-large"

    def test_no_aliases_returns_none(self) -> None:
        router = _make_router([])
        assert router.select_model(["code"]) is None


# ---------------------------------------------------------------------------
# select_with_fallback
# ---------------------------------------------------------------------------


class TestSelectWithFallback:
    def test_returns_chain_starting_with_alias(self) -> None:
        aliases = [_make_alias("a"), _make_alias("b"), _make_alias("c")]
        router = _make_router(aliases, tags_map={"a": [], "b": [], "c": []})
        router._workflow_reg.get_fallback_chain.side_effect = lambda n: (
            ["b"] if n == "a" else []
        )
        chain = router.select_with_fallback("a")
        assert chain[0] == "a"
        assert "b" in chain

    def test_auto_selects_when_alias_empty(self) -> None:
        aliases = [_make_alias("m", provider="ollama")]
        router = _make_router(aliases, tags_map={"m": ["summarization"]})
        chain = router.select_with_fallback("", required_tags=["summarization"])
        assert "m" in chain

    def test_all_remaining_aliases_appended(self) -> None:
        aliases = [_make_alias("a"), _make_alias("b"), _make_alias("c")]
        router = _make_router(aliases, tags_map={"a": [], "b": [], "c": []})
        router._workflow_reg.get_fallback_chain.return_value = []
        chain = router.select_with_fallback("a")
        # a is first, b and c appended as last-resort options
        assert set(chain) == {"a", "b", "c"}

    def test_no_duplicates_in_chain(self) -> None:
        aliases = [_make_alias("a"), _make_alias("b")]
        router = _make_router(aliases, tags_map={"a": [], "b": []})
        router._workflow_reg.get_fallback_chain.return_value = ["b"]
        chain = router.select_with_fallback("a")
        assert len(chain) == len(set(chain))


# ---------------------------------------------------------------------------
# rank_candidates
# ---------------------------------------------------------------------------


class TestRankCandidates:
    def test_returns_dicts_with_required_keys(self) -> None:
        aliases = [_make_alias("m", provider="ollama")]
        router = _make_router(aliases, tags_map={"m": ["code"]})
        candidates = router.rank_candidates(["code"])
        assert len(candidates) == 1
        assert "alias" in candidates[0]
        assert "score" in candidates[0]
        assert "is_exact" in candidates[0]
        assert "is_local" in candidates[0]

    def test_exact_match_marked(self) -> None:
        aliases = [_make_alias("m")]
        router = _make_router(aliases, tags_map={"m": ["code", "reasoning"]})
        candidates = router.rank_candidates(["code", "reasoning"])
        assert candidates[0]["is_exact"] is True

    def test_partial_match_not_exact(self) -> None:
        aliases = [_make_alias("m")]
        router = _make_router(aliases, tags_map={"m": ["code"]})
        candidates = router.rank_candidates(["code", "reasoning"])
        # Only "code" matched, "reasoning" missing → partial
        assert candidates[0]["is_exact"] is False

    def test_local_alias_flagged(self) -> None:
        aliases = [_make_alias("local-m", provider="ollama")]
        router = _make_router(aliases, tags_map={"local-m": ["code"]})
        candidates = router.rank_candidates(["code"])
        assert candidates[0]["is_local"] is True

    def test_cloud_alias_not_local(self) -> None:
        aliases = [_make_alias("cloud-m", provider="openai")]
        router = _make_router(aliases, tags_map={"cloud-m": ["code"]})
        candidates = router.rank_candidates(["code"])
        assert candidates[0]["is_local"] is False


# ---------------------------------------------------------------------------
# _is_local
# ---------------------------------------------------------------------------


class TestIsLocal:
    def test_ollama_is_local(self) -> None:
        assert "ollama" in _LOCAL_PROVIDERS

    def test_openai_not_local(self) -> None:
        assert "openai" not in _LOCAL_PROVIDERS
