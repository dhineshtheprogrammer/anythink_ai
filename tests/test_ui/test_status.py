"""Tests for ui/status.py."""

from __future__ import annotations

from rich.text import Text

from anythink.ui.status import ContextStatusBar
from anythink.ui.theme import MIDNIGHT


def _bar(used: int, max_tokens: int = 1000, bar_width: int = 20) -> Text:
    return ContextStatusBar(theme=MIDNIGHT, max_tokens=max_tokens, bar_width=bar_width).render(used)


def _color(used: int, max_tokens: int = 1000) -> str:
    """Return the style string applied to the first span."""
    t = _bar(used, max_tokens)
    return str(t._spans[0].style)  # type: ignore[union-attr]


class TestContextStatusBarRender:
    def test_returns_text_instance(self) -> None:
        assert isinstance(_bar(0), Text)

    def test_output_contains_percentage(self) -> None:
        text = _bar(500).plain
        assert "50%" in text

    def test_output_contains_used_tokens(self) -> None:
        text = _bar(750).plain
        assert "750" in text

    def test_output_contains_max_tokens(self) -> None:
        text = _bar(100, max_tokens=2000).plain
        assert "2,000" in text

    def test_zero_usage_green(self) -> None:
        assert _color(0) == MIDNIGHT.success

    def test_59_pct_green(self) -> None:
        assert _color(590) == MIDNIGHT.success

    def test_60_pct_yellow(self) -> None:
        assert _color(600) == MIDNIGHT.warning

    def test_84_pct_yellow(self) -> None:
        assert _color(840) == MIDNIGHT.warning

    def test_85_pct_red(self) -> None:
        assert _color(850) == MIDNIGHT.error

    def test_94_pct_red(self) -> None:
        assert _color(940) == MIDNIGHT.error

    def test_95_pct_bold_red(self) -> None:
        assert _color(950) == "bold red"

    def test_100_pct_bold_red(self) -> None:
        assert _color(1000) == "bold red"

    def test_max_tokens_zero_no_division_error(self) -> None:
        text = ContextStatusBar(theme=MIDNIGHT, max_tokens=0).render(0)
        assert isinstance(text, Text)

    def test_bar_all_empty_at_zero(self) -> None:
        plain = _bar(0, bar_width=10).plain
        assert "░░░░░░░░░░" in plain

    def test_bar_all_filled_at_100_pct(self) -> None:
        plain = _bar(1000, bar_width=10).plain
        assert "██████████" in plain

    def test_custom_bar_width(self) -> None:
        plain = _bar(0, bar_width=5).plain
        # bar should show 5 empty chars + brackets
        assert "░░░░░" in plain
