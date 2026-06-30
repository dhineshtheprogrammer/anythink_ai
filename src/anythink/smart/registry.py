"""SmartRegistry — persistent YAML-backed category-to-model mapping for MMAE."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import yaml

from anythink.smart.categories import CATEGORIES, TAG_TO_CATEGORY

_SLOT_ROUTER = "router"
_SLOT_COMBINER = "combiner"
_SLOT_FORMATTER = "formatter"

_DEFAULT_YAML: dict[str, Any] = {
    "categories": {k: "" for k in CATEGORIES},
    "slots": {_SLOT_ROUTER: "", _SLOT_COMBINER: "", _SLOT_FORMATTER: ""},
}


class SmartRegistry:
    """Maps MMAE category keys to model aliases and manages special pipeline slots.

    Backed by a YAML file at the given path. Missing or empty entries are treated
    as unset; callers should fall back to the session default model in that case.
    """

    def __init__(self, registry_file: Path) -> None:
        self._path = registry_file
        self._categories: dict[str, str] = {k: "" for k in CATEGORIES}
        self._slots: dict[str, str] = {
            _SLOT_ROUTER: "",
            _SLOT_COMBINER: "",
            _SLOT_FORMATTER: "",
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load registry from YAML file; silently initialise if absent."""
        if not self._path.exists():
            return
        try:
            raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        except Exception:
            return
        cats = raw.get("categories") or {}
        for key in CATEGORIES:
            self._categories[key] = cats.get(key, "") or ""
        slots = raw.get("slots") or {}
        for slot in (_SLOT_ROUTER, _SLOT_COMBINER, _SLOT_FORMATTER):
            self._slots[slot] = slots.get(slot, "") or ""

    def save(self) -> None:
        """Persist current state to YAML."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "categories": dict(self._categories),
            "slots": dict(self._slots),
        }
        self._path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

    # ------------------------------------------------------------------
    # Category CRUD
    # ------------------------------------------------------------------

    def get(self, category: str) -> str | None:
        """Return primary model alias for a category, or None if unset."""
        val = self._categories.get(category, "")
        return val or None

    def set(self, category: str, alias: str) -> None:
        if category not in CATEGORIES:
            raise ValueError(f"Unknown MMAE category: {category!r}")
        self._categories[category] = alias
        self.save()

    def reset(self, category: str) -> None:
        """Clear the user override for one category (reverts to auto-populated default)."""
        if category not in CATEGORIES:
            raise ValueError(f"Unknown MMAE category: {category!r}")
        self._categories[category] = ""
        self.save()

    def reset_all(self) -> None:
        """Clear all category assignments."""
        for key in self._categories:
            self._categories[key] = ""
        self.save()

    def all_assignments(self) -> dict[str, str]:
        """Return the full category → alias mapping (unset entries have empty string)."""
        return dict(self._categories)

    def has_any_assignments(self) -> bool:
        """Return True if at least one category or slot has a non-empty assignment."""
        return any(self._categories.values()) or any(self._slots.values())

    # ------------------------------------------------------------------
    # Special pipeline slots
    # ------------------------------------------------------------------

    def get_router(self) -> str | None:
        return self._slots[_SLOT_ROUTER] or None

    def set_router(self, alias: str) -> None:
        self._slots[_SLOT_ROUTER] = alias
        self.save()

    def get_combiner(self) -> str | None:
        return self._slots[_SLOT_COMBINER] or None

    def set_combiner(self, alias: str) -> None:
        self._slots[_SLOT_COMBINER] = alias
        self.save()

    def get_formatter(self) -> str | None:
        return self._slots[_SLOT_FORMATTER] or None

    def set_formatter(self, alias: str) -> None:
        self._slots[_SLOT_FORMATTER] = alias
        self.save()

    # ------------------------------------------------------------------
    # Auto-populate from MMWE WorkflowCapabilityRegistry
    # ------------------------------------------------------------------

    def auto_populate(self, workflow_registry: Any) -> None:
        """Seed category assignments from the MMWE WorkflowCapabilityRegistry.

        For each MMAE category, finds the alias whose tag set has the highest
        overlap with the TAG_TO_CATEGORY mappings for that category. Only assigns
        if the category currently has no alias set.
        """
        # Build inverse: category → set of relevant MMWE tags
        cat_tags: dict[str, set[str]] = {k: set() for k in CATEGORIES}
        for tag, cat in TAG_TO_CATEGORY.items():
            cat_tags[cat].add(tag)

        for cat_key, relevant_tags in cat_tags.items():
            if self._categories.get(cat_key):
                continue  # keep existing assignment
            best_alias = ""
            best_score = -1
            for tag in relevant_tags:
                with contextlib.suppress(Exception):
                    aliases = workflow_registry.aliases_with_tag(tag)
                    for alias in aliases:
                        all_tags: set[str] = set()
                        with contextlib.suppress(Exception):
                            all_tags = set(workflow_registry.get_tags(alias))
                        score = len(relevant_tags & all_tags)
                        if score > best_score:
                            best_score = score
                            best_alias = alias
            if best_alias:
                self._categories[cat_key] = best_alias

        self.save()
