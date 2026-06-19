"""Tests for the Anythink CLI entry point."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from anythink.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "anythink" in result.output.lower()


def test_keys_help() -> None:
    result = runner.invoke(app, ["keys", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output


def test_model_help() -> None:
    result = runner.invoke(app, ["model", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output


def test_keys_list_stub() -> None:
    result = runner.invoke(app, ["keys", "list"])
    assert result.exit_code == 0


def test_model_list_stub() -> None:
    result = runner.invoke(app, ["model", "list"])
    assert result.exit_code == 0


def test_main_when_not_configured_exits_with_error() -> None:
    mock_manager = MagicMock()
    mock_manager.is_configured.return_value = False
    with patch("anythink.cli.ConfigManager", return_value=mock_manager):
        result = runner.invoke(app, [])
    assert result.exit_code != 0
    assert "not configured" in result.output.lower()


def test_main_when_configured_shows_placeholder() -> None:
    mock_manager = MagicMock()
    mock_manager.is_configured.return_value = True
    with patch("anythink.cli.ConfigManager", return_value=mock_manager):
        result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "anythink" in result.output.lower()


def test_setup_wizard_stub() -> None:
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
    assert "wizard" in result.output.lower()


def test_keys_add_stub() -> None:
    result = runner.invoke(app, ["keys", "add", "groq"])
    assert result.exit_code == 0
    assert "groq" in result.output


def test_keys_show_stub() -> None:
    result = runner.invoke(app, ["keys", "show", "openai"])
    assert result.exit_code == 0


def test_keys_update_stub() -> None:
    result = runner.invoke(app, ["keys", "update", "anthropic"])
    assert result.exit_code == 0


def test_keys_delete_stub() -> None:
    result = runner.invoke(app, ["keys", "delete", "groq"])
    assert result.exit_code == 0


def test_keys_test_stub() -> None:
    result = runner.invoke(app, ["keys", "test", "groq"])
    assert result.exit_code == 0


def test_model_add_stub() -> None:
    result = runner.invoke(app, ["model", "add"])
    assert result.exit_code == 0


def test_model_remove_stub() -> None:
    result = runner.invoke(app, ["model", "remove", "myalias"])
    assert result.exit_code == 0
    assert "myalias" in result.output
