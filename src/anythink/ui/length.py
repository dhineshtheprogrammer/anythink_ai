"""Response length indicator: word count + category symbol for AI response bubbles."""

from __future__ import annotations

# Length categories from the V2 spec (Section 5.2)
_THRESHOLDS: list[tuple[int, str]] = [
    (80, "·"),
    (250, "··"),
    (600, "···"),
    (1200, "✦"),
]
_SYMBOL_LONG_PLUS = "✦✦"


def length_indicator(text: str) -> tuple[int, str]:
    """Return *(word_count, symbol)* for *text*.

    Categories:
        ``·``    1 – 80 words   (Brief)
        ``··``   81 – 250       (Short)
        ``···``  251 – 600      (Medium)
        ``✦``    601 – 1,200    (Long)
        ``✦✦``   1,201+         (Very Long)
    """
    word_count = len(text.split())
    for threshold, symbol in _THRESHOLDS:
        if word_count <= threshold:
            return word_count, symbol
    return word_count, _SYMBOL_LONG_PLUS
