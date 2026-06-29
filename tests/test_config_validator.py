"""Tests for ConfigValidator (V3.2.0 /config validate)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from anythink.config.validator import ConfigValidator, ValidationIssue, format_validation_table


def _make_ctx(
    aliases=None,
    schedules=None,
    plugins=None,
    rag_active=False,
    rag_cache_exists=True,
    theme="midnight",
) -> MagicMock:
    ctx = MagicMock()
    ctx.config.active_theme = theme
    ctx.config.active_rag_index = "my-index" if rag_active else None

    mock_aliases = aliases or []
    ctx.model_registry.list_all.return_value = mock_aliases

    mock_schedules = schedules or []
    ctx.schedule_manager.list_all.return_value = mock_schedules

    ctx.plugin_manager.list_plugins.return_value = plugins or []

    ctx.provider_registry.list_names.return_value = ["anthropic", "openai", "groq"]

    ctx.paths.config_file = MagicMock()
    ctx.paths.config_file.exists.return_value = False
    ctx.paths.rag_cache_dir = MagicMock()
    ctx.paths.rag_cache_dir.exists.return_value = rag_cache_exists

    return ctx


def test_validate_returns_list():
    ctx = _make_ctx()
    issues = ConfigValidator().validate(ctx)
    assert isinstance(issues, list)
    assert len(issues) > 0


def test_all_ok_with_empty_config():
    ctx = _make_ctx()
    issues = ConfigValidator().validate(ctx)
    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 0


def test_alias_consistency_ok():
    alias = MagicMock()
    alias.alias = "claude"
    alias.provider = "anthropic"
    ctx = _make_ctx(aliases=[alias])
    issues = ConfigValidator()._check_alias_consistency(ctx)
    ok = [i for i in issues if i.severity == "ok"]
    assert len(ok) > 0


def test_alias_consistency_bad_provider():
    alias = MagicMock()
    alias.alias = "mystery"
    alias.provider = "unknown-provider-xyz"
    ctx = _make_ctx(aliases=[alias])
    issues = ConfigValidator()._check_alias_consistency(ctx)
    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 1
    assert "unknown-provider-xyz" in errors[0].message


def test_param_ranges_ok():
    alias = MagicMock()
    alias.alias = "myalias"
    alias.gen_params = MagicMock()
    alias.gen_params.temperature = 0.7
    alias.gen_params.top_p = 0.9
    ctx = _make_ctx(aliases=[alias])
    issues = ConfigValidator()._check_param_ranges(ctx)
    ok = [i for i in issues if i.severity == "ok"]
    assert len(ok) > 0


def test_param_ranges_bad_temperature():
    alias = MagicMock()
    alias.alias = "myalias"
    alias.gen_params = MagicMock()
    alias.gen_params.temperature = 5.0
    alias.gen_params.top_p = None
    ctx = _make_ctx(aliases=[alias])
    issues = ConfigValidator()._check_param_ranges(ctx)
    warns = [i for i in issues if i.severity == "warn"]
    assert any("temperature" in i.field for i in warns)


def test_conflicting_rag_no_cache():
    ctx = _make_ctx(rag_active=True, rag_cache_exists=False)
    issues = ConfigValidator()._check_conflicting_settings(ctx)
    warns = [i for i in issues if i.severity == "warn"]
    assert len(warns) > 0
    assert "rag" in warns[0].message.lower()


def test_conflicting_rag_with_cache():
    ctx = _make_ctx(rag_active=True, rag_cache_exists=True)
    issues = ConfigValidator()._check_conflicting_settings(ctx)
    ok = [i for i in issues if i.severity == "ok"]
    assert len(ok) > 0


def test_theme_ok():
    ctx = _make_ctx(theme="midnight")
    issues = ConfigValidator()._check_theme_completeness(ctx)
    ok = [i for i in issues if i.severity == "ok"]
    assert len(ok) > 0


def test_theme_unknown():
    ctx = _make_ctx(theme="custom-theme")
    issues = ConfigValidator()._check_theme_completeness(ctx)
    warns = [i for i in issues if i.severity == "warn"]
    assert len(warns) > 0


def test_schedule_unknown_alias():
    sched = MagicMock()
    sched.name = "daily-report"
    sched.model_alias = "nonexistent-alias"
    ctx = _make_ctx(schedules=[sched])
    issues = ConfigValidator()._check_scheduled_prompts(ctx)
    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 1
    assert "nonexistent-alias" in errors[0].message


def test_schedule_valid_alias():
    alias = MagicMock()
    alias.alias = "claude"
    sched = MagicMock()
    sched.name = "daily"
    sched.model_alias = "claude"
    ctx = _make_ctx(aliases=[alias], schedules=[sched])
    issues = ConfigValidator()._check_scheduled_prompts(ctx)
    ok = [i for i in issues if i.severity == "ok"]
    assert len(ok) > 0


def test_model_aliases_exception_returns_warn():
    ctx = _make_ctx()
    ctx.model_registry.list_all.side_effect = RuntimeError("registry unavailable")
    issues = ConfigValidator()._check_alias_consistency(ctx)
    warns = [i for i in issues if i.severity == "warn"]
    assert len(warns) > 0
    assert "Could not validate" in warns[0].message


def test_param_ranges_no_gen_params():
    alias = MagicMock()
    alias.alias = "myalias"
    alias.gen_params = None
    ctx = _make_ctx(aliases=[alias])
    issues = ConfigValidator()._check_param_ranges(ctx)
    ok = [i for i in issues if i.severity == "ok"]
    assert len(ok) > 0


def test_param_ranges_bad_top_p():
    alias = MagicMock()
    alias.alias = "myalias"
    alias.gen_params = MagicMock()
    alias.gen_params.temperature = None
    alias.gen_params.top_p = 1.5
    ctx = _make_ctx(aliases=[alias])
    issues = ConfigValidator()._check_param_ranges(ctx)
    warns = [i for i in issues if i.severity == "warn"]
    assert any("top_p" in i.field for i in warns)


def test_param_ranges_exception_returns_warn():
    ctx = _make_ctx()
    ctx.model_registry.list_all.side_effect = RuntimeError("param check error")
    issues = ConfigValidator()._check_param_ranges(ctx)
    warns = [i for i in issues if i.severity == "warn"]
    assert len(warns) > 0


def test_deprecated_fields_config_exists() -> None:
    import yaml

    ctx = _make_ctx()
    ctx.paths.config_file.exists.return_value = True
    ctx.paths.config_file.read_text.return_value = yaml.dump({"active_theme": "midnight"})

    issues = ConfigValidator()._check_deprecated_fields(ctx)
    ok = [i for i in issues if i.severity == "ok"]
    assert len(ok) > 0


def test_deprecated_check_exception_returns_warn():
    ctx = _make_ctx()
    ctx.paths.config_file.exists.return_value = True
    ctx.paths.config_file.read_text.side_effect = RuntimeError("file error")
    issues = ConfigValidator()._check_deprecated_fields(ctx)
    warns = [i for i in issues if i.severity == "warn"]
    assert len(warns) > 0


def test_scheduled_prompts_exception_returns_warn():
    ctx = _make_ctx()
    ctx.schedule_manager.list_all.side_effect = RuntimeError("schedule error")
    issues = ConfigValidator()._check_scheduled_prompts(ctx)
    warns = [i for i in issues if i.severity == "warn"]
    assert len(warns) > 0


def test_plugin_conflicts_exception_returns_warn():
    ctx = _make_ctx()
    ctx.plugin_manager.list_plugins.side_effect = RuntimeError("plugin error")
    issues = ConfigValidator()._check_plugin_conflicts(ctx)
    warns = [i for i in issues if i.severity == "warn"]
    assert len(warns) > 0


def test_format_validation_table_empty():
    out = format_validation_table([])
    assert "passed" in out.lower()


def test_format_validation_table_with_issues():
    issues = [
        ValidationIssue("Aliases", "alias:bad", "error", "Not found", "install it"),
        ValidationIssue("Theme", "active_theme", "ok", "Valid"),
    ]
    out = format_validation_table(issues)
    assert "❌" in out
    assert "✓" in out
    assert "Not found" in out
    assert "install it" in out
