"""Retrieval quality scoring and tier classification for the RAG system.

The quality model summarises how good a set of retrieved chunks is for a
given query, exposing a single ``confidence`` score and a human-readable
tier (strong / good / weak / poor).

Formula:
    confidence = 0.5 * top_score + 0.3 * avg_score + 0.2 * (1 - spread)

Tier thresholds:
    strong  ≥ 0.85
    good    ≥ 0.65
    weak    ≥ 0.45
    poor    < 0.45

``passed_threshold`` is True when ``top_score >= threshold`` — the threshold
is set by the user via ``/rag threshold`` (default 0.65).

``low_relevance_chunks`` holds indices of results that fall below 50%
relevance while at least one other result is above 70%.  These are "drag"
chunks that would reduce answer quality if injected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from anythink.rag.models import RetrievalResult

Tier = Literal["strong", "good", "weak", "poor"]

# Tier colour mapping: tier → theme colour attribute name
TIER_STYLE: dict[str, str] = {
    "strong": "success",
    "good": "accent",
    "weak": "warning",
    "poor": "error",
}

# Tier display labels (with ANSI-escape-safe Unicode characters)
TIER_LABEL: dict[str, str] = {
    "strong": "strong ✓",
    "good": "good ✓",
    "weak": "weak ⚠",
    "poor": "poor ✗",
}


@dataclass
class RetrievalQuality:
    """Quality summary for a set of retrieved chunks.

    Computed by ``compute_quality()``; attached to ``AIBubble`` after each
    RAG-assisted response and read by ``/rag quality``.
    """

    confidence: float
    top_score: float
    avg_score: float
    score_spread: float
    passed_threshold: bool
    tier: Tier
    low_relevance_chunks: list[int] = field(default_factory=list)

    # ── derived helpers ───────────────────────────────────────────────────────

    @property
    def tier_label(self) -> str:
        return TIER_LABEL.get(self.tier, self.tier)

    @property
    def tier_style(self) -> str:
        return TIER_STYLE.get(self.tier, "muted")

    def summary_line(self, n_sources: int) -> str:
        """One-line footer text shown in the AIBubble."""
        icon = "📚"
        s = "s" if n_sources != 1 else ""
        return (
            f"{icon} {n_sources} source{s}  ·  "
            f"Confidence: {self.confidence:.0%}  ·  "
            f"[{self.tier_label}]"
        )


def compute_quality(
    results: list[RetrievalResult],
    threshold: float = 0.65,
) -> RetrievalQuality:
    """Compute retrieval quality for *results* against *threshold*.

    Args:
        results:   Retrieved chunks (any relevance, in ranked order).
        threshold: Minimum relevance for a chunk to count as a successful
                   match.  Typically ``config.rag_threshold``.

    Returns:
        A fully populated :class:`RetrievalQuality` instance.
    """
    if not results:
        return RetrievalQuality(
            confidence=0.0,
            top_score=0.0,
            avg_score=0.0,
            score_spread=0.0,
            passed_threshold=False,
            tier="poor",
        )

    scores = [r.relevance for r in results]
    top_score = max(scores)
    avg_score = sum(scores) / len(scores)
    spread = max(scores) - min(scores) if len(scores) > 1 else 0.0

    confidence = 0.5 * top_score + 0.3 * avg_score + 0.2 * (1.0 - spread)
    confidence = round(min(1.0, max(0.0, confidence)), 4)

    if confidence >= 0.85:
        tier: Tier = "strong"
    elif confidence >= 0.65:
        tier = "good"
    elif confidence >= 0.45:
        tier = "weak"
    else:
        tier = "poor"

    # Chunks with unusually low relevance while others are strong
    any_high = any(s > 0.70 for s in scores)
    low_relevance_chunks = [
        i for i, r in enumerate(results) if r.relevance < 0.50 and any_high
    ]

    return RetrievalQuality(
        confidence=confidence,
        top_score=round(top_score, 4),
        avg_score=round(avg_score, 4),
        score_spread=round(spread, 4),
        passed_threshold=top_score >= threshold,
        tier=tier,
        low_relevance_chunks=low_relevance_chunks,
    )
