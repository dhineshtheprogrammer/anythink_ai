"""Anythink — Think anything. Ask anything."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("anythink")
except PackageNotFoundError:
    __version__ = "2.0.0"

__all__ = ["__version__"]
