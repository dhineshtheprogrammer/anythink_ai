"""Built-in MMAE category definitions and tag-to-category mapping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str
    name: str
    description: str


CATEGORIES: dict[str, Category] = {
    "math": Category(
        key="math",
        name="Math / Calculations",
        description=(
            "Arithmetic, algebra, calculus, statistics, numerical reasoning, "
            "unit conversions, and any task requiring mathematical computation."
        ),
    ),
    "code": Category(
        key="code",
        name="Code / Programming",
        description=(
            "Writing code, debugging, explaining code, code review, algorithms, "
            "technical implementation, and any programming-related task."
        ),
    ),
    "writing": Category(
        key="writing",
        name="Writing / Creative",
        description=(
            "Essays, stories, emails, blog posts, copywriting, persuasive writing, "
            "creative prose, and any task requiring original written composition."
        ),
    ),
    "reasoning": Category(
        key="reasoning",
        name="Reasoning / Logic",
        description=(
            "Logical deduction, argument analysis, philosophical questions, "
            "structured thinking, and multi-step reasoning without computation."
        ),
    ),
    "research": Category(
        key="research",
        name="Research / Factual",
        description=(
            "Factual lookups, historical facts, definitions, explanations of concepts, "
            "'what is' and 'how does' questions requiring world knowledge."
        ),
    ),
    "data": Category(
        key="data",
        name="Data Analysis",
        description=(
            "Interpreting datasets, trends, statistics, charting suggestions, "
            "spreadsheet logic, and pattern identification in structured data."
        ),
    ),
    "translation": Category(
        key="translation",
        name="Translation",
        description=(
            "Translating text between languages, language detection, "
            "and multilingual paraphrasing."
        ),
    ),
    "summarization": Category(
        key="summarization",
        name="Summarization",
        description=(
            "Condensing long content, extracting key points, producing abstracts, "
            "and TL;DR requests."
        ),
    ),
    "general": Category(
        key="general",
        name="General / Conversational",
        description=(
            "Greetings, casual chat, ambiguous questions, and any question that does "
            "not clearly fit another specialist category. This is the fallback category."
        ),
    ),
}

# Maps WorkflowCapabilityRegistry tag names → MMAE category keys.
# Used by SmartRegistry.auto_populate() to seed assignments from the MMWE registry.
TAG_TO_CATEGORY: dict[str, str] = {
    "math": "math",
    "code": "code",
    "code-review": "code",
    "writing": "writing",
    "reasoning": "reasoning",
    "planning": "reasoning",
    "research": "research",
    "factual": "research",
    "extraction": "research",
    "data": "data",
    "analysis": "data",
    "translation": "translation",
    "summarization": "summarization",
    "classification": "general",
    "general": "general",
    "conversational": "general",
}

SPECIALIST_CATEGORIES: frozenset[str] = frozenset(CATEGORIES.keys()) - {"general"}
