"""Tests for Windows MCP cross-cutting infrastructure."""

from __future__ import annotations

import json
import os
import sys
import unittest.mock as mock
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anythink.config.schema import AppConfig
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.paths import WindowsPathGuard
from anythink.mcp.windows.safety import WindowsSafetyChecker


# ── WindowsAuditLog ─────────────────────────────────────────────────────────


class TestWindowsAuditLog:
    def _make_log(self, tmp_path: Path) -> WindowsAuditLog:
        return WindowsAuditLog(str(tmp_path / "windows_audit.log"))

    def test_log_creates_file(self, tmp_path: Path) -> None:
        log = self._make_log(tmp_path)
        log.log(
            session_id="s1",
            server="windows-filesystem",
            tool="list_dir",
            tier=1,
            arguments={"path": "C:\\Users\\test"},
            confirmation_status="not_required",
            outcome="success",
            duration_s=0.012,
        )
        log_file = tmp_path / "windows_audit.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "list_dir" in content

    def test_log_valid_json(self, tmp_path: Path) -> None:
        log = self._make_log(tmp_path)
        log.log(
            session_id="s2",
            server="windows-clipboard",
            tool="read_clipboard",
            tier=1,
            arguments={},
            confirmation_status="not_required",
            outcome="success",
            duration_s=0.003,
        )
        lines = (tmp_path / "windows_audit.log").read_text(encoding="utf-8").strip().splitlines()
        for line in lines:
            record = json.loads(line)  # must not raise
            assert "tool" in record
            assert "timestamp" in record

    def test_get_recent_returns_records(self, tmp_path: Path) -> None:
        log = self._make_log(tmp_path)
        for i in range(5):
            log.log(
                session_id="s",
                server="windows-system",
                tool="get_cpu_info",
                tier=1,
                arguments={},
                confirmation_status="not_required",
                outcome="success",
                duration_s=float(i) / 100,
            )
        records = log.get_recent(n=3)
        assert len(records) == 3

    def test_get_recent_tool_filter(self, tmp_path: Path) -> None:
        log = self._make_log(tmp_path)
        log.log("s", "windows-system", "get_cpu_info", 1, {}, "not_required", "success", 0.01)
        log.log("s", "windows-clipboard", "read_clipboard", 1, {}, "not_required", "success", 0.01)
        records = log.get_recent(n=10, tool_filter="get_cpu_info")
        assert all(r["tool"] == "get_cpu_info" for r in records)

    def test_clear_empties_log(self, tmp_path: Path) -> None:
        log = self._make_log(tmp_path)
        log.log("s", "windows-system", "get_cpu_info", 1, {}, "not_required", "success", 0.01)
        log.clear()
        assert (tmp_path / "windows_audit.log").read_text(encoding="utf-8") == ""

    def test_export_to_text(self, tmp_path: Path) -> None:
        log = self._make_log(tmp_path)
        log.log("s", "windows-system", "get_ram_info", 1, {}, "not_required", "success", 0.02)
        export_path = str(tmp_path / "export.txt")
        log.export_to_text(export_path)
        assert Path(export_path).exists()
        text = Path(export_path).read_text(encoding="utf-8")
        assert "get_ram_info" in text


# ── WindowsPathGuard ────────────────────────────────────────────────────────


