"""Four-tier safety classification system for Windows MCP tool calls."""

from __future__ import annotations

import os
from typing import Any


# Static tier assignment for every Windows MCP tool.
# Tier 1 = auto-allowed (read-only)
# Tier 2 = autonomy mode applies (non-destructive writes / launches)
# Tier 3 = always confirm (destructive / system-changing)
# Tier 4 = double confirm (highest risk — bulk destroy / system-critical paths)
_STATIC_TIERS: dict[str, dict[str, int]] = {
    "windows-filesystem": {
        "list_dir": 1,
        "read_file": 1,
        "get_file_metadata": 1,
        "search_files_by_name": 1,
        "search_files_by_content": 1,
        "write_file": 2,        # dynamic: escalates to 3 if overwrite=True / file exists
        "create_file": 2,
        "create_folder": 2,
        "copy_file": 2,         # dynamic: escalates to 3 if destination exists
        "move_file": 3,
        "rename_file": 3,
        "delete_file": 3,
        "delete_folder": 3,     # dynamic: escalates to 4 if recursive=True
    },
    "windows-explorer": {
        "open_folder_in_explorer": 2,
        "navigate_explorer_to_path": 2,
        "open_file_with_default_app": 2,
        "select_files_in_explorer": 2,
    },
    "windows-apps": {
        "list_installed_apps": 1,
        "launch_app": 2,
    },
    "windows-window": {
        "list_open_windows": 1,
        "bring_to_foreground": 2,
        "minimize_window": 2,
        "maximize_window": 2,
        "restore_window": 2,
        "close_window": 3,
        "send_text_to_window": 3,
    },
    "windows-process": {
        "list_processes": 1,
        "get_process_info": 1,
        "start_process": 2,
        "kill_process": 3,
    },
    "windows-system": {
        "get_cpu_info": 1,
        "get_ram_info": 1,
        "get_disk_info": 1,
        "get_battery_info": 1,
        "get_network_info": 1,
        "get_windows_version": 1,
        "get_hardware_info": 1,
        "get_installed_apps": 1,
    },
    "windows-settings": {
        "get_volume": 1,
        "set_volume": 3,
        "mute_audio": 3,
        "get_brightness": 1,
        "set_brightness": 3,
        "get_power_plan": 1,
        "list_power_plans": 1,
        "set_power_plan": 3,
        "get_timezone": 1,
        "set_timezone": 3,
        "get_display_info": 1,
    },
    "windows-clipboard": {
        "read_clipboard": 1,
        "write_clipboard": 2,
        "clear_clipboard": 2,
    },
    "windows-screenshot": {
        "take_screenshot": 2,
        "take_window_screenshot": 2,
        "save_screenshot": 2,
    },
    "windows-notification": {
        "send_notification": 2,
        "send_scheduled_notification": 2,
        "list_scheduled_notifications": 1,
        "cancel_scheduled_notification": 2,
    },
}


class WindowsSafetyChecker:
    """Classifies Windows MCP tool calls into safety tiers 1–4."""

    def get_tier(self, server_name: str, tool_name: str, **kwargs: Any) -> int:
        """Return the safety tier for a tool call, applying dynamic overrides where needed."""
        base = _STATIC_TIERS.get(server_name, {}).get(tool_name, 2)

        if tool_name == "write_file":
            path = str(kwargs.get("path", ""))
            overwrite = bool(kwargs.get("overwrite", False))
            if overwrite or (path and os.path.exists(path)):
                return 3
            return 2

        if tool_name == "copy_file":
            destination = str(kwargs.get("destination", ""))
            overwrite = bool(kwargs.get("overwrite", False))
            if overwrite or (destination and os.path.exists(destination)):
                return 3
            return 2

        if tool_name == "delete_folder":
            if bool(kwargs.get("recursive", False)):
                return 4
            return 3

        return base

    def is_auto_allowed(self, tier: int) -> bool:
        return tier == 1

    def requires_double_confirm(self, tier: int) -> bool:
        return tier >= 4

    def build_confirmation_prompt(
        self,
        tier: int,
        operation: str,
        server: str,
        target: str,
        consequence: str,
    ) -> str:
        if tier >= 4:
            header = "[bold red]Second Confirmation — High-Risk Operation[/bold red]"
            body = (
                f"  You are about to perform a [bold red]HIGH-RISK[/bold red] operation.\n"
                f"  Operation:    [yellow]{operation}[/yellow]\n"
                f"  Server:       {server}\n"
                f"  Target:       [red]{target}[/red]\n"
                f"  Consequence:  [red]{consequence}[/red]\n\n"
                f"  [bold]This cannot be undone.[/bold] Type [green]\"confirm\"[/green] to proceed:"
            )
        else:
            header = "[bold yellow]Confirmation Required — Tier 3 Operation[/bold yellow]"
            body = (
                f"  Operation:    [yellow]{operation}[/yellow]\n"
                f"  Server:       {server}\n"
                f"  Target:       {target}\n"
                f"  Consequence:  {consequence}\n\n"
                f"  Type [green]\"yes\"[/green] to confirm or [red]\"no\"[/red] to cancel:"
            )

        return (
            f"╭─ {header} {'─' * 20}╮\n"
            f"│\n"
            f"{body}\n"
            f"╰{'─' * 60}╯"
        )

    def all_tiers(self) -> dict[str, dict[str, int]]:
        return {s: dict(tools) for s, tools in _STATIC_TIERS.items()}
