"""Tests for ui/theme.py."""

from __future__ import annotations

import pytest

from anythink.config.schema import AppConfig
from anythink.exceptions import ConfigError
from anythink.ui.theme import (
    ARCTIC,
    AURORA,
    CHARCOAL,
    DRACULA,
    EMBER,
    LINEN,
    MIDNIGHT,
    ROSE,
    THEMES,
    Theme,
    get_theme,
)


class TestThemeDataclass:
    def test_midnight_name(self) -> None:
        assert MIDNIGHT.name == "midnight"

    def test_midnight_primary(self) -> None:
        assert MIDNIGHT.primary == "bright_cyan"

    def test_aurora_name(self) -> None:
        assert AURORA.name == "aurora"

    def test_ember_name(self) -> None:
        assert EMBER.name == "ember"

    def test_arctic_name(self) -> None:
        assert ARCTIC.name == "arctic"

    def test_theme_is_frozen(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            MIDNIGHT.name = "other"  # type: ignore[misc]

    def test_all_themes_have_required_fields(self) -> None:
        for theme in THEMES.values():
            assert isinstance(theme, Theme)
            for attr in ("primary", "secondary", "accent", "muted", "error", "warning", "success"):
                assert getattr(theme, attr), f"Theme {theme.name!r} missing {attr}"


class TestThemesDict:
    def test_eight_themes_registered(self) -> None:
        assert set(THEMES.keys()) == {
            "midnight",
            "aurora",
            "ember",
            "arctic",
            "charcoal",
            "linen",
            "rose",
            "dracula",
        }

    def test_themes_values_are_theme_instances(self) -> None:
        for t in THEMES.values():
            assert isinstance(t, Theme)

    def test_themes_consistent_with_appconfig_valid_themes(self) -> None:
        assert frozenset(THEMES.keys()) == AppConfig().VALID_THEMES


class TestGetTheme:
    def test_get_known_theme(self) -> None:
        theme = get_theme("aurora")
        assert theme is AURORA

    def test_get_all_eight_themes(self) -> None:
        for name in (
            "midnight",
            "aurora",
            "ember",
            "arctic",
            "charcoal",
            "linen",
            "rose",
            "dracula",
        ):
            assert get_theme(name).name == name

    def test_get_unknown_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="Unknown theme"):
            get_theme("neon")

    def test_get_unknown_error_message_lists_valid(self) -> None:
        with pytest.raises(ConfigError) as exc_info:
            get_theme("bogus")
        assert "midnight" in exc_info.value.user_message


class TestNewThemes:
    def test_charcoal_name(self) -> None:
        assert CHARCOAL.name == "charcoal"

    def test_charcoal_logo_override(self) -> None:
        assert CHARCOAL.logo == "#5C9CF5"

    def test_charcoal_is_not_light_bg(self) -> None:
        assert CHARCOAL.is_light_bg is False

    def test_linen_name(self) -> None:
        assert LINEN.name == "linen"

    def test_linen_is_light_bg(self) -> None:
        assert LINEN.is_light_bg is True

    def test_linen_logo_is_none(self) -> None:
        assert LINEN.logo is None

    def test_rose_name(self) -> None:
        assert ROSE.name == "rose"

    def test_rose_is_not_light_bg(self) -> None:
        assert ROSE.is_light_bg is False

    def test_dracula_name(self) -> None:
        assert DRACULA.name == "dracula"

    def test_dracula_primary(self) -> None:
        assert DRACULA.primary == "#BD93F9"

    def test_dark_themes_logo_defaults_to_none(self) -> None:
        for theme in (MIDNIGHT, AURORA, EMBER, ARCTIC, LINEN, ROSE, DRACULA):
            assert theme.logo is None, f"{theme.name} should have logo=None"

    def test_only_linen_is_light_bg(self) -> None:
        for theme in (MIDNIGHT, AURORA, EMBER, ARCTIC, CHARCOAL, ROSE, DRACULA):
            assert theme.is_light_bg is False, f"{theme.name} should not be light_bg"
