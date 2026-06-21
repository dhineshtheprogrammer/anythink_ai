"""Self-update mechanism for Anythink."""

from __future__ import annotations

import subprocess  # nosec B404
import sys


async def fetch_latest_version(package: str = "anythink") -> str | None:
    """Query PyPI for the latest published version. Returns None on any error."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://pypi.org/pypi/{package}/json")
            response.raise_for_status()
            return str(response.json()["info"]["version"])
    except Exception:
        return None


def current_version() -> str:
    """Return the currently installed Anythink version."""
    try:
        from anythink import __version__

        return str(__version__)
    except Exception:
        return "unknown"


async def check_update() -> tuple[str, str | None]:
    """Return (current_version, latest_version_or_None).

    latest is None when PyPI is unreachable.
    """
    current = current_version()
    latest = await fetch_latest_version()
    return current, latest


def run_upgrade() -> tuple[bool, str]:
    """Run ``pip install --upgrade anythink`` and return (success, output)."""
    result = subprocess.run(  # nosec B603 B607
        [sys.executable, "-m", "pip", "install", "--upgrade", "anythink"],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output
