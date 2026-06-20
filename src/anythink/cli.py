"""Anythink CLI entry point."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from anythink import __version__
from anythink.app.context import AppContext
from anythink.config.manager import ConfigManager
from anythink.ui.textual.app import AnythinkApp

app = typer.Typer(
    name="anythink",
    help="Think anything. Ask anything. — A universal AI-powered CLI chatbot.",
    no_args_is_help=False,
    add_completion=True,
)

keys_app = typer.Typer(name="keys", help="Manage API keys in the OS keychain.")
model_app = typer.Typer(name="model", help="Manage model aliases.")
plugins_app = typer.Typer(name="plugins", help="Manage Anythink plugins.")

app.add_typer(keys_app, name="keys")
app.add_typer(model_app, name="model")
app.add_typer(plugins_app, name="plugins")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"anythink {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
    dashboard: Annotated[
        bool,
        typer.Option(
            "--dashboard",
            "-D",
            help="Launch directly in 4-panel Dashboard mode.",
        ),
    ] = False,
) -> None:
    """Start an interactive chat session."""
    if ctx.invoked_subcommand is not None:
        return

    config_manager = ConfigManager()
    if not config_manager.is_configured():
        typer.echo("Anythink is not configured yet. Run `anythink setup` to get started.")
        raise typer.Exit(1)

    app_ctx = AppContext.create(paths=config_manager.paths)
    anythink_app = AnythinkApp(app_ctx, dashboard=dashboard)
    anythink_app.run()
    raise typer.Exit(anythink_app.return_code or 0)


@app.command("setup")
def setup_wizard() -> None:
    """Run the interactive first-run setup wizard."""
    typer.echo("Setup wizard coming in Phase 11.")


# ── keys sub-commands ──────────────────────────────────────────────────────────


@keys_app.command("list")
def keys_list() -> None:
    """List all configured providers and their key status."""
    from anythink.keys.manager import KeyManager

    km = KeyManager(paths=ConfigManager().paths)
    providers = km.list_providers()
    if not providers:
        typer.echo("No API keys configured. Use `anythink keys add <provider>` to add one.")
        return
    typer.echo("Configured API keys:")
    for p in providers:
        typer.echo(f"  {p:<20} [set]")


@keys_app.command("add")
def keys_add(
    provider: str = typer.Argument(..., help="Provider name (e.g. groq, openai).")
) -> None:
    """Add an API key for a provider."""
    from anythink.exceptions import KeychainError
    from anythink.keys.manager import KeyManager

    km = KeyManager(paths=ConfigManager().paths)
    api_key: str = typer.prompt(f"Enter API key for '{provider}'", hide_input=True)
    if not api_key.strip():
        typer.echo("Error: API key cannot be empty.", err=True)
        raise typer.Exit(1)
    try:
        km.set_key(provider, api_key.strip())
        typer.echo(f"API key for '{provider}' saved successfully.")
    except KeychainError as exc:
        typer.echo(f"Error: {exc.user_message}", err=True)
        raise typer.Exit(1) from None


@keys_app.command("show")
def keys_show(provider: str = typer.Argument(..., help="Provider name.")) -> None:
    """Show the stored key for a provider (masked)."""
    from anythink.exceptions import KeychainError
    from anythink.keys.manager import KeyManager

    km = KeyManager(paths=ConfigManager().paths)
    try:
        key = km.get_key(provider)
    except KeychainError as exc:
        typer.echo(f"Error: {exc.user_message}", err=True)
        raise typer.Exit(1) from None
    if key is None:
        typer.echo(f"No API key found for '{provider}'.")
        raise typer.Exit(1)
    masked = key[:4] + "*" * max(len(key) - 8, 0) + key[-4:] if len(key) > 8 else "****"
    typer.echo(f"Key for '{provider}': {masked}")


@keys_app.command("update")
def keys_update(provider: str = typer.Argument(..., help="Provider name.")) -> None:
    """Replace the stored key for a provider."""
    from anythink.exceptions import KeychainError
    from anythink.keys.manager import KeyManager

    km = KeyManager(paths=ConfigManager().paths)
    if not km.has_key(provider):
        typer.echo(
            f"No existing key for '{provider}'. Use `anythink keys add {provider}` to add one."
        )
        raise typer.Exit(1)
    api_key: str = typer.prompt(f"Enter new API key for '{provider}'", hide_input=True)
    if not api_key.strip():
        typer.echo("Error: API key cannot be empty.", err=True)
        raise typer.Exit(1)
    try:
        km.set_key(provider, api_key.strip())
        typer.echo(f"API key for '{provider}' updated successfully.")
    except KeychainError as exc:
        typer.echo(f"Error: {exc.user_message}", err=True)
        raise typer.Exit(1) from None


@keys_app.command("delete")
def keys_delete(
    provider: str = typer.Argument(..., help="Provider name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Remove a stored key from the keychain."""
    from anythink.exceptions import KeychainError
    from anythink.keys.manager import KeyManager

    if not yes and not typer.confirm(f"Delete API key for '{provider}'?"):
        typer.echo("Cancelled.")
        raise typer.Exit(0)
    km = KeyManager(paths=ConfigManager().paths)
    try:
        km.delete_key(provider)
        typer.echo(f"API key for '{provider}' deleted.")
    except KeychainError as exc:
        typer.echo(f"Error: {exc.user_message}", err=True)
        raise typer.Exit(1) from None


