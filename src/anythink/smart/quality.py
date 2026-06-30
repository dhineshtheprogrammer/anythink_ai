"""QualityGate — heuristic evaluation of specialist responses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Category keys that should produce code blocks in their responses
_CODE_CATEGORIES: frozenset[str] = frozenset({"code", "data", "math"})

# Phrases that indicate a model is refusing to answer
_REFUSAL_PATTERNS: list[str] = [
    r"i (can't|cannot|am unable to|don't know how to)",
    r"i (don't|do not) have (the |)information",
    r"i'm (not sure|unsure|unable)",
    r"as an ai",
    r"i (apologize|apologise)",
    r"i (am not able|am not capable)",
    r"that('s| is) (outside|beyond) (my|the scope)",
    r"i don't (understand|comprehend) the question",
    r"please (clarify|provide more|rephrase)",
]
_REFUSAL_RE = re.compile("|".join(_REFUSAL_PATTERNS), re.IGNORECASE)

# Patterns that suggest truncation / mid-sentence cutoff
_TRUNCATION_PATTERNS: list[str] = [
    r"\.{3}$",  # ends with "..."
    r"\s+and\s*$",  # ends with "and"
    r",\s*$",  # ends with comma
    r"\s+(the|a|an|is|are|was|were|to|for|of|in|on|at|by)\s*$",  # ends with connector word
]
_TRUNCATION_RE = re.compile("|".join(_TRUNCATION_PATTERNS))


@dataclass
class QualityCheckResult:
    """Composite quality evaluation for one specialist response."""

    score: int  # 0–100 weighted composite
    length_score: int  # 0–20
    nonrefusal_score: int  # 0–30
    coherence_score: int  # 0–30
    completion_score: int  # 0–20
    passed: bool
    checks_detail: dict[str, str] = field(default_factory=dict)


class QualityGate:
    """Evaluates specialist responses with four heuristic checks.

    Composite score = length(20%) + non-refusal(30%) + coherence(30%) + completion(20%).
    Responses at or above the threshold pass; below triggers retry logic.
    """

    def __init__(self, threshold: int = 50) -> None:
        self._threshold = max(0, min(100, threshold))

    @property
    def threshold(self) -> int:
        return self._threshold

    def set_threshold(self, value: int) -> None:
        self._threshold = max(0, min(100, value))

    def evaluate(
        self,
        response: str,
        category: str,
        sub_question: str,
    ) -> QualityCheckResult:
        """Score a specialist response against the four quality heuristics."""
        length_score = self._check_length(response, sub_question)
        nonrefusal_score = self._check_nonrefusal(response)
        coherence_score = self._check_coherence(response, category)
        completion_score = self._check_completion(response)

        score = length_score + nonrefusal_score + coherence_score + completion_score

        return QualityCheckResult(
            score=score,
            length_score=length_score,
            nonrefusal_score=nonrefusal_score,
            coherence_score=coherence_score,
            completion_score=completion_score,
            passed=score >= self._threshold,
            checks_detail={
                "length": f"{length_score}/20",
                "nonrefusal": f"{nonrefusal_score}/30",
                "coherence": f"{coherence_score}/30",
                "completion": f"{completion_score}/20",
            },
        )

    # ------------------------------------------------------------------
    # Individual checks (weights match spec section 12.2)
    # ------------------------------------------------------------------

    def _check_length(self, response: str, sub_question: str) -> int:
        """Length check — max 20 points.

        Short, simple questions deserve short answers; complex questions need more.
        We estimate minimum expected length from the sub-question word count.
        """
        if not response.strip():
            return 0
        q_words = len(sub_question.split())
        # Heuristic: expect at least 10 words per question word, capped at 60 words minimum
        min_words = min(60, max(15, q_words * 3))
        resp_words = len(response.split())
        ratio = resp_words / min_words
        if ratio >= 1.0:
            return 20
        elif ratio >= 0.6:
            return 14
        elif ratio >= 0.3:
            return 8
        else:
            return 2

    def _check_nonrefusal(self, response: str) -> int:
        """Non-refusal check — max 30 points.

        A response that refuses or only acknowledges the question scores 0.
        """
        if not response.strip():
            return 0
        if _REFUSAL_RE.search(response[:300]):
            # Partial credit if the model refuses but still provides *some* content
            if len(response.split()) > 30:
                return 10
            return 0
        return 30

    def _check_coherence(self, response: str, category: str) -> int:
        """Category coherence check — max 30 points.

        For code/data/math categories, presence of code blocks is a strong signal.
        For writing/summarization/translation, prose length matters.
        For reasoning/research/general, basic coherence (sentence count) matters.
        """
        if not response.strip():
            return 0

        if category in _CODE_CATEGORIES:
            has_code_block = bool(re.search(r"```[\s\S]*?```|`[^`]+`", response))
            has_formula = bool(re.search(r"[\d\+\-\*\/\=\^\(\)]{3,}", response))
            if has_code_block:
                return 30
            if has_formula:
                return 22
            # Prose-only answer for a code/math question
            return 10

        sentences = [s.strip() for s in re.split(r"[.!?]+", response) if s.strip()]
        if len(sentences) >= 3:
            return 30
        if len(sentences) == 2:
            return 22
        if len(sentences) == 1:
            return 14
        return 5

    def _check_completion(self, response: str) -> int:
        """Completion signal check — max 20 points.

        A response that appears truncated (mid-sentence or known truncation markers)
        loses points.
        """
        if not response.strip():
            return 0
        # Check the last 100 characters for truncation signals
        tail = response.rstrip()[-100:]
        if _TRUNCATION_RE.search(tail):
            return 5
        # Natural endings: sentence-ending punctuation or closing markdown
        if re.search(r"[.!?:)\]}\"`]$", tail):
            return 20
        return 14
