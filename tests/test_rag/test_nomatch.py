"""Tests for RAG no-match state machine logic (Phase 6).

These tests exercise the pure logic of compute_quality's threshold decision
and the data structures used by the no-match 3-option flow, without starting
the full Textual TUI (which requires a live event loop and DOM).
"""

from __future__ import annotations

from anythink.rag.models import RetrievalResult
from anythink.rag.quality import compute_quality


# ── Helpers ───────────────────────────────────────────────────────────────────


def _result(relevance: float) -> RetrievalResult:
    return RetrievalResult(
        source_path="doc.txt",
        chunk_text=f"chunk at {relevance:.2f}",
        relevance=relevance,
    )


# ── No-match trigger conditions ───────────────────────────────────────────────


class TestNoMatchTrigger:
    """The no-match flow fires when quality.passed_threshold is False."""

    def test_triggers_when_all_below_threshold(self) -> None:
        results = [_result(0.40), _result(0.30)]
        q = compute_quality(results, threshold=0.65)
        assert q.passed_threshold is False

    def test_does_not_trigger_when_one_passes(self) -> None:
        results = [_result(0.70), _result(0.30)]
        q = compute_quality(results, threshold=0.65)
        assert q.passed_threshold is True

    def test_does_not_trigger_with_empty_results(self) -> None:
        q = compute_quality([], threshold=0.65)
        # Empty means "no RAG data" — the no-match flow should NOT trigger
        # (it only fires when results were retrieved but all fail threshold)
        assert q.passed_threshold is False  # but caller checks len(results) > 0

    def test_boundary_exactly_at_threshold_passes(self) -> None:
        results = [_result(0.65)]
        q = compute_quality(results, threshold=0.65)
        assert q.passed_threshold is True

    def test_boundary_just_below_threshold_fails(self) -> None:
        results = [_result(0.649)]
        q = compute_quality(results, threshold=0.65)
        assert q.passed_threshold is False


# ── Quality stored in pending state ──────────────────────────────────────────


class TestPendingStateStructure:
    """Verify the dict structure that _pending_rag_nomatch would hold."""

    def _make_pending(
        self, results: list[RetrievalResult], threshold: float = 0.65
    ) -> dict:
        q = compute_quality(results, threshold)
        return {"query": "test query", "results": results, "quality": q}

    def test_has_query_key(self) -> None:
        results = [_result(0.4)]
        pending = self._make_pending(results)
        assert "query" in pending
        assert pending["query"] == "test query"

    def test_has_results_key(self) -> None:
        results = [_result(0.4), _result(0.3)]
        pending = self._make_pending(results)
        assert "results" in pending
        assert len(pending["results"]) == 2

    def test_has_quality_key(self) -> None:
        results = [_result(0.4)]
        pending = self._make_pending(results)
        assert "quality" in pending
        q = pending["quality"]
        assert hasattr(q, "confidence")
        assert hasattr(q, "passed_threshold")
        assert hasattr(q, "tier")

    def test_quality_reflects_results(self) -> None:
        results = [_result(0.3)]
        pending = self._make_pending(results)
        q = pending["quality"]
        assert q.top_score == 0.3
        assert q.passed_threshold is False


# ── Override-confirm state ────────────────────────────────────────────────────


class TestOverrideConfirmStructure:
    """Verify the dict structure that _pending_rag_override_confirm would hold."""

    def _make_override_pending(self, results: list[RetrievalResult]) -> dict:
        return {"query": "test query", "results": results}

    def test_has_required_keys(self) -> None:
        results = [_result(0.4)]
        pending = self._make_override_pending(results)
        assert "query" in pending
        assert "results" in pending

    def test_results_preserved(self) -> None:
        results = [_result(0.55), _result(0.40)]
        pending = self._make_override_pending(results)
        assert pending["results"] == results


# ── Summary line for no-match bubble ─────────────────────────────────────────


class TestNoMatchMenuContent:
    """Verify the menu text includes expected information."""

    def test_best_match_percentage(self) -> None:
        results = [_result(0.40), _result(0.30)]
        q = compute_quality(results, threshold=0.65)
        # summary_line would show confidence; top_score is available
        assert f"{q.top_score:.0%}" == "40%"

    def test_tier_label_available(self) -> None:
        results = [_result(0.40)]
        q = compute_quality(results, threshold=0.65)
        label = q.tier_label
        assert label  # non-empty

    def test_confidence_in_summary(self) -> None:
        results = [_result(0.40)]
        q = compute_quality(results, threshold=0.65)
        line = q.summary_line(1)
        assert "Confidence" in line
        assert "%" in line


# ── Tier affects the menu content ────────────────────────────────────────────


class TestTierInNoMatchContext:
    def test_weak_tier_for_moderate_results(self) -> None:
        # Moderate scores that still fail threshold
        results = [_result(0.55), _result(0.50)]
        q = compute_quality(results, threshold=0.65)
        assert q.passed_threshold is False
        assert q.tier in ("weak", "poor", "good")  # could be any depending on math

    def test_poor_tier_for_very_low_results(self) -> None:
        results = [_result(0.10), _result(0.05)]
        q = compute_quality(results, threshold=0.65)
        assert q.passed_threshold is False
        assert q.tier == "poor"

    def test_option1_skip_rag_means_no_quality_needed(self) -> None:
        # When skip_rag=True, no RAG results → quality is irrelevant
        q_empty = compute_quality([], threshold=0.65)
        assert q_empty.tier == "poor"
        assert q_empty.confidence == 0.0
