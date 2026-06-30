"""FormatDetector — extract format instructions from user message text."""

from __future__ import annotations

import re

# Spec section 16 — format trigger keywords keyed by canonical format name
FORMAT_KEYWORDS: dict[str, list[str]] = {
    "markdown": ["markdown", "as markdown", "in markdown"],
    "list": ["bullet points", "numbered list", "as a list", "bullet list", " list ", "in a list"],
    "table": ["table", "as a table", "in a table", "comparison table"],
    "code_only": [
        "just the code",
        "code only",
        "strip explanation",
        "no explanation",
        "only the code",
    ],
    "json": ["as json", " json ", "as an object", "structured data", "in json"],
    "summary": [
        "tldr",
        "tl;dr",
        "brief",
        "summary only",
        "executive summary",
        " short ",
        "in short",
    ],
    "detailed": [
        "explain in detail",
        "in detail",
        "detailed explanation",
        "verbose",
        "full explanation",
        "step by step",
    ],
}


def detect_format(message: str) -> str | None:
    """Scan message for format trigger keywords.

    Returns a canonical format name (e.g. "markdown", "table") or None.
    Matches are checked in definition order; first match wins.
    """
    lower = " " + message.lower() + " "
    for format_name, keywords in FORMAT_KEYWORDS.items():
        for kw in keywords:
            # Use word-boundary-aware matching for short keywords
            pattern = re.escape(kw)
            if re.search(pattern, lower):
                return format_name
    return None