@keys_app.command("test")
def keys_test(provider: str = typer.Argument(..., help="Provider name.")) -> None:
    """Validate the stored key by making a test API call."""
    from anythink.exceptions import AnythinkError
    from anythink.keys.manager import KeyManager
    from anythink.providers.registry import ProviderRegistry

    km = KeyManager(paths=ConfigManager().paths)
    api_key = km.get_key(provider)
    if api_key is None:
        typer.echo(f"No API key found for '{provider}'. Add one with: anythink keys add {provider}")
        raise typer.Exit(1)

    pr = ProviderRegistry()
    try:
        prov = pr.instantiate(provider, api_key=api_key)
    except AnythinkError as exc:
        typer.echo(f"Error: {exc.user_message}", err=True)
        raise typer.Exit(1) from None

    typer.echo(f"Testing connection to '{provider}'...")
    ok: bool = asyncio.run(prov.test_connection())
    if ok:
        typer.echo(f"  Connection to '{provider}' is working.")
    else:
        typer.echo(f"  Connection to '{provider}' failed.", err=True)
        raise typer.Exit(1)


# ── model sub-commands ─────────────────────────────────────────────────────────


@model_app.command("list")
def model_list() -> None:
    """List all configured model aliases."""
    from anythink.config.models import ModelRegistry

    registry = ModelRegistry(path=ConfigManager().paths.models_file)
    aliases = registry.list_all()
    if not aliases:
        typer.echo("No model aliases configured. Use `anythink model add` to add one.")
        return
    header = f"  {'Alias':<20} {'Provider':<14} {'Model ID':<30} {'Context':>10}  Vision"
    typer.echo(header)
    typer.echo("  " + "-" * (len(header) - 2))
    for a in aliases:
        vision = "yes" if a.supports_vision else "no"
        typer.echo(
            f"  {a.alias:<20} {a.provider:<14} {a.model_id:<30} {a.context_window:>10,}  {vision}"
        )


