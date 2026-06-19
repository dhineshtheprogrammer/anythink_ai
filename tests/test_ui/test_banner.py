"""Tests for ui/banner.py."""

from __future__ import annotations

from io import StringIO

from anythink.ui.banner import print_banner
from anythink.ui.console import make_console
from anythink.ui.theme import MIDNIGHT, AURORA


def _captured_banner(version: str, theme=MIDNIGHT) -> str:
    buf = StringIO()
    console = make_console(theme, file=buf)
    print_banner(console, theme, version)
    return buf.getvalue()


class TestPrintBanner:
    def test_version_in_output(self) -> None:
        output = _captured_banner("1.2.3")
        assert "1.2.3" in output

    def test_tagline_in_output(self) -> None:
        output = _captured_banner("0.1.0")
        assert "Think anything" in output

    def test_trailing_blank_line(self) -> None:
        output = _captured_banner("0.1.0")
        assert output.endswith("\n\n")

    def test_works_with_different_themes(self) -> None:
        output = _captured_banner("2.0.0", theme=AURORA)
        assert "2.0.0" in output

    def test_different_versions_reflected(self) -> None:
        out1 = _captured_banner("0.1.0")
        out2 = _captured_banner("9.9.9")
        assert "0.1.0" in out1
        assert "9.9.9" in out2
        assert out1 != out2
