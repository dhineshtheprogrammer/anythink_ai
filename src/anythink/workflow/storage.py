"""WorkflowStorage — save, load, list, rename, and delete named workflows."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from anythink.exceptions import WorkflowError
from anythink.workflow.models import WorkflowPlan


def _slugify(name: str) -> str:
    """Convert *name* to a filesystem-safe slug for use as a filename."""
    name = name.lower().strip()
    name = re.sub(r"[\s]+", "-", name)
    name = re.sub(r"[^a-z0-9\-]", "", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name[:80] or "workflow"


class WorkflowStorage:
    """Persists named workflows as individual YAML files in *workflows_dir*.

    Each workflow is stored at ``<workflows_dir>/<name>.yaml``.
    Backups (created before edits) are written to ``<name>.yaml.bak``.
    """

    def __init__(self, workflows_dir: Path) -> None:
        self._dir = workflows_dir

    def _path(self, name: str) -> Path:
        return self._dir / f"{_slugify(name)}.yaml"

    def _bak_path(self, name: str) -> Path:
        return self._dir / f"{_slugify(name)}.yaml.bak"

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(self, name: str, plan: WorkflowPlan) -> None:
        """Persist *plan* under *name*. Creates or overwrites the file."""
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(name).write_text(
            yaml.dump(plan.to_dict(), default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    def load(self, name: str) -> WorkflowPlan:
        """Load and return the named workflow. Raises WorkflowError if absent."""
        path = self._path(name)
        if not path.exists():
            raise WorkflowError(
                f"Workflow '{name}' not found.",
                user_message=f"No saved workflow named '{name}'. Use /workflow list to see all.",
            )
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise WorkflowError(
                f"Failed to parse workflow '{name}': {exc}",
                user_message=f"Workflow file for '{name}' is corrupt.",
            ) from exc
        return WorkflowPlan.from_dict(raw)

    def delete(self, name: str) -> None:
        """Delete a saved workflow file. Raises WorkflowError if not found."""
        path = self._path(name)
        if not path.exists():
            raise WorkflowError(
                f"Workflow '{name}' not found.",
                user_message=f"Cannot delete: no workflow named '{name}'.",
            )
        path.unlink()
        bak = self._bak_path(name)
        if bak.exists():
            bak.unlink()

    def rename(self, old_name: str, new_name: str) -> None:
        """Rename a saved workflow. Backs up then replaces. Raises on conflict."""
        old_path = self._path(old_name)
        if not old_path.exists():
            raise WorkflowError(
                f"Workflow '{old_name}' not found.",
                user_message=f"Cannot rename: no workflow named '{old_name}'.",
            )
        new_path = self._path(new_name)
        if new_path.exists():
            raise WorkflowError(
                f"Workflow '{new_name}' already exists.",
                user_message=f"A workflow named '{new_name}' already exists. Delete it first.",
            )
        plan = self.load(old_name)
        plan.name = new_name
        self.save(new_name, plan)
        old_path.unlink()
        old_bak = self._bak_path(old_name)
        if old_bak.exists():
            old_bak.unlink()

    def backup(self, name: str) -> None:
        """Write a ``.bak`` copy of *name*. No-op if the file does not exist."""
        path = self._path(name)
        if not path.exists():
            return
        self._bak_path(name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_names(self) -> list[str]:
        """Return workflow names in alphabetical order (excludes .bak files)."""
        if not self._dir.exists():
            return []
        return sorted(
            p.stem
            for p in self._dir.glob("*.yaml")
            if not p.name.endswith(".bak.yaml")
        )

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def list_summaries(self) -> list[dict[str, object]]:
        """Return lightweight ``{name, trigger, stage_count}`` dicts for all workflows.

        Corrupt files are silently skipped.
        """
        summaries: list[dict[str, object]] = []
        for name in self.list_names():
            try:
                plan = self.load(name)
                summaries.append(
                    {
                        "name": plan.name,
                        "trigger": plan.trigger,
                        "stage_count": len(plan.stages),
                        "models_used": plan.models_used,
                    }
                )
            except WorkflowError:
                continue
        return summaries
