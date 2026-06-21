"""Tests for the Anythink diagnostics module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from anythink.diagnostics import (
    DiagResult,
    _check_api_keys,
    _check_config,
    _check_deps,
    _check_disk,
    _check_python,
    run_diagnostics,
)


class TestCheckPython:
    def test_current_python_passes(self) -> None:
        results = _check_python()
        assert len(results) == 1
        assert results[0].status == "ok"

    def test_old_python_fails(self) -> None:
        from collections import namedtuple

        FakeVersionInfo = namedtuple("version_info", ["major", "minor", "micro"])
        fake = FakeVersionInfo(3, 10, 0)
        with patch("anythink.diagnostics.sys") as mock_sys:
            mock_sys.version_info = fake
            results = _check_python()
        assert results[0].status == "fail"


class TestCheckDeps:
    def test_returns_list(self) -> None:
        results = _check_deps()
        assert isinstance(results, list)
        assert all(isinstance(r, DiagResult) for r in results)

    def test_yaml_always_installed(self) -> None:
        # yaml is always available since it's a hard dep
        import importlib.util

        assert importlib.util.find_spec("yaml") is not None


class TestCheckApiKeys:
    def test_no_keys_configured(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.key_manager.list_providers.return_value = []
        results = _check_api_keys(ctx)
        assert len(results) == 1
        assert results[0].status == "warn"

    def test_with_keys(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.key_manager.list_providers.return_value = ["groq", "openai"]
        results = _check_api_keys(ctx)
        assert len(results) == 2
        assert all(r.status == "ok" for r in results)

    def test_key_manager_error(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.key_manager.list_providers.side_effect = Exception("keychain error")
        results = _check_api_keys(ctx)
        assert len(results) == 1
        assert results[0].status == "fail"


class TestCheckConfig:
    def test_missing_files_ok(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        results = _check_config(ctx)
        assert all(r.status == "ok" for r in results)

    def test_valid_yaml_passes(self, xdg_dirs: Paths) -> None:
        xdg_dirs.config_file.write_text("active_theme: midnight\n")
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        results = _check_config(ctx)
        config_result = next(r for r in results if r.name == "config.yaml")
        assert config_result.status == "ok"

    def test_invalid_yaml_fails(self, xdg_dirs: Paths) -> None:
        xdg_dirs.config_file.write_text("{{invalid: yaml: :")
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        results = _check_config(ctx)
        config_result = next(r for r in results if r.name == "config.yaml")
        assert config_result.status == "fail"


class TestCheckDisk:
    def test_returns_result(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        results = _check_disk(ctx)
        assert len(results) == 1
        assert results[0].name == "Free space"


class TestRunDiagnostics:
    async def test_returns_list_of_results(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        ctx.key_manager.list_providers.return_value = []
        ctx.model_registry.list_all.return_value = []
        results = await run_diagnostics(ctx)
        assert isinstance(results, list)
        assert all(isinstance(r, DiagResult) for r in results)

    async def test_categories_present(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        ctx.key_manager.list_providers.return_value = []
        ctx.model_registry.list_all.return_value = []
        results = await run_diagnostics(ctx)
        categories = {r.category for r in results}
        assert "Python Environment" in categories
        assert "Config Files" in categories
