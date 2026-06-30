"""WorkflowCapabilityRegistry — per-alias workflow tags and fallback chains."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

import yaml

from anythink.exceptions import WorkflowError

# ---------------------------------------------------------------------------
# Pre-defined tag set (canonical names the planner/router recognise)
# ---------------------------------------------------------------------------

PREDEFINED_TAGS: frozenset[str] = frozenset(
    [
        "planning",
        "reasoning",
        "summarization",
        "extraction",
        "code",
        "code-review",
        "classification",
        "translation",
        "writing",
        "analysis",
        "long-context",
        "multimodal",
        "fast",
        "high-quality",
    ]
)

# ---------------------------------------------------------------------------
# Default tag inference — keyed by glob patterns matching model IDs/aliases
# ---------------------------------------------------------------------------

_TAG_INFERENCE_TABLE: list[tuple[str, list[str]]] = [
    ("mistral*", ["summarization", "extraction"]),
    ("deepseek-coder*", ["code", "code-review"]),
    ("deepseek*", ["reasoning", "code"]),
    ("llama3*", ["planning", "reasoning", "summarization"]),
    ("llama*", ["reasoning", "summarization"]),
    ("gemini*", ["summarization", "reasoning", "multimodal", "long-context"]),
    ("gpt-4*", ["reasoning", "code", "planning", "analysis"]),
    ("gpt-3.5*", ["summarization", "extraction", "fast"]),
    ("claude*", ["reasoning", "writing", "analysis", "long-context"]),
    ("phi*", ["reasoning", "fast"]),
    ("qwen*", ["reasoning", "code"]),
    ("codellama*", ["code", "code-review"]),
    ("solar*", ["summarization", "reasoning"]),
]


def _infer_tags(model_id: str) -> list[str]:
    """Return inferred tags for *model_id* using the pattern table."""
    lower = model_id.lower()
    for pattern, tags in _TAG_INFERENCE_TABLE:
        if fnmatch.fnmatch(lower, pattern):
            return list(tags)
    return []


# ---------------------------------------------------------------------------
# Registry entry
# ---------------------------------------------------------------------------


class _AliasEntry:
    """In-memory representation of one alias in the registry."""

    def __init__(
        self,
        alias: str,
        tags: list[str] | None = None,
        fallback: str = "",
    ) -> None:
        self.alias = alias
        # None means "not yet user-defined — use inferred defaults at read time"
        self._tags: list[str] | None = tags
        self.fallback: str = fallback

    def get_tags(self) -> list[str]:
        if self._tags is not None:
            return list(self._tags)
        return _infer_tags(self.alias)

    def set_tags(self, tags: list[str]) -> None:
        self._tags = list(tags)

    def has_user_tags(self) -> bool:
        return self._tags is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tags": self._tags,  # None → infer at load time
            "fallback": self.fallback,
        }

    @classmethod
    def from_dict(cls, alias: str, data: dict[str, Any]) -> _AliasEntry:
        return cls(
            alias=alias,
            tags=data.get("tags"),  # may be None
            fallback=data.get("fallback", ""),
        )


# ---------------------------------------------------------------------------
# Registry class
# ---------------------------------------------------------------------------


class WorkflowCapabilityRegistry:
    """Stores per-alias workflow capability tags and fallback chains.

    Backed by ``workflow_capabilities.yaml`` in the user config directory.
    Tags set explicitly by the user override inferred defaults entirely.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: dict[str, _AliasEntry] | None = None

    # ------------------------------------------------------------------
    # Internal load / save
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, _AliasEntry]:
        if self._entries is not None:
            return self._entries

        if not self._path.exists():
            self._entries = {}
            return self._entries

        try:
            raw: dict[str, Any] = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise WorkflowError(
                f"Failed to parse workflow_capabilities.yaml: {exc}",
                user_message="The workflow capability file is corrupt and could not be loaded.",
            ) from exc

        self._entries = {
            alias: _AliasEntry.from_dict(alias, entry)
            for alias, entry in raw.items()
        }
        return self._entries

    def save(self) -> None:
        """Persist the current registry to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        entries = self._load()
        data = {alias: entry.to_dict() for alias, entry in sorted(entries.items())}
        self._path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    def _get_or_create(self, alias: str) -> _AliasEntry:
        entries = self._load()
        if alias not in entries:
            entries[alias] = _AliasEntry(alias=alias)
        return entries[alias]

    # ------------------------------------------------------------------
    # Tag management
    # ------------------------------------------------------------------

    def get_tags(self, alias: str) -> list[str]:
        """Return tags for *alias* (user-set or inferred from model name)."""
        entries = self._load()
        if alias in entries:
            return entries[alias].get_tags()
        return _infer_tags(alias)

    def set_tags(self, alias: str, tags: list[str]) -> None:
        """Replace all tags for *alias*. Persists immediately."""
        self._get_or_create(alias).set_tags(tags)
        self.save()

    def add_tag(self, alias: str, tag: str) -> None:
        """Add one tag to *alias* if not already present. Persists immediately."""
        entry = self._get_or_create(alias)
        current = entry.get_tags()
        if tag not in current:
            entry.set_tags(current + [tag])
            self.save()

    def remove_tag(self, alias: str, tag: str) -> None:
        """Remove one tag from *alias*. Persists immediately."""
        entry = self._get_or_create(alias)
        current = entry.get_tags()
        if tag in current:
            entry.set_tags([t for t in current if t != tag])
            self.save()

    # ------------------------------------------------------------------
    # Fallback chain
    # ------------------------------------------------------------------

    def set_fallback(self, alias: str, fallback_alias: str) -> None:
        """Set the fallback alias for *alias*. Persists immediately."""
        self._get_or_create(alias).fallback = fallback_alias
        self.save()

    def get_fallback_chain(self, alias: str) -> list[str]:
        """Return the ordered fallback chain starting from *alias*.

        Cycles are detected and cut after 10 hops to prevent infinite loops.
        """
        chain: list[str] = []
        seen: set[str] = {alias}
        current = alias

        for _ in range(10):
            entries = self._load()
            entry = entries.get(current)
            nxt = entry.fallback if entry else ""
            if not nxt or nxt in seen:
                break
            chain.append(nxt)
            seen.add(nxt)
            current = nxt

        return chain

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def all_aliases(self) -> list[dict[str, Any]]:
        """Return a list of ``{alias, tags, fallback, inferred}`` dicts."""
        entries = self._load()
        return [
            {
                "alias": alias,
                "tags": entry.get_tags(),
                "fallback": entry.fallback,
                "inferred": not entry.has_user_tags(),
            }
            for alias, entry in sorted(entries.items())
        ]

    def has_alias(self, alias: str) -> bool:
        return alias in self._load()

    def aliases_with_tag(self, tag: str) -> list[str]:
        """Return all alias names that carry *tag*."""
        return [
            alias
            for alias, entry in self._load().items()
            if tag in entry.get_tags()
        ]

    def remove_alias(self, alias: str) -> None:
        """Delete an alias entry entirely. No-op if not present."""
        entries = self._load()
        if alias in entries:
            del entries[alias]
            self.save()

    # ------------------------------------------------------------------
    # Public helper
    # ------------------------------------------------------------------

    def infer_tags(self, model_id: str) -> list[str]:
        """Public access to the tag-inference table for a given model ID."""
        return _infer_tags(model_id)
