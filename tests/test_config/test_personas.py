"""Tests for Persona and PersonaManager."""

from __future__ import annotations

import pytest

from anythink.config.manager import Paths
from anythink.config.personas import Persona, PersonaManager
from anythink.exceptions import ConfigError


def _make_persona(name: str = "python-expert") -> Persona:
    return Persona(name=name, system_prompt="You are a Python expert.")


class TestPersona:
    def test_roundtrip_dict(self) -> None:
        original = _make_persona()
        restored = Persona.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.system_prompt == original.system_prompt

    def test_default_created_at_set(self) -> None:
        from datetime import datetime
        before = datetime.utcnow()
        p = _make_persona()
        after = datetime.utcnow()
        assert before <= p.created_at <= after


class TestPersonaManager:
    def test_empty_when_no_file(self, xdg_dirs: Paths) -> None:
        manager = PersonaManager(xdg_dirs.personas_file)
        assert manager.list_all() == []

    def test_add_and_get(self, xdg_dirs: Paths) -> None:
        manager = PersonaManager(xdg_dirs.personas_file)
        manager.add(_make_persona())
        p = manager.get("python-expert")
        assert p is not None
        assert "Python expert" in p.system_prompt

    def test_add_persists_to_disk(self, xdg_dirs: Paths) -> None:
        manager = PersonaManager(xdg_dirs.personas_file)
        manager.add(_make_persona())
        manager2 = PersonaManager(xdg_dirs.personas_file)
        assert manager2.exists("python-expert")

    def test_remove(self, xdg_dirs: Paths) -> None:
        manager = PersonaManager(xdg_dirs.personas_file)
        manager.add(_make_persona())
        manager.remove("python-expert")
        assert manager.get("python-expert") is None

    def test_remove_nonexistent_raises(self, xdg_dirs: Paths) -> None:
        manager = PersonaManager(xdg_dirs.personas_file)
        with pytest.raises(ConfigError):
            manager.remove("nonexistent")

    def test_exists_false_for_unknown(self, xdg_dirs: Paths) -> None:
        manager = PersonaManager(xdg_dirs.personas_file)
        assert manager.exists("nope") is False

    def test_load_invalid_yaml_raises(self, xdg_dirs: Paths) -> None:
        xdg_dirs.personas_file.write_text("!!bad_type")
        manager = PersonaManager(xdg_dirs.personas_file)
        with pytest.raises(ConfigError):
            manager._load()

    def test_save_when_not_dirty_is_noop(self, xdg_dirs: Paths) -> None:
        manager = PersonaManager(xdg_dirs.personas_file)
        manager._load()
        assert manager._dirty is False
        manager.save()
        assert not xdg_dirs.personas_file.exists()
