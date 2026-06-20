"""Tests for SearchRegistry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from anythink.search.base import BaseSearchBackend
from anythink.search.registry import SearchRegistry


def _make_backend(name: str, available: bool = True) -> BaseSearchBackend:
    backend = MagicMock(spec=BaseSearchBackend)
    backend.name = name
    backend.is_available = MagicMock(return_value=available)
    return backend


class TestSearchRegistry:
    def test_register_and_get(self) -> None:
        r = SearchRegistry()
        b = _make_backend("ddg")
        r.register(b)
        assert r.get("ddg") is b

    def test_get_returns_none_for_unknown(self) -> None:
        r = SearchRegistry()
        assert r.get("missing") is None

    def test_names_lists_registered(self) -> None:
        r = SearchRegistry()
        r.register(_make_backend("a"))
        r.register(_make_backend("b"))
        assert set(r.names()) == {"a", "b"}

    def test_get_available_returns_preferred_when_available(self) -> None:
        r = SearchRegistry()
        r.register(_make_backend("a", available=False))
        r.register(_make_backend("b", available=True))
        assert r.get_available(preferred="b") is r.get("b")

    def test_get_available_falls_back_to_first_available(self) -> None:
        r = SearchRegistry()
        r.register(_make_backend("a", available=False))
        r.register(_make_backend("b", available=True))
        assert r.get_available(preferred="a") is r.get("b")

    def test_get_available_returns_none_when_none_available(self) -> None:
        r = SearchRegistry()
        r.register(_make_backend("a", available=False))
        assert r.get_available() is None

    def test_get_available_no_preferred_returns_first_available(self) -> None:
        r = SearchRegistry()
        r.register(_make_backend("x", available=True))
        result = r.get_available()
        assert result is r.get("x")

    def test_from_entry_points_loads_backends(self) -> None:
        mock_ep = MagicMock()
        mock_ep.name = "ddg"
        mock_backend_cls = MagicMock(return_value=_make_backend("ddg"))
        mock_ep.load = MagicMock(return_value=mock_backend_cls)

        with patch(
            "anythink.search.registry.entry_points",
            return_value=[mock_ep],
        ):
            registry = SearchRegistry.from_entry_points()

        assert "ddg" in registry.names()

    def test_from_entry_points_skips_failed_backends(self) -> None:
        mock_ep = MagicMock()
        mock_ep.name = "broken"
        mock_ep.load = MagicMock(side_effect=ImportError("no module"))

        with patch(
            "anythink.search.registry.entry_points",
            return_value=[mock_ep],
        ):
            registry = SearchRegistry.from_entry_points()

        assert registry.names() == []

    def test_from_entry_points_passes_api_key(self) -> None:
        mock_backend_instance = _make_backend("serpapi")
        mock_backend_cls = MagicMock(return_value=mock_backend_instance)

        mock_ep = MagicMock()
        mock_ep.name = "serpapi"
        mock_ep.load = MagicMock(return_value=mock_backend_cls)

        with patch(
            "anythink.search.registry.entry_points",
            return_value=[mock_ep],
        ):
            SearchRegistry.from_entry_points(api_keys={"serpapi": "mykey"})

        mock_backend_cls.assert_called_once_with(api_key="mykey")
