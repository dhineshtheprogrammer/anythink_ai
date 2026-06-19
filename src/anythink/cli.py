"""Anythink CLI entry point."""

from __future__ import annotations

import typer
from typing_extensions import Annotated

from anythink import __version__
from anythink.config.manager import ConfigManager

app = typer.Typer(
    name="anythink",
    help="Think anything. Ask anything. — A universal AI-powered CLI chatbot.",
    no_args_is_help=False,
    add_completion=True,
)

keys_app = typer.Typer(name="keys", help="Manage API keys in the OS keychain.")
model_app = typer.Typer(name="model", help="Manage model aliases.")

app.add_typer(keys_app, name="keys")
app.add_typer(model_app, name="model")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"anythink {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option("--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit."),
    ] = False,
) -> None:
    """Start an interactive chat session."""
    if ctx.invoked_subcommand is not None:
        return

    # Placeholder until App orchestrator is implemented (Phase 5)
    config_manager = ConfigManager()
    if not config_manager.is_configured():
        typer.echo("Anythink is not configured yet. Run `anythink setup` to get started.")
        raise typer.Exit(1)

    typer.echo("Starting Anythink chat session... (full UI coming in Phase 5)")


@app.command("setup")
def setup_wizard() -> None:
    """Run the interactive first-run setup wizard."""
    typer.echo("Setup wizard coming in Phase 11.")


# ── keys sub-commands ──────────────────────────────────────────────────────────

@keys_app.command("list")
def keys_list() -> None:
    """List all configured providers and their key status."""
    typer.echo("Keys list coming in Phase 12.")


@keys_app.command("add")
def keys_add(provider: str = typer.Argument(..., help="Provider name (e.g. groq, openai).")) -> None:
    """Add or update an API key for a provider."""
    typer.echo(f"Adding key for {provider}... (coming in Phase 12)")


@keys_app.command("show")
def keys_show(provider: str = typer.Argument(..., help="Provider name.")) -> None:
    """Show the stored key for a provider (masked)."""
    typer.echo(f"Showing key for {provider}... (coming in Phase 12)")


@keys_app.command("update")
def keys_update(provider: str = typer.Argument(..., help="Provider name.")) -> None:
    """Replace the stored key for a provider."""
    typer.echo(f"Updating key for {provider}... (coming in Phase 12)")


@keys_app.command("delete")
def keys_delete(provider: str = typer.Argument(..., help="Provider name.")) -> None:
    """Remove a stored key from the keychain."""
    typer.echo(f"Deleting key for {provider}... (coming in Phase 12)")


@keys_app.command("test")
def keys_test(provider: str = typer.Argument(..., help="Provider name.")) -> None:
    """Validate the stored key by making a test API call."""
    typer.echo(f"Testing key for {provider}... (coming in Phase 12)")


# ── model sub-commands ─────────────────────────────────────────────────────────

@model_app.command("list")
def model_list() -> None:
    """List all configured model aliases."""
    typer.echo("Model list coming in Phase 2.")


@model_app.command("add")
def model_add() -> None:
    """Add a new model alias interactively."""
    typer.echo("Model add coming in Phase 2.")


@model_app.command("remove")
def model_remove(alias: str = typer.Argument(..., help="Alias name to remove.")) -> None:
    """Remove a model alias."""
    typer.echo(f"Removing alias {alias}... (coming in Phase 2)")
