"""Tests for workflow/log.py — WorkflowLogger."""

from __future__ import annotations

from pathlib import Path

import pytest

from anythink.workflow.log import WorkflowLogger
from anythink.workflow.models import (
    Stage,
    StageResult,
    StageType,
    WorkflowLog,
    WorkflowPlan,
    WorkflowStatus,
)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_plan(name: str = "test-plan") -> WorkflowPlan:
    return WorkflowPlan(
        name=name,
        trigger="Do something useful",
        stages=[Stage(id="stage_1", type=StageType.MCP_CALL)],
        models_used=["local-summarizer"],
        mcp_servers_used=["gmail"],
    )


def make_result(
    stage_id: str = "stage_1",
    stage_type: StageType = StageType.MCP_CALL,
    **kwargs: object,
) -> StageResult:
    return StageResult(stage_id=stage_id, stage_type=stage_type, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# WorkflowLogger.begin
# ---------------------------------------------------------------------------


class TestBegin:
    def test_creates_log_with_correct_fields(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        plan = make_plan("my-flow")
        log = logger.begin(plan)
        assert log.workflow_name == "my-flow"
        assert log.trigger == "Do something useful"
        assert log.status == WorkflowStatus.RUNNING
        assert log.stage_records == []
        assert log.final_output == ""

    def test_copies_models_and_servers(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        plan = make_plan()
        log = logger.begin(plan)
        assert "local-summarizer" in log.models_used
        assert "gmail" in log.mcp_servers_called


# ---------------------------------------------------------------------------
# WorkflowLogger.record_stage
# ---------------------------------------------------------------------------


class TestRecordStage:
    def test_appends_to_stage_records(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan())
        result = make_result(model_alias="local-summarizer")
        logger.record_stage(log, result)
        assert len(log.stage_records) == 1

    def test_updates_models_used(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan())
        log.models_used.clear()
        result = make_result(
            stage_type=StageType.LLM_SPECIALIST,
            model_alias="new-model",
        )
        logger.record_stage(log, result)
        assert "new-model" in log.models_used

    def test_no_duplicate_models(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan())
        for _ in range(3):
            logger.record_stage(log, make_result(stage_type=StageType.LLM_SPECIALIST, model_alias="m"))
        assert log.models_used.count("m") == 1

    def test_updates_mcp_servers_from_tool_name(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan())
        log.mcp_servers_called.clear()
        result = make_result(tool_name="filesystem.write_file")
        logger.record_stage(log, result)
        assert "filesystem" in log.mcp_servers_called


# ---------------------------------------------------------------------------
# WorkflowLogger.record_loop_iteration
# ---------------------------------------------------------------------------


class TestRecordLoopIteration:
    def test_appends_iteration(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan())
        logger.record_loop_iteration(log, "email_1", 0, 1.5, "Summarized ok")
        assert len(log.loop_iterations) == 1
        assert log.loop_iterations[0].item_id == "email_1"
        assert log.loop_iterations[0].duration_s == pytest.approx(1.5)

    def test_skipped_iteration(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan())
        logger.record_loop_iteration(log, "email_2", 1, 0.0, "", skipped=True)
        assert log.loop_iterations[0].skipped is True


# ---------------------------------------------------------------------------
# WorkflowLogger.finalize
# ---------------------------------------------------------------------------


class TestFinalize:
    def test_writes_log_file(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan("my-flow"))
        path = logger.finalize(log, WorkflowStatus.COMPLETED, "All done.")
        assert path.exists()
        assert path.suffix == ".log"

    def test_log_filename_contains_workflow_name(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan("email-summary"))
        path = logger.finalize(log, WorkflowStatus.COMPLETED, "Done")
        assert "email-summary" in path.name

    def test_log_sets_end_time_and_status(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan())
        logger.finalize(log, WorkflowStatus.ABORTED, "")
        assert log.end_time is not None
        assert log.status == WorkflowStatus.ABORTED

    def test_log_content_contains_sections(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan("my-flow"))
        result = make_result(raw_content="email list returned")
        logger.record_stage(log, result)
        path = logger.finalize(log, WorkflowStatus.COMPLETED, "Final answer here.")
        content = path.read_text(encoding="utf-8")
        assert "FINAL OUTPUT" in content
        assert "Final answer here." in content
        assert "stage_1" in content
        assert "email list returned" in content

    def test_log_content_includes_loop_summary(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan())
        logger.record_loop_iteration(log, "email_1", 0, 1.2, "done")
        logger.record_loop_iteration(log, "email_2", 1, 0.0, "", skipped=True)
        path = logger.finalize(log, WorkflowStatus.COMPLETED, "")
        content = path.read_text(encoding="utf-8")
        assert "LOOP SUMMARY" in content
        assert "email_1" in content
        assert "SKIP" in content

    def test_log_content_includes_errors(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan())
        result = make_result(error="Connection refused")
        logger.record_stage(log, result)
        path = logger.finalize(log, WorkflowStatus.FAILED, "")
        content = path.read_text(encoding="utf-8")
        assert "ERRORS" in content
        assert "Connection refused" in content

    def test_creates_log_dir_if_missing(self, tmp_path: "pytest.fixture") -> None:
        log_dir = tmp_path / "deep" / "nested" / "logs"
        logger = WorkflowLogger(log_dir)
        log = logger.begin(make_plan())
        path = logger.finalize(log, WorkflowStatus.COMPLETED, "")
        assert path.exists()


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


class TestListing:
    def test_list_logs_empty_dir(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        assert logger.list_logs() == []
        assert logger.latest_log() is None

    def test_list_logs_returns_most_recent_first(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        for name in ["alpha", "beta", "gamma"]:
            log = logger.begin(make_plan(name))
            logger.finalize(log, WorkflowStatus.COMPLETED, "")
        logs = logger.list_logs()
        assert len(logs) == 3
        # Sorted reverse — last finalized first
        assert logs[0].name > logs[1].name

    def test_latest_log(self, tmp_path: "pytest.fixture") -> None:
        logger = WorkflowLogger(tmp_path / "logs")
        log = logger.begin(make_plan("only-one"))
        path = logger.finalize(log, WorkflowStatus.COMPLETED, "")
        assert logger.latest_log() == path
