"""TemporaryResponseStore — in-memory per-turn store for specialist responses."""

from __future__ import annotations

from anythink.smart.models import SpecialistResponse


class TemporaryResponseStore:
    """Holds all specialist responses for the current MMAE turn.

    Cleared by clear() at the start of each new turn. The combiner receives
    the full ordered list from all()."""

    def __init__(self) -> None:
        self._entries: list[SpecialistResponse] = []

    def add(self, entry: SpecialistResponse) -> None:
        self._entries.append(entry)

    def all(self) -> list[SpecialistResponse]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
