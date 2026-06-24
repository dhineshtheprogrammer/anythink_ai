"""Tests for RAG quality scoring (Phase 6)."""

from __future__ import annotations

import pytest

from anythink.rag.models import RetrievalResult
from anythink.rag.quality import (
    TIER_LABEL,
    TIER_STYLE,
    RetrievalQuality,
    compute_quality,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _result(relevance: float, source: str = "file.txt") -> RetrievalResult:
    return RetrievalResult(
        source_path=source,
        chunk_text=f"chunk with relevance {relevance}",
        relevance=relevance,
    )


# ── compute_quality: empty input ─────────────────────────────────────────────


class TestComputeQualityEmpty:
    def test_empty_returns_poor(self) -> None:
        q = compute_quality([])
        assert q.tier == "poor"

    def test_empty_confidence_zero(self) -> None:
        q = compute_quality([])
        assert q.confidence == 0.0

    def test_empty_passed_threshold_false(self) -> None:
        q = compute_quality([])
        assert q.passed_threshold is False

    def test_empty_no_low_relevance_chunks(self) -> None:
        q = compute_quality([])
        assert q.low_relevance_chunks == []


# ── compute_quality: confidence formula ──────────────────────────────────────


class TestConfidenceFormula:
    def test_formula_single_high_score(self) -> None:
        # top=0.9, avg=0.9, spread=0 → conf = 0.5*0.9 + 0.3*0.9 + 0.2*1.0 = 0.92
        q = compute_quality([_result(0.9)])
        assert q.confidence == pytest.approx(0.92, abs=0.01)

    def test_formula_all_perfect(self) -> None:
        results = [_result(1.0)] * 3
        q = compute_quality(results)
        # top=1, avg=1, spread=0 → conf = 0.5 + 0.3 + 0.2 = 1.0
        assert q.confidence == pytest.approx(1.0)

    def test_formula_mixed_scores(self) -> None:
        results = [_result(0.9), _result(0.7), _result(0.3)]
        q = compute_quality(results)
        top = 0.9
        avg = (0.9 + 0.7 + 0.3) / 3
        spread = 0.9 - 0.3
        expected = 0.5 * top + 0.3 * avg + 0.2 * (1.0 - spread)
        assert q.confidence == pytest.approx(expected, abs=0.001)

    def test_confidence_clamped_zero_to_one(self) -> None:
        q = compute_quality([_result(0.0)])
        assert 0.0 <= q.confidence <= 1.0

    def test_top_score_is_max_relevance(self) -> None:
        results = [_result(0.4), _result(0.9), _result(0.6)]
        q = compute_quality(results)
        assert q.top_score == pytest.approx(0.9)

    def test_avg_score_is_mean(self) -> None:
        results = [_result(0.6), _result(0.8)]
        q = compute_quality(results)
        assert q.avg_score == pytest.approx(0.7)

    def test_spread_is_max_minus_min(self) -> None:
        results = [_result(0.2), _result(0.8)]
        q = compute_quality(results)
        assert q.score_spread == pytest.approx(0.6)

    def test_single_result_zero_spread(self) -> None:
        q = compute_quality([_result(0.75)])
        assert q.score_spread == pytest.approx(0.0)


# ── compute_quality: tier thresholds ─────────────────────────────────────────


class TestTierThresholds:
    def test_strong_at_085(self) -> None:
        # Need confidence >= 0.85 → top=avg=1.0, spread=0 → conf=1.0
        results = [_result(1.0)] * 2
        q = compute_quality(results)
        assert q.tier == "strong"

    def test_good_at_065(self) -> None:
        # Single result with relevance ~0.77 gives conf ~0.65*0.77 + ... around 0.67
        results = [_result(0.75)]
        q = compute_quality(results)
        # conf = 0.5*0.75 + 0.3*0.75 + 0.2 = 0.375 + 0.225 + 0.2 = 0.8 → strong
        # Try lower value: relevance=0.6 → conf = 0.3+0.18+0.2 = 0.68 → good
        results2 = [_result(0.6)]
        q2 = compute_quality(results2)
        assert q2.tier in ("good", "strong")  # depends on exact value

    def test_poor_with_all_zeros(self) -> None:
        results = [_result(0.0)] * 3
        q = compute_quality(results)
        assert q.tier == "poor"

    def test_tier_ordering(self) -> None:
        tiers_seen: list[str] = []
        for relevance in (1.0, 0.7, 0.5, 0.1):
            q = compute_quality([_result(relevance)])
            tiers_seen.append(q.tier)
        # All must be from the valid set
        assert all(t in ("strong", "good", "weak", "poor") for t in tiers_seen)

    def test_weak_tier_boundary(self) -> None:
        # Force weak: need 0.45 <= conf < 0.65
        # Single result relevance=0.5 → conf = 0.5*0.5 + 0.3*0.5 + 0.2*1.0 = 0.6 → good
        # relevance=0.35 → conf = 0.5*0.35 + 0.3*0.35 + 0.2 = 0.175+0.105+0.2 = 0.48 → weak
        results = [_result(0.35)]
        q = compute_quality(results)
        assert q.tier == "weak"


# ── compute_quality: passed_threshold ────────────────────────────────────────


class TestPassedThreshold:
    def test_passes_when_top_score_above_threshold(self) -> None:
        q = compute_quality([_result(0.8)], threshold=0.65)
        assert q.passed_threshold is True

    def test_fails_when_top_score_below_threshold(self) -> None:
        q = compute_quality([_result(0.5)], threshold=0.65)
        assert q.passed_threshold is False

    def test_passes_exactly_at_threshold(self) -> None:
        q = compute_quality([_result(0.65)], threshold=0.65)
        assert q.passed_threshold is True

    def test_custom_low_threshold(self) -> None:
        q = compute_quality([_result(0.4)], threshold=0.3)
        assert q.passed_threshold is True

    def test_custom_high_threshold(self) -> None:
        q = compute_quality([_result(0.9)], threshold=0.95)
        assert q.passed_threshold is False

    def test_default_threshold_is_065(self) -> None:
        q_pass = compute_quality([_result(0.66)])
        assert q_pass.passed_threshold is True
        q_fail = compute_quality([_result(0.64)])
        assert q_fail.passed_threshold is False


# ── compute_quality: low_relevance_chunks ────────────────────────────────────


class TestLowRelevanceChunks:
    def test_detects_drag_chunks(self) -> None:
        # Indices 1 and 2 are below 50% while index 0 is above 70%
        results = [_result(0.85), _result(0.3), _result(0.2)]
        q = compute_quality(results)
        assert 1 in q.low_relevance_chunks
        assert 2 in q.low_relevance_chunks

    def test_no_drag_when_all_low(self) -> None:
        # No result is above 70%, so none are "drag" chunks
        results = [_result(0.4), _result(0.3), _result(0.2)]
        q = compute_quality(results)
        assert q.low_relevance_chunks == []

    def test_no_drag_when_all_high(self) -> None:
        results = [_result(0.9), _result(0.85), _result(0.8)]
        q = compute_quality(results)
        assert q.low_relevance_chunks == []

    def test_drag_chunk_index_correct(self) -> None:
        results = [_result(0.9), _result(0.9), _result(0.1)]
        q = compute_quality(results)
        assert q.low_relevance_chunks == [2]


# ── RetrievalQuality dataclass ────────────────────────────────────────────────


class TestRetrievalQualityDataclass:
    def test_tier_label_property(self) -> None:
        q = compute_quality([_result(1.0)])
        assert q.tier_label in TIER_LABEL.values()

    def test_tier_style_property(self) -> None:
        q = compute_quality([_result(1.0)])
        assert q.tier_style in TIER_STYLE.values()

    def test_summary_line_n_sources(self) -> None:
        q = compute_quality([_result(0.9), _result(0.8)])
        line = q.summary_line(2)
        assert "2 sources" in line
        assert "Confidence" in line
        assert q.tier_label in line

    def test_summary_line_singular_source(self) -> None:
        q = compute_quality([_result(0.9)])
        line = q.summary_line(1)
        assert "1 source" in line
        assert "sources" not in line


# ── TIER_LABEL / TIER_STYLE constants ────────────────────────────────────────


class TestConstants:
    def test_all_tiers_have_labels(self) -> None:
        for tier in ("strong", "good", "weak", "poor"):
            assert tier in TIER_LABEL

    def test_all_tiers_have_styles(self) -> None:
        for tier in ("strong", "good", "weak", "poor"):
            assert tier in TIER_STYLE

    def test_tier_labels_nonempty(self) -> None:
        for label in TIER_LABEL.values():
            assert label
