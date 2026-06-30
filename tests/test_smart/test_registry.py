"""Tests for smart/registry.py."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anythink.smart.categories import CATEGORIES
from anythink.smart.registry import SmartRegistry


@pytest.fixture()
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / "smart_registry.yaml"


@pytest.fixture()
def reg(registry_path: Path) -> SmartRegistry:
    r = SmartRegistry(registry_path)
    r.load()
    return r


def test_load_missing_file_does_not_raise(registry_path: Path) -> None:
    r = SmartRegistry(registry_path)
    r.load()  # file does not exist — should be silent


def test_get_unset_returns_none(reg: SmartRegistry) -> None:
    assert reg.get("math") is None


def test_has_no_assignments_initially(reg: SmartRegistry) -> None:
    assert reg.has_any_assignments() is False


def test_set_and_get_category(reg: SmartRegistry) -> None:
    reg.set("math", "local-math")
    assert reg.get("math") == "local-math"


def test_set_unknown_category_raises(reg: SmartRegistry) -> None:
    with pytest.raises(ValueError, match="Unknown MMAE category"):
        reg.set("not-a-category", "alias")


def test_reset_category(reg: SmartRegistry) -> None:
    reg.set("code", "coder")
    reg.reset("code")
    assert reg.get("code") is None


def test_reset_unknown_category_raises(reg: SmartRegistry) -> None:
    with pytest.raises(ValueError):
        reg.reset("nonexistent")


def test_reset_all(reg: SmartRegistry) -> None:
    reg.set("math", "m1")
    reg.set("code", "c1")
    reg.reset_all()
    assert reg.get("math") is None
    assert reg.get("code") is None


def test_all_assignments_returns_full_dict(reg: SmartRegistry) -> None:
    reg.set("math", "m1")
    assignments = reg.all_assignments()
    assert "math" in assignments
    assert assignments["math"] == "m1"
    for key in CATEGORIES:
        assert key in assignments


def test_all_assignments_returns_copy(reg: SmartRegistry) -> None:
    reg.set("math", "m1")
    assignments = reg.all_assignments()
    assignments["math"] = "different"
    assert reg.get("math") == "m1"


def test_router_slot(reg: SmartRegistry) -> None:
    assert reg.get_router() is None
    reg.set_router("router-alias")
    assert reg.get_router() == "router-alias"


def test_combiner_slot(reg: SmartRegistry) -> None:
    assert reg.get_combiner() is None
    reg.set_combiner("combiner-alias")
    assert reg.get_combiner() == "combiner-alias"


def test_formatter_slot(reg: SmartRegistry) -> None:
    assert reg.get_formatter() is None
    reg.set_formatter("fmt-alias")
    assert reg.get_formatter() == "fmt-alias"


def test_has_assignments_after_slot_set(reg: SmartRegistry) -> None:
    assert reg.has_any_assignments() is False
    reg.set_router("router")
    assert reg.has_any_assignments() is True


def test_save_and_reload(registry_path: Path) -> None:
    r1 = SmartRegistry(registry_path)
    r1.load()
    r1.set("math", "math-model")
    r1.set_router("my-router")

    r2 = SmartRegistry(registry_path)
    r2.load()
    assert r2.get("math") == "math-model"
    assert r2.get_router() == "my-router"


def test_auto_populate_from_workflow_registry(registry_path: Path) -> None:
    workflow_reg = MagicMock()
    workflow_reg.aliases_with_tag.side_effect = lambda tag: (
        ["coder-model"] if tag == "code" else ["general-model"]
    )
    workflow_reg.get_tags.side_effect = lambda alias: (
        ["code", "code-review"] if alias == "coder-model" else ["general"]
    )

    r = SmartRegistry(registry_path)
    r.load()
    r.auto_populate(workflow_reg)

    # code category should have coder-model (highest tag overlap)
    assert r.get("code") == "coder-model"
    # general category gets general-model
    assert r.get("general") == "general-model"


def test_auto_populate_skips_existing(registry_path: Path) -> None:
    workflow_reg = MagicMock()
    workflow_reg.aliases_with_tag.return_value = ["auto-model"]
    workflow_reg.get_tags.return_value = ["code"]

    r = SmartRegistry(registry_path)
    r.load()
    r.set("code", "my-coder")  # pre-existing assignment
    r.auto_populate(workflow_reg)

    # Should not overwrite the existing assignment
    assert r.get("code") == "my-coder"


def test_auto_populate_handles_registry_exception(registry_path: Path) -> None:
    workflow_reg = MagicMock()
    workflow_reg.aliases_with_tag.side_effect = RuntimeError("Registry error")

    r = SmartRegistry(registry_path)
    r.load()
    # Should not raise — gracefully handles errors
    r.auto_populate(workflow_reg)
