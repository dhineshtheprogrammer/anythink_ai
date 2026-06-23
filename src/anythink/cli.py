"""Anythink CLI entry point."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from anythink import __version__
from anythink.app.context import AppContext
from anythink.config.manager import ConfigManager
from anythink.ui.icons import VS15
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
    debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            help="Start with debug mode active (Level 2).",
        ),
    ] = False,
    debug_level: Annotated[
        int,
        typer.Option(
            "--debug-level",
            help="Debug verbosity level when --debug is set (1, 2, or 3).",
        ),
    ] = 2,
) -> None:
    """Start an interactive chat session."""
    if ctx.invoked_subcommand is not None:
        return

    config_manager = ConfigManager()
    if not config_manager.is_configured():
        typer.echo("Anythink is not configured yet. Run `anythink setup` to get started.")
        raise typer.Exit(1)

    app_ctx = AppContext.create(paths=config_manager.paths)
    if debug:
        app_ctx.debug_manager.enable(level=max(1, min(3, debug_level)))
    anythink_app = AnythinkApp(app_ctx, dashboard=dashboard)
    anythink_app.run()
    raise typer.Exit(anythink_app.return_code or 0)


@app.command("setup")
def setup_wizard() -> None:
    """Run the interactive first-run setup wizard."""
    import asyncio

    from anythink.config.models import ModelAlias, ModelRegistry
    from anythink.config.schema import AppConfig
    from anythink.exceptions import AnythinkError, KeychainError
    from anythink.keys.manager import KeyManager
    from anythink.providers.registry import ProviderRegistry

    config_manager = ConfigManager()
    paths = config_manager.paths

    typer.echo("\nWelcome to Anythink Setup!")
    typer.echo("─" * 40)
    typer.echo("Configures your first AI provider and model.\n")

    if config_manager.is_configured() and not typer.confirm(
        "Anythink is already configured. Reconfigure?", default=False
    ):
        typer.echo("Cancelled.")
        raise typer.Exit(0)

    # ── Step 1: Provider ──────────────────────────────────────────────────────
    pr = ProviderRegistry()
    available = pr.list_names()
    typer.echo("Step 1/4  Provider")
    typer.echo(f"  Available: {', '.join(available)}")
    provider_name: str = typer.prompt("  Provider")
    if provider_name not in available:
        typer.echo(f"  Warning: '{provider_name}' is not in the known list. Continuing anyway.")

    # ── Step 2: API key ───────────────────────────────────────────────────────
    km = KeyManager(paths=paths)
    api_key: str | None = None

    try:
        probe = pr.instantiate(provider_name, api_key=None)
        needs_key = probe.requires_api_key
    except AnythinkError:
        needs_key = True

    typer.echo("\nStep 2/4  API Key")
    if needs_key:
        raw_key: str = typer.prompt(f"  Enter API key for '{provider_name}'", hide_input=True)
        if not raw_key.strip():
            typer.echo("  Error: API key cannot be empty.", err=True)
            raise typer.Exit(1)
        api_key = raw_key.strip()
        try:
            km.set_key(provider_name, api_key)
            typer.echo("  ✓ API key saved.")
        except KeychainError as exc:
            typer.echo(f"  Error: {exc.user_message}", err=True)
            raise typer.Exit(1) from None

        if typer.confirm("  Test connection?", default=True):
            typer.echo("  Connecting...", nl=False)
            try:
                ok = asyncio.run(pr.instantiate(provider_name, api_key=api_key).test_connection())
                typer.echo(" ✓" if ok else " ✗ (connection failed — you can still continue)")
            except AnythinkError as exc:
                typer.echo(f" ✗ ({exc.user_message})")
    else:
        typer.echo(f"  '{provider_name}' does not require an API key. Skipping.")

    # ── Step 3: Model ─────────────────────────────────────────────────────────
    typer.echo("\nStep 3/4  Model")
    model_id: str
    context_window: int
    supports_vision: bool

    models = []
    try:
        typer.echo(f"  Fetching models from '{provider_name}'...", nl=False)
        models = asyncio.run(pr.instantiate(provider_name, api_key=api_key).list_models())
        typer.echo(f" {len(models)} found.")
    except Exception:
        typer.echo(" (could not fetch — enter model ID manually)")

    if models:
        for i, m in enumerate(models, 1):
            label = m.display_name if m.display_name != m.id else m.id
            typer.echo(f"  {i:>3}.  {label:<38} {m.context_window:>8,} tokens")
        typer.echo(f"  {len(models) + 1:>3}.  Enter model ID manually")

        raw_choice = typer.prompt(f"  Pick [1-{len(models) + 1}]")
        try:
            choice = int(raw_choice)
        except ValueError:
            choice = 0

        if 1 <= choice <= len(models):
            chosen = models[choice - 1]
            model_id = chosen.id
            context_window = chosen.context_window or 4096
            supports_vision = chosen.supports_vision
        else:
            model_id = typer.prompt("  Model ID")
            context_window = int(typer.prompt("  Context window (tokens)", default="4096"))
            supports_vision = typer.confirm("  Supports image input?", default=False)
    else:
        model_id = typer.prompt("  Model ID")
        context_window = int(typer.prompt("  Context window (tokens)", default="4096"))
        supports_vision = typer.confirm("  Supports image input?", default=False)

    default_alias = f"{provider_name}-{model_id.split('-')[0]}"
    alias: str = typer.prompt("  Alias name for this model", default=default_alias)

    model_registry = ModelRegistry(path=paths.models_file)
    if model_registry.exists(alias):
        typer.echo(f"  Alias '{alias}' already exists — overwriting.")
        model_registry.remove(alias)
    model_registry.add(
        ModelAlias(
            alias=alias,
            provider=provider_name,
            model_id=model_id,
            context_window=context_window,
            supports_vision=supports_vision,
        )
    )
    typer.echo(f"  ✓ Model alias '{alias}' saved.")

    # ── Step 4: Preferences ───────────────────────────────────────────────────
    typer.echo("\nStep 4/4  Preferences")
    _THEMES = ("midnight", "aurora", "ember", "arctic", "charcoal", "linen", "rose", "dracula")
    theme = typer.prompt(f"  Theme ({'/'.join(_THEMES)})", default="midnight")
    if theme not in _THEMES:
        typer.echo(f"  Unknown theme '{theme}', using 'midnight'.")
        theme = "midnight"

    set_as_default = typer.confirm("  Set as default model?", default=True)

    paths.ensure_dirs()
    config_manager.save(
        AppConfig(
            active_theme=theme,
            default_model_alias=alias if set_as_default else None,
        )
    )

    typer.echo("\n✓ Setup complete!")
    typer.echo(f"  Config : {paths.config_file}")
    typer.echo(f"  Model  : {alias}  ({provider_name} / {model_id})")
    typer.echo("  Run `anythink` to start chatting.")
    if not set_as_default:
        typer.echo(f"  Tip: use /model {alias} in-session to select your model.")


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


# ── V3: batch run ─────────────────────────────────────────────────────────────


@app.command("run")
def batch_run(
    file: Annotated[
        typer.FileText,
        typer.Option("--file", "-f", help="Input file with one prompt per line."),
    ],
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output file path."),
    ],
    parallel: Annotated[
        int,
        typer.Option("--parallel", "-p", help="Number of prompts to run concurrently (max 20)."),
    ] = 1,
    alias: Annotated[
        str | None,
        typer.Option("--alias", "-a", help="Model alias to use (defaults to configured default)."),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: markdown or json."),
    ] = "markdown",
) -> None:
    """Run a batch of prompts from a file and write results to an output file."""
    from pathlib import Path

    from anythink.batch.runner import run_batch
    from anythink.batch.writers import write_json, write_markdown

    config_manager = ConfigManager()
    if not config_manager.is_configured():
        typer.echo("Anythink is not configured. Run `anythink setup` first.", err=True)
        raise typer.Exit(1)

    prompts = [line.strip() for line in file if line.strip()]
    if not prompts:
        typer.echo("No prompts found in input file.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Running {len(prompts)} prompt(s) with parallel={min(parallel, 20)}…")

    app_ctx = AppContext.create(paths=config_manager.paths)
    results = asyncio.run(run_batch(app_ctx, prompts, parallel=parallel, alias=alias))

    out_path = Path(output)
    if fmt.lower() == "json":
        write_json(results, out_path)
    else:
        write_markdown(results, out_path)

    errors = sum(1 for r in results if r.error)
    typer.echo(f"Done. {len(results) - errors}/{len(results)} succeeded. Written to: {out_path}")
    if errors:
        raise typer.Exit(1)


# ── V3: diagnostics (CLI shortcut) ────────────────────────────────────────────


@app.command("doctor")
def cli_doctor() -> None:
    """Run diagnostics on the Anythink installation."""
    from anythink.diagnostics import run_diagnostics

    config_manager = ConfigManager()
    if not config_manager.is_configured():
        typer.echo("Anythink is not configured. Run `anythink setup` first.", err=True)
        raise typer.Exit(1)

    app_ctx = AppContext.create(paths=config_manager.paths)
    results = asyncio.run(run_diagnostics(app_ctx))

    current_category = ""
    pass_count = warn_count = fail_count = 0
    for r in results:
        if r.category != current_category:
            current_category = r.category
            typer.echo(f"\n{r.category}")
        icon = {"ok": "✓", "warn": f"⚠{VS15}", "fail": "✗"}.get(r.status, "?")
        typer.echo(f"  {icon} {r.name}: {r.message}")
        if r.detail:
            typer.echo(f"    → {r.detail}")
        if r.status == "ok":
            pass_count += 1
        elif r.status == "warn":
            warn_count += 1
        else:
            fail_count += 1

    typer.echo(f"\nSummary: {pass_count} passed, {warn_count} warnings, {fail_count} failed")
    if fail_count:
        raise typer.Exit(1)


# ── V3: scheduler sub-commands ────────────────────────────────────────────────

scheduler_app = typer.Typer(name="scheduler", help="Manage and run the Anythink prompt scheduler.")
app.add_typer(scheduler_app, name="scheduler")


@scheduler_app.command("start")
def scheduler_start(
    poll: Annotated[
        int,
        typer.Option("--poll", "-p", help="Seconds between schedule checks (default 60)."),
    ] = 60,
) -> None:
    """Start the foreground scheduler loop.

    Checks all enabled schedules every POLL seconds and fires any that are due.
    Run this in a separate terminal or configure it as a system service.
    """
    from anythink.schedule.runner import ScheduleRunner

    config_manager = ConfigManager()
    if not config_manager.is_configured():
        typer.echo("Anythink is not configured. Run `anythink setup` first.", err=True)
        raise typer.Exit(1)

    app_ctx = AppContext.create(paths=config_manager.paths)
    runner = ScheduleRunner(app_ctx)
    asyncio.run(runner.start(poll_interval=poll))


@scheduler_app.command("run")
def scheduler_run_once(
    name: str = typer.Argument(..., help="Name of the schedule to run immediately."),
) -> None:
    """Run a named schedule right now, outside its normal cron schedule."""
    from anythink.schedule.runner import ScheduleRunner

    config_manager = ConfigManager()
    if not config_manager.is_configured():
        typer.echo("Anythink is not configured. Run `anythink setup` first.", err=True)
        raise typer.Exit(1)

    app_ctx = AppContext.create(paths=config_manager.paths)
    schedule = app_ctx.schedule_manager.get(name)
    if schedule is None:
        typer.echo(f"Schedule '{name}' not found.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Running schedule '{name}'…")
    runner = ScheduleRunner(app_ctx)
    try:
        text = asyncio.run(runner.run_once(schedule))
        preview = text[:300] + ("…" if len(text) > 300 else "")
        typer.echo(f"✓ Done.\n{preview}")
    except Exception as exc:
        typer.echo(f"✗ Failed: {exc}", err=True)
        raise typer.Exit(1) from None


@scheduler_app.command("list")
def scheduler_list() -> None:
    """List all configured schedules and their status."""
    config_manager = ConfigManager()
    if not config_manager.is_configured():
        typer.echo("Anythink is not configured. Run `anythink setup` first.", err=True)
        raise typer.Exit(1)

    app_ctx = AppContext.create(paths=config_manager.paths)
    schedules = app_ctx.schedule_manager.list_all()
    if not schedules:
        typer.echo("No schedules configured. Use /schedule add inside Anythink.")
        return

    header = f"  {'Name':<24} {'Status':<10} {'Cron':<16} Last run"
    typer.echo(header)
    typer.echo("  " + "─" * (len(header) - 2))
    for s in schedules:
        status = "enabled" if s.enabled else "paused"
        last = s.last_run.strftime("%Y-%m-%d %H:%M") if s.last_run else "never"
        typer.echo(f"  {s.name:<24} {status:<10} {s.cron_expr:<16} {last}")
