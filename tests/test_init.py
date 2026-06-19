"""Tests for anythink package __init__."""

from __future__ import annotations

from unittest.mock import patch


def test_version_when_package_not_installed() -> None:
    """The PackageNotFoundError fallback returns the hardcoded version."""
    from importlib.metadata import PackageNotFoundError
    import importlib
    import anythink

    with patch("importlib.metadata.version", side_effect=PackageNotFoundError("anythink")):
        importlib.reload(anythink)
        assert anythink.__version__ == "0.1.0"
