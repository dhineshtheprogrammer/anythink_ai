"""Tests for the response length indicator (word count + symbol)."""

from __future__ import annotations

import pytest

from anythink.ui.length import length_indicator


def _words(n: int) -> str:
    """Return a string with exactly *n* words."""
    return " ".join(["word"] * n)


class TestLengthBoundaries:
    """Verify exact category boundaries from the V2 spec (Section 5.2)."""

    def test_1_word_is_brief(self) -> None:
        count, symbol = length_indicator(_words(1))
        assert count == 1
        assert symbol == "·"

    def test_80_words_is_brief(self) -> None:
        count, symbol = length_indicator(_words(80))
        assert count == 80
        assert symbol == "·"

    def test_81_words_is_short(self) -> None:
        count, symbol = length_indicator(_words(81))
        assert count == 81
        assert symbol == "··"

    def test_250_words_is_short(self) -> None:
        count, symbol = length_indicator(_words(250))
        assert count == 250
        assert symbol == "··"

    def test_251_words_is_medium(self) -> None:
        count, symbol = length_indicator(_words(251))
        assert count == 251
        assert symbol == "···"

    def test_600_words_is_medium(self) -> None:
        count, symbol = length_indicator(_words(600))
        assert count == 600
        assert symbol == "···"

    def test_601_words_is_long(self) -> None:
        count, symbol = length_indicator(_words(601))
        assert count == 601
        assert symbol == "✦"

    def test_1200_words_is_long(self) -> None:
        count, symbol = length_indicator(_words(1200))
        assert count == 1200
        assert symbol == "✦"

    def test_1201_words_is_very_long(self) -> None:
        count, symbol = length_indicator(_words(1201))
        assert count == 1201
        assert symbol == "✦✦"

    def test_large_count_is_very_long(self) -> None:
        count, symbol = length_indicator(_words(5000))
        assert count == 5000
        assert symbol == "✦✦"


class TestLengthEdgeCases:
    def test_empty_string(self) -> None:
        count, symbol = length_indicator("")
        assert count == 0
        assert symbol == "·"

    def test_whitespace_only(self) -> None:
        count, symbol = length_indicator("   \n\t  ")
        assert count == 0
        assert symbol == "·"

    def test_real_text(self) -> None:
        text = "The quick brown fox jumps over the lazy dog"
        count, symbol = length_indicator(text)
        assert count == 9
        assert symbol == "·"

    def test_returns_tuple_of_two(self) -> None:
        result = length_indicator("hello world")
        assert len(result) == 2

    def test_word_count_is_int(self) -> None:
        count, _ = length_indicator("one two three")
        assert isinstance(count, int)

    def test_symbol_is_str(self) -> None:
        _, symbol = length_indicator("one two three")
        assert isinstance(symbol, str)
