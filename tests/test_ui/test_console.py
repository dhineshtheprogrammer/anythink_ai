"""Tests for ui/console.py."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from anythink.ui.console import make_console
from anythink.ui.theme import ARCTIC, AURORA, EMBER, MIDNIGHT


class TestMakeConsole:
    def test_returns_console_instance(self) -> None:
        console = make_console(MIDNIGHT)
        assert isinstance(console, Console)

    def test_with_file_captures_output(self) -> None:
        buf = StringIO()
        console = make_console(MIDNIGHT, file=buf)
        console.print("hello world")
        assert "hello world" in buf.getvalue()

    def test_theme_styles_registered(self) -> None:
        console = make_console(MIDNIGHT)
        for key in (
            "anythink.primary",
            "anythink.secondary",
            "anythink.accent",
            "anythink.muted",
            "anythink.error",
            "anythink.warning",
            "anythink.success",
        ):
            assert console._theme_stack.get(key) is not None, f"Missing style: {key}"

    def test_different_themes_produce_different_primaries(self) -> None:
        c1 = make_console(MIDNIGHT)
        c2 = make_console(EMBER)
        assert str(c1._theme_stack.get("anythink.primary")) != str(
            c2._theme_stack.get("anythink.primary")
        )

    def test_markup_enabled(self) -> None:
        buf = StringIO()
        console = make_console(MIDNIGHT, file=buf)
        # markup=True: [bold] tags are processed, not printed literally
        console.print("[bold]hi[/bold]")
        output = buf.getvalue()
        assert "hi" in output
        assert "[bold]" not in output

    def test_all_themes_produce_console(self) -> None:
        for theme in (MIDNIGHT, AURORA, EMBER, ARCTIC):
            console = make_console(theme)
            assert isinstance(console, Console)
