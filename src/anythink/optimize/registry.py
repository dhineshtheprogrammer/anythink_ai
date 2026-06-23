"""Model Capability Registry — bundled base + user-editable overlay."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from anythink.optimize.models import ModelCapability


def _load_bundled_registry(bundled_path: Path | None) -> dict[str, ModelCapability]:
    """Load the bundled model_registry.json shipped with the package."""
    if bundled_path is not None and bundled_path.exists():
        raw_text = bundled_path.read_text(encoding="utf-8")
    else:
        # Fallback: load from package data via importlib.resources
        try:
            ref = resources.files("anythink.data").joinpath("model_registry.json")
            raw_text = ref.read_text(encoding="utf-8")
        except Exception:
            return {}

    try:
        data: dict[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError:
        return {}

    result: dict[str, ModelCapability] = {}
    for entry in data.get("models", []):
        try:
            cap = ModelCapability.from_dict(entry)
            result[cap.id] = cap
        except (KeyError, ValueError):
            continue
    return result


class ModelCapabilityRegistry:
    """Merged view of bundled base registry + user overlay.

    User entries always win over bundled entries on any field conflict.
    Only the user overlay is ever written; bundled data is read-only.
    """

    def __init__(self, bundled_path: Path | None, user_path: Path) -> None:
        self._bundled_path = bundled_path
        self._user_path = user_path
        self._data: dict[str, ModelCapability] | None = None
        self._user_data: dict[str, ModelCapability] | None = None
        self._dirty = False

    # ── Internal loading ──────────────────────────────────────────────────

    def _load_user(self) -> dict[str, ModelCapability]:
        if self._user_data is not None:
            return self._user_data

        if not self._user_path.exists():
            self._user_data = {}
            return self._user_data

        try:
            raw: dict[str, Any] = json.loads(self._user_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._user_data = {}
            return self._user_data

        result: dict[str, ModelCapability] = {}
        for entry in raw.get("models", []):
            try:
                cap = ModelCapability.from_dict(entry)
                result[cap.id] = cap
            except (KeyError, ValueError):
                continue
        self._user_data = result
        return self._user_data

    def _load(self) -> dict[str, ModelCapability]:
        if self._data is not None:
            return self._data

        bundled = _load_bundled_registry(self._bundled_path)
        user = self._load_user()

        # Merge: start with bundled, then overlay user entries (user wins)
        merged = {**bundled, **user}
        self._data = merged
        return self._data

    # ── Public read API ───────────────────────────────────────────────────

    def get(self, model_id: str) -> ModelCapability | None:
        return self._load().get(model_id)

    def all(self) -> list[ModelCapability]:
        return list(self._load().values())

    def available_online(self) -> list[ModelCapability]:
        return [cap for cap in self._load().values() if cap.tier == "free-api"]

    def available_offline(self) -> list[ModelCapability]:
        return [cap for cap in self._load().values() if cap.tier == "local"]

    def by_strength(self, category: str) -> list[ModelCapability]:
        return [cap for cap in self._load().values() if category in cap.strength_categories]

    # ── User overlay mutation ─────────────────────────────────────────────

    def add_user_entry(self, cap: ModelCapability) -> None:
        """Add or replace an entry in the user overlay."""
        user = self._load_user()
        user[cap.id] = cap
        # Invalidate merged cache so next _load() re-merges
        self._data = None
        self._dirty = True
        self.save_user()

    def remove_user_entry(self, model_id: str) -> None:
        """Remove a user-added entry. Bundled entries are not affected."""
        user = self._load_user()
        if model_id not in user:
            return
        del user[model_id]
        self._data = None
        self._dirty = True
        self.save_user()

    def reset_to_bundled(self, model_id: str) -> None:
        """Remove any user override for a bundled model ID."""
        self.remove_user_entry(model_id)

    # ── Persistence ───────────────────────────────────────────────────────

    def save_user(self) -> None:
        if not self._dirty:
            return
        user = self._load_user()
        self._user_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"models": [cap.to_dict() for cap in user.values()]}
        self._user_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._dirty = False

    # ── Import / Export ───────────────────────────────────────────────────

    def export_json(self, path: Path) -> None:
        data = {
            "_registry_version": "4.0.0",
            "models": [cap.to_dict() for cap in self._load().values()],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def import_json(self, path: Path) -> int:
        """Import entries from a JSON file into the user overlay. Returns count imported."""
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        for entry in raw.get("models", []):
            try:
                cap = ModelCapability.from_dict(entry)
                self.add_user_entry(cap)
                count += 1
            except (KeyError, ValueError):
                continue
        return count
