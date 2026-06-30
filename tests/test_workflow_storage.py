"""Tests for workflow/storage.py — WorkflowStorage."""

from __future__ import annotations

import pytest

from anythink.exceptions import WorkflowError
from anythink.workflow.models import Stage, StageType, WorkflowPlan
from anythink.workflow.storage import WorkflowStorage, _slugify


# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self) -> None:
        assert _slugify("email summary") == "email-summary"

    def test_special_chars_stripped(self) -> None:
        assert _slugify("email/summary!") == "emailsummary"

    def test_max_length(self) -> None:
        assert len(_slugify("a" * 200)) <= 80

    def test_empty_fallback(self) -> None:
        assert _slugify("") == "workflow"
        assert _slugify("!!!") == "workflow"


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_plan(name: str = "test-plan") -> WorkflowPlan:
    return WorkflowPlan(
        name=name,
        trigger="Do something",
        stages=[Stage(id="stage_1", type=StageType.MCP_CALL, tool_name="fs.read_file")],
        models_used=["local-summarizer"],
        mcp_servers_used=["filesystem"],
    )


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------


class TestWorkflowStorage:
    def test_save_and_load(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        plan = make_plan("email-summary")
        storage.save("email-summary", plan)
        loaded = storage.load("email-summary")
        assert loaded.name == "email-summary"
        assert loaded.trigger == "Do something"
        assert len(loaded.stages) == 1
        assert loaded.stages[0].tool_name == "fs.read_file"

    def test_load_missing_raises(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        with pytest.raises(WorkflowError, match="not found"):
            storage.load("nonexistent")

    def test_load_corrupt_raises(self, tmp_path: "pytest.fixture") -> None:
        wdir = tmp_path / "workflows"
        wdir.mkdir()
        (wdir / "bad.yaml").write_text("{corrupt: [yaml", encoding="utf-8")
        storage = WorkflowStorage(wdir)
        with pytest.raises(WorkflowError):
            storage.load("bad")

    def test_save_creates_parent_dirs(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "deep" / "nested" / "workflows")
        storage.save("test", make_plan("test"))
        assert storage.exists("test")

    def test_overwrite(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        storage.save("p", make_plan("p"))
        updated = make_plan("p")
        updated.trigger = "Updated trigger"
        storage.save("p", updated)
        assert storage.load("p").trigger == "Updated trigger"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_removes_file(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        storage.save("del-me", make_plan("del-me"))
        assert storage.exists("del-me")
        storage.delete("del-me")
        assert not storage.exists("del-me")

    def test_delete_also_removes_bak(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        storage.save("del-me", make_plan("del-me"))
        storage.backup("del-me")
        storage.delete("del-me")
        assert not storage.exists("del-me")
        bak = tmp_path / "workflows" / "del-me.yaml.bak"
        assert not bak.exists()

    def test_delete_missing_raises(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        with pytest.raises(WorkflowError, match="not found"):
            storage.delete("ghost")


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


class TestRename:
    def test_rename_basic(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        storage.save("old-name", make_plan("old-name"))
        storage.rename("old-name", "new-name")
        assert not storage.exists("old-name")
        assert storage.exists("new-name")
        loaded = storage.load("new-name")
        assert loaded.name == "new-name"

    def test_rename_missing_source_raises(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        with pytest.raises(WorkflowError, match="not found"):
            storage.rename("ghost", "target")

    def test_rename_to_existing_raises(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        storage.save("source", make_plan("source"))
        storage.save("target", make_plan("target"))
        with pytest.raises(WorkflowError, match="already exists"):
            storage.rename("source", "target")


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


class TestBackup:
    def test_backup_creates_bak_file(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        storage.save("my-flow", make_plan("my-flow"))
        storage.backup("my-flow")
        bak = tmp_path / "workflows" / "my-flow.yaml.bak"
        assert bak.exists()

    def test_backup_noop_for_missing(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        storage.backup("nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


class TestListing:
    def test_list_names_empty(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        assert storage.list_names() == []

    def test_list_names_alphabetical(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        for n in ["zebra", "apple", "mango"]:
            storage.save(n, make_plan(n))
        assert storage.list_names() == ["apple", "mango", "zebra"]

    def test_list_names_excludes_bak(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        storage.save("real", make_plan("real"))
        storage.backup("real")
        names = storage.list_names()
        assert "real" in names
        assert all("bak" not in n for n in names)

    def test_list_names_nonexistent_dir(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "no-such-dir")
        assert storage.list_names() == []

    def test_list_summaries(self, tmp_path: "pytest.fixture") -> None:
        storage = WorkflowStorage(tmp_path / "workflows")
        storage.save("flow-a", make_plan("flow-a"))
        summaries = storage.list_summaries()
        assert len(summaries) == 1
        assert summaries[0]["name"] == "flow-a"
        assert summaries[0]["stage_count"] == 1

    def test_list_summaries_skips_corrupt(self, tmp_path: "pytest.fixture") -> None:
        wdir = tmp_path / "workflows"
        wdir.mkdir()
        (wdir / "corrupt.yaml").write_text("{{bad", encoding="utf-8")
        storage = WorkflowStorage(wdir)
        assert storage.list_summaries() == []