@model_app.command("add")
def model_add() -> None:
    """Add a new model alias interactively."""
    from anythink.config.models import ModelAlias, ModelRegistry

    registry = ModelRegistry(path=ConfigManager().paths.models_file)

    alias: str = typer.prompt("Alias name (your personal name for this model)")
    if registry.exists(alias):
        typer.echo(
            f"Alias '{alias}' already exists. Remove it first with: anythink model remove {alias}",
            err=True,
        )
        raise typer.Exit(1)

    provider: str = typer.prompt("Provider (groq, openai, anthropic, gemini, ollama, ...)")
    model_id: str = typer.prompt("Model ID (e.g. llama3-8b-8192, gpt-4o)")
    context_raw: str = typer.prompt("Context window size (tokens)", default="4096")
    try:
        context_window = int(context_raw)
    except ValueError:
        typer.echo("Error: context window must be an integer.", err=True)
        raise typer.Exit(1) from None

    supports_vision: bool = typer.confirm("Does this model support image input?", default=False)

    registry.add(
        ModelAlias(
            alias=alias,
            provider=provider,
            model_id=model_id,
            context_window=context_window,
            supports_vision=supports_vision,
        )
    )
    typer.echo(f"Model alias '{alias}' added successfully.")


@model_app.command("remove")
def model_remove(
    alias: str = typer.Argument(..., help="Alias name to remove."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Remove a model alias."""
    from anythink.config.models import ModelRegistry
    from anythink.exceptions import ConfigError

    registry = ModelRegistry(path=ConfigManager().paths.models_file)
    if not registry.exists(alias):
        typer.echo(f"Alias '{alias}' not found.", err=True)
        raise typer.Exit(1)

    if not yes and not typer.confirm(f"Remove model alias '{alias}'?"):
        typer.echo("Cancelled.")
        raise typer.Exit(0)

    try:
        registry.remove(alias)
        typer.echo(f"Model alias '{alias}' removed.")
    except ConfigError as exc:
        typer.echo(f"Error: {exc.user_message}", err=True)
        raise typer.Exit(1) from None


# ── plugins sub-commands ──────────────────────────────────────────────────────


@plugins_app.command("list")
def plugins_list() -> None:
    """List all installed Anythink plugins."""
    from anythink.plugins.manager import PluginManager

    pm = PluginManager()
    plugins = pm.list_plugins()
    if not plugins:
        typer.echo("No plugins installed.")
        return
    for p in plugins:
        desc = f" — {p.description}" if p.description else ""
        typer.echo(f"{p.name} {p.version}{desc}")


@plugins_app.command("info")
def plugins_info(package: str = typer.Argument(..., help="Plugin package name.")) -> None:
    """Show details about an installed plugin."""
    from anythink.plugins.manager import PluginManager

    pm = PluginManager()
    p = pm.get_plugin(package)
    if p is None:
        typer.echo(f"Plugin '{package}' not found.", err=True)
        raise typer.Exit(1)
    typer.echo(f"Name:        {p.name}")
    typer.echo(f"Version:     {p.version}")
    typer.echo(f"Description: {p.description}")
    typer.echo(f"Author:      {p.author}")
    typer.echo(f"Groups:      {', '.join(p.entry_point_groups)}")
    if p.homepage:
        typer.echo(f"Homepage:    {p.homepage}")


@plugins_app.command("install")
def plugins_install(
    package: str = typer.Argument(..., help="PyPI package name to install.")
) -> None:
    """Install a plugin package from PyPI."""
    from anythink.plugins.manager import PluginManager

    pm = PluginManager()
    typer.echo(f"Installing '{package}'...")
    ok, output = pm.install(package)
    if ok:
        typer.echo(f"Installed '{package}'. Restart anythink to load it.")
    else:
        typer.echo(f"Installation failed:\n{output[:500]}", err=True)
        raise typer.Exit(1)


@plugins_app.command("remove")
def plugins_remove(
    package: str = typer.Argument(..., help="Plugin package name to remove.")
) -> None:
    """Remove an installed plugin package."""
    from anythink.plugins.manager import PluginManager

    pm = PluginManager()
    ok, output = pm.remove(package)
    if ok:
        typer.echo(f"Removed '{package}'. Restart anythink to apply changes.")
    else:
        typer.echo(f"Removal failed:\n{output[:500]}", err=True)
        raise typer.Exit(1)
