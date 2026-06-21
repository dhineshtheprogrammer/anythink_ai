"""Config backup and restore for Anythink."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from anythink.config.manager import validate_config

if TYPE_CHECKING:
    from anythink.app.context import AppContext


def export_config(ctx: AppContext, output_path: Path) -> None:
    """Bundle all non-credential config files into a portable JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _read_yaml(p: Path) -> Any:
        if not p.exists():
            return None
        return yaml.safe_load(p.read_text())

    bundle: dict[str, Any] = {
        "version": 3,
        "exported_at": datetime.utcnow().isoformat(),
        "config": _read_yaml(ctx.paths.config_file),
        "models": _read_yaml(ctx.paths.models_file),
        "personas": _read_yaml(ctx.paths.personas_file),
        "templates": _read_yaml(ctx.paths.templates_file),
        "schedules": _read_yaml(ctx.paths.schedules_file),
    }
    output_path.write_text(json.dumps(bundle, indent=2, default=str))


def import_config(ctx: AppContext, input_path: Path) -> None:
    """Restore config from a backup bundle.

    Creates a safety snapshot of the current config before applying changes.
    Restarts are required for changes to take full effect.
    """
    raw = json.loads(input_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("Invalid backup file: expected a JSON object.")

    version = raw.get("version", 1)
    if version > 3:
        raise ValueError(f"Backup version {version} is newer than this Anythink installation.")

    # Validate config section before writing anything
    config_section = raw.get("config") or {}
    if isinstance(config_section, dict) and config_section:
        errors = validate_config(config_section)
        if errors:
            msgs = "; ".join(str(e) for e in errors)
            raise ValueError(f"Backup contains invalid config: {msgs}")

    # Create a safety snapshot first
    _create_snapshot(ctx)

    # Apply each section
    def _write_yaml(p: Path, data: Any) -> None:
        if data is None:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    if raw.get("config"):
        _write_yaml(ctx.paths.config_file, raw["config"])
    if raw.get("models"):
        _write_yaml(ctx.paths.models_file, raw["models"])
    if raw.get("personas"):
        _write_yaml(ctx.paths.personas_file, raw["personas"])
    if raw.get("templates"):
        _write_yaml(ctx.paths.templates_file, raw["templates"])
    if raw.get("schedules"):
        _write_yaml(ctx.paths.schedules_file, raw["schedules"])


def _create_snapshot(ctx: AppContext) -> Path:
    """Save the current config as a dated snapshot before import."""
    snapshot_dir = ctx.paths.data_dir / "config_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"snapshot-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"
    export_config(ctx, snapshot_path)
    return snapshot_path
