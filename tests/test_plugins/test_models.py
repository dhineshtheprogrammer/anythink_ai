"""Tests for plugins/models.py."""

from __future__ import annotations

from anythink.plugins.models import PluginInfo


class TestPluginInfo:
    def test_stores_name(self) -> None:
        p = PluginInfo(name="anythink-groq", version="1.0.0", description="Groq", author="Dev")
        assert p.name == "anythink-groq"

    def test_stores_version(self) -> None:
        p = PluginInfo(name="pkg", version="2.3.4", description="", author="")
        assert p.version == "2.3.4"

    def test_stores_description(self) -> None:
        p = PluginInfo(name="pkg", version="1.0", description="A plugin", author="")
        assert p.description == "A plugin"

    def test_stores_author(self) -> None:
        p = PluginInfo(name="pkg", version="1.0", description="", author="Alice")
        assert p.author == "Alice"

    def test_homepage_defaults_empty(self) -> None:
        p = PluginInfo(name="pkg", version="1.0", description="", author="")
        assert p.homepage == ""

    def test_homepage_stored(self) -> None:
        p = PluginInfo(
            name="pkg", version="1.0", description="", author="", homepage="https://example.com"
        )
        assert p.homepage == "https://example.com"

    def test_entry_point_groups_default_empty(self) -> None:
        p = PluginInfo(name="pkg", version="1.0", description="", author="")
        assert p.entry_point_groups == []

    def test_entry_point_groups_stored(self) -> None:
        groups = ["anythink.providers", "anythink.search_backends"]
        p = PluginInfo(
            name="pkg", version="1.0", description="", author="", entry_point_groups=groups
        )
        assert p.entry_point_groups == groups
