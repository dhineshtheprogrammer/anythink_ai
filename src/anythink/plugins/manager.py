"""Plugin manager: discovers installed plugins and wraps pip install/uninstall."""

from __future__ import annotations

import subprocess  # nosec B404 - used only to shell out to pip with fixed, list-form args
import sys
from importlib.metadata import entry_points
from typing import Any  # noqa: F401 — used in V4 hook type hints

from anythink.plugins.models import PluginInfo

_PLUGIN_GROUPS = [
    "anythink.providers",
    "anythink.search_backends",
    "anythink.slash_commands",
    # V4 MMOS hook groups
    "anythink.pre_routing_hooks",
    "anythink.post_phase_hooks",
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
                meta: Any = dist.metadata
                name: str = meta["Name"]

                if name not in seen:
                    seen[name] = PluginInfo(
                        name=name,
                        version=dist.version,
                        description=meta.get("Summary", ""),
                        author=meta.get("Author", ""),
                        entry_point_groups=[group],
                        homepage=meta.get("Home-page", ""),
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
        result = subprocess.run(  # nosec B603 - args are list-form; package_name is user-supplied
            [sys.executable, "-m", "pip", "install", package_name],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output

    def remove(self, package_name: str) -> tuple[bool, str]:
        """Uninstall *package_name* via pip. Returns (success, combined output)."""
        result = subprocess.run(  # nosec B603 - args are list-form; package_name is user-supplied
            [sys.executable, "-m", "pip", "uninstall", "-y", package_name],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output

    # ── V4 MMOS hook points ───────────────────────────────────────────────

    def invoke_pre_routing_hooks(
        self,
        query: str,
        intent: dict[str, Any],
    ) -> dict[str, Any]:
        """Call all registered pre_routing_hook entry points.

        Each hook receives (query, intent_dict) and may return a dict of
        routing hints that are merged into the final context. Failures in
        individual hooks are silently swallowed so they never block queries.
        """
        hints: dict[str, Any] = {}
        for ep in entry_points(group="anythink.pre_routing_hooks"):
            try:
                hook_fn = ep.load()
                result = hook_fn(query, intent)
                if isinstance(result, dict):
                    hints.update(result)
            except Exception:  # nosec B110 - plugin failures must not break queries
                pass
        return hints

    def invoke_post_phase_hooks(
        self,
        phase: dict[str, Any],
        output: str,
    ) -> str:
        """Call all registered post_phase_hook entry points.

        Each hook receives (phase_dict, output_text) and may return a
        transformed output string. Failures fall back to the original output.
        """
        result = output
        for ep in entry_points(group="anythink.post_phase_hooks"):
            try:
                hook_fn = ep.load()
                transformed = hook_fn(phase, result)
                if isinstance(transformed, str):
                    result = transformed
            except Exception:  # nosec B110 - plugin failures must not break queries
                pass
        return result
