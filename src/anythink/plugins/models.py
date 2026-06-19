"""Plugin metadata model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PluginInfo:
    """Metadata for an installed Anythink plugin package."""

    name: str
    version: str
    description: str
    author: str
    entry_point_groups: list[str] = field(default_factory=list)
    homepage: str = ""
