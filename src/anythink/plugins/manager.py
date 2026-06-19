"""Plugin manager: discovers installed plugins and wraps pip install/uninstall."""

from __future__ import annotations

import subprocess
import sys
from importlib.metadata import entry_points

from anythink.plugins.models import PluginInfo

_PLUGIN_GROUPS = [
    "anythink.providers",
    "anythink.search_backends",
    "anythink.slash_commands",
]


class PluginManager:
    """Discovers installed Anythink plugins and provides install/remove helpers."""

    def list_plugins(self) -> list[PluginInfo]:
        """Return all packages that contribute to any Anythink entry point group."""
        seen: dict[str, PluginInfo] = {}

        for group in _PLUGIN_GROUPS:
            for ep in entry_points(group=group):
                if ep.dist is None:
                    continue
                dist = ep.dist
                name: str = dist.metadata["Name"]

                if name not in seen:
                    seen[name] = PluginInfo(
                        name=name,
                        version=dist.version,
                        description=dist.metadata.get("Summary", ""),
                        author=dist.metadata.get("Author", ""),
                        entry_point_groups=[group],
                        homepage=dist.metadata.get("Home-page", ""),
                    )
                elif group not in seen[name].entry_point_groups:
                    seen[name].entry_point_groups.append(group)

        return sorted(seen.values(), key=lambda p: p.name)

    def get_plugin(self, name: str) -> PluginInfo | None:
        """Return the PluginInfo for *name*, or None if not found."""
        for p in self.list_plugins():
            if p.name.lower() == name.lower():
                return p
        return None

    def install(self, package_name: str) -> tuple[bool, str]:
        """Install *package_name* via pip. Returns (success, combined output)."""
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output

    def remove(self, package_name: str) -> tuple[bool, str]:
        """Uninstall *package_name* via pip. Returns (success, combined output)."""
        result = subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", package_name],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