class TestWindowsPathGuard:
    def _make_guard(self, tmp_path: Path) -> WindowsPathGuard:
        allowed = str(tmp_path / "allowed") + os.sep
        os.makedirs(allowed, exist_ok=True)
        config = AppConfig(
            windows_allowed_paths=(allowed,),
            windows_blocked_paths=(),
        )
        return WindowsPathGuard(config)

    def test_allowed_path_passes(self, tmp_path: Path) -> None:
        guard = self._make_guard(tmp_path)
        allowed_file = str(tmp_path / "allowed" / "file.txt")
        result = guard.validate(allowed_file)
        assert result is None

    def test_outside_allowed_rejected(self, tmp_path: Path) -> None:
        guard = self._make_guard(tmp_path)
        outside = str(tmp_path / "outside" / "secret.txt")
        result = guard.validate(outside)
        assert result is not None
        assert "not within any allowed path" in result

    def test_blocked_path_rejected(self, tmp_path: Path) -> None:
        blocked = str(tmp_path / "blocked") + os.sep
        allowed = str(tmp_path / "blocked") + os.sep  # same — blocked takes priority
        config = AppConfig(
            windows_allowed_paths=(allowed,),
            windows_blocked_paths=(blocked,),
        )
        guard = WindowsPathGuard(config)
        result = guard.validate(str(tmp_path / "blocked" / "file.txt"))
        assert result is not None
        assert "blocked" in result.lower()

    def test_system_blocked_cannot_be_unblocked(self, tmp_path: Path) -> None:
        config = AppConfig(
            windows_allowed_paths=(str(tmp_path / "allowed") + os.sep,),
            windows_blocked_paths=(),
        )
        guard = WindowsPathGuard(config)
        # Try to remove a system-critical blocked path
        removed = guard.remove_blocked("c:\\windows\\")
        assert not removed

    def test_traversal_attack_blocked(self, tmp_path: Path) -> None:
        guard = self._make_guard(tmp_path)
        # Path that tries to escape allowed dir
        traversal = str(tmp_path / "allowed" / ".." / "outside" / "secret.txt")
        result = guard.validate(traversal)
        # Should be rejected because normalized path exits the allowed prefix
        assert result is not None

    def test_add_remove_allowed(self, tmp_path: Path) -> None:
        guard = self._make_guard(tmp_path)
        new_dir = str(tmp_path / "new_allowed") + os.sep
        guard.add_allowed(new_dir)
        assert guard.validate(str(tmp_path / "new_allowed" / "f.txt")) is None
        guard.remove_allowed(new_dir)
        assert guard.validate(str(tmp_path / "new_allowed" / "f.txt")) is not None

    def test_add_remove_blocked(self, tmp_path: Path) -> None:
        guard = self._make_guard(tmp_path)
        bad_dir = str(tmp_path / "allowed" / "private") + os.sep
        guard.add_blocked(bad_dir)
        assert guard.validate(str(tmp_path / "allowed" / "private" / "x.txt")) is not None
        guard.remove_blocked(bad_dir)
        # Now it should pass (allowed parent)
        assert guard.validate(str(tmp_path / "allowed" / "private" / "x.txt")) is None


# ── WindowsSafetyChecker ────────────────────────────────────────────────────


class TestWindowsSafetyChecker:
    def _checker(self) -> WindowsSafetyChecker:
        return WindowsSafetyChecker()

    def test_tier1_is_auto_allowed(self) -> None:
        c = self._checker()
        assert c.is_auto_allowed(1)
        assert not c.is_auto_allowed(2)
        assert not c.is_auto_allowed(3)

    def test_tier4_requires_double_confirm(self) -> None:
        c = self._checker()
        assert not c.requires_double_confirm(3)
        assert c.requires_double_confirm(4)

    def test_static_tier_lookup(self) -> None:
        c = self._checker()
        assert c.get_tier("windows-system", "get_cpu_info") == 1
        assert c.get_tier("windows-clipboard", "read_clipboard") == 1
        assert c.get_tier("windows-clipboard", "write_clipboard") == 2
        assert c.get_tier("windows-filesystem", "delete_file") == 3
        assert c.get_tier("windows-settings", "set_volume") == 3

    def test_write_file_dynamic_tier(self, tmp_path: Path) -> None:
        c = self._checker()
        new_file = str(tmp_path / "new.txt")
        # New file → Tier 2
        assert c.get_tier("windows-filesystem", "write_file", path=new_file) == 2
        # Create it, then check overwrite → Tier 3
        Path(new_file).write_text("x")
        assert c.get_tier("windows-filesystem", "write_file", path=new_file) == 3
        # Explicit overwrite flag → Tier 3 even if file doesn't exist
        assert c.get_tier("windows-filesystem", "write_file", path="/nonexistent.txt", overwrite=True) == 3

    def test_delete_folder_dynamic_tier(self) -> None:
        c = self._checker()
        assert c.get_tier("windows-filesystem", "delete_folder") == 3
        assert c.get_tier("windows-filesystem", "delete_folder", recursive=True) == 4

    def test_confirmation_prompt_contains_operation(self) -> None:
        c = self._checker()
        prompt = c.build_confirmation_prompt(3, "delete_file", "windows-filesystem", "C:\\test.txt", "File deleted.")
        assert "delete_file" in prompt
        assert "windows-filesystem" in prompt

    def test_tier4_prompt_contains_double_confirm_text(self) -> None:
        c = self._checker()
        prompt = c.build_confirmation_prompt(4, "delete_folder", "windows-filesystem", "C:\\Data\\", "All contents deleted.")
        assert "confirm" in prompt.lower()

    def test_all_tiers_coverage(self) -> None:
        c = self._checker()
        all_tiers = c.all_tiers()
        # All 10 servers should have entries
        assert "windows-filesystem" in all_tiers
        assert "windows-notification" in all_tiers
        # All tier values should be 1–4
        for srv, tools in all_tiers.items():
            for tool, tier in tools.items():
                assert 1 <= tier <= 4, f"{srv}.{tool} has invalid tier {tier}"
