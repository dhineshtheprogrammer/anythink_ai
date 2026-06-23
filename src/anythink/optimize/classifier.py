"""Intent classifier — zero-latency keyword-based query classification."""

from __future__ import annotations

import re

from anythink.optimize.models import QueryIntent

# ── Category keyword sets ─────────────────────────────────────────────────────

CODING_PATTERNS: frozenset[str] = frozenset(
    {
        "function",
        "class",
        "def ",
        "import ",
        "bug",
        "error",
        "exception",
        "debug",
        "code",
        "script",
        "algorithm",
        "implement",
        "syntax",
        "compile",
        "runtime",
        "api",
        "endpoint",
        "refactor",
        "unittest",
        "test case",
        "loop",
        "array",
        "dictionary",
        "list comprehension",
        "lambda",
        "async",
        "await",
        "decorator",
        "module",
        "package",
        "library",
        "framework",
        "sql",
        "query",
        "database",
        "git",
        "dockerfile",
        "kubernetes",
        "regex",
        "parse",
        "serialize",
        "json",
        "xml",
        "html",
        "css",
        "javascript",
        "python",
        "typescript",
        "rust",
        "golang",
        "java",
        "c++",
        "bash",
        "shell script",
    }
)

RESEARCH_PATTERNS: frozenset[str] = frozenset(
    {
        "comprehensive",
        "detailed",
        "in-depth",
        "full implementation",
        "architecture",
        "system design",
        "compare all",
        "list all",
        "step-by-step plan",
        "overview of",
        "survey",
        "research",
        "explain everything",
        "complete guide",
        "deep dive",
        "thorough",
        "exhaustive",
        "all aspects",
        "best practices",
        "trade-offs",
        "tradeoffs",
        "pros and cons of all",
    }
)

CREATIVE_PATTERNS: frozenset[str] = frozenset(
    {
        "write a story",
        "write a poem",
        "poem",
        "story",
        "imagine",
        "creative",
        "fiction",
        "narrative",
        "character",
        "plot",
        "dialogue",
        "write a song",
        "lyrics",
        "essay",
        "write about",
        "compose",
        "invent",
        "brainstorm",
        "generate ideas",
        "metaphor",
        "analogy",
    }
)

FACTUAL_PATTERNS: frozenset[str] = frozenset(
    {
        "what is",
        "what are",
        "who is",
        "who was",
        "when did",
        "where is",
        "where was",
        "how many",
        "define ",
        "definition of",
        "meaning of",
        "fact",
        "history of",
        "origin of",
        "founded",
        "invented",
        "discovered",
        "capital of",
        "population of",
    }
)

REASONING_PATTERNS: frozenset[str] = frozenset(
    {
        "compare",
        "pros and cons",
        "evaluate",
        "which is better",
        "should i",
        "what would happen if",
        "analyse",
        "analyze",
        "assess",
        "judge",
        "recommend",
        "weigh",
        "decision",
        "trade-off",
        "tradeoff",
        "versus",
        " vs ",
        "advantage",
        "disadvantage",
        "critique",
        "review",
        "justify",
        "reasoning",
        "logical",
    }
)

MATH_PATTERNS: frozenset[str] = frozenset(
    {
        "calculate",
        "solve",
        "equation",
        "formula",
        "proof",
        "derivative",
        "integral",
        "matrix",
        "probability",
        "statistics",
        "theorem",
        "algebra",
        "calculus",
        "geometry",
        "trigonometry",
        "math",
        "maths",
        "arithmetic",
        "percentage",
        "ratio",
    }
)

# ── Plan Mode trigger phrases ─────────────────────────────────────────────────

_PLAN_TRIGGER_PHRASES: frozenset[str] = frozenset(
    {
        "detailed",
        "comprehensive",
        "full implementation",
        "architecture",
        "system design",
        "step-by-step plan",
        "complete guide",
        "in-depth",
        "deep dive",
        "exhaustive",
        "build a full",
        "design a",
        "walk me through",
        "explain in detail",
        "research",
        "compare all",
        "list all",
    }
)

