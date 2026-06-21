"""Spend tracking for Anythink — records estimated cost per LLM response."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from anythink.exceptions import SpendError
from anythink.providers.base import TokenUsage


@dataclass
class SpendRecord:
    """One recorded LLM response with its token usage and estimated cost."""

    session_id: str
    model_id: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "model_id": self.model_id,
            "provider": self.provider,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpendRecord:
        return cls(
            session_id=data["session_id"],
            model_id=data["model_id"],
            provider=data["provider"],
            prompt_tokens=int(data.get("prompt_tokens", 0)),
            completion_tokens=int(data.get("completion_tokens", 0)),
            cost_usd=float(data.get("cost_usd", 0.0)),
            recorded_at=datetime.fromisoformat(data["recorded_at"]),
        )


class SpendTracker:
    """Persistent spend log backed by spend.yaml."""

    def __init__(self, log_file: Path) -> None:
        self._path = log_file
        self._records: list[SpendRecord] | None = None
        self._dirty = False

    def _load(self) -> list[SpendRecord]:
        if self._records is not None:
            return self._records

        if not self._path.exists():
            self._records = []
            return self._records

        try:
            raw: list[dict[str, Any]] = yaml.safe_load(self._path.read_text()) or []
        except yaml.YAMLError as e:
            raise SpendError(f"Failed to parse spend.yaml: {e}") from e

        self._records = [SpendRecord.from_dict(r) for r in raw if "session_id" in r]
        return self._records

    def save(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self._load()]
        self._path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        self._dirty = False

    def record(
        self,
        session_id: str,
        model_id: str,
        provider: str,
        usage: TokenUsage,
        cost_usd: float,
    ) -> SpendRecord:
        rec = SpendRecord(
            session_id=session_id,
            model_id=model_id,
            provider=provider,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=cost_usd,
        )
        self._load().append(rec)
        self._dirty = True
        self.save()
        return rec

    def all_records(self) -> list[SpendRecord]:
        return list(self._load())

    def session_total(self, session_id: str) -> float:
        return sum(r.cost_usd for r in self._load() if r.session_id == session_id)

    def daily_total(self, date: datetime | None = None) -> float:
        target = (date or datetime.now(UTC)).date()
        return sum(
            r.cost_usd for r in self._load() if r.recorded_at.astimezone(UTC).date() == target
        )

    def monthly_total(self, year: int | None = None, month: int | None = None) -> float:
        now = datetime.now(UTC)
        y = year if year is not None else now.year
        m = month if month is not None else now.month
        return sum(
            r.cost_usd
            for r in self._load()
            if r.recorded_at.astimezone(UTC).year == y and r.recorded_at.astimezone(UTC).month == m
        )

    def by_model(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for r in self._load():
            totals[r.model_id] = totals.get(r.model_id, 0.0) + r.cost_usd
        return totals

    def by_provider(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for r in self._load():
            totals[r.provider] = totals.get(r.provider, 0.0) + r.cost_usd
        return totals

    def prune(self, keep_days: int = 90) -> None:
        """Silently remove records older than ``keep_days`` days."""
        cutoff = datetime.now(UTC).timestamp() - keep_days * 86400
        records = self._load()
        pruned = [r for r in records if r.recorded_at.timestamp() >= cutoff]
        if len(pruned) < len(records):
            self._records = pruned
            self._dirty = True
            self.save()
