"""Tests for the Anythink CLI entry point."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from anythink.cli import app

runner = CliRunner()


# ── core / startup ─────────────────────────────────────────────────────────────


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "2.0.0" in result.output


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


def test_main_when_not_configured_exits_with_error() -> None:
    mock_manager = MagicMock()
    mock_manager.is_configured.return_value = False
    with patch("anythink.cli.ConfigManager", return_value=mock_manager):
        result = runner.invoke(app, [])
    assert result.exit_code != 0
    assert "not configured" in result.output.lower()


def test_main_when_configured_starts_chat() -> None:
    mock_manager = MagicMock()
    mock_manager.is_configured.return_value = True
    with (
        patch("anythink.cli.ConfigManager", return_value=mock_manager),
        patch("anythink.cli.AppContext") as MockCtx,
        patch("anythink.cli.AnythinkApp") as MockApp,
    ):
        MockApp.return_value.run = MagicMock()
        MockApp.return_value.return_code = 0
        result = runner.invoke(app, [])
    assert result.exit_code == 0
    MockApp.assert_called_once_with(MockCtx.create.return_value, dashboard=False)
    MockApp.return_value.run.assert_called_once()


def test_setup_wizard_stub() -> None:
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
    assert "wizard" in result.output.lower()


# ── keys list ─────────────────────────────────────────────────────────────────


def test_keys_list_no_keys() -> None:
    with patch("anythink.keys.manager.KeyManager.list_providers", return_value=[]):
        result = runner.invoke(app, ["keys", "list"])
    assert result.exit_code == 0
    assert "No API keys" in result.output


def test_keys_list_shows_providers() -> None:
    with patch("anythink.keys.manager.KeyManager.list_providers", return_value=["groq", "openai"]):
        result = runner.invoke(app, ["keys", "list"])
    assert result.exit_code == 0
    assert "groq" in result.output
    assert "openai" in result.output
    assert "[set]" in result.output


# ── keys add ──────────────────────────────────────────────────────────────────


def test_keys_add_success() -> None:
    with patch("anythink.keys.manager.KeyManager.set_key") as mock_set:
        result = runner.invoke(app, ["keys", "add", "groq"], input="sk-test-key-abc123\n")
    assert result.exit_code == 0
    assert "saved successfully" in result.output
    mock_set.assert_called_once_with("groq", "sk-test-key-abc123")


def test_keys_add_empty_key_exits_with_error() -> None:
    result = runner.invoke(app, ["keys", "add", "groq"], input="\n")
    assert result.exit_code != 0


def test_keys_add_keychain_error_exits() -> None:
    from anythink.exceptions import KeychainError

    with patch(
        "anythink.keys.manager.KeyManager.set_key",
        side_effect=KeychainError("fail", user_message="Keychain unavailable"),
    ):
        result = runner.invoke(app, ["keys", "add", "groq"], input="sk-key\n")
    assert result.exit_code != 0


# ── keys show ─────────────────────────────────────────────────────────────────


def test_keys_show_masks_key() -> None:
    with patch("anythink.keys.manager.KeyManager.get_key", return_value="sk-abcdefghijklmnop"):
        result = runner.invoke(app, ["keys", "show", "groq"])
    assert result.exit_code == 0
    assert "sk-a" in result.output
    assert "mnop" in result.output
    # Should not show the full key plainly
    assert "sk-abcdefghijklmnop" not in result.output


def test_keys_show_not_found_exits() -> None:
    with patch("anythink.keys.manager.KeyManager.get_key", return_value=None):
        result = runner.invoke(app, ["keys", "show", "groq"])
    assert result.exit_code != 0
    assert "No API key" in result.output


def test_keys_show_short_key_shows_masked() -> None:
    with patch("anythink.keys.manager.KeyManager.get_key", return_value="abc"):
        result = runner.invoke(app, ["keys", "show", "groq"])
    assert result.exit_code == 0
    assert "****" in result.output


# ── keys update ───────────────────────────────────────────────────────────────


def test_keys_update_success() -> None:
    with (
        patch("anythink.keys.manager.KeyManager.has_key", return_value=True),
        patch("anythink.keys.manager.KeyManager.set_key") as mock_set,
    ):
        result = runner.invoke(app, ["keys", "update", "groq"], input="sk-new-key-xyz\n")
    assert result.exit_code == 0
    assert "updated successfully" in result.output
    mock_set.assert_called_once_with("groq", "sk-new-key-xyz")


def test_keys_update_no_existing_key_exits() -> None:
    with patch("anythink.keys.manager.KeyManager.has_key", return_value=False):
        result = runner.invoke(app, ["keys", "update", "groq"])
    assert result.exit_code != 0
    assert "No existing key" in result.output


# ── keys delete ───────────────────────────────────────────────────────────────


def test_keys_delete_with_yes_flag() -> None:
    with patch("anythink.keys.manager.KeyManager.delete_key") as mock_del:
        result = runner.invoke(app, ["keys", "delete", "groq", "--yes"])
    assert result.exit_code == 0
    assert "deleted" in result.output
    mock_del.assert_called_once_with("groq")


def test_keys_delete_confirmed_via_prompt() -> None:
    with patch("anythink.keys.manager.KeyManager.delete_key"):
        result = runner.invoke(app, ["keys", "delete", "groq"], input="y\n")
    assert result.exit_code == 0
    assert "deleted" in result.output


def test_keys_delete_cancelled() -> None:
    with patch("anythink.keys.manager.KeyManager.delete_key") as mock_del:
        result = runner.invoke(app, ["keys", "delete", "groq"], input="n\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output
    mock_del.assert_not_called()


# ── keys test ─────────────────────────────────────────────────────────────────


def test_keys_test_success() -> None:
    mock_provider = MagicMock()
    mock_provider.test_connection = AsyncMock(return_value=True)
    with (
        patch("anythink.keys.manager.KeyManager.get_key", return_value="sk-key"),
        patch(
            "anythink.providers.registry.ProviderRegistry.instantiate", return_value=mock_provider
        ),
    ):
        result = runner.invoke(app, ["keys", "test", "groq"])
    assert result.exit_code == 0
    assert "working" in result.output.lower()


def test_keys_test_failure() -> None:
    mock_provider = MagicMock()
    mock_provider.test_connection = AsyncMock(return_value=False)
    with (
        patch("anythink.keys.manager.KeyManager.get_key", return_value="sk-key"),
        patch(
            "anythink.providers.registry.ProviderRegistry.instantiate", return_value=mock_provider
        ),
    ):
        result = runner.invoke(app, ["keys", "test", "groq"])
    assert result.exit_code != 0


def test_keys_test_no_key_exits() -> None:
    with patch("anythink.keys.manager.KeyManager.get_key", return_value=None):
        result = runner.invoke(app, ["keys", "test", "groq"])
    assert result.exit_code != 0
    assert "No API key" in result.output


def test_keys_test_provider_load_error_exits() -> None:
    from anythink.exceptions import PluginError

    with (
        patch("anythink.keys.manager.KeyManager.get_key", return_value="sk-key"),
        patch(
            "anythink.providers.registry.ProviderRegistry.instantiate",
            side_effect=PluginError("no sdk", user_message="SDK not installed"),
        ),
    ):
        result = runner.invoke(app, ["keys", "test", "groq"])
    assert result.exit_code != 0


# ── model list ────────────────────────────────────────────────────────────────


def test_model_list_no_aliases() -> None:
    with patch("anythink.config.models.ModelRegistry.list_all", return_value=[]):
        result = runner.invoke(app, ["model", "list"])
    assert result.exit_code == 0
    assert "No model aliases" in result.output


def test_model_list_shows_aliases() -> None:
    from anythink.config.models import ModelAlias

    aliases = [
        ModelAlias(alias="mymodel", provider="groq", model_id="llama3-8b", context_window=8192),
    ]
    with patch("anythink.config.models.ModelRegistry.list_all", return_value=aliases):
        result = runner.invoke(app, ["model", "list"])
    assert result.exit_code == 0
    assert "mymodel" in result.output
    assert "groq" in result.output
    assert "llama3-8b" in result.output


def test_model_list_shows_vision_flag() -> None:
    from anythink.config.models import ModelAlias

    aliases = [
        ModelAlias(
            alias="vision-model",
            provider="openai",
            model_id="gpt-4o",
            context_window=128000,
            supports_vision=True,
        ),
    ]
    with patch("anythink.config.models.ModelRegistry.list_all", return_value=aliases):
        result = runner.invoke(app, ["model", "list"])
    assert "yes" in result.output


# ── model add ─────────────────────────────────────────────────────────────────


def test_model_add_success() -> None:
    with (
        patch("anythink.config.models.ModelRegistry.exists", return_value=False),
        patch("anythink.config.models.ModelRegistry.add") as mock_add,
    ):
        result = runner.invoke(
            app,
            ["model", "add"],
            input="mymodel\ngroq\nllama3-8b-8192\n8192\nn\n",
        )
    assert result.exit_code == 0
    assert "added successfully" in result.output
    added: object = mock_add.call_args[0][0]
    assert getattr(added, "alias", None) == "mymodel"
    assert getattr(added, "provider", None) == "groq"
    assert getattr(added, "context_window", None) == 8192


def test_model_add_duplicate_alias_exits() -> None:
    with patch("anythink.config.models.ModelRegistry.exists", return_value=True):
        result = runner.invoke(app, ["model", "add"], input="mymodel\n")
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_model_add_invalid_context_window_exits() -> None:
    with patch("anythink.config.models.ModelRegistry.exists", return_value=False):
        result = runner.invoke(
            app,
            ["model", "add"],
            input="mymodel\ngroq\nllama3\nnot-a-number\nn\n",
        )
    assert result.exit_code != 0
    assert "integer" in result.output.lower()


# ── model remove ──────────────────────────────────────────────────────────────


def test_model_remove_with_yes_flag() -> None:
    with (
        patch("anythink.config.models.ModelRegistry.exists", return_value=True),
        patch("anythink.config.models.ModelRegistry.remove") as mock_rm,
    ):
        result = runner.invoke(app, ["model", "remove", "mymodel", "--yes"])
    assert result.exit_code == 0
    assert "removed" in result.output
    mock_rm.assert_called_once_with("mymodel")


def test_model_remove_confirmed_via_prompt() -> None:
    with (
        patch("anythink.config.models.ModelRegistry.exists", return_value=True),
        patch("anythink.config.models.ModelRegistry.remove"),
    ):
        result = runner.invoke(app, ["model", "remove", "mymodel"], input="y\n")
    assert result.exit_code == 0
    assert "removed" in result.output


def test_model_remove_cancelled() -> None:
    with (
        patch("anythink.config.models.ModelRegistry.exists", return_value=True),
        patch("anythink.config.models.ModelRegistry.remove") as mock_rm,
    ):
        result = runner.invoke(app, ["model", "remove", "mymodel"], input="n\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output
    mock_rm.assert_not_called()


def test_model_remove_not_found_exits() -> None:
    with patch("anythink.config.models.ModelRegistry.exists", return_value=False):
        result = runner.invoke(app, ["model", "remove", "ghost"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# ── plugins ───────────────────────────────────────────────────────────────────


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
        name="anythink-groq",
        version="1.0.0",
        description="Groq provider",
        author="Dev",
        entry_point_groups=["anythink.providers"],
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
