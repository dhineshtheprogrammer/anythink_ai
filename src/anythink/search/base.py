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
    published_date: str | None = None
    source_domain: str | None = None


class BaseSearchBackend(ABC):
    """Abstract base class for all web search backends."""

    name: str
    display_name: str

    # Capability flags — subclasses override to reflect actual support.
    supports_freshness: bool = False
    supports_safe_search: bool = False
    supports_news: bool = False

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 5,
        date_from: str | None = None,
        date_to: str | None = None,
        safe_search: str | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[SearchResult]:
        """Perform a web search and return up to *max_results* results.

        Backends that do not support a given filter param silently ignore it.
        """
        ...  # pragma: no cover

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this backend's dependencies are installed and configured."""
        ...  # pragma: no cover
