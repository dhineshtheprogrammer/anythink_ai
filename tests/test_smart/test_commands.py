"""Tests for smart/commands.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anythink.smart.commands import (
    _handle_combiner,
    _handle_format,
    _handle_quality,
    _handle_registry,
    _handle_status,
    _smart_handler,
    register_smart_commands,
)
from anythink.smart.registry import SmartRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ctx(tmp_path: Path, smart_enabled: bool = False) -> MagicMock:
    from anythink.config.schema import AppConfig

    # Use a real AppConfig so replace() works
    config = AppConfig()

    ctx = MagicMock()
    ctx.config = config
    ctx.smart_enabled = smart_enabled

    reg = SmartRegistry(tmp_path / "reg.yaml")
    reg.load()
    ctx.smart_registry = reg

    ctx.config_manager = MagicMock()
    ctx.config_manager.save = MagicMock()

    return ctx


def _make_state() -> MagicMock:
    return MagicMock()


def _make_registry() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# Toggle / status tests
# ---------------------------------------------------------------------------


async def test_smart_on_enables(tmp_path: Path):
    ctx = _make_ctx(tmp_path, smart_enabled=False)
    result = await _smart_handler(ctx, "on", _make_state(), _make_registry())
    assert ctx.smart_enabled is True
    assert result.action == "smart_hud_update"
    assert not result.error


async def test_smart_off_disables(tmp_path: Path):
    ctx = _make_ctx(tmp_path, smart_enabled=True)
    result = await _smart_handler(ctx, "off", _make_state(), _make_registry())
    assert ctx.smart_enabled is False
    assert result.action == "smart_hud_update"


async def test_smart_toggle_flips_state(tmp_path: Path):
    ctx = _make_ctx(tmp_path, smart_enabled=False)
    result = await _smart_handler(ctx, "toggle", _make_state(), _make_registry())
    assert ctx.smart_enabled is True
    assert result.action == "smart_hud_update"


async def test_smart_toggle_from_on_to_off(tmp_path: Path):
    ctx = _make_ctx(tmp_path, smart_enabled=True)
    result = await _smart_handler(ctx, "toggle", _make_state(), _make_registry())
    assert ctx.smart_enabled is False


async def test_smart_status_returns_info(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = await _smart_handler(ctx, "status", _make_state(), _make_registry())
    assert not result.error
    assert "Smart mode" in result.message


async def test_smart_empty_args_returns_status(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = await _smart_handler(ctx, "", _make_state(), _make_registry())
    assert not result.error
    assert result.message


async def test_smart_help(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = await _smart_handler(ctx, "help", _make_state(), _make_registry())
    assert not result.error
    assert "/smart" in result.message


async def test_smart_unknown_subcommand(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = await _smart_handler(ctx, "xyz", _make_state(), _make_registry())
    assert result.error is True


# ---------------------------------------------------------------------------
# Status detail tests
# ---------------------------------------------------------------------------


def test_handle_status_shows_all_categories(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_status(ctx)
    # All 9 categories should appear in the status output
    for cat in (
        "math",
        "code",
        "writing",
        "reasoning",
        "research",
        "data",
        "translation",
        "summarization",
        "general",
    ):
        assert cat in result.message


# ---------------------------------------------------------------------------
# Registry subcommand tests
# ---------------------------------------------------------------------------


def test_handle_registry_show(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_registry(ctx, "show")
    assert "Category" in result.message
    assert not result.error


def test_handle_registry_set(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_registry(ctx, "set math my-math-model")
    assert not result.error
    assert ctx.smart_registry.get("math") == "my-math-model"


def test_handle_registry_set_unknown_category(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_registry(ctx, "set not-a-category some-alias")
    assert result.error is True


def test_handle_registry_reset_single(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    ctx.smart_registry.set("math", "model")
    result = _handle_registry(ctx, "reset math")
    assert not result.error
    assert ctx.smart_registry.get("math") is None


def test_handle_registry_reset_all(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    ctx.smart_registry.set("math", "m1")
    ctx.smart_registry.set("code", "c1")
    result = _handle_registry(ctx, "reset all")
    assert not result.error
    assert ctx.smart_registry.get("math") is None
    assert ctx.smart_registry.get("code") is None


def test_handle_registry_set_router(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_registry(ctx, "router my-router")
    assert not result.error
    assert ctx.smart_registry.get_router() == "my-router"


def test_handle_registry_set_combiner(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_registry(ctx, "combiner my-combiner")
    assert not result.error
    assert ctx.smart_registry.get_combiner() == "my-combiner"


def test_handle_registry_set_formatter(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_registry(ctx, "formatter my-fmt")
    assert not result.error
    assert ctx.smart_registry.get_formatter() == "my-fmt"


def test_handle_registry_fallback(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_registry(ctx, "fallback fallback-model")
    assert not result.error
    assert ctx.smart_registry.get("general") == "fallback-model"


def test_handle_registry_bad_usage(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_registry(ctx, "invalid-subcommand")
    assert result.error is True


# ---------------------------------------------------------------------------
# Combiner tests
# ---------------------------------------------------------------------------


def test_handle_combiner_stitch(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_combiner(ctx, "stitch")
    assert not result.error
    assert ctx.config.smart_combiner_mode == "stitch"


def test_handle_combiner_merge(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_combiner(ctx, "merge")
    assert not result.error
    assert ctx.config.smart_combiner_mode == "merge"


def test_handle_combiner_show(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_combiner(ctx, "show")
    assert not result.error
    assert "Combiner mode" in result.message


def test_handle_combiner_invalid(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_combiner(ctx, "invalid")
    assert result.error is True


# ---------------------------------------------------------------------------
# Format tests
# ---------------------------------------------------------------------------


def test_handle_format_valid(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_format(ctx, "table")
    assert not result.error
    assert ctx.config.smart_session_format == "table"


def test_handle_format_off(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_format(ctx, "off")
    assert not result.error
    assert ctx.config.smart_session_format == ""


def test_handle_format_show(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_format(ctx, "show")
    assert not result.error
    assert "Session format" in result.message


def test_handle_format_invalid(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_format(ctx, "html")
    assert result.error is True
    assert "Valid formats" in result.message


# ---------------------------------------------------------------------------
# Quality tests
# ---------------------------------------------------------------------------


def test_handle_quality_set(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_quality(ctx, "70")
    assert not result.error
    assert ctx.config.smart_quality_threshold == 70


def test_handle_quality_clamped_to_100(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_quality(ctx, "150")
    assert not result.error
    assert ctx.config.smart_quality_threshold == 100


def test_handle_quality_clamped_to_0(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_quality(ctx, "-5")
    assert not result.error
    assert ctx.config.smart_quality_threshold == 0


def test_handle_quality_show(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_quality(ctx, "show")
    assert not result.error
    assert "Quality threshold" in result.message


def test_handle_quality_invalid(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    result = _handle_quality(ctx, "not-a-number")
    assert result.error is True


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_smart_commands():
    reg = MagicMock()
    register_smart_commands(reg)
    reg.register.assert_called_once()
    cmd = reg.register.call_args[0][0]
    assert cmd.name == "smart"
