"""Tests for the Anythink diagnostics module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from anythink.config.manager import Paths
from anythink.diagnostics import (
    DiagResult,
    _check_api_keys,
    _check_config,
    _check_deps,
    _check_disk,
    _check_providers,
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


class TestCheckProviders:
    async def test_no_aliases_returns_warn(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        ctx.model_registry.list_all.return_value = []
        results = await _check_providers(ctx)
        assert any(r.status == "warn" for r in results)
        assert any("No model aliases" in r.message for r in results)

    async def test_provider_reachable(self, xdg_dirs: Paths) -> None:
        alias = MagicMock()
        alias.provider = "anthropic"
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        ctx.model_registry.list_all.return_value = [alias]
        ctx.key_manager.get_key.return_value = "sk-test"
        provider = MagicMock()
        provider.test_connection = AsyncMock(return_value=True)
        ctx.provider_registry.get.return_value = lambda **kwargs: provider
        results = await _check_providers(ctx)
        ok_results = [r for r in results if r.status == "ok"]
        assert len(ok_results) > 0

    async def test_provider_unreachable(self, xdg_dirs: Paths) -> None:
        alias = MagicMock()
        alias.provider = "openai"
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        ctx.model_registry.list_all.return_value = [alias]
        ctx.key_manager.get_key.return_value = "sk-test"
        provider = MagicMock()
        provider.test_connection = AsyncMock(return_value=False)
        ctx.provider_registry.get.return_value = lambda **kwargs: provider
        results = await _check_providers(ctx)
        fail_results = [r for r in results if r.status == "fail"]
        assert len(fail_results) > 0

    async def test_provider_not_in_registry(self, xdg_dirs: Paths) -> None:
        alias = MagicMock()
        alias.provider = "unknown"
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        ctx.model_registry.list_all.return_value = [alias]
        ctx.key_manager.get_key.return_value = None
        ctx.provider_registry.get.return_value = None
        results = await _check_providers(ctx)
        warn_results = [r for r in results if r.status == "warn"]
        assert len(warn_results) > 0

    async def test_provider_timeout(self, xdg_dirs: Paths) -> None:
        alias = MagicMock()
        alias.provider = "groq"
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        ctx.model_registry.list_all.return_value = [alias]
        ctx.key_manager.get_key.return_value = "key"
        provider = MagicMock()
        provider.test_connection = AsyncMock(side_effect=TimeoutError())
        ctx.provider_registry.get.return_value = lambda **kwargs: provider
        results = await _check_providers(ctx)
        assert any("timed out" in r.message for r in results)

    async def test_provider_generic_exception(self, xdg_dirs: Paths) -> None:
        alias = MagicMock()
        alias.provider = "groq"
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        ctx.model_registry.list_all.return_value = [alias]
        ctx.key_manager.get_key.side_effect = RuntimeError("keychain broke")
        results = await _check_providers(ctx)
        warn_results = [r for r in results if r.status == "warn"]
        assert len(warn_results) > 0

    async def test_deduplicate_provider(self, xdg_dirs: Paths) -> None:
        alias1 = MagicMock()
        alias1.provider = "anthropic"
        alias2 = MagicMock()
        alias2.provider = "anthropic"  # same provider, different alias
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        ctx.model_registry.list_all.return_value = [alias1, alias2]
        ctx.key_manager.get_key.return_value = "key"
        provider = MagicMock()
        provider.test_connection = AsyncMock(return_value=True)
        ctx.provider_registry.get.return_value = lambda **kwargs: provider
        results = await _check_providers(ctx)
        # Should only check anthropic once
        assert len([r for r in results if r.name == "anthropic"]) == 1


class TestCheckDisk:
    def test_returns_result(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        results = _check_disk(ctx)
        assert len(results) == 1
        assert results[0].name == "Free space"

    def test_low_disk_warn(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        fake_usage = MagicMock()
        fake_usage.free = int(0.5 * 1024**3)  # 0.5 GB — below 1 GB threshold
        with patch("anythink.diagnostics.shutil.disk_usage", return_value=fake_usage):
            results = _check_disk(ctx)
        assert results[0].status == "warn"

    def test_very_low_disk_fail(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        fake_usage = MagicMock()
        fake_usage.free = int(0.05 * 1024**3)  # 50 MB — below 0.1 GB threshold
        with patch("anythink.diagnostics.shutil.disk_usage", return_value=fake_usage):
            results = _check_disk(ctx)
        assert results[0].status == "fail"

    def test_disk_usage_exception(self, xdg_dirs: Paths) -> None:
        ctx = MagicMock()
        ctx.paths = xdg_dirs
        with patch("anythink.diagnostics.shutil.disk_usage", side_effect=OSError("no disk")):
            results = _check_disk(ctx)
        assert results[0].status == "warn"


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
