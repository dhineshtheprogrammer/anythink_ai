"""Routing rules loader — user-defined YAML routing rules for the deterministic engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class RoutingRule:
    """A single user-defined routing rule."""

    name: str
    condition: str   # simple DSL: "category == 'Coding' and tokens > 1000"
    action: str      # e.g. "strategy=ensemble" | "model=groq/llama3-70b" | "plan=true"
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "condition": self.condition,
            "action": self.action,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutingRule:
        return cls(
            name=str(data["name"]),
            condition=str(data.get("condition", "")),
            action=str(data.get("action", "")),
            priority=int(data.get("priority", 0)),
        )


class RoutingRulesLoader:
    """Loads user-defined routing rules from routing_rules.yaml.

    Rules are evaluated by the RoutingEngine after the deterministic
    keyword pass and before the meta-LLM fallback.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._rules: list[RoutingRule] | None = None

    def _load(self) -> list[RoutingRule]:
        if self._rules is not None:
            return self._rules

        if not self._path.exists():
            self._rules = []
            return self._rules

        try:
            raw: list[dict[str, Any]] = yaml.safe_load(self._path.read_text()) or []
        except yaml.YAMLError:
            self._rules = []
            return self._rules

        rules: list[RoutingRule] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            try:
                rules.append(RoutingRule.from_dict(entry))
            except (KeyError, ValueError):
                continue

        self._rules = sorted(rules, key=lambda r: r.priority, reverse=True)
        return self._rules

    def all(self) -> list[RoutingRule]:
        return self._load()

    def evaluate(self, context: dict[str, Any]) -> RoutingRule | None:
        """Return the highest-priority rule whose condition matches *context*, or None.

        The condition is a simple expression evaluated via Python's ``eval``
        against *context*. Only basic comparisons and boolean operators are
        supported. Unknown variables evaluate to ``False`` rather than raising.
        """
        for rule in self._load():
            if not rule.condition:
                continue
            try:
                matched = bool(eval(rule.condition, {"__builtins__": {}}, context))  # noqa: S307
            except Exception:
                matched = False
            if matched:
                return rule
        return None

    def invalidate(self) -> None:
        """Force a reload on the next access (useful after the file changes)."""
        self._rules = None
