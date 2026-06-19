"""SessionManager: save, load, list, delete, and find sessions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from anythink.exceptions import SessionError
from anythink.session.models import Session


class SessionManager:
    """Persists sessions as YAML files under *sessions_dir*."""

    def __init__(self, sessions_dir: Path) -> None:
        self._dir = sessions_dir

    def save(self, session: Session) -> None:
        """Write (or overwrite) a session file. Updates session.updated_at in place."""
        self._dir.mkdir(parents=True, exist_ok=True)
        session.updated_at = datetime.utcnow()
        path = self._dir / f"{session.id}.yaml"
        path.write_text(
            yaml.dump(session.to_dict(), default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    def load(self, session_id: str) -> Session:
        """Load a session by its exact ID. Raises SessionError if not found."""
        path = self._dir / f"{session_id}.yaml"
        if not path.exists():
            raise SessionError(
                f"Session '{session_id}' not found.",
                user_message=f"No session with ID '{session_id}' exists.",
            )
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise SessionError(
                f"Failed to parse session '{session_id}': {exc}",
                user_message=f"Session file for '{session_id}' is corrupt.",
            ) from exc
        return Session.from_dict(raw)

    def list_sessions(self) -> list[Session]:
        """Return all sessions sorted by most-recently updated first.

        Corrupt files are silently skipped.
        """
        if not self._dir.exists():
            return []
        sessions: list[Session] = []
        for path in sorted(self._dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                sessions.append(Session.from_dict(raw))
            except Exception:
                continue
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)

    def delete(self, session_id: str) -> None:
        """Delete a session file. Raises SessionError if not found."""
        path = self._dir / f"{session_id}.yaml"
        if not path.exists():
            raise SessionError(
                f"Session '{session_id}' not found.",
                user_message=f"No session with ID '{session_id}' exists.",
            )
        path.unlink()

    def find_by_name_or_id(self, query: str) -> Session | None:
        """Search by exact name, then by ID prefix. Returns None if not found."""
        sessions = self.list_sessions()
        for s in sessions:
            if s.name and s.name == query:
                return s
        for s in sessions:
            if s.id.startswith(query):
                return s
        return None