_PLAN_TOKEN_THRESHOLD = 300  # tokens; below this, plan mode is rarely useful
_PLAN_CONTEXT_RATIO = 0.6   # if estimated tokens > 60% of model context → plan


# ── Override flag parser ──────────────────────────────────────────────────────

_FLAG_PATTERN = re.compile(
    r"--(?P<flag>model|strategy|speed|quality|no-plan)\s*(?P<value>[^\s-][^\s]*)?",
    re.IGNORECASE,
)


class IntentClassifier:
    """Zero-latency deterministic query classifier.

    Makes no model calls; uses keyword matching and heuristics only.
    """

    def classify(self, text: str) -> QueryIntent:
        """Classify *text* into a QueryIntent using keyword heuristics."""
        lower = text.lower()
        category = self._detect_category(lower)
        return QueryIntent(
            category=category,
            format_preference=self._detect_format(lower),
            priority_override=None,
            from_user=False,
        )

    def _detect_category(self, lower: str) -> str:
        scores: dict[str, int] = {
            "Coding": 0,
            "Research": 0,
            "Creative": 0,
            "Factual": 0,
            "Reasoning": 0,
            "Math": 0,
        }

        for pattern in CODING_PATTERNS:
            if pattern in lower:
                scores["Coding"] += 1
        for pattern in RESEARCH_PATTERNS:
            if pattern in lower:
                scores["Research"] += 2  # weight higher — research always benefits from planning
        for pattern in CREATIVE_PATTERNS:
            if pattern in lower:
                scores["Creative"] += 2
        for pattern in FACTUAL_PATTERNS:
            if pattern in lower:
                scores["Factual"] += 1
        for pattern in REASONING_PATTERNS:
            if pattern in lower:
                scores["Reasoning"] += 1
        for pattern in MATH_PATTERNS:
            if pattern in lower:
                scores["Math"] += 2

        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return "Other"
        return best

    def _detect_format(self, lower: str) -> str:
        if any(kw in lower for kw in ("step by step", "step-by-step", "walk me through")):
            return "step_by_step"
        if any(kw in lower for kw in ("bullet", "list", "enumerate", "outline")):
            return "bullet"
        if any(kw in lower for kw in ("code only", "just the code", "show me the code")):
            return "code_only"
        if any(kw in lower for kw in ("brief", "short", "quick", "summarize", "tldr")):
            return "concise"
        return "detailed"

    def estimate_tokens(self, text: str) -> int:
        """Rough token count heuristic: ~4 chars per token."""
        return max(1, len(text) // 4)

    def should_trigger_plan_mode(
        self,
        text: str,
        token_estimate: int,
        model_context: int,
    ) -> bool:
        """Return True if this query should activate Plan Mode."""
        lower = text.lower()

        # Explicit plan triggers via phrases
        for phrase in _PLAN_TRIGGER_PHRASES:
            if phrase in lower:
                return True

        # Token-based: query alone consumes a large fraction of model context
        exceeds_ratio = token_estimate > model_context * _PLAN_CONTEXT_RATIO
        return token_estimate > _PLAN_TOKEN_THRESHOLD and exceeds_ratio

    def extract_override_flags(self, text: str) -> tuple[str, dict[str, str]]:
        """Parse --flag [value] tokens from *text*.

        Returns (clean_text, flags_dict) where clean_text has all flag tokens
        stripped and flags_dict contains the parsed overrides.
        """
        flags: dict[str, str] = {}
        clean = text

        for match in _FLAG_PATTERN.finditer(text):
            flag = match.group("flag").lower()
            value = (match.group("value") or "").strip()

            if flag == "model":
                flags["model"] = value
            elif flag == "strategy":
                flags["strategy"] = value
            elif flag == "speed":
                flags["priority"] = "speed"
            elif flag == "quality":
                flags["priority"] = "quality"
            elif flag == "no-plan":
                flags["no_plan"] = "true"

            # Strip the matched token from clean text
            clean = clean.replace(match.group(0), "")

        return clean.strip(), flags
