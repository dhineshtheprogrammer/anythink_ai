"""Tests for session file locking."""

from __future__ import annotations

import threading
from pathlib import Path

from anythink.session.locking import SessionLock


class TestSessionLock:
    def test_lock_acquires_and_releases(self, tmp_path: Path) -> None:
        path = tmp_path / "session.yaml"
        with SessionLock(path):
            assert (tmp_path / "session.yaml.lock").exists()
        # Lock file may persist; what matters is no exception was raised

    def test_nested_locks_same_path_block(self, tmp_path: Path) -> None:
        """A second thread should not be able to acquire the lock simultaneously."""
        path = tmp_path / "s.yaml"
        results: list[bool] = []

        def _try_lock() -> None:
            try:
                with SessionLock(path, timeout=0.1):
                    results.append(True)
            except Exception:
                results.append(False)

        with SessionLock(path):
            t = threading.Thread(target=_try_lock)
            t.start()
            t.join()

        assert results == [False]

    def test_sequential_locks_on_same_path_succeed(self, tmp_path: Path) -> None:
        path = tmp_path / "s.yaml"
        with SessionLock(path):
            pass
        with SessionLock(path):
            pass  # should not raise


class TestSlugify:
    def test_basic_slug(self) -> None:
        from anythink.session.manager import slugify

        assert slugify("BERT vs GPT research") == "bert-vs-gpt-research"

    def test_strips_special_chars(self) -> None:
        from anythink.session.manager import slugify

        assert slugify("Hello, World!") == "hello-world"

    def test_collapses_spaces(self) -> None:
        from anythink.session.manager import slugify

        assert slugify("a  b   c") == "a-b-c"

    def test_truncates_at_80(self) -> None:
        from anythink.session.manager import slugify

        long = "word " * 30
        result = slugify(long)
        assert len(result) <= 80

    def test_empty_string(self) -> None:
        from anythink.session.manager import slugify

        assert slugify("") == ""

    def test_auto_session_name(self) -> None:
        from anythink.session.manager import auto_session_name

        name = auto_session_name("gpt-4o")
        assert "Session" in name
        assert "gpt-4o" in name
