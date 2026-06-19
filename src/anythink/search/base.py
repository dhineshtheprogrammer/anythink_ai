"""Base classes for web search backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str


class BaseSearchBackend(ABC):
    """Abstract base class for all web search backends."""

    name: str
    display_name: str

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Perform a web search and return up to *max_results* results."""
        ...  # pragma: no cover

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this backend's dependencies are installed and configured."""
        ...  # pragma: no cover
