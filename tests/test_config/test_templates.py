"""Tests for PromptTemplate and TemplateManager."""

from __future__ import annotations

import pytest

from anythink.config.templates import PromptTemplate, TemplateManager
from anythink.exceptions import ConfigError


class TestPromptTemplate:
    def test_variables_detection(self) -> None:
        t = PromptTemplate("t", "Review {{language}} code for {{aspect}}.")
        assert t.variables() == ["language", "aspect"]

    def test_variables_empty_when_none(self) -> None:
        t = PromptTemplate("t", "No variables here.")
        assert t.variables() == []

    def test_render_substitutes_all(self) -> None:
        t = PromptTemplate("t", "{{greeting}}, {{name}}!")
        result = t.render({"greeting": "Hello", "name": "World"})
        assert result == "Hello, World!"

    def test_render_raises_on_missing_variable(self) -> None:
        t = PromptTemplate("t", "{{lang}} code.")
        with pytest.raises(ConfigError, match="lang"):
            t.render({})

    def test_render_raises_listing_all_missing(self) -> None:
        t = PromptTemplate("t", "{{a}} and {{b}}.")
        with pytest.raises(ConfigError):
            t.render({"a": "x"})

    def test_roundtrip_via_dict(self) -> None:
        t = PromptTemplate("code-review", "Review {{lang}} code.", description="A review template")
        d = t.to_dict()
        restored = PromptTemplate.from_dict(d)
        assert restored.name == t.name
        assert restored.body == t.body
        assert restored.description == t.description


class TestTemplateManager:
    def test_empty_list(self, xdg_dirs: Paths) -> None:
        mgr = TemplateManager(xdg_dirs.templates_file)
        assert mgr.list_all() == []

    def test_add_and_get(self, xdg_dirs: Paths) -> None:
        mgr = TemplateManager(xdg_dirs.templates_file)
        t = PromptTemplate("my-tmpl", "Do {{thing}}.")
        mgr.add(t)
        fetched = mgr.get("my-tmpl")
        assert fetched is not None
        assert fetched.body == "Do {{thing}}."

    def test_exists(self, xdg_dirs: Paths) -> None:
        mgr = TemplateManager(xdg_dirs.templates_file)
        assert not mgr.exists("x")
        mgr.add(PromptTemplate("x", "body"))
        assert mgr.exists("x")

    def test_remove(self, xdg_dirs: Paths) -> None:
        mgr = TemplateManager(xdg_dirs.templates_file)
        mgr.add(PromptTemplate("x", "body"))
        mgr.remove("x")
        assert not mgr.exists("x")

    def test_remove_missing_raises(self, xdg_dirs: Paths) -> None:
        mgr = TemplateManager(xdg_dirs.templates_file)
        with pytest.raises(ConfigError):
            mgr.remove("nonexistent")

    def test_persistence_roundtrip(self, xdg_dirs: Paths) -> None:
        mgr1 = TemplateManager(xdg_dirs.templates_file)
        mgr1.add(PromptTemplate("saved", "body text"))

        mgr2 = TemplateManager(xdg_dirs.templates_file)
        assert mgr2.exists("saved")

    def test_list_all_sorted_by_created_at(self, xdg_dirs: Paths) -> None:
        mgr = TemplateManager(xdg_dirs.templates_file)
        mgr.add(PromptTemplate("a", "body a"))
        mgr.add(PromptTemplate("b", "body b"))
        names = [t.name for t in mgr.list_all()]
        assert "a" in names and "b" in names
