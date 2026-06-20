"""Exclusive file lock for concurrent session write safety."""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

from filelock import FileLock


class SessionLock:
    """Thin context manager that holds an exclusive lock beside a session file.

    The lock file is placed at ``<session_path>.lock`` so it is always
    co-located with the session data and cleaned up on a normal exit.
    Raises ``filelock.Timeout`` if the lock cannot be acquired within
    *timeout* seconds.
    """

    def __init__(self, session_path: Path, *, timeout: float = 10.0) -> None:
        self._lock = FileLock(str(session_path) + ".lock", timeout=timeout)

    def __enter__(self) -> SessionLock:
        self._lock.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._lock.release()
