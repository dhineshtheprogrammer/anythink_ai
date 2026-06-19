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


def test_main_when_configured_starts_chat() -> None:
    from unittest.mock import AsyncMock
    mock_manager = MagicMock()
    mock_manager.is_configured.return_value = True
    with patch("anythink.cli.ConfigManager", return_value=mock_manager), \
            patch("anythink.cli.AppContext") as MockCtx, \
            patch("anythink.cli.ChatApp") as MockChat:
        MockChat.return_value.run = AsyncMock(return_value=0)
        result = runner.invoke(app, [])
    assert result.exit_code == 0
    MockChat.assert_called_once_with(MockCtx.create.return_value)
    MockChat.return_value.run.assert_awaited_once()


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


def test_plugins_help() -> None:
    result = runner.invoke(app, ["plugins", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output


def test_plugins_list_no_plugins() -> None:
    with patch("anythink.plugins.manager.PluginManager.list_plugins", return_value=[]):
        result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0
    assert "No plugins" in result.output


def test_plugins_list_shows_installed() -> None:
    from anythink.plugins.models import PluginInfo

    plugins = [PluginInfo(name="anythink-groq", version="1.0.0", description="Groq", author="Dev")]
    with patch("anythink.plugins.manager.PluginManager.list_plugins", return_value=plugins):
        result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0
    assert "anythink-groq" in result.output


def test_plugins_info_found() -> None:
    from anythink.plugins.models import PluginInfo

    p = PluginInfo(
        name="anythink-groq", version="1.0.0", description="Groq provider",
        author="Dev", entry_point_groups=["anythink.providers"]
    )
    with patch("anythink.plugins.manager.PluginManager.get_plugin", return_value=p):
        result = runner.invoke(app, ["plugins", "info", "anythink-groq"])
    assert result.exit_code == 0
    assert "anythink-groq" in result.output
    assert "Groq provider" in result.output


def test_plugins_info_not_found() -> None:
    with patch("anythink.plugins.manager.PluginManager.get_plugin", return_value=None):
        result = runner.invoke(app, ["plugins", "info", "missing"])
    assert result.exit_code != 0


def test_plugins_install_success() -> None:
    with patch("anythink.plugins.manager.PluginManager.install", return_value=(True, "ok")):
        result = runner.invoke(app, ["plugins", "install", "anythink-groq"])
    assert result.exit_code == 0
    assert "Installed" in result.output


def test_plugins_install_failure() -> None:
    with patch("anythink.plugins.manager.PluginManager.install", return_value=(False, "error msg")):
        result = runner.invoke(app, ["plugins", "install", "bad-pkg"])
    assert result.exit_code != 0


def test_plugins_remove_success() -> None:
    with patch("anythink.plugins.manager.PluginManager.remove", return_value=(True, "ok")):
        result = runner.invoke(app, ["plugins", "remove", "anythink-groq"])
    assert result.exit_code == 0
    assert "Removed" in result.output


def test_plugins_remove_failure() -> None:
    with patch("anythink.plugins.manager.PluginManager.remove", return_value=(False, "error")):
        result = runner.invoke(app, ["plugins", "remove", "bad-pkg"])
    assert result.exit_code != 0
